#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import posixpath
import re
import sys
import urllib.parse
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
V = "urn:schemas-microsoft-com:vml"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"w": W, "r": R, "a": A, "wp": WP, "v": V}
SUPPORTED_MIME = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
}
CARD_RE = re.compile(r"【插图】.*?【/插图】", re.S)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_stem(name: str) -> str:
    stem = Path(name).stem or "image"
    stem = re.sub(r"[^\w.-]+", "-", stem, flags=re.UNICODE).strip("-._")
    return stem[:48] or "image"


def sniff_image(data: bytes) -> tuple[str, str] | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg", "jpg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif", "gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None


def image_card(file_value: str, alt: str = "", constraint: str = "固定") -> str:
    return (
        "\n\n【插图】\n"
        f"文件：{file_value}\n"
        "位置：此处\n"
        "样式：自动\n"
        "裁剪：自动\n"
        f"替代文字：{alt.strip()}\n"
        f"约束：{constraint}\n"
        "【/插图】\n\n"
    )


class Ingestor:
    def __init__(self, source: Path, output_dir: Path, max_image_bytes: int):
        self.source = source.resolve()
        self.output_dir = output_dir.resolve()
        self.assets_dir = self.output_dir / "assets"
        self.max_image_bytes = max_image_bytes
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.assets: dict[str, dict[str, Any]] = {}

    def save_asset(
        self,
        data: bytes,
        *,
        hint: str,
        origin: str,
        location: str,
        declared_mime: str | None = None,
    ) -> str:
        if len(data) > self.max_image_bytes:
            self.errors.append(
                f"图片超过摄取限制 {self.max_image_bytes} 字节：{origin} ({len(data)} 字节)"
            )
        detected = sniff_image(data)
        if not detected:
            suffix = Path(hint).suffix.lower().lstrip(".") or "bin"
            self.warnings.append(f"图片格式需后续转换或人工检查：{origin} ({suffix})")
            mime, extension = declared_mime or "application/octet-stream", suffix
        else:
            mime, extension = detected
            if declared_mime and declared_mime.lower() in SUPPORTED_MIME:
                expected = SUPPORTED_MIME[declared_mime.lower()]
                if expected != extension:
                    self.errors.append(
                        f"声明 MIME 与图片字节不一致：{origin} ({declared_mime} vs {mime})"
                    )
        digest = sha256_bytes(data)
        filename = f"{safe_stem(hint)}-{digest[:12]}.{extension}"
        relative = Path("assets") / filename
        destination = self.output_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if destination.read_bytes() != data:
                self.errors.append(f"哈希命名冲突：{destination}")
        else:
            destination.write_bytes(data)
        record = self.assets.setdefault(
            digest,
            {
                "file": relative.as_posix(),
                "sha256": digest,
                "size": len(data),
                "mime": mime,
                "origins": [],
            },
        )
        record["origins"].append({"source": origin, "location": location})
        return relative.as_posix()

    def external_asset(self, url: str, location: str) -> str:
        digest = sha256_bytes(url.encode("utf-8"))
        self.assets.setdefault(
            f"external:{digest}",
            {
                "url": url,
                "kind": "external",
                "sha256": None,
                "origins": [{"source": url, "location": location}],
            },
        )
        return url

    def resolve_markdown_image(self, target: str, alt: str, location: str) -> str:
        target = target.strip()
        if target.startswith("<") and target.endswith(">"):
            target = target[1:-1]
        data_match = re.match(r"^data:([^;,]+);base64,(.*)$", target, re.I | re.S)
        if data_match:
            mime = data_match.group(1).lower()
            if mime not in SUPPORTED_MIME:
                self.errors.append(f"不支持的 Base64 图片 MIME：{mime} ({location})")
                return image_card(f"UNRESOLVED:{location}", alt)
            payload = re.sub(r"\s+", "", data_match.group(2))
            try:
                data = base64.b64decode(payload, validate=True)
            except (binascii.Error, ValueError) as exc:
                self.errors.append(f"Base64 图片解码失败：{location}: {exc}")
                return image_card(f"UNRESOLVED:{location}", alt)
            relative = self.save_asset(
                data,
                hint=f"clip-{location.replace(':', '-')}.{SUPPORTED_MIME[mime]}",
                origin="markdown-base64",
                location=location,
                declared_mime=mime,
            )
            return image_card(relative, alt)
        if re.match(r"^https?://", target, re.I):
            return image_card(self.external_asset(target, location), alt)
        decoded = urllib.parse.unquote(target)
        candidate = Path(decoded)
        if not candidate.is_absolute():
            candidate = self.source.parent / candidate
        candidate = candidate.resolve()
        if not candidate.is_file():
            self.errors.append(f"Markdown 本地图片不存在：{target} ({location})")
            return image_card(f"UNRESOLVED:{target}", alt)
        data = candidate.read_bytes()
        relative = self.save_asset(
            data,
            hint=candidate.name,
            origin=str(candidate),
            location=location,
        )
        return image_card(relative, alt)

    def ingest_markdown(self) -> str:
        text = self.source.read_text(encoding="utf-8-sig")
        definitions: dict[str, str] = {}
        definition_lines: dict[str, str] = {}
        definition_re = re.compile(r"^\s*\[([^\]]+)\]:\s*(\S+)\s*$", re.M)
        for match in definition_re.finditer(text):
            definitions[match.group(1).casefold()] = match.group(2)
            definition_lines[match.group(1).casefold()] = match.group(0)

        consumed_definitions: set[str] = set()

        def replace_reference(match: re.Match[str]) -> str:
            alt, key = match.group(1), match.group(2).casefold()
            target = definitions.get(key)
            if not target:
                self.errors.append(f"Markdown 图片引用未定义：{match.group(2)}")
                return match.group(0)
            consumed_definitions.add(key)
            line = text.count("\n", 0, match.start()) + 1
            return self.resolve_markdown_image(target, alt, f"line:{line}")

        text = re.sub(r"!\[([^\]]*)\]\[([^\]]+)\]", replace_reference, text)
        for key in consumed_definitions:
            text = text.replace(definition_lines[key], "")

        def replace_inline(match: re.Match[str]) -> str:
            alt, target = match.group(1), match.group(2).strip()
            if not target.lower().startswith("data:"):
                title_match = re.match(r'^(<[^>]+>|\S+)\s+["\'].*["\']$', target)
                if title_match:
                    target = title_match.group(1)
            line = text.count("\n", 0, match.start()) + 1
            return self.resolve_markdown_image(target, alt, f"line:{line}")

        text = re.sub(r"!\[([^\]]*)\]\(([^)\n]+)\)", replace_inline, text)

        def replace_html(match: re.Match[str]) -> str:
            tag = match.group(0)
            src_match = re.search(r"\bsrc\s*=\s*([\"'])(.*?)\1", tag, re.I | re.S)
            if not src_match:
                self.errors.append("HTML img 缺少可解析的 src")
                return tag
            alt_match = re.search(r"\balt\s*=\s*([\"'])(.*?)\1", tag, re.I | re.S)
            alt = alt_match.group(2) if alt_match else ""
            line = text.count("\n", 0, match.start()) + 1
            return self.resolve_markdown_image(src_match.group(2), alt, f"line:{line}")

        return re.sub(r"<img\b[^>]*>", replace_html, text, flags=re.I | re.S)

    def docx_relationships(self, archive: zipfile.ZipFile) -> dict[str, dict[str, str]]:
        root = ET.fromstring(archive.read("word/_rels/document.xml.rels"))
        relationships = {}
        for rel in root.findall(f"{{{PKG_REL}}}Relationship"):
            relationships[rel.attrib["Id"]] = {
                "target": rel.attrib.get("Target", ""),
                "mode": rel.attrib.get("TargetMode", ""),
                "type": rel.attrib.get("Type", ""),
            }
        return relationships

    def extract_docx_image(
        self,
        archive: zipfile.ZipFile,
        relationships: dict[str, dict[str, str]],
        rid: str,
        alt: str,
        location: str,
    ) -> str:
        relationship = relationships.get(rid)
        if not relationship:
            self.errors.append(f"Word 图片关系不存在：{rid} ({location})")
            return image_card(f"UNRESOLVED:{rid}", alt)
        target = relationship["target"]
        if relationship["mode"].lower() == "external":
            if re.match(r"^https?://", target, re.I):
                return image_card(self.external_asset(target, location), alt)
            self.errors.append(f"Word 外链图片不是 HTTP(S)：{target}")
            return image_card(f"UNRESOLVED:{target}", alt)
        archive_name = posixpath.normpath(posixpath.join("word", target.replace("\\", "/")))
        if not archive_name.startswith("word/") or "../" in archive_name:
            self.errors.append(f"Word 图片路径越界：{target}")
            return image_card(f"UNRESOLVED:{target}", alt)
        try:
            info = archive.getinfo(archive_name)
        except KeyError:
            self.errors.append(f"Word 图片文件缺失：{archive_name}")
            return image_card(f"UNRESOLVED:{archive_name}", alt)
        if info.file_size > self.max_image_bytes:
            self.errors.append(
                f"Word 图片超过摄取限制 {self.max_image_bytes} 字节：{archive_name}"
            )
        data = archive.read(archive_name)
        relative = self.save_asset(
            data,
            hint=Path(archive_name).name,
            origin=f"docx:{archive_name}",
            location=location,
        )
        return image_card(relative, alt)

    def paragraph_markdown(
        self,
        paragraph: ET.Element,
        archive: zipfile.ZipFile,
        relationships: dict[str, dict[str, str]],
        paragraph_index: int,
    ) -> str:
        style_node = paragraph.find("./w:pPr/w:pStyle", NS)
        style = style_node.attrib.get(f"{{{W}}}val", "") if style_node is not None else ""
        doc_props = paragraph.findall(".//wp:docPr", NS)
        alts = [node.attrib.get("descr") or node.attrib.get("title") or "" for node in doc_props]
        alt_index = 0
        floating_rids = {
            node.attrib.get(f"{{{R}}}embed") or node.attrib.get(f"{{{R}}}link")
            for anchor in paragraph.findall(".//wp:anchor", NS)
            for node in anchor.findall(".//a:blip", NS)
        }
        pieces: list[str] = []
        seen_rids: set[str] = set()

        def walk(node: ET.Element, deleted: bool = False) -> None:
            nonlocal alt_index
            deleted = deleted or node.tag == f"{{{W}}}del"
            if not deleted and node.tag == f"{{{W}}}t" and node.text:
                pieces.append(node.text)
            elif not deleted and node.tag == f"{{{W}}}tab":
                pieces.append("\t")
            elif not deleted and node.tag in {f"{{{W}}}br", f"{{{W}}}cr"}:
                pieces.append("\n")
            elif not deleted and node.tag in {f"{{{A}}}blip", f"{{{V}}}imagedata"}:
                rid = (
                    node.attrib.get(f"{{{R}}}embed")
                    or node.attrib.get(f"{{{R}}}link")
                    or node.attrib.get(f"{{{R}}}id")
                )
                if rid and rid not in seen_rids:
                    seen_rids.add(rid)
                    alt = alts[alt_index] if alt_index < len(alts) else ""
                    alt_index += 1
                    location = f"paragraph:{paragraph_index}"
                    pieces.append(self.extract_docx_image(archive, relationships, rid, alt, location))
                    if rid in floating_rids:
                        self.warnings.append(
                            f"浮动 Word 图片 {rid} 已映射到所属段落 {paragraph_index}；页面坐标无法用于手机流式排版"
                        )
            for child in list(node):
                walk(child, deleted)

        walk(paragraph)
        content = "".join(pieces).strip()
        if not content:
            return ""
        heading_level = None
        style_lower = style.casefold()
        if "title" in style_lower or "标题" == style:
            heading_level = 1
        else:
            match = re.search(r"(?:heading|标题)\s*([1-6])", style, re.I)
            if match:
                heading_level = int(match.group(1))
        if heading_level and "【插图】" not in content:
            content = f"{'#' * heading_level} {content}"
        return content

    def table_markdown(
        self,
        table: ET.Element,
        archive: zipfile.ZipFile,
        relationships: dict[str, dict[str, str]],
        paragraph_counter: list[int],
    ) -> str:
        rows: list[list[str]] = []
        cards: list[str] = []
        for row in table.findall("./w:tr", NS):
            values = []
            for cell in row.findall("./w:tc", NS):
                parts = []
                for paragraph in cell.findall("./w:p", NS):
                    paragraph_counter[0] += 1
                    rendered = self.paragraph_markdown(
                        paragraph, archive, relationships, paragraph_counter[0]
                    )
                    found_cards = CARD_RE.findall(rendered)
                    if found_cards:
                        cards.extend(found_cards)
                        rendered = CARD_RE.sub("", rendered)
                        self.warnings.append(
                            f"表格单元格内图片已移动到表格之后：paragraph:{paragraph_counter[0]}"
                        )
                    if rendered.strip():
                        parts.append(rendered.strip())
                values.append("<br>".join(parts).replace("|", "\\|"))
            rows.append(values)
        if not rows:
            return ""
        width = max(len(row) for row in rows)
        rows = [row + [""] * (width - len(row)) for row in rows]
        lines = ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join(["---"] * width) + " |"]
        lines.extend("| " + " | ".join(row) + " |" for row in rows[1:])
        if cards:
            lines.extend(["", *cards])
        return "\n".join(lines)

    def ingest_docx(self) -> str:
        with zipfile.ZipFile(self.source) as archive:
            total_size = sum(info.file_size for info in archive.infolist())
            if total_size > 200 * 1024 * 1024:
                raise ValueError("DOCX 解压后超过 200 MB 安全上限")
            required = {"word/document.xml", "word/_rels/document.xml.rels"}
            missing = required.difference(archive.namelist())
            if missing:
                raise ValueError(f"DOCX 缺少必要部件：{sorted(missing)}")
            relationships = self.docx_relationships(archive)
            document = ET.fromstring(archive.read("word/document.xml"))
            body = document.find("w:body", NS)
            if body is None:
                raise ValueError("DOCX 没有 word body")
            blocks: list[str] = []
            paragraph_counter = [0]
            for child in list(body):
                if child.tag == f"{{{W}}}p":
                    paragraph_counter[0] += 1
                    rendered = self.paragraph_markdown(
                        child, archive, relationships, paragraph_counter[0]
                    )
                elif child.tag == f"{{{W}}}tbl":
                    rendered = self.table_markdown(
                        child, archive, relationships, paragraph_counter
                    )
                else:
                    rendered = ""
                if rendered.strip():
                    blocks.append(rendered.strip())
            return "\n\n".join(blocks) + "\n"

    def run(self, force: bool) -> dict[str, Any]:
        normalized_path = self.output_dir / "normalized.md"
        manifest_path = self.output_dir / "ingest-manifest.json"
        if not force and (normalized_path.exists() or manifest_path.exists()):
            raise FileExistsError("输出已存在；使用 --force 明确覆盖规范化文本和清单")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        suffix = self.source.suffix.lower()
        if suffix in {".doc", ".docm"}:
            raise ValueError(f"不接受 {suffix}；请先转换为无宏的 .docx")
        if suffix == ".docx":
            normalized = self.ingest_docx()
            source_format = "docx"
        elif suffix in {".md", ".markdown"}:
            normalized = self.ingest_markdown()
            source_format = "markdown"
        else:
            raise ValueError("仅支持 .docx、.md、.markdown")
        normalized_path.write_text(normalized, encoding="utf-8")
        manifest = {
            "version": 1,
            "source": str(self.source),
            "source_format": source_format,
            "source_sha256": sha256_bytes(self.source.read_bytes()),
            "normalized_file": normalized_path.name,
            "normalized_sha256": sha256_bytes(normalized.encode("utf-8")),
            "assets": sorted(self.assets.values(), key=lambda item: item.get("file", item.get("url", ""))),
            "warnings": self.warnings,
            "errors": self.errors,
            "stats": {
                "assets": len(self.assets),
                "image_cards": normalized.count("【插图】"),
                "base64_remaining": len(re.findall(r"data:image/[^;]+;base64,", normalized, re.I)),
            },
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="把 DOCX 或 Markdown 图文转换为统一排版输入")
    parser.add_argument("source", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-image-bytes", type=int, default=20 * 1024 * 1024)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if not args.source.is_file():
        print(json.dumps({"ok": False, "errors": [f"输入不存在：{args.source}"]}, ensure_ascii=False))
        return 1
    ingestor = Ingestor(args.source, args.output_dir, args.max_image_bytes)
    try:
        manifest = ingestor.run(args.force)
    except (OSError, ValueError, zipfile.BadZipFile, ET.ParseError) as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 1
    result = {
        "ok": not manifest["errors"],
        "normalized_file": str((args.output_dir / "normalized.md").resolve()),
        "manifest_file": str((args.output_dir / "ingest-manifest.json").resolve()),
        "stats": manifest["stats"],
        "warnings": manifest["warnings"],
        "errors": manifest["errors"],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
