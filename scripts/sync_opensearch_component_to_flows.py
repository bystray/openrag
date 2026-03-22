#!/usr/bin/env python3
"""
Replace embedded OpenSearch multimodal component Python in flow JSON files
with the current flows/components/opensearch_multimodal.py source.

Run from repo root after editing the component:
  uv run python scripts/sync_opensearch_component_to_flows.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
COMPONENT = REPO / "flows" / "components" / "opensearch_multimodal.py"
FLOW_FILES = [
    REPO / "flows" / "openrag_agent.json",
    REPO / "flows" / "openrag_nudges.json",
    REPO / "flows" / "openrag_url_mcp.json",
    REPO / "flows" / "ingestion_flow.json",
]
MARKER = "class OpenSearchVectorStoreComponentMultimodalMultiEmbedding"


def walk_replace(obj, new_code: str):
    """Recursively replace embedded component code strings."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "value" and isinstance(v, str) and MARKER in v:
                obj[k] = new_code
            else:
                walk_replace(v, new_code)
    elif isinstance(obj, list):
        for item in obj:
            walk_replace(item, new_code)


def main() -> int:
    if not COMPONENT.is_file():
        print(f"Missing {COMPONENT}", file=sys.stderr)
        return 1
    new_code = COMPONENT.read_text(encoding="utf-8")
    if MARKER not in new_code:
        print("Component file does not contain expected class marker", file=sys.stderr)
        return 1
    for fp in FLOW_FILES:
        if not fp.is_file():
            print(f"Skip missing {fp}")
            continue
        data = json.loads(fp.read_text(encoding="utf-8"))
        before = json.dumps(data)
        walk_replace(data, new_code)
        after = json.dumps(data)
        if before == after:
            print(f"No embedded component updated in {fp.name} (marker not found?)")
            continue
        fp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Updated {fp.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
