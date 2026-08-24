#!/usr/bin/env python3
"""LLM batch translation: upstream/en/*.md -> translations/zh/*.md.

Talks to any OpenAI-compatible chat completions API. Configure via env:
  VZ_API_BASE  e.g. https://api.openai.com/v1  (no trailing slash)
  VZ_API_KEY   API key
  VZ_MODEL     model name

The glossary (glossary/terms.json) and style guide (glossary/style-guide.md)
are injected into the system prompt. Successfully translated pages are
stamped automatically (translated_hash = current upstream hash).

Usage:
  VZ_API_BASE=... VZ_API_KEY=... VZ_MODEL=... \
    python3 scripts/translate.py --status untranslated --limit 20
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "upstream" / "manifest.json"
EN_DIR = ROOT / "upstream" / "en"
ZH_DIR = ROOT / "translations" / "zh" / "docs"
GLOSSARY_PATH = ROOT / "glossary" / "terms.json"
STYLE_PATH = ROOT / "glossary" / "style-guide.md"

API_BASE = os.environ.get("VZ_API_BASE", "").rstrip("/")
API_KEY = os.environ.get("VZ_API_KEY", "")
MODEL = os.environ.get("VZ_MODEL", "")

SYSTEM_PROMPT = """You are a professional technical translator localizing Vercel platform documentation into Simplified Chinese.

Hard rules:
- Translate prose, headings, list items, table cells, bold/italic text, and image alt text. Keep meaning precise; never add or drop information.
- DO NOT translate or alter: code blocks (fenced or inline), commands, file paths, package names, URLs, environment variable names, CLI flags, HTTP headers, JSON/YAML keys, version numbers.
- Keep the Markdown structure identical: same heading levels, same list nesting, same table column count, same blockquotes, same horizontal rules.
- Keep the YAML frontmatter between --- markers unchanged EXCEPT you may translate the value of `title` (keep it concise) and `description`/`summary` if present.
- Keep link targets exactly as they are (including /docs/... paths and anchors); translate only link display text.
- Use the glossary below as mandatory terminology; terms listed as "keep" must remain in English.
- Output ONLY the translated Markdown document. No preamble, no notes, no code fences around the whole output.

Glossary:
{GLOSSARY}

Style guide:
{STYLE}"""


def load_glossary_text() -> str:
    if GLOSSARY_PATH.exists():
        terms = json.loads(GLOSSARY_PATH.read_text(encoding="utf-8"))
        lines = []
        for en, zh in terms.get("translate", {}).items():
            lines.append(f"- {en} -> {zh}")
        for term in terms.get("keep", []):
            lines.append(f"- {term} (keep in English)")
        return "\n".join(lines) or "(empty)"
    return "(empty)"


def load_style_text() -> str:
    if STYLE_PATH.exists():
        return STYLE_PATH.read_text(encoding="utf-8").strip()
    return "(empty)"


def translate_text(text: str, system: str) -> str:
    payload = json.dumps(
        {
            "model": MODEL,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": text},
            ],
        }
    ).encode("utf-8")
    req = Request(
        f"{API_BASE}/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
    )
    with urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"].strip()


def select_files(manifest: dict, args) -> list[str]:
    zh_files = {str(p.relative_to(ZH_DIR)) for p in ZH_DIR.rglob("*.md")} if ZH_DIR.exists() else set()
    selected: list[str] = []
    for path, entry in manifest["pages"].items():
        if entry.get("removed") or not entry.get("hash"):
            continue
        file = entry["file"]
        has_zh = file in zh_files
        if args.status == "untranslated" and has_zh:
            continue
        if args.status == "needs_update":
            if not has_zh or entry.get("translated_hash") == entry["hash"]:
                continue
        if args.files and file not in args.files:
            continue
        selected.append(file)
        if args.limit and len(selected) >= args.limit:
            break
    return selected


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--status", choices=["untranslated", "needs_update"], default="untranslated")
    ap.add_argument("--files", nargs="*", help="specific upstream-relative files, e.g. fundamentals/builds.md")
    ap.add_argument("--limit", type=int, default=0, help="max pages in this batch (0 = no limit)")
    ap.add_argument("--max-chars", type=int, default=60000, help="skip pages larger than this (chunking is M1)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    files = select_files(manifest, args)
    if not files:
        print("nothing selected")
        return 0

    if args.dry_run:
        for f in files:
            print(f)
        print(f"{len(files)} page(s) selected")
        return 0

    if not (API_BASE and API_KEY and MODEL):
        print("set VZ_API_BASE, VZ_API_KEY, VZ_MODEL (any OpenAI-compatible endpoint).", file=sys.stderr)
        return 1

    system = SYSTEM_PROMPT.replace("{GLOSSARY}", load_glossary_text()).replace("{STYLE}", load_style_text())
    by_file = {e["file"]: (path, e) for path, e in manifest["pages"].items()}
    done = failed = skipped = 0

    for i, file in enumerate(files, 1):
        src = (EN_DIR / file).read_text(encoding="utf-8")
        if len(src) > args.max_chars:
            print(f"[{i}/{len(files)}] SKIP {file}: {len(src)} chars > {args.max_chars} (needs chunking)")
            skipped += 1
            continue
        print(f"[{i}/{len(files)}] translating {file} ({len(src)} chars) ...", flush=True)
        try:
            translated = translate_text(src, system)
        except Exception as err:  # noqa: BLE001
            print(f"  FAIL {file}: {err}", file=sys.stderr)
            failed += 1
            time.sleep(1)
            continue
        if "---" not in translated[:200] or len(translated) < len(src) // 4:
            print(f"  FAIL {file}: output looks truncated or missing frontmatter", file=sys.stderr)
            failed += 1
            continue
        out = ZH_DIR / file
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(translated + "\n", encoding="utf-8")
        path, entry = by_file[file]
        entry["translated_hash"] = entry["hash"]
        done += 1

    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\ntranslated={done} failed={failed} skipped={skipped} (stamped {done})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
