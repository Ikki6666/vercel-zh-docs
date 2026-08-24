#!/usr/bin/env python3
"""Stamp translated pages: record the upstream hash a translation is based on.

Accepts paths as either upstream-relative files (`frameworks/nextjs.md`) or
official doc paths (`/docs/frameworks/nextjs`).

Usage:
  python3 scripts/stamp.py frameworks/nextjs.md fundamentals/infrastructure.md
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "upstream" / "manifest.json"


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    if not MANIFEST_PATH.exists():
        print("manifest.json not found - run sync first.", file=sys.stderr)
        return 1
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    by_file = {e["file"]: (path, e) for path, e in manifest["pages"].items()}

    stamped = 0
    for arg in sys.argv[1:]:
        file = arg[len("/docs/") :].removesuffix(".md") + ".md" if arg.startswith("/docs/") else arg
        if file not in by_file:
            print(f"  SKIP {arg}: not in manifest", file=sys.stderr)
            continue
        path, entry = by_file[file]
        if not entry.get("hash"):
            print(f"  SKIP {path}: upstream hash unknown (download failed?)", file=sys.stderr)
            continue
        entry["translated_hash"] = entry["hash"]
        stamped += 1
        print(f"  stamped {path} @ {entry['hash'][:12]}")

    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"stamped {stamped} page(s)")
    return 0 if stamped else 1


if __name__ == "__main__":
    sys.exit(main())
