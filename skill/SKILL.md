---
name: wechat-article-publisher
description: Turn a user's raw manuscript and own images—including DOCX, Markdown, local image references, and ClipImage64 Base64 images—into a planned, styled, validated WeChat article; assign explicit image positions, process/cache images, and create drafts through the WeChat Draft API. Use for 用户拿 Word/Markdown/图文素材寻求公众号排版、图片位置规划、自动排版、SVG/SMIL 检查、图片缓存及草稿箱提交。Never upload or create a draft before explicit approval; never publish or mass-send.
---

# WeChat Article Publisher

Treat publishing as a deterministic content pipeline. The normal input is raw text plus images, not HTML. Do not require users to write markup, slot tokens, or manifests. Do not require npm, a browser extension, DOM injection, or a particular editor UI.

## Input contract

Accept any practical content package:

- text pasted in chat, UTF-8 Markdown/plain text, or `.docx`;
- a folder or attachments containing the user's images;
- optional title, audience, tone, brand colors, desired interactions, and draft metadata.
- optional inline image instruction cards written directly between the intended paragraphs.

If the user provides only text and images, infer a sensible article structure and image plan. Ask only when a missing choice materially changes meaning, image ownership, or publication metadata.

Create these internal artifacts; do not ask the user to author them:

1. `article-plan.json`: normalized title, lead, sections, paragraph/block IDs, callouts, and image placements.
2. `image-manifest.json`: exact files, derivatives, semantic slot IDs, alt text, crop/layout rules, and hashes.
3. layout-source HTML containing internal `{{IMAGE:slot-id}}` tokens.
4. validated final HTML containing local preview paths or WeChat-hosted URLs.

Read [references/article-plan.md](references/article-plan.md) when converting raw material into the internal content plan.
When the user wants to specify image positions, prefer the fillable syntax in [references/user-image-instructions.md](references/user-image-instructions.md) and copy [assets/image-placement-form.md](assets/image-placement-form.md) for them. Treat these instructions as user input, then normalize them into the internal article plan.

For `.docx` or `.md`, read [references/input-formats.md](references/input-formats.md) and run `scripts/ingest_content.py`. The ingest output must be `normalized.md`, extracted image files, and `ingest-manifest.json`. Never carry Base64 data URIs into layout HTML.

## User-facing image instructions

Prefer an inline card placed exactly where the image should appear:

```text
【插图】
文件：读书会合影.jpg
样式：通栏
裁剪：保留全图
图注：共读让相遇有了回声
约束：固定
【/插图】
```

Allow omitted fields and infer sensible defaults. Use `约束：固定` for a hard requirement and `约束：可调整` for a preference. Support `插图`, `图组`, `对比图`, `长图`, and `封面`. Do not ask the user to reference paragraph numbers; the card's inline location is the primary anchor.
Run `scripts/parse_image_directives.py` to extract cards into stable markers before reorganizing the manuscript.

## Own-image-first policy

- Prefer images supplied by the user. Do not generate substitutes unless the user explicitly requests generation.
- Never overwrite originals. Put resized, cropped, compressed, or converted derivatives in a separate output directory.
- Inventory candidate files before layout: path, SHA-256, dimensions, aspect ratio, format, byte size, and orientation.
- Inspect image content and assign every selected image a stable semantic slot ID such as `cover`, `hero`, `activity-reading`, `gallery-02`, `compare-before`, or `long-summary`.
- Show the image placement table and preview before editing or uploading images.

## Explicit image placement

Generate a manifest as the source of truth, then generate exact tokens in internal layout-source HTML:

```html
<img src="{{IMAGE:hero}}" alt="社团成员共读">
<img src="{{IMAGE:compare-before}}" alt="活动筹备现场">
```

The user never needs to write these tokens. Do not identify images internally by DOM order, filenames alone, or “the third image.” A slot must declare its file, reader-facing placement, content anchor, target type, layout treatment, alt text, and expected occurrence count. Keep `cover` separate because it becomes a permanent-material `thumb_media_id` and does not appear as a body token.

Read [references/image-manifest.md](references/image-manifest.md) when creating or changing image placement. Start from [assets/image-manifest.example.json](assets/image-manifest.example.json). Run `scripts/validate_image_manifest.py` before rendering and write a lock file for approval.

## Required gates

### Gate 0: content and image plan

Block when:

- slot IDs or tokens are duplicated, missing, unknown, or used an unexpected number of times;
- a declared file is missing, not an image, exceeds the configured upload limit, or violates its required aspect ratio;
- a body slot lacks meaningful `placement`, `target`, `layout`, or `alt` metadata;
- a cover is missing;
- the manifest or image bytes changed after approval.

Also block when an image placement references an unknown section/block anchor, or when a paragraph/block from the source was silently dropped.

Report unused candidate images without blocking. Produce a placement table ordered by article position.

### Gate 1: layout source

