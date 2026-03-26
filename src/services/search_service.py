import copy
from typing import Any, Dict
from agentd.tool_decorator import tool
from config.settings import (
    EMBED_MODEL,
    LOG_LEVEL,
    SEARCH_QUALITY_GUARD_ENABLED,
    SEARCH_QUALITY_GUARD_HYBRID_THRESHOLD,
    SEARCH_QUALITY_GUARD_LEX_THRESHOLD,
    clients,
    get_embedding_model,
    get_index_name,
    WATSONX_EMBEDDING_DIMENSIONS,
)
from auth_context import get_auth_context
from utils.logging_config import get_logger, log_event
from utils.openrag_query_filters import EXACT_FILTER_FIELD_MAPPING, build_opensearch_filter_clauses
from services import opensearch_search_engine as ose
from services.search_quality_guard import (
    _apply_search_quality_guard,
    max_chunk_score,
)

logger = get_logger(__name__)


def _query_preview_for_log(query: str, max_len: int = 120) -> str:
    if not isinstance(query, str):
        return ""
    q = query.strip()
    if len(q) <= max_len:
        return q
    return q[:max_len] + "…"


def build_local_aggs_from_chunks(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    """Build facet-like aggregations from the returned chunk window (same keys as legacy aggs)."""

    def buckets_for(field: str, size: int) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for c in chunks:
            v = c.get(field)
            if v is None:
                continue
            key = str(v)
            if not key:
                continue
            counts[key] = counts.get(key, 0) + 1
        items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:size]
        return [{"key": k, "doc_count": n} for k, n in items]

    return {
        "data_sources": {"buckets": buckets_for("filename", 20)},
        "document_types": {"buckets": buckets_for("mimetype", 10)},
        "owners": {"buckets": buckets_for("owner", 10)},
        "connector_types": {"buckets": buckets_for("connector_type", 10)},
        "embedding_models": {"buckets": buckets_for("embedding_model", 10)},
    }


