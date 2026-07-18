#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


TYPES = "插图|图组|对比图|长图|封面"
CARD_RE = re.compile(
    rf"【(?P<full_type>{TYPES})】(?P<body>.*?)【/(?P=full_type)】"
    rf"|【(?P<quick_type>{TYPES})[：:](?P<quick>[^】]+)】",
    re.S,
)
FIELD_MAP = {
    "文件": "files",
    "位置": "position",
    "用途": "purpose",
    "样式": "layout",
    "裁剪": "crop",
    "焦点": "focal_point",
    "图注": "caption",
    "替代文字": "alt",
    "约束": "constraint",
}


def parse_fields(card_type: str, body: str, quick: bool) -> tuple[dict, list[str]]:
    fields: dict[str, object] = {"type": card_type}
    unknown: dict[str, str] = {}
    parts = re.split(r"[｜|]" if quick else r"\r?\n", body)
    for index, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue
        match = re.match(r"^([^：:]+)[：:](.*)$", part)
        if not match and quick and index == 0:
            fields["files"] = [item.strip() for item in re.split(r"[，,]", part) if item.strip()]
            continue
        if not match:
            unknown[f"line_{index + 1}"] = part
            continue
        key, value = match.group(1).strip(), match.group(2).strip()
        normalized = FIELD_MAP.get(key)
        if not normalized:
            unknown[key] = value
        elif normalized == "files":
            fields[normalized] = [item.strip() for item in re.split(r"[，,]", value) if item.strip()]
        else:
            fields[normalized] = value
    fields.setdefault("position", "此处")
    fields.setdefault("layout", "自动")
    fields.setdefault("crop", "自动")
    fields.setdefault("constraint", "可调整")
    if unknown:
        fields["unknown_fields"] = unknown
    errors = []
    if not fields.get("files"):
        errors.append(f"{card_type} 缺少文件")
    if fields["constraint"] not in {"固定", "可调整"}:
        errors.append(f"{card_type} 的约束必须是“固定”或“可调整”")
    return fields, errors


def preceding_text(source: str) -> str:
    paragraphs = [item.strip() for item in re.split(r"\n\s*\n", source) if item.strip()]
    return paragraphs[-1][-100:] if paragraphs else ""


def parse(source: str) -> dict:
    directives = []
    errors = []
    output = []
    cursor = 0
    for index, match in enumerate(CARD_RE.finditer(source), start=1):
        output.append(source[cursor:match.start()])
        card_type = match.group("full_type") or match.group("quick_type")
        body = match.group("body") if match.group("full_type") else match.group("quick")
        marker = f"user-image-{index:03d}"
        fields, field_errors = parse_fields(card_type, body or "", bool(match.group("quick_type")))
        directive = {
            "marker": marker,
            "line": source.count("\n", 0, match.start()) + 1,
            "preceding_text": preceding_text(source[:match.start()]),
            **fields,
        }
        directives.append(directive)
        errors.extend(f"{marker}: {message}" for message in field_errors)
        if card_type != "封面":
            output.append(f"\n[[USER_IMAGE:{marker}]]\n")
        cursor = match.end()
    output.append(source[cursor:])
    return {
        "ok": not errors,
        "errors": errors,
        "directives": directives,
        "body_with_markers": "".join(output),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="解析正文中的中文图片指令卡")
    parser.add_argument("source", nargs="?", default="-", help="UTF-8 文本文件；- 表示 stdin")
    parser.add_argument("--output", type=Path, help="可选 JSON 输出文件")
    args = parser.parse_args()
    text = sys.stdin.read() if args.source == "-" else Path(args.source).read_text(encoding="utf-8")
    result = parse(text)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
