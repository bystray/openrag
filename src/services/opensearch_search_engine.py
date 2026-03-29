"""
OpenSearch search engine (core runtime).

PR-3 goal:
- Provide a single source-of-truth implementation of the core multi-index /
  multi-embedding search mechanics.
- Do NOT switch any runtime callers yet. Adapters will be added in later PRs.

This module is intentionally free of Langflow-specific code (no Data(), no UI).
It operates on plain OpenSearch client calls and plain Python dict/list objects.
"""

from __future__ import annotations

from dataclasses import dataclass
import copy
import importlib.util
import logging
import inspect
from pathlib import Path
from typing import Any, Callable, Iterable, Awaitable, TypeVar

from opensearchpy import OpenSearch
from opensearchpy.exceptions import OpenSearchException, RequestError


logger = logging.getLogger(__name__)

# Optional lightweight logger hook for callers to reuse their own logging system.
LogFn = Callable[[str], None]

T = TypeVar("T")


@dataclass(frozen=True)
class MergedHit:
    """Engine output shape (plain Python), adapter-friendly."""

    page_content: str
    metadata: dict[str, Any]
    score: Any


_FLOWS_ALIAS_SEARCH_MOD: Any | None = None


def _get_flows_alias_search_module() -> Any:
    """Load shared per-index merge implementation from flows/ (same logic as Langflow)."""
    global _FLOWS_ALIAS_SEARCH_MOD
    if _FLOWS_ALIAS_SEARCH_MOD is not None:
        return _FLOWS_ALIAS_SEARCH_MOD
    path = Path(__file__).resolve().parents[2] / "flows" / "opensearch_alias_search.py"
    spec = importlib.util.spec_from_file_location("_openrag_opensearch_alias_search", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load OpenRAG alias search module from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _FLOWS_ALIAS_SEARCH_MOD = mod
    return mod


def get_physical_indices(client: OpenSearch, index_name: str) -> tuple[list[str], bool]:
    """Resolve index/alias into physical indices.

    Returns:
      (physical_indices, is_alias)
    """
    try:
        alias_map = client.indices.get_alias(name=index_name)
        if isinstance(alias_map, dict) and len(alias_map) > 0:
            return list(alias_map.keys()), True
    except Exception as e:
        logger.warning(
            "get_alias failed for '%s' (using index name as target): %s",
            index_name,
            e,
        )
    return [index_name], False


def get_index_properties_for(client: OpenSearch, index_name: str) -> dict[str, Any] | None:
    """Retrieve flattened mapping properties for a single physical index."""
    try:
        mapping = client.indices.get_mapping(index=index_name)
    except OpenSearchException as e:
        logger.warning("Failed to fetch mapping for index '%s': %s", index_name, e)
        return None

    index_data = mapping.get(index_name, {})
    props = index_data.get("mappings", {}).get("properties", {})
    return props if isinstance(props, dict) else None


def extract_knn_fields(properties: dict[str, Any] | None) -> dict[str, int | None]:
    """Extract knn_vector fields with optional dimensions from mapping properties."""
    if not isinstance(properties, dict):
        return {}
    knn_fields: dict[str, int | None] = {}
    for field_name, field_def in properties.items():
        if not isinstance(field_def, dict):
            continue
        if field_def.get("type") == "knn_vector":
            knn_fields[field_name] = field_def.get("dimension")
    return knn_fields


def detect_available_models_for_index(
    client: OpenSearch,
    index_name: str,
    filter_clauses: list[dict] | None = None,
) -> list[str]:
    """Detect embedding models for a single physical index (scoped by filters)."""
    try:
        agg_query: dict[str, Any] = {
            "size": 0,
            "aggs": {"embedding_models": {"terms": {"field": "embedding_model", "size": 20}}},
        }
        if filter_clauses:
            agg_query["query"] = {"bool": {"filter": filter_clauses}}
        result = client.search(index=index_name, body=agg_query, params={"terminate_after": 0})
        buckets = result.get("aggregations", {}).get("embedding_models", {}).get("buckets", [])
        return [b["key"] for b in buckets if isinstance(b, dict) and b.get("key")]
    except (OpenSearchException, KeyError, ValueError) as e:
        logger.warning("Failed to detect embedding models for index '%s': %s", index_name, e)
        return []


def detect_search_topology(client: OpenSearch, physical_indices: list[str]) -> str:
    """Classify topology as single_index, homogeneous_alias, or heterogeneous_alias."""
    if len(physical_indices) <= 1:
        return "single_index"

    signatures: set[tuple[tuple[str, int | None], ...]] = set()
    for index_name in physical_indices:
        properties = get_index_properties_for(client, index_name)
        knn_fields = extract_knn_fields(properties)
        signature = tuple(sorted(knn_fields.items()))
        signatures.add(signature)

    return "homogeneous_alias" if len(signatures) <= 1 else "heterogeneous_alias"


def build_heterogeneous_search_body(
    query_text: str,
    filter_clauses: list[dict],
    limit: int,
    score_threshold: int | float,
    knn_queries: list[dict],
    include_aggs: bool,
) -> dict[str, Any]:
    """Build per-index search body for hybrid (KNN+keyword) or text-only mode."""
    should_clauses: list[dict[str, Any]] = [
        {
            "multi_match": {
                "query": query_text,
                "fields": ["text^2", "filename^1.5"],
                "type": "best_fields",
                "fuzziness": "AUTO",
                "boost": 0.3 if knn_queries else 1.0,
            }
        }
    ]
    if knn_queries:
        should_clauses.insert(
            0,
            {
                "dis_max": {
                    "tie_breaker": 0.0,
                    "boost": 0.7,
                    "queries": knn_queries,
                }
            },
        )

    body: dict[str, Any] = {
        "query": {
            "bool": {
                "should": should_clauses,
                "minimum_should_match": 1,
                "filter": filter_clauses,
            }
        },
        "_source": [
            "filename",
            "mimetype",
            "page",
            "text",
            "source_url",
            "owner",
            "embedding_model",
            "allowed_users",
            "allowed_groups",
            "document_id",
        ],
        "size": limit,
    }
    # include_aggs retained for API compatibility; facet terms on filename/mimetype were removed
    # (text fielddata + heterogeneous indices). No default aggs here.
    if isinstance(score_threshold, (int, float)) and score_threshold > 0:
        body["min_score"] = score_threshold
    return body


def dedup_key_for_hit(hit: dict[str, Any]) -> str:
    """Create a stable dedup key across indices for document chunks."""
    source = hit.get("_source", {}) if isinstance(hit, dict) else {}
    doc_id = source.get("document_id")
    page = source.get("page")
    text = source.get("text", "")
    filename = source.get("filename", "")
    source_url = source.get("source_url", "")
    if doc_id:
        return f"doc:{doc_id}|page:{page}"
    return f"fn:{filename}|url:{source_url}|page:{page}|txt:{str(text)[:120]}"


def _safe_log(log_fn: LogFn | None, msg: str) -> None:
    if not log_fn:
        return
    try:
        log_fn(msg)
    except Exception:
        # Never allow engine logging to break search execution.
        return


async def _maybe_await(value: T | Awaitable[T]) -> T:
    """Await if the value is awaitable, otherwise return as-is.

    This allows the engine to support both `OpenSearch` and `AsyncOpenSearch`
    style clients without taking a dependency on async client types.
    """
    if inspect.isawaitable(value):
        return await value  # type: ignore[return-value]
    return value  # type: ignore[return-value]


async def async_get_physical_indices(client: Any, index_name: str) -> tuple[list[str], bool]:
    """Async variant of `get_physical_indices` (supports AsyncOpenSearch)."""
    try:
        alias_map = await _maybe_await(client.indices.get_alias(name=index_name))
        if isinstance(alias_map, dict) and len(alias_map) > 0:
            return list(alias_map.keys()), True
    except Exception as e:
        logger.warning(
            "async get_alias failed for '%s' (using index name as target): %s",
            index_name,
            e,
        )
    return [index_name], False


async def async_get_index_properties_for(client: Any, index_name: str) -> dict[str, Any] | None:
    """Async variant of `get_index_properties_for` (supports AsyncOpenSearch)."""
    try:
        mapping = await _maybe_await(client.indices.get_mapping(index=index_name))
    except OpenSearchException as e:
        logger.warning("Failed to fetch mapping for index '%s': %s", index_name, e)
        return None

    index_data = mapping.get(index_name, {})
    props = index_data.get("mappings", {}).get("properties", {})
    return props if isinstance(props, dict) else None


async def async_detect_search_topology(client: Any, physical_indices: list[str]) -> str:
    """Async variant of `detect_search_topology` (supports AsyncOpenSearch)."""
    if len(physical_indices) <= 1:
        return "single_index"

    signatures: set[tuple[tuple[str, int | None], ...]] = set()
    for index_name in physical_indices:
        properties = await async_get_index_properties_for(client, index_name)
        knn_fields = extract_knn_fields(properties)
        signature = tuple(sorted(knn_fields.items()))
        signatures.add(signature)

    return "homogeneous_alias" if len(signatures) <= 1 else "heterogeneous_alias"


async def async_detect_available_models_for_index(
    client: Any,
    index_name: str,
    filter_clauses: list[dict] | None = None,
) -> list[str]:
    """Async variant of `detect_available_models_for_index` (supports AsyncOpenSearch)."""
    try:
        agg_query: dict[str, Any] = {
            "size": 0,
            "aggs": {"embedding_models": {"terms": {"field": "embedding_model", "size": 20}}},
        }
        if filter_clauses:
            agg_query["query"] = {"bool": {"filter": filter_clauses}}
        result = await _maybe_await(
            client.search(index=index_name, body=agg_query, params={"terminate_after": 0})
        )
        buckets = result.get("aggregations", {}).get("embedding_models", {}).get("buckets", [])
        return [b["key"] for b in buckets if isinstance(b, dict) and b.get("key")]
    except (OpenSearchException, KeyError, ValueError) as e:
        logger.warning("Failed to detect embedding models for index '%s': %s", index_name, e)
        return []


async def async_run_heterogeneous_alias_search(
    *,
    client: Any,
    query_text: str,
    filter_clauses: list[dict],
    limit: int,
    score_threshold: int | float,
    query_embeddings: dict[str, list[float]],
    use_num_candidates: bool,
    num_candidates: int,
    physical_indices: list[str],
    get_embedding_field_name: Callable[[str], str],
    log_fn: LogFn | None = None,
) -> list[MergedHit]:
    """Async per-index alias search; logic aligned with flows/opensearch_alias_search.py."""
    mod = _get_flows_alias_search_module()
    per_index_hits: list[dict[str, Any]] = []
    failure_messages: list[str] = []
    per_index_limit = max(limit, limit * 2)
    q = (query_text or "").strip()

    for idx_num, index_name in enumerate(physical_indices):
        properties = await async_get_index_properties_for(client, index_name)
        knn_fields = extract_knn_fields(properties)
        model_hint = await async_detect_available_models_for_index(client, index_name, filter_clauses)
        local_knn = mod.knn_queries_for_physical_index(
            knn_fields, query_embeddings, get_embedding_field_name
        )
        mode = "knn_hybrid" if local_knn else "text_only"
        _safe_log(
            log_fn,
            f"[HETERO-A] index={index_name}; mode={mode}; agg_models={model_hint}; "
            f"knn_fields={list(knn_fields.keys())}",
        )
        if not q and not local_knn:
            failure_messages.append(f"{index_name}: skipped (empty query, no KNN fields)")
            continue

        body = mod.build_heterogeneous_search_body(
            q,
            filter_clauses,
            per_index_limit,
            score_threshold,
            local_knn,
            idx_num == 0,
        )
        fallback_body: dict[str, Any] | None = None
        if local_knn and use_num_candidates:
            fallback_body = copy.deepcopy(body)
            try:
                fallback_body["query"]["bool"]["should"][0]["dis_max"]["queries"] = list(local_knn)
            except (KeyError, IndexError, TypeError):
                fallback_body = None

        resp: dict[str, Any] | None = None
        try:
            resp = await _maybe_await(
                client.search(index=index_name, body=body, params={"terminate_after": 0})
            )
        except RequestError as e:
            lowered = str(e).lower()
            if fallback_body is not None and "num_candidates" in lowered:
                try:
                    resp = await _maybe_await(
                        client.search(index=index_name, body=fallback_body, params={"terminate_after": 0})
                    )
                except Exception as sub_err:
                    logger.warning(
                        "Async per-index search retry failed for '%s': %s", index_name, sub_err
                    )
                    _safe_log(log_fn, f"[HETERO-A] index={index_name}; num_candidates retry failed={sub_err}")
                    resp = None
            if resp is None and local_knn:
                try:
                    body_lex = mod.build_heterogeneous_search_body(
                        q,
                        filter_clauses,
                        per_index_limit,
                        score_threshold,
                        [],
                        False,
                    )
                    resp = await _maybe_await(
                        client.search(index=index_name, body=body_lex, params={"terminate_after": 0})
                    )
                    _safe_log(log_fn, f"[HETERO-A] index={index_name}; lexical fallback after error={e}")
                except Exception as lex_e:
                    msg = f"{index_name}: hybrid_error={e!s}; lexical_fallback={lex_e!s}"
                    failure_messages.append(msg)
                    logger.warning("Async per-index search failed for '%s': %s", index_name, msg)
                    _safe_log(log_fn, f"[HETERO-A] failed {msg}")
                    continue
            elif resp is None:
                msg = f"{index_name}: {e!s}"
                failure_messages.append(msg)
                logger.warning("Async per-index search failed for '%s': %s", index_name, e)
                _safe_log(log_fn, f"[HETERO-A] failed {msg}")
                continue
        except Exception as e:
            if local_knn:
                try:
                    body_lex = mod.build_heterogeneous_search_body(
                        q,
                        filter_clauses,
                        per_index_limit,
                        score_threshold,
                        [],
                        False,
                    )
                    resp = await _maybe_await(
                        client.search(index=index_name, body=body_lex, params={"terminate_after": 0})
                    )
                    _safe_log(log_fn, f"[HETERO-A] index={index_name}; lexical fallback after {e!s}")
                except Exception as lex_e:
                    msg = f"{index_name}: error={e!s}; lexical_fallback={lex_e!s}"
                    failure_messages.append(msg)
                    _safe_log(log_fn, f"[HETERO-A] failed {msg}")
                    continue
            else:
                msg = f"{index_name}: {e!s}"
                failure_messages.append(msg)
                _safe_log(log_fn, f"[HETERO-A] failed {msg}")
                continue

        if resp is None:
            continue

        hits = resp.get("hits", {}).get("hits", []) if isinstance(resp, dict) else []
        max_score_index = max((hit.get("_score") or 0.0) for hit in hits) if hits else 0.0
        _safe_log(log_fn, f"[HETERO-A] index={index_name}; max_score={max_score_index}; hits={len(hits)}")
        for hit in hits:
            raw_score = hit.get("_score") or 0.0
            hit["_normalized_score"] = (raw_score / max_score_index) if max_score_index > 0 else 0.0
        per_index_hits.extend(hits)

    _safe_log(log_fn, f"[HETERO-A] total hits before dedup={len(per_index_hits)}")
    if not per_index_hits and failure_messages:
        logger.error(
            "Async OpenSearch per-index search returned no hits; failures=%s",
            failure_messages,
        )
        _safe_log(log_fn, f"[HETERO-A] complete failure; failures={failure_messages}")

    deduped: dict[str, dict[str, Any]] = {}
    for hit in per_index_hits:
        key = mod.dedup_key_for_hit(hit)
        existing = deduped.get(key)
        hit_rank = hit.get("_normalized_score", hit.get("_score") or 0.0)
        existing_rank = (
            existing.get("_normalized_score", existing.get("_score") or 0.0) if existing else None
        )
        if existing is None or (existing_rank is not None and hit_rank > existing_rank):
            deduped[key] = hit

    merged_hits = list(deduped.values())
    merged_hits.sort(key=lambda h: h.get("_normalized_score", h.get("_score") or 0.0), reverse=True)
    merged_hits = merged_hits[:limit]
    _safe_log(log_fn, f"[HETERO-A] total hits after dedup={len(merged_hits)}")

    out: list[MergedHit] = []
    for hit in merged_hits:
        src = hit.get("_source", {}) if isinstance(hit, dict) else {}
        page_content = src.get("text", "") if isinstance(src, dict) else ""
        metadata = {k: v for k, v in src.items() if k != "text"} if isinstance(src, dict) else {}
        out.append(MergedHit(page_content=page_content, metadata=metadata, score=hit.get("_score")))
    return out


async def async_search(
    *,
    client: Any,
    index_name: str,
    query_text: str,
    filter_clauses: list[dict],
    limit: int,
    score_threshold: int | float,
    query_embeddings: dict[str, list[float]],
    use_num_candidates: bool,
    num_candidates: int,
    get_embedding_field_name: Callable[[str], str],
    log_fn: LogFn | None = None,
) -> tuple[str, list[MergedHit]]:
    """Async engine entrypoint.

    Returns:
      (topology, merged_hits)
    """
    physical_indices, is_alias = await async_get_physical_indices(client, index_name)
    topology = (await async_detect_search_topology(client, physical_indices)) if is_alias else "single_index"
    _safe_log(log_fn, f"[TOPOLOGY] detected={topology}; alias={is_alias}; indices={physical_indices}")

    merged_hits = await async_run_heterogeneous_alias_search(
        client=client,
        query_text=query_text,
        filter_clauses=filter_clauses,
        limit=limit,
        score_threshold=score_threshold,
        query_embeddings=query_embeddings,
        use_num_candidates=use_num_candidates,
        num_candidates=num_candidates,
        physical_indices=physical_indices,
        get_embedding_field_name=get_embedding_field_name,
        log_fn=log_fn,
    )
    return topology, merged_hits

def run_heterogeneous_alias_search(
    *,
    client: OpenSearch,
    query_text: str,
    filter_clauses: list[dict],
    limit: int,
    score_threshold: int | float,
    query_embeddings: dict[str, list[float]],
    use_num_candidates: bool,
    num_candidates: int,
    physical_indices: list[str],
    get_embedding_field_name: Callable[[str], str],
    log_fn: LogFn | None = None,
) -> list[MergedHit]:
    """Execute per-index search behind an alias and merge results (shared with Langflow).

    Delegates to flows/opensearch_alias_search.py for KNN/lexical fallback and mapping-based
    model selection (no dependency on embedding_model terms agg).
    """
    mod = _get_flows_alias_search_module()
    rows, failures = mod.run_per_index_merged_search(
        client=client,
        query_text=query_text,
        filter_clauses=filter_clauses,
        limit=limit,
        score_threshold=score_threshold,
        query_embeddings=query_embeddings,
        physical_indices=physical_indices,
        get_embedding_field_name=get_embedding_field_name,
        use_num_candidates=use_num_candidates,
        num_candidates=num_candidates,
        log_fn=log_fn,
    )
    if not rows and failures:
        logger.error(
            "OpenSearch per-index search returned no hits; failures=%s",
            failures,
        )
        _safe_log(log_fn, f"[HETERO] complete failure; failures={failures}")
    return [
        MergedHit(page_content=r["page_content"], metadata=r["metadata"], score=r["score"])
        for r in rows
    ]


def search(
    *,
    client: OpenSearch,
    index_name: str,
    query_text: str,
    filter_clauses: list[dict],
    limit: int,
    score_threshold: int | float,
    query_embeddings: dict[str, list[float]],
    use_num_candidates: bool,
    num_candidates: int,
    get_embedding_field_name: Callable[[str], str],
    log_fn: LogFn | None = None,
) -> list[MergedHit]:
    """Engine entrypoint (plain Python).

    PR-3 scope:
    - Provide heterogeneous per-index execution path + merge/dedup/normalize.
    - Caller is responsible for generating query embeddings and providing filters.

    TODO(PR-4): add adapters and switch `/api/search` heterogeneous path to use this engine.
    TODO(PR-5): switch Langflow tool search_documents to use this engine.
    """

    physical_indices, is_alias = get_physical_indices(client, index_name)
    topology = detect_search_topology(client, physical_indices) if is_alias else "single_index"
    _safe_log(log_fn, f"[TOPOLOGY] detected={topology}; alias={is_alias}; indices={physical_indices}")

    # PR-3: keep behavior simple; core feature is heterogeneous per-index execution.
    # For non-heterogeneous topologies we still can safely run the same per-index flow
    # with a single physical index, which avoids adding more code in this PR.
    return run_heterogeneous_alias_search(
        client=client,
        query_text=query_text,
        filter_clauses=filter_clauses,
        limit=limit,
        score_threshold=score_threshold,
        query_embeddings=query_embeddings,
        use_num_candidates=use_num_candidates,
        num_candidates=num_candidates,
        physical_indices=physical_indices,
        get_embedding_field_name=get_embedding_field_name,
        log_fn=log_fn,
    )

