# Validation rules

Run four independent gates: image plan, draft metadata/typography, layout source, and exact final HTML. Do not substitute a browser preview for deterministic checks.

## Draft metadata errors

- Compute title length with `len(title.encode("utf-8"))`, not Chinese character count.
- The effective WeChat draft title must be at most 64 UTF-8 bytes.
- When the complete literary title exceeds the limit, keep it unchanged in the article header and require a concise `draft_title`; show both titles and the exact byte count before approval.
- Any title change invalidates approval. Never discover the title limit only after uploading.

## Paragraph typography

Run `scripts/validate_draft_layout.py metadata.json article.html --source normalized.md`.

Block on empty `<p>` elements, leading/trailing ASCII or full-width spaces, whitespace-only paragraphs, two consecutive `<br>` elements, or more than one blank source line. Use CSS spacing instead of blank text.

For mobile prose, default to:

- body font size: 15-18 px, normally 16 px;
- unitless line height: 1.65-2.20, normally 1.85-1.95;
- paragraph bottom margin: 12-28 px, normally 16-20 px;
- `text-align:justify` or `left`; avoid forced justification for short lines;
- ordinary Chinese prose paragraphs use CSS `text-indent:2em` when the editor/API preserves it;
- if exact API readback proves that `text-indent`, leading whitespace entities, and whitespace-only spans are stripped, use a leading `<span style="padding-left:2em;">&#8203;</span>` as the final-HTML fallback and validate that version before approval;
- opening leads, headings, captions, labels, lists, quotations styled as cards, and poetry do not inherit prose indentation;
- never type two literal ASCII or full-width spaces to imitate indentation; use CSS or the verified 2em padding compatibility fallback.

For poetry, center only verse/stanza content, use 1.90-2.40 line height, and create 24-36 px stanza gaps with CSS. Do not apply prose indentation. Headings need more space above than below so they remain attached to the following paragraph.

Typography deviations are warnings when an outer callout/card supplies equivalent spacing. Record the manual decision in the preview checklist rather than silently ignoring it.

## Image plan errors

- Missing/duplicate slot IDs, files, or tokens.
- Unknown `{{IMAGE:*}}` tokens or unexpected occurrence counts.
- Cover missing, body alt/placement/layout missing, invalid image magic bytes, excessive file size, or aspect-ratio mismatch.
- Manifest/lock mismatch after approval.

## Layout errors

- Scripts, handlers, external fonts, ordinary HTML class/id, CSS variables, at-rules, grid, float, unsafe positioning, or editor-dependent layout.

## Final HTML errors

- Script/style/link/div, handlers, unsafe URLs/CSS, unsupported SVG, unresolved tokens/local URLs, or deployment byte-limit overflow.
- Missing leaf wrapping only when the chosen WeChat editor path requires it. Draft API payloads may omit editor-only leaf metadata.

## Warnings

- SVG/SMIL, click animation, `foreignObject`, filters, SVG ID references, half-width Chinese punctuation, aggressive crops, upscaling, or low-resolution assets.

Warnings require an explicit mobile-preview checklist; they do not become hidden errors.