Reject or remove external fonts/scripts, event handlers, ordinary HTML `class`/`id`, CSS variables, at-rules, grid, float, and `position:fixed|absolute|sticky`. Require inline-compatible structure that can survive WeChat sanitization.

### Gate 2: final HTML

Block scripts, stylesheets, `<style>`, `<link>`, `<div>`, event attributes, `javascript:` URLs, unsafe CSS/URL schemes, unsupported SVG, unresolved `{{IMAGE:*}}` tokens, unresolved local URLs, and deployment byte-limit violations. Validate Chinese leaf wrapping when the selected editor path requires it.

Warn for SVG/SMIL, `foreignObject`, click animation, filters, SVG IDs/references, and half-width Chinese punctuation. Require WeChat mobile verification for these warnings.

## Workflow

1. Ingest the raw manuscript without rewriting away meaning. For DOCX/Markdown, extract text and images with `scripts/ingest_content.py`; convert embedded images or Base64 data URIs into independent files and inline image cards. Parse image cards, preserve exact markers, then normalize sections and stable paragraph/block IDs; record source coverage.
2. Inventory and visually inspect the user's image folder without modifying it. Record file facts and a short content description.
3. Apply explicit user image instructions before inference. Resolve inline cards to adjacent block anchors; then match unspecified images by meaning, chronology, orientation, and quality. Create `article-plan.json` and `image-manifest.json` internally.
4. Show a reader-facing storyboard and placement table: article section, exact before/after block anchor, slot ID, thumbnail/file, dimensions, purpose, layout/crop, caption, alt text, and fixed/adjustable status. Resolve material ambiguity before layout. Never silently override a fixed card.
5. After the plan is accepted, create processed derivatives only where required. Preserve originals and record `source_file` plus derivative `file`.
6. Generate layout-source HTML and insert exact `{{IMAGE:slot-id}}` tokens at planned anchors. For SVG layers and CSS backgrounds, use the same slot ID convention.
7. Run content-coverage and manifest validation; write plan and image lock hashes. Stop on errors.
8. Validate draft metadata and typography with `scripts/validate_draft_layout.py`. Treat a draft title over 64 UTF-8 bytes as an error; preserve the full title in the article and require a separate approved `draft_title`. For Chinese prose, use CSS `text-indent:2em` when the target path preserves it; when verified API readback strips both that property and leading whitespace entities, use a leading inline-block span with `width:2em` and a nonbreaking-space payload as the WeChat-compatible fallback. Exempt headings, poetry, labels, and intentionally styled opening leads. Reject empty paragraphs, leading/trailing paragraph spaces, literal full-width indentation spaces, and repeated blank lines. Read [references/validation-rules.md](references/validation-rules.md) for prose and poetry spacing ranges.
9. Render a phone-width preview using local derivative paths. Run layout-source and final-HTML validation. Report title bytes, paragraph-spacing warnings, image/SVG counts, characters, UTF-8 bytes, errors, and warnings.
10. Build an immutable preview payload containing HTML, plan/manifest lock hashes, full title, effective draft title, title byte count, typography report, theme, digest, author, cover hash, and all draft settings. Hash it and require explicit approval. Approval expires after 30 minutes and any changed byte invalidates it.
11. After approval, open one authenticated proxy/API context and reuse its TLS session for health check, cache lookup, image upload, draft creation, and readback.
12. Cache uploads by `endpoint-kind + SHA-256`, never by filename. Keep cover `media_id` and inline-image URL caches separate. Save cache atomically after every successful upload.
13. Replace tokens by slot ID, not document order. Rewrite HTML `img`, SVG/XHTML images, and CSS backgrounds. Remove source-only markers and rerun Gate 2.
14. Create the draft with the effective `draft_title`, read it back, and verify title, image-host count, unresolved token count, local URL count, placeholder/debug-text count, and source-content coverage.
15. Return the draft `media_id`. Never publish, preview-send, or mass-send automatically.

## Cache behavior

- A cache hit requires the same endpoint kind and exact file SHA-256.
- Store filename, size, hash, created/last-used time, returned URL or `media_id`, and provenance. Never store credentials.
- Support cache inspection, selective refresh, full clear, and seeding from a verified existing draft.
- Persist each successful upload immediately so a later draft failure does not cause duplicate uploads.
- Treat a cached cover as invalid only when the API rejects its permanent `media_id`; then refresh that entry explicitly.

## Output contract

Return:

- source-content coverage, storyboard, ordered placement table, and plan/manifest lock hashes;
- exact preview and approval hashes;
- validation errors, warnings, image/SVG statistics, character count, and UTF-8 byte count;
- per-slot rewrite report with cache hit/miss and derivative used;
- actual upload count, cover `thumb_media_id`, and draft `media_id`;
- explicit manual checks for image crop/loading, captions, SVG/SMIL, click behavior, and mobile preview.
