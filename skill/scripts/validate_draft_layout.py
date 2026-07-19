#!/usr/bin/env python3
"""Validate WeChat draft metadata and mobile paragraph typography."""
from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path


TITLE_LIMIT_BYTES = 64
BODY_FONT_RANGE = (15.0, 18.0)
BODY_LINE_HEIGHT_RANGE = (1.65, 2.20)
BODY_MARGIN_RANGE = (12.0, 28.0)
POETRY_LINE_HEIGHT_RANGE = (1.90, 2.40)
INDENT_TOKEN = "__WECHAT_INDENT_2EM__"


def css_map(style: str) -> dict[str, str]:
    result = {}
    for declaration in style.split(";"):
        key, separator, value = declaration.partition(":")
        if separator:
            result[key.strip().lower()] = value.strip().lower()
    return result


def css_number(value: str | None, unit: str = "") -> float | None:
    if not value:
        return None
    if value.strip() in {"0", "+0", "-0"}:
        return 0.0
    match = re.fullmatch(r"(-?\d+(?:\.\d+)?)" + re.escape(unit), value.strip())
    return float(match.group(1)) if match else None


def margin_bottom(style: dict[str, str]) -> float | None:
    direct = css_number(style.get("margin-bottom"), "px")
    if direct is not None:
        return direct
    shorthand = style.get("margin")
    if not shorthand:
        return None
    parts = shorthand.split()
    values = [css_number(part, "px") for part in parts]
    if any(value is None for value in values):
        return None
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return values[0]
    if len(values) in {3, 4}:
        return values[2]
    return None


class ParagraphParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paragraphs: list[dict] = []
        self.stack: list[dict] = []
        self.br_run = 0
        self.max_br_run = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br":
            self.br_run += 1
            self.max_br_run = max(self.max_br_run, self.br_run)
            return
        self.br_run = 0
        if tag in {"p", "h1", "h2", "h3", "h4"}:
            record = {
                "tag": tag,
                "attrs": dict(attrs),
                "parts": [],
                "indent_spacer": False,
                "line": self.getpos()[0],
            }
            self.stack.append(record)
        elif tag == "span" and self.stack:
            style = css_map(dict(attrs).get("style") or "")
            width = css_number(style.get("width"), "em")
            if style.get("display") == "inline-block" and width is not None:
                if 1.9 <= width <= 2.1:
                    self.stack[-1]["indent_spacer"] = True

    def handle_endtag(self, tag: str) -> None:
        self.br_run = 0
        if self.stack and self.stack[-1]["tag"] == tag:
            self.paragraphs.append(self.stack.pop())

    def handle_data(self, data: str) -> None:
        self.br_run = 0
        for record in self.stack:
            record["parts"].append(data)


