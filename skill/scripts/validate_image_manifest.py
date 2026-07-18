#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
from pathlib import Path
from typing import Any


SLOT_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TOKEN_RE = re.compile(r"\{\{IMAGE:([a-z0-9]+(?:-[a-z0-9]+)*)\}\}")
TARGETS = {"cover", "html-img", "svg-image", "svg-foreignobject", "css-background"}
ANCHORS = {"before_section", "after_heading", "before_block", "after_block", "gallery_in_section", "svg_layer"}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    index = 2
    sof = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while index + 9 <= len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        while index < len(data) and data[index] == 0xFF:
            index += 1
        if index >= len(data):
            return None
        marker = data[index]
        index += 1
        if marker in {0xD8, 0xD9}:
            continue
        if index + 2 > len(data):
            return None
        length = int.from_bytes(data[index:index + 2], "big")
        if length < 2 or index + length > len(data):
            return None
        if marker in sof and length >= 7:
            height = int.from_bytes(data[index + 3:index + 5], "big")
            width = int.from_bytes(data[index + 5:index + 7], "big")
            return width, height
        index += length
    return None


def image_info(path: Path) -> dict[str, Any] | None:
    data = path.read_bytes()
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        fmt = "png"
    elif data.startswith((b"GIF87a", b"GIF89a")) and len(data) >= 10:
        width, height = struct.unpack("<HH", data[6:10])
        fmt = "gif"
    elif data.startswith(b"\xff\xd8"):
        dimensions = jpeg_dimensions(data)
        if not dimensions:
            return None
        width, height = dimensions
        fmt = "jpeg"
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        fmt = "webp"
        width = height = 0
        if data[12:16] == b"VP8X" and len(data) >= 30:
            width = 1 + int.from_bytes(data[24:27], "little")
            height = 1 + int.from_bytes(data[27:30], "little")
        elif data[12:16] == b"VP8 " and len(data) >= 30:
            width = int.from_bytes(data[26:28], "little") & 0x3FFF
            height = int.from_bytes(data[28:30], "little") & 0x3FFF
        if not width or not height:
            return {"format": fmt, "width": None, "height": None, "size": len(data)}
    else:
        return None
    return {"format": fmt, "width": width, "height": height, "size": len(data)}


def load_json(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} 顶层必须是 JSON object")
    return data, raw


def validate_plan(plan: dict[str, Any], errors: list[str]) -> tuple[set[str], dict[str, dict[str, Any]]]:
    section_ids: set[str] = set()
    block_ids: set[str] = set()
    for section in plan.get("sections", []):
        section_id = section.get("id")
        if not isinstance(section_id, str) or not SLOT_RE.fullmatch(section_id):
            errors.append(f"无效 section id：{section_id!r}")
            continue
        if section_id in section_ids:
            errors.append(f"重复 section id：{section_id}")
        section_ids.add(section_id)
        for block in section.get("blocks", []):
            block_id = block.get("id")
            if not isinstance(block_id, str) or not SLOT_RE.fullmatch(block_id):
                errors.append(f"无效 block id：{block_id!r}")
                continue
            if block_id in block_ids:
                errors.append(f"重复 block id：{block_id}")
            block_ids.add(block_id)
            if not str(block.get("text", "")).strip():
                errors.append(f"正文 block 为空：{block_id}")

    media: dict[str, dict[str, Any]] = {}
    for item in plan.get("media", []):
        slot = item.get("slot")
        if not isinstance(slot, str) or not SLOT_RE.fullmatch(slot):
            errors.append(f"无效 media slot：{slot!r}")
            continue
        if slot in media:
            errors.append(f"重复 media slot：{slot}")
        media[slot] = item
        anchor = item.get("anchor")
        if not isinstance(anchor, dict) or len(anchor) != 1:
            errors.append(f"{slot} 的 anchor 必须只包含一个语义锚点")
            continue
        anchor_type, anchor_value = next(iter(anchor.items()))
        if anchor_type not in ANCHORS:
            errors.append(f"{slot} 使用未知 anchor：{anchor_type}")
        elif anchor_type in {"before_section", "after_heading", "gallery_in_section"} and anchor_value not in section_ids:
            errors.append(f"{slot} 引用未知 section：{anchor_value}")
        elif anchor_type in {"before_block", "after_block"} and anchor_value not in block_ids:
            errors.append(f"{slot} 引用未知 block：{anchor_value}")
        if not str(item.get("purpose", "")).strip():
            errors.append(f"{slot} 缺少图片用途 purpose")
        if not str(item.get("presentation", "")).strip():
            errors.append(f"{slot} 缺少呈现方式 presentation")
    return section_ids | block_ids, media


