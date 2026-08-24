#!/usr/bin/env python3
"""Materialize the Starlight content directory.

For every active upstream page, copy the Chinese translation when present,
otherwise the English original, into site/src/content/docs/. Rewrites
vercel.com-internal links to site-local or absolute URLs, and injects
source metadata into frontmatter (source_url, source_lastmod, translated).

The handwritten homepage site/src/content/docs/index.md is preserved.
Output is generated content: do not edit, do not commit (gitignored).

Usage:
  python3 scripts/publish.py
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "upstream" / "manifest.json"
EN_DIR = ROOT / "upstream" / "en"
ZH_DIR = ROOT / "translations" / "zh" / "docs"
CONTENT_DIR = ROOT / "site" / "src" / "content" / "docs"

FM_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.S)
LINK_RE = re.compile(r"\]\((?P<url>/[^)\s]*)(?P<rest>\s+[^()]*)?\)")
# Code fence boundary, tolerant of a leading list marker so fences nested in
# list items (e.g. `5) ``` `) toggle rather than desyncing the tracker.
FENCE_RE = re.compile(r"^\s*(?:\d+[.)]\s*|[-*+]\s*)?(`{3,}|~{3,})")


def is_fence_marker(line: str) -> bool:
    return bool(FENCE_RE.match(line))


def split_frontmatter(text: str) -> tuple[str | None, str]:
    m = FM_RE.match(text)
    if not m:
        return None, text
    return m.group(1), text[m.end() :]


def rewrite_target(m: re.Match) -> str:
    target = m.group("url")
    rest = m.group("rest") or ""  # preserve Markdown link titles like ` "T"`.
    anchor = ""
    if "#" in target:
        target, anchor = target.split("#", 1)
        anchor = "#" + anchor
    if target in ("/docs", "/docs/"):
        return "](/" + (anchor or "") + ")" + rest
    if target.startswith("/docs/"):
        return "](" + target[len("/docs") :] + anchor + ")" + rest
    return "](https://vercel.com" + target + anchor + ")" + rest


def rewrite_body_links(body: str) -> str:
    out: list[str] = []
    in_fence = False
    for line in body.splitlines(keepends=True):
        if is_fence_marker(line):
            in_fence = not in_fence
            out.append(line)
            continue
        out.append(line if in_fence else LINK_RE.sub(rewrite_target, line))
    return "".join(out)


def yaml_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def normalize_frontmatter(fm: str, fallback_title: str) -> str:
    """Return a guaranteed-valid, normalized YAML frontmatter body.

    Some official pages ship frontmatter that strict YAML parsers reject
    (e.g. `title: @vercel/global-config` - a plain scalar cannot start with
    the reserved indicator `@`). Re-serialize through PyYAML so Starlight's
    js-yaml-based parser always succeeds, quoting values as needed.
    """
    fm = fm or ""
    data = None
    try:
        parsed = yaml.safe_load(fm)
        if isinstance(parsed, dict):
            data = parsed
    except Exception:  # noqa: BLE001
        data = None
    if not data:
        # Fallback: quote plain scalar values starting with a reserved indicator.
        lines = []
        for line in fm.splitlines():
            m = re.match(r"^([A-Za-z_][\w]*)\s*:\s*(.+)$", line)
            if m and not line[:1].isspace() and m.group(2)[0] in "@`*&!#":
                lines.append(f"{m.group(1)}: '{m.group(2).strip()}'")
            else:
                lines.append(line)
        try:
            repaired = yaml.safe_load("\n".join(lines))
            data = repaired if isinstance(repaired, dict) else None
        except Exception:  # noqa: BLE001
            data = None
    if not isinstance(data, dict):
        data = {"title": fallback_title}
    if not isinstance(data.get("title"), str) or not data["title"]:
        data["title"] = fallback_title
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False).strip()


def build_page(page_path: str, entry: dict) -> None:
    zh_file = ZH_DIR / entry["file"]
    src_file = zh_file if zh_file.exists() else EN_DIR / entry["file"]
    text = src_file.read_text(encoding="utf-8")
    fm, body = split_frontmatter(text)
    fm = normalize_frontmatter(fm, entry.get("title", page_path))
    fm += (
        f"\nsource_url: {yaml_quote('https://vercel.com' + page_path)}"
        f"\nsource_lastmod: {yaml_quote(entry.get('lastmod', ''))}"
        f"\ntranslated: {'true' if src_file == zh_file else 'false'}"
    )
    out = CONTENT_DIR / entry["file"]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f"---\n{fm}\n---\n" + rewrite_body_links(body), encoding="utf-8")


def main() -> int:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if CONTENT_DIR.exists():
        for p in sorted(CONTENT_DIR.rglob("*"), reverse=True):
            if p.name == "index.md" and p.parent == CONTENT_DIR:
                continue
            if p.is_file() or p.is_symlink():
                p.unlink()
            elif p.is_dir():
                try:
                    p.rmdir()
                except OSError:
                    shutil.rmtree(p)
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)

    pages = {p: e for p, e in manifest["pages"].items() if not e.get("removed") and e.get("hash")}
    zh_count = 0
    for page_path, entry in pages.items():
        build_page(page_path, entry)
        if (ZH_DIR / entry["file"]).exists():
            zh_count += 1
    print(f"published {len(pages)} pages ({zh_count} translated, {len(pages) - zh_count} English)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