def validate(
    metadata: dict,
    html_text: str,
    source_text: str | None,
    mode: str,
) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    full_title = str(metadata.get("title", ""))
    draft_title = metadata.get("draft_title")
    effective_title = str(draft_title if draft_title is not None else full_title)

    if not full_title.strip():
        errors.append("metadata.title 不能为空")
    if full_title != full_title.strip():
        errors.append("metadata.title 含首尾空格")
    if draft_title is not None and str(draft_title) != str(draft_title).strip():
        errors.append("metadata.draft_title 含首尾空格")
    if len(full_title.encode("utf-8")) > TITLE_LIMIT_BYTES and not draft_title:
        errors.append(
            f"完整标题为 {len(full_title.encode('utf-8'))} 字节，超过 {TITLE_LIMIT_BYTES}；"
            "必须提供合规的 draft_title，正文标题仍保留完整原题"
        )
    effective_bytes = len(effective_title.encode("utf-8"))
    if effective_bytes > TITLE_LIMIT_BYTES:
        errors.append(
            f"实际草稿标题为 {effective_bytes} 字节，超过 {TITLE_LIMIT_BYTES}：{effective_title}"
        )
    if not effective_title.strip():
        errors.append("实际草稿标题不能为空")

    parser = ParagraphParser()
    parser.feed(re.sub(r"(?i)&emsp;\s*&emsp;", INDENT_TOKEN, html_text))
    if parser.max_br_run >= 2 or re.search(r"(?:<br\s*/?>\s*){2,}", html_text, re.I):
        errors.append("HTML 含连续两个及以上 <br>，请用段距而不是空行制造留白")

    body_candidates = 0
    for record in parser.paragraphs:
        text = "".join(record["parts"])
        has_entity_indent = text.startswith(INDENT_TOKEN)
        has_spacer_indent = bool(record["indent_spacer"])
        text_without_indent = text.removeprefix(INDENT_TOKEN)
        if has_spacer_indent:
            text_without_indent = text_without_indent.removeprefix("\u00a0")
        visible = re.sub(r"\s+", " ", text_without_indent)
        if not visible.strip():
            errors.append(f"第 {record['line']} 行存在空的 <{record['tag']}>")
            continue
        if (
            text_without_indent != text_without_indent.strip()
            or text_without_indent.startswith("\u3000")
            or text_without_indent.endswith("\u3000")
        ):
            errors.append(f"第 {record['line']} 行段落含首尾空格或全角空格")
        if record["tag"] != "p":
            continue
        style = css_map(record["attrs"].get("style") or "")
        centered = style.get("text-align") == "center"
        font_size = css_number(style.get("font-size"), "px")
        likely_body = len(visible.strip()) >= 24 and not centered
        likely_poetry = (
            centered
            and len(visible.strip()) <= 80
            and font_size is not None
            and font_size >= BODY_FONT_RANGE[0]
            and (mode == "poetry" or "<br>" in "".join(record["parts"]))
        )
        if not likely_body and not likely_poetry:
            continue
        body_candidates += 1
        line_height = css_number(style.get("line-height"))
        gap = margin_bottom(style)

        if font_size is None:
            warnings.append(f"第 {record['line']} 行正文未设置 px 字号")
        elif not BODY_FONT_RANGE[0] <= font_size <= BODY_FONT_RANGE[1]:
            warnings.append(
                f"第 {record['line']} 行正文字号 {font_size:g}px，建议 "
                f"{BODY_FONT_RANGE[0]:g}-{BODY_FONT_RANGE[1]:g}px"
            )

        expected_height = POETRY_LINE_HEIGHT_RANGE if likely_poetry else BODY_LINE_HEIGHT_RANGE
        if line_height is None:
            warnings.append(f"第 {record['line']} 行正文未设置无单位行高")
        elif not expected_height[0] <= line_height <= expected_height[1]:
            warnings.append(
                f"第 {record['line']} 行行高 {line_height:g}，建议 "
                f"{expected_height[0]:g}-{expected_height[1]:g}"
            )

        if gap is None:
            warnings.append(f"第 {record['line']} 行正文未设置明确的段后距")
        elif not BODY_MARGIN_RANGE[0] <= gap <= BODY_MARGIN_RANGE[1]:
            warnings.append(
                f"第 {record['line']} 行段后距 {gap:g}px，建议 "
                f"{BODY_MARGIN_RANGE[0]:g}-{BODY_MARGIN_RANGE[1]:g}px；"
                "若由外层卡片提供间距可人工复核"
            )

        if likely_body and style.get("text-align") not in {"justify", "left"}:
            warnings.append(f"第 {record['line']} 行长正文建议使用 justify 或 left 对齐")
        if likely_body and mode != "poetry":
            indent = css_number(style.get("text-indent"), "em")
            lead_exception = record["attrs"].get("data-typography") == "lead"
            if lead_exception:
                if indent not in {None, 0.0} or has_entity_indent or has_spacer_indent:
                    warnings.append(f"第 {record['line']} 行卷首引文不应再做首行缩进")
            elif indent is None and not has_entity_indent and not has_spacer_indent:
                warnings.append(
                    f"第 {record['line']} 行普通正文未设置 2em 首行缩进；"
                    "API 回读会清除 text-indent/空白实体时可使用 2em 内联占位块"
                )
            elif indent is not None and not 1.9 <= indent <= 2.1:
                warnings.append(
                    f"第 {record['line']} 行首行缩进为 {indent:g}em，建议 2em"
                )

    if source_text is not None:
        if re.search(r"\n[ \t]+\n", source_text):
            errors.append("源稿含只由空格组成的空段")
        if re.search(r"\n{3,}", source_text):
            errors.append("源稿含连续两个以上空行")
        for line_no, line in enumerate(source_text.splitlines(), 1):
            if line and line != line.strip():
                errors.append(f"源稿第 {line_no} 行含首尾 ASCII 空格")
            if line.startswith("\u3000") or line.endswith("\u3000"):
                errors.append(f"源稿第 {line_no} 行含首尾全角空格")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "full_title_bytes": len(full_title.encode("utf-8")),
            "draft_title_bytes": effective_bytes,
            "paragraphs": len(parser.paragraphs),
            "body_candidates": body_candidates,
            "mode": mode,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="校验公众号标题字节数、段落空格与移动端排版参数"
    )
    parser.add_argument("metadata", type=Path, help="含 title/draft_title 的 JSON")
    parser.add_argument("html", type=Path, help="待发布 HTML")
    parser.add_argument("--source", type=Path, help="可选：规范化 Markdown/纯文本源稿")
    parser.add_argument(
        "--mode", choices=["prose", "poetry", "mixed"], default="prose"
    )
    parser.add_argument(
        "--strict-warnings", action="store_true", help="将排版警告视为失败"
    )
    args = parser.parse_args()
    metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
    report = validate(
        metadata,
        args.html.read_text(encoding="utf-8"),
        args.source.read_text(encoding="utf-8") if args.source else None,
        args.mode,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["ok"] or (args.strict_warnings and report["warnings"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
