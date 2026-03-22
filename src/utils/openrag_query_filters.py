"""
Shared OpenSearch filter clauses for Knowledge search and Langflow chat/nudges.

Field names match `create_dynamic_index_body` in utils/embeddings.py: filename,
mimetype, owner, connector_type are mapped as **keyword** (no `.keyword` subfield).
Using `field.keyword` on those indices causes "field not found" and breaks search.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# Frontend filter keys -> OpenSearch field names (keyword-typed in standard index)
EXACT_FILTER_FIELD_MAPPING = {
    "data_sources": "filename",
    "document_types": "mimetype",
    "owners": "owner",
    "connector_types": "connector_type",
}


def build_opensearch_filter_clauses(
    filters: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Build term/terms clauses from UI/context filter dict.

    Semantics match SearchService.search_tool: empty array means "match nothing"
    via an impossible term value.
    """
    if not filters:
        return []
    clauses: List[Dict[str, Any]] = []
    for filter_key, values in filters.items():
        if values is not None and isinstance(values, list):
            field_name = EXACT_FILTER_FIELD_MAPPING.get(filter_key, filter_key)
            if len(values) == 0:
                clauses.append({"term": {field_name: "__IMPOSSIBLE_VALUE__"}})
            elif len(values) == 1:
                clauses.append({"term": {field_name: values[0]}})
            else:
                clauses.append({"terms": {field_name: values}})
    return clauses
