#!/usr/bin/env python3
"""Sync upstream English docs from vercel.com into upstream/en/.

Reads https://vercel.com/docs/sitemap.md, parses the page hierarchy, diffs
against upstream/manifest.json, and downloads changed pages as raw Markdown
from https://vercel.com/docs/<path>.md.

Manifest entry per page:
  {title, depth, parent, type, lastmod, summary, hash, file, translated_hash}

The `translated_hash` field is owned by stamp.py and is never touched here.

Usage:
  python3 scripts/sync.py [--limit N] [--force] [--concurrency N]
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

BASE = "https://vercel.com"
SITEMAP_URL = f"{BASE}/docs/sitemap.md"
ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_DIR = ROOT / "upstream"
EN_DIR = UPSTREAM_DIR / "en"
MANIFEST_PATH = UPSTREAM_DIR / "manifest.json"
SITEMAP_PATH = UPSTREAM_DIR / "sitemap.md"
USER_AGENT = "vercel-zh-docs-sync/0.1 (community translation project)"

LINE_RE = re.compile(r"^(?P<indent>\s*)-\s+\[(?P<title>[^\]]+)\]\((?P<path>/docs/[^\s)]+)\)(?P<rest>.*)$")


def fetch(url: str, retries: int = 3) -> bytes:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
            with urlopen(req, timeout=60) as resp:
                return resp.read()
        except Exception as err:  # noqa: BLE001 - report per-page failures
            last_err = err
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"failed to fetch {url}: {last_err}")


def parse_fields(rest: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for piece in rest.split("|"):
        piece = piece.strip()
        m = re.match(r"^(\w+):\s*(.*)$", piece)
        if m:
            fields[m.group(1)] = m.group(2).strip()
    return fields


def parse_sitemap(text: str) -> list[dict]:
    """Return pages in sitemap order with depth/parent resolved."""
    pages: list[dict] = []
    stack: list[tuple[int, str]] = []
    for line in text.splitlines():
        m = LINE_RE.match(line)
        if not m:
            continue
        depth = len(m.group("indent")) // 4
        path = m.group("path")
        fields = parse_fields(m.group("rest"))
        while stack and stack[-1][0] >= depth:
            stack.pop()
        parent = stack[-1][1] if stack else None
        stack.append((depth, path))
        pages.append(
            {
                "path": path,
                "title": m.group("title").strip(),
                "depth": depth,
                "parent": parent,
                "type": fields.get("Type", ""),
                "lastmod": fields.get("Lastmod", ""),
                "summary": fields.get("Summary", ""),
            }
        )
    return pages


def rel_file(page_path: str) -> str:
    return page_path[len("/docs/") :] + ".md"


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {"synced_at": None, "pages": {}}


def download_page(page: dict) -> tuple[dict, str | None]:
    """Download one page; returns (page, hash-or-None-on-failure)."""
    url = f"{BASE}{page['path']}.md"
    try:
        body = fetch(url)
    except RuntimeError as err:
        print(f"  FAIL {page['path']}: {err}", file=sys.stderr)
        return page, None
    out = EN_DIR / rel_file(page["path"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(body)
    return page, hashlib.sha256(body).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, help="only process first N sitemap pages (testing)")
    ap.add_argument("--force", action="store_true", help="re-download every page even if unchanged")
    ap.add_argument("--concurrency", type=int, default=8)
    args = ap.parse_args()

    print(f"Fetching sitemap: {SITEMAP_URL}")
    sitemap_text = fetch(SITEMAP_URL).decode("utf-8")
    SITEMAP_PATH.write_text(sitemap_text, encoding="utf-8")
    pages = parse_sitemap(sitemap_text)
    if args.limit:
        pages = pages[: args.limit]
    # Drop non-content entries (sitemap/llms/taxonomy/graph endpoints that the
    # sitemap links to but which are not regular documentation pages) and the
    # REST API reference (no per-page .md endpoint; content is generated from
    # the OpenAPI spec at openapi.vercel.sh, handled separately in M2).
    pages = [
        p
        for p in pages
        if not p["path"].endswith((".md", ".json", ".txt"))
        and not p["path"].startswith("/docs/rest-api/")
    ]
    print(f"Sitemap parsed: {len(pages)} pages")

    manifest = load_manifest()
    prev_pages: dict[str, dict] = manifest["pages"]

    sitemap_paths = {p["path"] for p in pages}
    to_download: list[dict] = []
    unchanged = removed = 0

    # Detect removals: pages in manifest but no longer in sitemap.
    for path, entry in list(prev_pages.items()):
        if path not in sitemap_paths and not entry.get("removed"):
            entry["removed"] = True
            old_file = EN_DIR / entry["file"]
            if old_file.exists():
                old_file.unlink()
            removed += 1
            print(f"  REMOVED upstream: {path}")

    for page in pages:
        prev = prev_pages.get(page["path"])
        if args.force or prev is None or not prev.get("hash") or prev.get("lastmod") != page["lastmod"]:
            to_download.append(page)
        else:
            unchanged += 1

    print(f"Downloading {len(to_download)} pages (concurrency={args.concurrency}) ...")
    failed: list[str] = []
    added = updated = unchanged_redownloaded = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        for page, digest in pool.map(download_page, to_download):
            old = prev_pages.get(page["path"], {})
            entry = prev_pages.setdefault(page["path"], {})
            entry.update(
                {
                    "title": page["title"],
                    "depth": page["depth"],
                    "parent": page["parent"],
                    "type": page["type"],
                    "lastmod": page["lastmod"],
                    "summary": page["summary"],
                    "file": rel_file(page["path"]),
                    "removed": False,
                }
            )
            if digest is None:
                entry["hash"] = None
                failed.append(page["path"])
                continue
            entry["hash"] = digest
            if not old.get("hash"):
                added += 1
            elif old["hash"] != digest:
                updated += 1
            else:
                unchanged_redownloaded += 1

    manifest["synced_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print()
    print("Sync report:")
    print(f"  sitemap pages : {len(pages)}")
    print(f"  added         : {added}")
    print(f"  updated       : {updated}")
    print(f"  unchanged     : {unchanged + unchanged_redownloaded}")
    print(f"  removed       : {removed}")
    print(f"  failed        : {len(failed)}")
    if failed:
        print("  failed paths (will retry next sync):")
        for p in failed:
            print(f"    {p}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
