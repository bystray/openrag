"""
Shared multi physical-index OpenSearch retrieval (alias → documents_*).

Used by Langflow (flows/) and backend (importlib from repo flows/).
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Callable

from opensearchpy import OpenSearch
from opensearchpy.exceptions import OpenSearchException, RequestError

logger = logging.getLogger(__name__)
LogFn = Callable[[str], None]


def _safe_log(log_fn: LogFn | None, msg: str) -> None:
    if not log_fn:
        return
    try:
        log_fn(msg)
    except Exception:
        return


def get_physical_indices(client: OpenSearch, index_name: str) -> tuple[list[str], bool]:
    try:
        alias_map = client.indices.get_alias(name=index_name)
        if isinstance(alias_map, dict) and len(alias_map) > 0:
            return list(alias_map.keys()), True
    except Exception as e:
        logger.warning("get_alias failed for '%s' (using index name as target): %s", index_name, e)
    return [index_name], False


def get_index_properties_for(client: OpenSearch, index_name: str) -> dict[str, Any] | None:
    try:
        mapping = client.indices.get_mapping(index=index_name)
    except OpenSearchException as e:
        logger.warning("Failed to fetch mapping for index '%s': %s", index_name, e)
        return None
    index_data = mapping.get(index_name, {})
    props = index_data.get("mappings", {}).get("properties", {})
    return props if isinstance(props, dict) else None


def extract_knn_fields(properties: dict[str, Any] | None) -> dict[str, int | None]:
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
    if len(physical_indices) <= 1:
        return "single_index"
    signatures: set[tuple[tuple[str, int | None], ...]] = set()
    for idx in physical_indices:
        properties = get_index_properties_for(client, idx)
        knn_fields = extract_knn_fields(properties)
        signatures.add(tuple(sorted(knn_fields.items())))
    return "homogeneous_alias" if len(signatures) <= 1 else "heterogeneous_alias"


def build_heterogeneous_search_body(
    query_text: str,
    filter_clauses: list[dict],
    limit: int,
    score_threshold: int | float,
    knn_queries: list[dict],
    include_aggs: bool,
) -> dict[str, Any]:
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
    if include_aggs:
        pass
    if isinstance(score_threshold, (int, float)) and score_threshold > 0:
        body["min_score"] = score_threshold
    return body


def dedup_key_for_hit(hit: dict[str, Any]) -> str:
    source = hit.get("_source", {}) if isinstance(hit, dict) else {}
    doc_id = source.get("document_id")
    page = source.get("page")
    text = source.get("text", "")
    filename = source.get("filename", "")
    source_url = source.get("source_url", "")
    if doc_id:
        return f"doc:{doc_id}|page:{page}"
    return f"fn:{filename}|url:{source_url}|page:{page}|txt:{str(text)[:120]}"


def knn_queries_for_physical_index(
    knn_fields: dict[str, int | None],
    query_embeddings: dict[str, list[float]],
    get_embedding_field_name: Callable[[str], str],
) -> list[dict[str, Any]]:
    local: list[dict[str, Any]] = []
    for model_name, embedding_vector in query_embeddings.items():
        field_name = get_embedding_field_name(model_name)
        if field_name not in knn_fields:
            continue
        field_dim = knn_fields.get(field_name)
        if field_dim is not None and field_dim != len(embedding_vector):
            continue
        local.append({"knn": {field_name: {"vector": embedding_vector, "k": 50}}})
    return local


def run_per_index_merged_search(
    *,
    client: OpenSearch,
    query_text: str,
    filter_clauses: list[dict],
    limit: int,
    score_threshold: int | float,
    query_embeddings: dict[str, list[float]],
    physical_indices: list[str],
    get_embedding_field_name: Callable[[str], str],
    use_num_candidates: bool,
    num_candidates: int,
    log_fn: LogFn | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    per_index_hits: list[dict[str, Any]] = []
    failure_messages: list[str] = []
    per_index_limit = max(limit, limit * 2)
    q = (query_text or "").strip()

    for idx_num, index_name in enumerate(physical_indices):
        properties = get_index_properties_for(client, index_name)
        knn_fields = extract_knn_fields(properties)
        model_hint = detect_available_models_for_index(client, index_name, filter_clauses)
        local_knn = knn_queries_for_physical_index(knn_fields, query_embeddings, get_embedding_field_name)
        mode = "knn_hybrid" if local_knn else "text_only"
        _safe_log(
            log_fn,
            f"[ALIAS] index={index_name}; mode={mode}; agg_models={model_hint}; knn_fields={list(knn_fields.keys())}",
        )
        if not q and not local_knn:
            _safe_log(log_fn, f"[ALIAS] index={index_name}; skip empty query and no KNN")
            failure_messages.append(f"{index_name}: skipped (empty query, no KNN fields)")
            continue
        body = build_heterogeneous_search_body(
            query_text=q,
            filter_clauses=filter_clauses,
            limit=per_index_limit,
            score_threshold=score_threshold,
            knn_queries=local_knn,
            include_aggs=(idx_num == 0),
        )
        fallback_body: dict[str, Any] | None = None
        if local_knn and use_num_candidates:
            fallback_body = copy.deepcopy(body)
            try:
                fallback_body["query"]["bool"]["should"][0]["dis_max"]["queries"] = list(local_knn)
            except (KeyError, IndexError, TypeError):
                fallback_body = None

        def _do_search(b: dict[str, Any]) -> dict[str, Any]:
            return client.search(index=index_name, body=b, params={"terminate_after": 0})

        resp: dict[str, Any] | None = None
        try:
            resp = _do_search(body)
        except RequestError as e:
            lowered = str(e).lower()
            if fallback_body is not None and "num_candidates" in lowered:
                try:
                    resp = _do_search(fallback_body)
                except Exception as sub_err:
                    logger.warning("Per-index search retry failed for '%s': %s", index_name, sub_err)
                    _safe_log(log_fn, f"[ALIAS] index={index_name}; num_candidates retry failed={sub_err}")
                    resp = None
            if resp is None and local_knn:
                try:
                    body_lex = build_heterogeneous_search_body(
                        query_text=q,
                        filter_clauses=filter_clauses,
                        limit=per_index_limit,
                        score_threshold=score_threshold,
                        knn_queries=[],
                        include_aggs=False,
                    )
                    resp = _do_search(body_lex)
                    _safe_log(log_fn, f"[ALIAS] index={index_name}; lexical fallback after error={e}")
                except Exception as lex_e:
                    msg = f"{index_name}: hybrid_error={e!s}; lexical_fallback={lex_e!s}"
                    failure_messages.append(msg)
                    logger.warning("Per-index search failed for '%s': %s", index_name, msg)
                    _safe_log(log_fn, f"[ALIAS] failed {msg}")
                    continue
            elif resp is None:
                msg = f"{index_name}: {e!s}"
                failure_messages.append(msg)
                logger.warning("Per-index search failed for '%s': %s", index_name, e)
                _safe_log(log_fn, f"[ALIAS] failed {msg}")
                continue
        except Exception as e:
            if local_knn:
                try:
                    body_lex = build_heterogeneous_search_body(
                        query_text=q,
                        filter_clauses=filter_clauses,
                        limit=per_index_limit,
                        score_threshold=score_threshold,
                        knn_queries=[],
                        include_aggs=False,
                    )
                    resp = _do_search(body_lex)
                    _safe_log(log_fn, f"[ALIAS] index={index_name}; lexical fallback after {e!s}")
                except Exception as lex_e:
                    msg = f"{index_name}: error={e!s}; lexical_fallback={lex_e!s}"
                    failure_messages.append(msg)
                    _safe_log(log_fn, f"[ALIAS] failed {msg}")
                    continue
            else:
                msg = f"{index_name}: {e!s}"
                failure_messages.append(msg)
                _safe_log(log_fn, f"[ALIAS] failed {msg}")
                continue
        if resp is None:
            continue
        hits = resp.get("hits", {}).get("hits", []) if isinstance(resp, dict) else []
        max_score_index = max((hit.get("_score") or 0.0) for hit in hits) if hits else 0.0
        _safe_log(log_fn, f"[ALIAS] index={index_name}; max_score={max_score_index}; hits={len(hits)}")
        for hit in hits:
            raw_score = hit.get("_score") or 0.0
            hit["_normalized_score"] = (raw_score / max_score_index) if max_score_index > 0 else 0.0
        per_index_hits.extend(hits)
    _safe_log(log_fn, f"[ALIAS] total hits before dedup={len(per_index_hits)}")
    deduped: dict[str, dict[str, Any]] = {}
    for hit in per_index_hits:
        key = dedup_key_for_hit(hit)
        existing = deduped.get(key)
        hit_rank = hit.get("_normalized_score", hit.get("_score") or 0.0)
        existing_rank = existing.get("_normalized_score", existing.get("_score") or 0.0) if existing else None
        if existing is None or (existing_rank is not None and hit_rank > existing_rank):
            deduped[key] = hit
    merged_hits = list(deduped.values())
    merged_hits.sort(key=lambda h: h.get("_normalized_score", h.get("_score") or 0.0), reverse=True)
    merged_hits = merged_hits[:limit]
    out: list[dict[str, Any]] = []
    for hit in merged_hits:
        src = hit.get("_source", {}) if isinstance(hit, dict) else {}
        page_content = src.get("text", "") if isinstance(src, dict) else ""
        metadata = {k: v for k, v in src.items() if k != "text"} if isinstance(src, dict) else {}
        out.append({"page_content": page_content, "metadata": metadata, "score": hit.get("_score")})
    if not out and physical_indices:
        _safe_log(log_fn, "[ALIAS] no merged hits after per-index search")
    return out, failure_messages