def main() -> int:
    parser = argparse.ArgumentParser(description="校验原始图文编排计划、图片清单和内部 HTML token")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--html", type=Path)
    parser.add_argument("--write-lock", type=Path)
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []
    placements: list[dict[str, Any]] = []
    try:
        manifest, manifest_raw = load_json(args.manifest)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 1

    plan = None
    plan_raw = None
    plan_media: dict[str, dict[str, Any]] = {}
    if args.plan:
        try:
            plan, plan_raw = load_json(args.plan)
            _, plan_media = validate_plan(plan, errors)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            errors.append(str(exc))

    html = args.html.read_text(encoding="utf-8") if args.html else None
    token_counts = {slot: count for slot, count in __import__("collections").Counter(TOKEN_RE.findall(html or "")).items()}
    assets_root_value = manifest.get("assets_root", ".")
    assets_root = Path(assets_root_value)
    if not assets_root.is_absolute():
        assets_root = (args.manifest.parent / assets_root).resolve()
    max_bytes = int(manifest.get("max_upload_bytes", 2_097_152))

    entries: list[tuple[str, dict[str, Any], bool]] = []
    cover = manifest.get("cover")
    if not isinstance(cover, dict):
        errors.append("缺少 cover object")
    else:
        entries.append(("cover", cover, True))
    slots = manifest.get("slots")
    if not isinstance(slots, list):
        errors.append("slots 必须是 array")
        slots = []
    for entry in slots:
        if isinstance(entry, dict):
            entries.append((str(entry.get("id", "")), entry, False))
        else:
            errors.append("slots 中存在非 object 项")

    seen: set[str] = set()
    lock_assets: list[dict[str, Any]] = []
    for slot, entry, is_cover in entries:
        if not SLOT_RE.fullmatch(slot):
            errors.append(f"无效 slot id：{slot!r}")
            continue
        if slot in seen:
            errors.append(f"重复 slot id：{slot}")
        seen.add(slot)
        target = entry.get("target")
        if target not in TARGETS or (is_cover and target != "cover"):
            errors.append(f"{slot} 的 target 无效：{target!r}")
        for field in ("file", "placement", "layout"):
            if not str(entry.get(field, "")).strip():
                errors.append(f"{slot} 缺少 {field}")
        if not is_cover and not str(entry.get("alt", "")).strip():
            errors.append(f"{slot} 缺少 alt")

        relative = Path(str(entry.get("file", "")))
        path = relative if relative.is_absolute() else assets_root / relative
        path = path.resolve()
        if not path.is_file():
            errors.append(f"{slot} 图片不存在：{path}")
            continue
        info = image_info(path)
        if not info:
            errors.append(f"{slot} 不是支持的 PNG/JPEG/GIF/WebP：{path}")
            continue
        if info["size"] > max_bytes:
            errors.append(f"{slot} 为 {info['size']} 字节，超过 {max_bytes}；请生成独立压缩副本")
        expected_ratio = entry.get("expected_ratio")
        if expected_ratio is not None and info.get("width") and info.get("height"):
            actual = info["width"] / info["height"]
            tolerance = float(entry.get("ratio_tolerance", 0.1))
            if abs(actual - float(expected_ratio)) > tolerance:
                errors.append(f"{slot} 宽高比 {actual:.3f} 不符合 {expected_ratio}±{tolerance}")
        elif expected_ratio is not None:
            warnings.append(f"{slot} 无法读取尺寸，未检查宽高比")

        expected = 0 if is_cover else int(entry.get("expected_occurrences", 1))
        if html is not None and token_counts.get(slot, 0) != expected:
            errors.append(f"{slot} token 出现 {token_counts.get(slot, 0)} 次，预期 {expected} 次")
        if plan is not None and not is_cover and slot not in plan_media:
            errors.append(f"{slot} 未出现在 article plan 的 media 中")
        plan_item = plan_media.get(slot, {})
        placements.append({
            "order": len(placements) + 1,
            "slot": slot,
            "file": str(path),
            "dimensions": [info.get("width"), info.get("height")],
            "placement": entry.get("placement"),
            "anchor": plan_item.get("anchor"),
            "purpose": plan_item.get("purpose"),
            "target": target,
            "layout": entry.get("layout"),
            "caption": entry.get("caption", ""),
            "alt": entry.get("alt", ""),
        })
        lock_assets.append({
            "slot": slot,
            "kind": "cover" if is_cover else "inline",
            "sha256": sha256_file(path),
            "size": info["size"],
            "format": info["format"],
            "width": info.get("width"),
            "height": info.get("height"),
        })

    if plan is not None:
        for slot in plan_media:
            if slot not in seen:
                errors.append(f"article plan 的 {slot} 没有对应图片清单项")
    if html is not None:
        for slot in token_counts:
            if slot not in seen:
                errors.append(f"HTML 出现未知图片 token：{slot}")

    lock = {
        "version": 1,
        "manifest_sha256": sha256_bytes(manifest_raw),
        "plan_sha256": sha256_bytes(plan_raw) if plan_raw else None,
        "html_sha256": sha256_file(args.html) if args.html else None,
        "assets": sorted(lock_assets, key=lambda item: item["slot"]),
    }
    lock_bytes = json.dumps(lock, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    report = {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "slots": len(entries),
            "body_slots": len(slots),
            "tokens": sum(token_counts.values()),
            "source_blocks": sum(len(section.get("blocks", [])) for section in (plan or {}).get("sections", [])),
        },
        "lock_sha256": sha256_bytes(lock_bytes),
        "placements": placements,
    }
    if args.write_lock and not errors:
        args.write_lock.write_text(json.dumps(lock, ensure_ascii=False, indent=2), encoding="utf-8")
        report["lock_file"] = str(args.write_lock)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
