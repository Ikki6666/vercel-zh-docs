#!/usr/bin/env python3
"""Generate the Starlight sidebar tree from the manifest.

Output: site/src/nav.json - a Starlight-compatible sidebar structure.
Chinese page titles are read from translation frontmatter when available.

A page that has children becomes a collapsible group with itself as the
first entry; leaf pages become plain links.

Usage:
  python3 scripts/build_nav.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "upstream" / "manifest.json"
ZH_DIR = ROOT / "translations" / "zh" / "docs"
NAV_PATH = ROOT / "site" / "src" / "nav.json"

TITLE_RE = re.compile(r"^title:\s*(.+)$", re.M)


def page_title(entry: dict) -> str:
    zh = ZH_DIR / entry["file"]
    if zh.exists():
        m = TITLE_RE.search(zh.read_text(encoding="utf-8"))
        if m:
            return m.group(1).strip().strip("\"'")
    return entry["title"]


def main() -> int:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    pages = {p: e for p, e in manifest["pages"].items() if not e.get("removed") and e.get("hash")}

    children: dict[str | None, list[str]] = {}
    for path, entry in pages.items():
        children.setdefault(entry.get("parent"), []).append(path)

    def to_item(path: str) -> dict:
        entry = pages[path]
        link = "/" + entry["file"].removesuffix(".md")
        kids = children.get(path, [])
        if not kids:
            return {"label": page_title(entry), "link": link}
        items = [{"label": page_title(entry), "link": link}]
        items += [to_item(k) for k in kids]
        return {"label": page_title(entry), "collapsed": True, "items": items}

    sidebar = [to_item(p) for p in children.get(None, [])]
    NAV_PATH.parent.mkdir(parents=True, exist_ok=True)
    NAV_PATH.write_text(json.dumps(sidebar, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    total = len(pages)
    print(f"nav.json written: {len(sidebar)} top-level groups, {total} pages total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
