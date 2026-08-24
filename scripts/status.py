#!/usr/bin/env python3
"""Report translation status for every upstream page.

Status per page:
  translated         translated_hash == current upstream hash
  needs_update       translation exists but is based on an older upstream hash
  untranslated       no translation file yet
  unverified         translation file exists but was never stamped
  removed_upstream   upstream page deleted; translation kept only as archive

Usage:
  python3 scripts/status.py [--list STATUS] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "upstream" / "manifest.json"
ZH_DIR = ROOT / "translations" / "zh" / "docs"

STATUSES = ["translated", "needs_update", "untranslated", "unverified", "removed_upstream"]


def load_translations() -> set[str]:
    if not ZH_DIR.exists():
        return set()
    return {str(p.relative_to(ZH_DIR)) for p in ZH_DIR.rglob("*.md")}


def compute(manifest: dict, translated_files: set[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for path, entry in manifest["pages"].items():
        file = entry["file"]
        has_translation = file in translated_files
        if entry.get("removed"):
            status = "removed_upstream" if has_translation else None
        elif not has_translation:
            status = "untranslated"
        elif entry.get("translated_hash") is None:
            status = "unverified"
        elif entry["translated_hash"] == entry.get("hash"):
            status = "translated"
        else:
            status = "needs_update"
        if status:
            result[path] = status
    # Translation files whose upstream page is gone entirely.
    known_files = {e["file"] for e in manifest["pages"].values()}
    for file in sorted(translated_files - known_files):
        result[f"(orphan) {file}"] = "removed_upstream"
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", choices=STATUSES, help="print file list for one status")
    ap.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = ap.parse_args()

    if not MANIFEST_PATH.exists():
        print("manifest.json not found - run `python3 scripts/sync.py` first.", file=sys.stderr)
        return 1
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    translated_files = load_translations()
    result = compute(manifest, translated_files)

    counts = Counter(result.values())
    if args.json:
        print(json.dumps({"synced_at": manifest.get("synced_at"), "counts": dict(counts), "pages": result},
                         ensure_ascii=False, indent=2))
        return 0
    if args.list:
        for path in sorted(p for p, s in result.items() if s == args.list):
            print(path)
        return 0

    total_pages = sum(1 for e in manifest["pages"].values() if not e.get("removed"))
    print(f"upstream synced at: {manifest.get('synced_at')}")
    print(f"active upstream pages: {total_pages}")
    print()
    for status in STATUSES:
        print(f"  {status:<18} {counts.get(status, 0):>5}")
    orphans = counts.get("removed_upstream", 0)
    if orphans:
        print(f"\n  ({orphans} of these are archived translations of removed upstream pages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
