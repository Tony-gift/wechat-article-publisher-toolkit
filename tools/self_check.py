#!/usr/bin/env python3
"""Offline repository sanity checks used by CI."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLOCKED_PATTERNS = {
    "private IPv4 proxy": re.compile(r"https://\d{1,3}(?:\.\d{1,3}){3}"),
    "GitHub token": re.compile(r"\bgh[opusr]_[A-Za-z0-9_]{20,}\b"),
    "WeChat draft/media ID": re.compile(r"\bQr2v-[A-Za-z0-9_-]{20,}\b"),
}


def main() -> None:
    required = [
        ROOT / "skill" / "SKILL.md",
        ROOT / "skill" / "scripts" / "ingest_content.py",
        ROOT / "skill" / "scripts" / "parse_image_directives.py",
        ROOT / "skill" / "scripts" / "validate_image_manifest.py",
        ROOT / "mp_proxy" / "client.py",
        ROOT / "tools" / "publish_draft.py",
        ROOT / "examples" / "article.html",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        raise SystemExit(f"Missing required files: {missing}")

    article = (ROOT / "examples" / "article.html").read_text(encoding="utf-8")
    if article.count("{{IMAGE:hero}}") != 1:
        raise SystemExit("Example article must contain one hero token")

    json.loads((ROOT / "examples" / "article-plan.json").read_text(encoding="utf-8"))
    json.loads((ROOT / "examples" / "image-manifest.json").read_text(encoding="utf-8"))

    violations: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pyc"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for label, pattern in BLOCKED_PATTERNS.items():
            if pattern.search(text):
                violations.append(f"{path.relative_to(ROOT)}: {label}")
    if violations:
        raise SystemExit("Sensitive release content detected:\n" + "\n".join(violations))

    print("self-check: ok")


if __name__ == "__main__":
    main()
