#!/usr/bin/env python3
"""
Compare repo flow JSON IDs with LANGFLOW_*_FLOW_ID in .env and print dev sync hints.

Non-destructive. Run from repository root: uv run python scripts/langflow_dev_sync_check.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
FLOWS_DIR = REPO_ROOT / "flows"

FLOW_ENV_KEYS = (
    ("LANGFLOW_CHAT_FLOW_ID", "openrag_agent.json", "retrieval / chat"),
    ("LANGFLOW_INGEST_FLOW_ID", "ingestion_flow.json", "ingest"),
    ("LANGFLOW_URL_INGEST_FLOW_ID", "openrag_url_mcp.json", "url ingest"),
    ("NUDGES_FLOW_ID", "openrag_nudges.json", "nudges"),
)


def _load_dotenv_simple(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip("'\"")
        out[k] = v
    return out


def _flow_meta(json_path: Path) -> tuple[str | None, str | None]:
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return None, f"read error: {e}"
    fid = data.get("id")
    name = data.get("name")
    return (str(fid) if fid else None, str(name) if name else None)


def main() -> int:
    os.chdir(REPO_ROOT)
    env = _load_dotenv_simple(REPO_ROOT / ".env")
    example = _load_dotenv_simple(REPO_ROOT / ".env.example")

    flows_path = env.get("OPENRAG_FLOWS_PATH") or example.get("OPENRAG_FLOWS_PATH") or "./flows"
    resolved = (REPO_ROOT / flows_path).resolve() if not os.path.isabs(flows_path) else Path(flows_path)

    print("=== Langflow / OpenRAG dev sync check ===\n")
    print(f"Repo root:     {REPO_ROOT}")
    print(f"OPENRAG_FLOWS_PATH (env): {env.get('OPENRAG_FLOWS_PATH', '(unset, compose default ./flows)')}")
    print(f"Resolved host path:      {resolved}")
    print(f"Expected repo flows dir: {FLOWS_DIR}")
    if resolved != FLOWS_DIR:
        print(
            "\n  [!] Flows path is NOT the repository ./flows. "
            "Docker will mount this path to /app/flows — sync JSON from repo or set OPENRAG_FLOWS_PATH to ./flows."
        )
    else:
        print("\n  [OK] OPENRAG_FLOWS_PATH matches repository flows directory (or default).")

    print("\n--- Flow IDs: .env vs flows/*.json ---")
    mismatches = 0
    for env_key, fname, role in FLOW_ENV_KEYS:
        fp = FLOWS_DIR / fname
        fid_file, name = _flow_meta(fp) if fp.is_file() else (None, None)
        fid_env = env.get(env_key) or example.get(env_key)
        ok = fid_file and fid_env and fid_file.lower() == fid_env.lower()
        status = "OK" if ok else "MISMATCH"
        if not ok:
            mismatches += 1
        print(f"  {env_key} ({role})")
        print(f"    .env:     {fid_env or '(missing)'}")
        print(f"    {fname}: {fid_file or '(missing)'}  {name or ''}")
        print(f"    -> {status}\n")

    print("--- Index / embedding (from .env only; config.yaml not loaded) ---")
    print(f"  OPENSEARCH_INDEX_NAME={env.get('OPENSEARCH_INDEX_NAME', example.get('OPENSEARCH_INDEX_NAME', '(unset)'))}")
    print(f"  SELECTED_EMBEDDING_MODEL={env.get('SELECTED_EMBEDDING_MODEL', '(unset)')}")

    print("\nNotes:")
    print("  - Chat/nudges requests send OPENSEARCH_INDEX_NAME=documents alias (Knowledge search alignment).")
    print("  - Ingest uses model-specific index via headers + ensure_documents_alias on backend startup.")
    print("  - After changing .env: restart openrag-backend; soft-restart Langflow: make langflow-soft-rebuild")

    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