def _filters_for_lexical_probe(
    hybrid_filter_for_probe: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Drop term/terms on `filename` so the probe never touches that field (avoids
    fielddata / mapping issues on heterogeneous aliases where `filename` may be text).
    """
    out: list[dict[str, Any]] = []
    for clause in hybrid_filter_for_probe:
        if isinstance(clause, dict):
            term = clause.get("term")
            if isinstance(term, dict) and "filename" in term:
                continue
            terms = clause.get("terms")
            if isinstance(terms, dict) and "filename" in terms:
                continue
        out.append(clause)
    return out


async def _filter_query_embeddings_for_safe_knn(
    opensearch_client: Any,
    index_name: str,
    query_embeddings: dict[str, list[float]],
    get_embedding_field_name,
) -> tuple[dict[str, list[float]], list[str]]:
    """
    Keep only models whose embedding field exists as knn_vector on every physical
    index behind the alias, with matching dimension. Avoids OpenSearch errors like
    "Field X is not knn_vector type" when the alias is heterogeneous.

    Empty dict => caller should use lexical-only hybrid (no KNN clauses).
    """
    if not query_embeddings:
        return {}, []

    try:
        physical_indices, _ = await ose.async_get_physical_indices(
            opensearch_client, index_name
        )
    except Exception as e:
        logger.warning(
            "Could not resolve physical indices for safe KNN; lexical-only fallback",
            error=str(e),
        )
        return {}, []

    if not physical_indices:
        return {}, []

    allowed: dict[str, list[float]] = {}
    debug_filtered_out: dict[str, str] | None = (
        {} if LOG_LEVEL == "DEBUG" else None
    )
    for model_name, embedding_vector in query_embeddings.items():
        field_name = get_embedding_field_name(model_name)
        dim = len(embedding_vector)
        ok_all = True
        drop_reason: str | None = None
        for phys in physical_indices:
            props = await ose.async_get_index_properties_for(opensearch_client, phys)
            knn_fields = ose.extract_knn_fields(props)
            if field_name not in knn_fields:
                ok_all = False
                drop_reason = f"field_not_knn_vector:{phys}"
                break
            field_dim = knn_fields.get(field_name)
            if field_dim is not None and field_dim != dim:
                ok_all = False
                drop_reason = f"dim_mismatch:{phys}:{field_dim}!={dim}"
                break
        if ok_all:
            allowed[model_name] = embedding_vector
        elif debug_filtered_out is not None and drop_reason is not None:
            debug_filtered_out[model_name] = drop_reason

    if LOG_LEVEL == "DEBUG":
        log_event(
            logger,
            "knn_filtering",
            level="debug",
            input_models=list(query_embeddings.keys()),
            valid_models=list(allowed.keys()),
            filtered_out=debug_filtered_out or {},
        )

    return allowed, list(physical_indices)


async def _run_lexical_probe(
    opensearch_client: Any,
    index_name: str,
    query: str,
    hybrid_filter_for_probe: list[dict[str, Any]],
) -> float:
    """Strict phrase match on `text` only (slop=0); max score as lexical evidence. No KNN.

    Body is intentionally minimal (no aggs, no sort) to avoid fielddata on text fields.
    """
    probe_filters = _filters_for_lexical_probe(hybrid_filter_for_probe)
    bool_query: dict[str, Any] = {
        "must": [
            {
                "match_phrase": {
                    "text": {
                        "query": query,
                        "slop": 0,
                    }
                }
            }
        ],
    }
    if probe_filters:
        bool_query["filter"] = probe_filters

    body: dict[str, Any] = {
        "query": {"bool": bool_query},
        "size": 1,
        "_source": False,
    }
    try:
        resp = await opensearch_client.search(
            index=index_name, body=body, params={}
        )
    except Exception as e:
        logger.warning(
            "search_quality_guard lexical_probe exception",
            query_preview=query[:80] if query else None,
            index_name=index_name,
            error=str(e),
            exc_info=True,
        )
        raise

    hits = resp.get("hits", {}).get("hits", [])
    top_score = float(hits[0].get("_score") or 0.0) if hits else 0.0
    if not hits:
        return 0.0
    return top_score


async def _apply_guard_to_chunks(
    *,
    query: str,
    chunks: list[dict[str, Any]],
    is_wildcard_match_all: bool,
    hybrid_filter_for_probe: list[dict[str, Any]] | None,
    opensearch_client: Any,
    index_name: str,
) -> tuple[list[dict[str, Any]], bool]:
    """
    Optionally filter chunks via quality guard. Returns (chunks, blocked_by_guard).
    """
    if (
        not SEARCH_QUALITY_GUARD_ENABLED
        or is_wildcard_match_all
        or hybrid_filter_for_probe is None
    ):
        return chunks, False

    lex_max: float | None = None
    try:
        lex_max = await _run_lexical_probe(
            opensearch_client,
            index_name,
            query,
            hybrid_filter_for_probe,
        )
    except Exception as e:
        logger.warning(
            "Lexical quality probe failed; fail-open (keeping results)",
            error=str(e),
            exc_info=True,
        )
        lex_max = None

    top = max_chunk_score(chunks)
    keep, out = _apply_search_quality_guard(
        query,
        chunks,
        top,
        lex_max,
        SEARCH_QUALITY_GUARD_LEX_THRESHOLD,
        SEARCH_QUALITY_GUARD_HYBRID_THRESHOLD,
        SEARCH_QUALITY_GUARD_ENABLED,
        is_wildcard_match_all,
    )
    if not keep:
        reason = "blocked"
    elif lex_max is None:
        reason = "fail_open"
    else:
        reason = "passed"
    log_event(
        logger,
        "quality_guard",
        blocked=not keep,
        lex_score=lex_max,
        hybrid_score=top,
        reason=reason,
    )
    if not keep:
        return [], True
    return out, False

MAX_EMBED_RETRIES = 3
EMBED_RETRY_INITIAL_DELAY = 1.0
EMBED_RETRY_MAX_DELAY = 8.0

AGGREGATION_FIELDS = {
    "data_sources": "filename",
    "document_types": "mimetype",
    "owners": "owner",
    "connector_types": "connector_type",
    "embedding_models": "embedding_model",
}


class SearchService:
    def __init__(self, session_manager=None):
        self.session_manager = session_manager

    @tool
    async def search_tool(self, query: str, embedding_model: str = None) -> Dict[str, Any]:
        """
        Use this tool to search for documents relevant to the query.

        Args:
            query (str): query string to search the corpus
            embedding_model (str): Optional override for embedding model.
                                  If not provided, uses the current embedding
                                  model from configuration.

        Returns:
            dict (str, Any): {"results": [chunks]} on success
        """
        from utils.embedding_fields import get_embedding_field_name

        # Strategy: Use provided model, or default to the configured embedding
        # model. This assumes documents are embedded with that model by default.
        # Future enhancement: Could auto-detect available models in corpus.
        embedding_model = embedding_model or get_embedding_model() or EMBED_MODEL
        embedding_field_name = get_embedding_field_name(embedding_model)

        logger.debug(
            "Search with embedding model",
            embedding_model=embedding_model,
            embedding_field=embedding_field_name,
            query_preview=_query_preview_for_log(query, 50),
        )

        # Get authentication context from the current async context
        user_id, jwt_token = get_auth_context()
        # Get search filters, limit, and score threshold from context
        from auth_context import (
            get_search_filters,
            get_search_limit,
            get_score_threshold,
        )

        filters = get_search_filters() or {}
        limit = get_search_limit()
        score_threshold = get_score_threshold()
        # Detect wildcard request ("*") to return global facets/stats without semantic search
        is_wildcard_match_all = isinstance(query, str) and query.strip() == "*"

        # Get available embedding models from corpus
        query_embeddings = {}
        available_models = []

        opensearch_client = self.session_manager.get_user_opensearch_client(
            user_id, jwt_token
        )

        if not is_wildcard_match_all:
            # Build filter clauses first so we can use them in model detection
            filter_clauses = build_opensearch_filter_clauses(filters)

            try:
                # Build aggregation query with filters applied
                agg_query = {
                    "size": 0,
                    "aggs": {
                        "embedding_models": {
                            "terms": {
                                "field": AGGREGATION_FIELDS["embedding_models"],
                                "size": 10
                            }
                        }
                    }
                }

                # Apply filters to model detection if any exist
                if filter_clauses:
                    agg_query["query"] = {
                        "bool": {
                            "filter": filter_clauses
                        }
                    }

                agg_result = await opensearch_client.search(
                    index=get_index_name(), body=agg_query, params={"terminate_after": 0}
                )
                buckets = agg_result.get("aggregations", {}).get("embedding_models", {}).get("buckets", [])
                available_models = [b["key"] for b in buckets if b["key"]]

                if not available_models:
                    # Fallback to configured model if no documents indexed yet
                    available_models = [embedding_model]

                logger.debug(
                    "Detected embedding models in corpus",
                    available_models=available_models,
                    model_counts={b["key"]: b["doc_count"] for b in buckets},
                    with_filters=len(filter_clauses) > 0,
                )
            except Exception as e:
                logger.warning("Failed to detect embedding models, using configured model", error=str(e))
                available_models = [embedding_model]

            # Parallelize embedding generation for all models
            import asyncio

            async def embed_with_model(model_name):
                delay = EMBED_RETRY_INITIAL_DELAY
                attempts = 0
                last_exception = None

                # Format model name for LiteLLM compatibility
                # The patched client routes through LiteLLM for non-OpenAI providers
                formatted_model = model_name

                # Skip if already has a provider prefix
                if not any(model_name.startswith(prefix + "/") for prefix in ["openai", "ollama", "watsonx", "anthropic"]):
                    # Detect provider from model name characteristics:
                    # - Ollama: contains ":" (e.g., "nomic-embed-text:latest")
                    # - WatsonX: check against known IBM embedding models
                    # - OpenAI: everything else (no prefix needed)

                    if ":" in model_name:
                        # Ollama models use tags with colons
                        formatted_model = f"ollama/{model_name}"
                        logger.debug(f"Formatted Ollama model: {model_name} -> {formatted_model}")
                    elif model_name in WATSONX_EMBEDDING_DIMENSIONS:
                        # WatsonX embedding models - use hardcoded list from settings
                        formatted_model = f"watsonx/{model_name}"
                        logger.debug(f"Formatted WatsonX model: {model_name} -> {formatted_model}")
                    # else: OpenAI models don't need a prefix

                while attempts < MAX_EMBED_RETRIES:
                    attempts += 1
                    try:
                        resp = await clients.patched_embedding_client.embeddings.create(
                            model=formatted_model, input=[query]
                        )
                        # Try to get embedding - some providers return .embedding, others return ['embedding']
                        embedding = getattr(resp.data[0], 'embedding', None)
                        if embedding is None:
                            embedding = resp.data[0]['embedding']
                        return model_name, embedding
                    except Exception as e:
                        last_exception = e
                        if attempts >= MAX_EMBED_RETRIES:
                            logger.error(
                                "Failed to embed with model after retries",
                                model=model_name,
                                attempts=attempts,
                                error=str(e),
                            )
                            raise RuntimeError(
                                f"Failed to embed with model {model_name}"
                            ) from e

                        logger.warning(
                            "Retrying embedding generation",
                            model=model_name,
                            attempt=attempts,
                            max_attempts=MAX_EMBED_RETRIES,
                            error=str(e),
                        )
                        await asyncio.sleep(delay)
                        delay = min(delay * 2, EMBED_RETRY_MAX_DELAY)

                # Should not reach here, but guard in case
                raise RuntimeError(
                    f"Failed to embed with model {model_name}"
                ) from last_exception

            # Run all embeddings in parallel
            try:
                embedding_results = await asyncio.gather(
                    *[embed_with_model(model) for model in available_models]
                )
            except Exception as e:
                logger.error("Embedding generation failed", error=str(e))
                raise

            # Collect successful embeddings
            for result in embedding_results:
                if isinstance(result, tuple) and result[1] is not None:
                    model_name, embedding = result
                    query_embeddings[model_name] = embedding

            logger.debug(
                "Generated query embeddings",
                models=list(query_embeddings.keys()),
                query_preview=_query_preview_for_log(query, 50),
            )

            query_embeddings, physical_index_names = (
                await _filter_query_embeddings_for_safe_knn(
                    opensearch_client,
                    get_index_name(),
                    query_embeddings,
                    get_embedding_field_name,
                )
            )
            log_event(
                logger,
                "search_mode",
                mode="hybrid" if query_embeddings else "lexical_only",
                knn_fields=(
                    [get_embedding_field_name(m) for m in query_embeddings]
                    if query_embeddings
                    else []
                ),
                indices=physical_index_names,
            )
        else:
            # Wildcard query - no embedding needed
            filter_clauses = build_opensearch_filter_clauses(filters)

        # Same filters as hybrid query (incl. exists embedding) for lexical probe / DLS alignment
        hybrid_filter_for_probe: list[dict[str, Any]] | None = None

        # Build query body
        if is_wildcard_match_all:
            # Match all documents; still allow filters to narrow scope
            if filter_clauses:
                query_block = {"bool": {"filter": filter_clauses}}
            else:
                query_block = {"match_all": {}}
        else:
            # Build multi-model KNN queries (fields verified as knn_vector on every backing index)
            knn_queries = []
            embedding_fields_to_check = []

            for model_name, embedding_vector in query_embeddings.items():
                field_name = get_embedding_field_name(model_name)
                embedding_fields_to_check.append(field_name)
                knn_queries.append({
                    "knn": {
                        field_name: {
                            "vector": embedding_vector,
                            "k": 50,
                        }
                    }
                })

            if knn_queries:
                exists_any_embedding = {
                    "bool": {
                        "should": [{"exists": {"field": f}} for f in embedding_fields_to_check],
                        "minimum_should_match": 1
                    }
                }
                all_filters = [*filter_clauses, exists_any_embedding]
            else:
                all_filters = list(filter_clauses)

            hybrid_filter_for_probe = all_filters

            logger.debug(
                "Building hybrid query with filters",
                user_filters_count=len(filter_clauses),
                total_filters_count=len(all_filters),
                filter_types=[type(f).__name__ for f in all_filters]
            )

            if knn_queries:
                query_block = {
                    "bool": {
                        "should": [
                            {
                                "dis_max": {
                                    "tie_breaker": 0.0,
                                    "boost": 0.7,
                                    "queries": knn_queries
                                }
                            },
                            {
                                "multi_match": {
                                    "query": query,
                                    "fields": ["text^2", "filename^1.5"],
                                    "type": "best_fields",
                                    "fuzziness": "AUTO",
                                    "boost": 0.3,
                                }
                            },
                        ],
                        "minimum_should_match": 1,
                        "filter": all_filters,
                    }
                }
            else:
                query_block = {
                    "bool": {
                        "should": [
                            {
                                "multi_match": {
                                    "query": query,
                                    "fields": ["text^2", "filename^1.5"],
                                    "type": "best_fields",
                                    "fuzziness": "AUTO",
                                    "boost": 1.0,
                                }
                            }
                        ],
                        "minimum_should_match": 1,
                        "filter": all_filters,
                    }
                }

        # No OpenSearch terms aggregations here: `terms` on `filename` (and similar)
        # triggers fielddata errors when those fields are mapped as `text` on some indices.
        # `/api/search` facets match the heterogeneous path: built locally from returned chunks.
        search_body = {
            "query": query_block,
            "_source": [
                "filename",
                "mimetype",
                "page",
                "text",
                "source_url",
                "owner",
                "owner_name",
                "owner_email",
                "file_size",
                "connector_type",
                "embedding_model",  # Include embedding model in results
                "embedding_dimensions",
                "allowed_users",
                "allowed_groups",
            ],
            "size": limit,
        }

        # Add score threshold only for hybrid (not meaningful for match_all)
        if not is_wildcard_match_all and score_threshold > 0:
            search_body["min_score"] = score_threshold

        # Prepare fallback search body without num_candidates for clusters that don't support it
        fallback_search_body = None
        if not is_wildcard_match_all:
            try:
                fallback_search_body = copy.deepcopy(search_body)
                knn_query_blocks = (
                    fallback_search_body["query"]["bool"]["should"][0]["dis_max"]["queries"]
                )
                for query_candidate in knn_query_blocks:
                    knn_section = query_candidate.get("knn")
                    if isinstance(knn_section, dict):
                        for params in knn_section.values():
                            if isinstance(params, dict):
                                params.pop("num_candidates", None)
            except (KeyError, IndexError, AttributeError, TypeError):
                fallback_search_body = None

        # Authentication required - DLS will handle document filtering automatically
        logger.debug(
            "search_service authentication info",
            user_id=user_id,
            has_jwt_token=jwt_token is not None,
        )
        if not user_id:
            logger.debug("search_service: user_id is None/empty, returning auth error")
            return {"results": [], "error": "Authentication required"}

        # Get user's OpenSearch client with JWT for OIDC auth through session manager
        opensearch_client = self.session_manager.get_user_opensearch_client(
            user_id, jwt_token
        )

        from opensearchpy.exceptions import RequestError

        search_params = {"terminate_after": 0}

        try:
            index_name = get_index_name()

            # PR-4: Use engine only for heterogeneous aliases (non-wildcard).
            if not is_wildcard_match_all:
                try:
                    physical_indices, is_alias = await ose.async_get_physical_indices(
                        opensearch_client, index_name
                    )
                    topology = (
                        await ose.async_detect_search_topology(opensearch_client, physical_indices)
                        if is_alias
                        else "single_index"
                    )
                except Exception as engine_err:
                    logger.warning(
                        "Engine topology detection failed; falling back to legacy search",
                        error=str(engine_err),
                    )
                    topology = "engine_failed"

                if topology == "heterogeneous_alias":
                    merged_hits = await ose.async_run_heterogeneous_alias_search(
                        client=opensearch_client,
                        query_text=query,
                        filter_clauses=filter_clauses,
                        limit=limit,
                        score_threshold=score_threshold,
                        query_embeddings=query_embeddings,
                        # Safety: our clusters may not support num_candidates. Engine avoids injecting it anyway.
                        use_num_candidates=False,
                        num_candidates=0,
                        physical_indices=physical_indices,
                        get_embedding_field_name=get_embedding_field_name,
                        log_fn=(
                            (lambda m: logger.debug(m))
                            if LOG_LEVEL == "DEBUG"
                            else (lambda _m: None)
                        ),
                    )
                    chunks: list[dict[str, Any]] = []
                    for mh in merged_hits:
                        meta = mh.metadata or {}
                        chunks.append(
                            {
                                "filename": meta.get("filename"),
                                "mimetype": meta.get("mimetype"),
                                "page": meta.get("page"),
                                "text": mh.page_content,
                                "score": mh.score,
                                "source_url": meta.get("source_url"),
                                "owner": meta.get("owner"),
                                "owner_name": meta.get("owner_name"),
                                "owner_email": meta.get("owner_email"),
                                "file_size": meta.get("file_size"),
                                "connector_type": meta.get("connector_type"),
                                "embedding_model": meta.get("embedding_model"),
                                "embedding_dimensions": meta.get("embedding_dimensions"),
                                "allowed_users": meta.get("allowed_users", []),
                                "allowed_groups": meta.get("allowed_groups", []),
                            }
                        )

                    chunks, blocked = await _apply_guard_to_chunks(
                        query=query,
                        chunks=chunks,
                        is_wildcard_match_all=is_wildcard_match_all,
                        hybrid_filter_for_probe=hybrid_filter_for_probe,
                        opensearch_client=opensearch_client,
                        index_name=index_name,
                    )
                    if blocked:
                        return {
                            "results": [],
                            "aggregations": build_local_aggs_from_chunks([]),
                            "total": 0,
                        }
                    return {
                        "results": chunks,
                        "aggregations": build_local_aggs_from_chunks(chunks),
                        "total": len(chunks),
                    }

            results = await opensearch_client.search(
                index=index_name, body=search_body, params=search_params
            )
        except RequestError as e:
            error_message = str(e)
            if (
                fallback_search_body is not None
                and "unknown field [num_candidates]" in error_message.lower()
            ):
                logger.warning(
                    "OpenSearch cluster does not support num_candidates; retrying without it"
                )
                try:
                    results = await opensearch_client.search(
                        index=get_index_name(),
                        body=fallback_search_body,
                        params=search_params,
                    )
                except RequestError as retry_error:
                    log_event(
                        logger,
                        "search_failed",
                        level="error",
                        query=_query_preview_for_log(query),
                        error=str(retry_error),
                        index=get_index_name(),
                    )
                    raise
            else:
                log_event(
                    logger,
                    "search_failed",
                    level="error",
                    query=_query_preview_for_log(query),
                    error=error_message,
                    index=get_index_name(),
                )
                raise
        except Exception as e:
            error_message = str(e)
            root_cause = None
            if hasattr(e, "info") and isinstance(getattr(e, "info"), dict):
                err = getattr(e, "info", {}).get("error", {})
                root_cause = err.get("root_cause") or err.get("reason", str(e))
            log_event(
                logger,
                "search_failed",
                level="error",
                query=_query_preview_for_log(query),
                error=error_message,
                index=get_index_name(),
                root_cause=root_cause,
            )
            raise

        # Transform results (keep for backward compatibility)
        chunks = []
        for hit in results["hits"]["hits"]:
            source = hit.get("_source", {})
            chunks.append(
                {
                    "filename": source.get("filename"),
                    "mimetype": source.get("mimetype"),
                    "page": source.get("page"),
                    "text": source.get("text"),
                    "score": hit.get("_score"),
                    "source_url": source.get("source_url"),
                    "owner": source.get("owner"),
                    "owner_name": source.get("owner_name"),
                    "owner_email": source.get("owner_email"),
                    "file_size": source.get("file_size"),
                    "connector_type": source.get("connector_type"),
                    "embedding_model": source.get("embedding_model"),  # Include in results
                    "embedding_dimensions": source.get("embedding_dimensions"),
                    # ACL fields (may be missing for some documents)
                    "allowed_users": source.get("allowed_users", []),
                    "allowed_groups": source.get("allowed_groups", []),
                }
            )

        chunks, blocked = await _apply_guard_to_chunks(
            query=query,
            chunks=chunks,
            is_wildcard_match_all=is_wildcard_match_all,
            hybrid_filter_for_probe=hybrid_filter_for_probe,
            opensearch_client=opensearch_client,
            index_name=index_name,
        )
        if blocked:
            return {
                "results": [],
                "aggregations": build_local_aggs_from_chunks([]),
                "total": 0,
            }

        # Return both transformed results and aggregations (local facets from hit window)
        return {
            "results": chunks,
            "aggregations": build_local_aggs_from_chunks(chunks),
            "total": (
                results.get("hits", {}).get("total", {}).get("value")
                if isinstance(results.get("hits", {}).get("total"), dict)
                else results.get("hits", {}).get("total")
            ),
        }

    async def search(
        self,
        query: str,
        user_id: str = None,
        jwt_token: str = None,
        filters: Dict[str, Any] = None,
        limit: int = 10,
        score_threshold: float = 0,
        embedding_model: str = None,
    ) -> Dict[str, Any]:
        """Public search method for API endpoints

        Args:
            embedding_model: Embedding model to use for search (defaults to the
                currently configured embedding model)
        """
        # Set auth context if provided (for direct API calls)
        from config.settings import is_no_auth_mode

        if user_id and (jwt_token or is_no_auth_mode()):
            from auth_context import set_auth_context

            set_auth_context(user_id, jwt_token)

        # Set filters and limit in context if provided
        if filters:
            from auth_context import set_search_filters

            set_search_filters(filters)

        from auth_context import set_search_limit, set_score_threshold

        set_search_limit(limit)
        set_score_threshold(score_threshold)

        return await self.search_tool(query, embedding_model=embedding_model)