#!/usr/bin/env python3
"""Create a validated WeChat draft through the configured HTTPS proxy."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPOSITORY_ROOT))

from mp_proxy import RemoteMP

CACHE_VERSION = 1
DEFAULT_LIMIT = 20_000
TOKEN_RE = re.compile(r"\{\{IMAGE:([a-z0-9]+(?:-[a-z0-9]+)*)\}\}")
BLOCKED_RE = re.compile(
    r"<(?:script|style|link|div)\b|"
    r"\son[a-z][\w:-]*\s*=|"
    r"javascript:|"
    r"position:(?:fixed|absolute|sticky)|"
    r"display:grid|"
    r"float:",
    re.I,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class UploadCache:
    def __init__(self, path: Path):
        self.path = path
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"version": CACHE_VERSION, "entries": {}}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if data.get("version") != CACHE_VERSION or not isinstance(data.get("entries"), dict):
            raise RuntimeError(f"Unsupported cache format: {self.path}")
        return data

    def get(self, kind: str, path: Path) -> str | None:
        digest = sha256_file(path)
        entry = self.data["entries"].get(f"{kind}:{digest}")
        field = "media_id" if kind == "thumb" else "url"
        if isinstance(entry, dict) and isinstance(entry.get(field), str):
            entry["last_used_at"] = now_iso()
            self.save()
            return entry[field]
        return None

    def put(self, kind: str, path: Path, value: str) -> None:
        digest = sha256_file(path)
        timestamp = now_iso()
        entry = {
            "kind": kind,
            "sha256": digest,
            "filename": path.name,
            "size": path.stat().st_size,
            "created_at": timestamp,
            "last_used_at": timestamp,
            "source": "upload",
        }
        entry["media_id" if kind == "thumb" else "url"] = value
        self.data["entries"][f"{kind}:{digest}"] = entry
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)


def parse_image(value: str) -> tuple[str, Path]:
    slot, separator, raw_path = value.partition("=")
    if not separator or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slot):
        raise argparse.ArgumentTypeError("Use SLOT=/path/to/image.jpg")
    path = Path(raw_path).expanduser().resolve()
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"Image does not exist: {path}")
    return slot, path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate and create a WeChat draft")
    parser.add_argument("--title", required=True)
    parser.add_argument("--html", type=Path, required=True)
    parser.add_argument("--cover", type=Path, required=True)
    parser.add_argument("--image", action="append", default=[], type=parse_image, metavar="SLOT=PATH")
    parser.add_argument("--author", default="")
    parser.add_argument("--digest", default="")
    parser.add_argument("--cache", type=Path, default=Path(".wechat-upload-cache.json"))
    parser.add_argument("--content-limit", type=int, default=DEFAULT_LIMIT)
    return parser.parse_args()


def compact(html: str) -> str:
    html = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    html = re.sub(r">\s+<", "><", html)
    return html.strip()


def main() -> None:
    args = parse_args()
    html_path = args.html.resolve()
    cover_path = args.cover.resolve()
    if not html_path.is_file() or not cover_path.is_file():
        raise RuntimeError("HTML or cover file does not exist")

    source = html_path.read_text(encoding="utf-8")
    if BLOCKED_RE.search(source):
        raise RuntimeError("Layout source contains a blocked tag, event, URL, or CSS feature")

    supplied = dict(args.image)
    tokens = TOKEN_RE.findall(source)
    if len(tokens) != len(set(tokens)):
        raise RuntimeError("Each image token must occur exactly once")
    if set(tokens) != set(supplied):
        raise RuntimeError(
            f"Token/image mismatch: tokens={sorted(set(tokens))}, images={sorted(supplied)}"
        )

    cache = UploadCache(args.cache.resolve())
    cache_hits = 0
    uploads = 0

    with RemoteMP(timeout=120) as mp:
        health = mp.health()
        if health.get("ok") is not True:
            raise RuntimeError(f"Proxy health check failed: {health}")

        thumb_media_id = cache.get("thumb", cover_path)
        if thumb_media_id:
            cache_hits += 1
        else:
            thumb_media_id = mp.upload_thumb(cover_path)
            cache.put("thumb", cover_path, thumb_media_id)
            uploads += 1

        rewritten = compact(source)
        for slot, path in supplied.items():
            url = cache.get("inline", path)
            if url:
                cache_hits += 1
            else:
                url = mp.upload_inline_image(path)
                cache.put("inline", path, url)
                uploads += 1
            rewritten = rewritten.replace(f"{{{{IMAGE:{slot}}}}}", url)

        if TOKEN_RE.search(rewritten):
            raise RuntimeError("Unresolved image token after upload")
        if re.search(r'<img\b[^>]*\bsrc="(?!https?://)', rewritten, re.I):
            raise RuntimeError("Local image URL remains after upload")
        content_bytes = len(rewritten.encode("utf-8"))
        if content_bytes > args.content_limit:
            raise RuntimeError(
                f"Draft content is {content_bytes} bytes; limit is {args.content_limit}"
            )

        draft_media_id = mp.add_draft(
            title=args.title,
            html_content=rewritten,
            thumb_media_id=thumb_media_id,
            author=args.author,
            digest=args.digest,
        )
        fetched = mp.get_draft(draft_media_id)

    fetched_text = json.dumps(fetched, ensure_ascii=False)
    result = {
        "ok": True,
        "draft_media_id": draft_media_id,
        "title": args.title,
        "content_bytes": content_bytes,
        "inline_images": len(supplied),
        "actual_uploads": uploads,
        "cache_hits": cache_hits,
        "readback_title_present": args.title in fetched_text,
        "readback_image_urls": fetched_text.count("mmbiz.qpic.cn"),
        "unresolved_tokens": fetched_text.count("{{IMAGE:"),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
