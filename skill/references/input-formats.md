# DOCX and Markdown ingestion

Run:

```bash
python scripts/ingest_content.py input.docx --output-dir article-ingest
python scripts/ingest_content.py input.md --output-dir article-ingest
```

The command writes:

- `normalized.md`: source text with extracted images represented as Chinese inline image cards;
- `assets/`: deduplicated standalone image files named with content hashes;
- `ingest-manifest.json`: source hash, image hashes, original locations, warnings, and counts.

## DOCX

- Support `.docx` as OOXML without launching Word or executing macros.
- Preserve body paragraph order, common Heading/Title styles, simple tables, inline pictures, VML pictures, and tracked insertions while excluding tracked deletions.
- Convert each embedded picture at its paragraph anchor into `【插图】...【/插图】`.
- Place floating/anchored pictures at their owning paragraph and emit a warning because Word's page coordinates do not translate to mobile flow.
- Ignore headers, footers, comments, footnotes, and drawing-only decorative shapes unless the user explicitly asks to include them.
- Reject legacy `.doc`; convert it to `.docx` first. Do not accept `.docm` in this pipeline.

## Markdown

- Support standard `![alt](path)` images, reference images, and HTML `<img src="...">`.
- Resolve relative local paths from the Markdown file directory and copy bytes into the ingest `assets/` directory without modifying originals.
- Support ClipImage64-style `data:image/png;base64,...` (also JPEG/GIF/WebP). Decode with strict Base64 validation, verify image magic bytes, enforce size limits, and store a standalone file.
- Never put data URIs into preview HTML, the upload cache, or WeChat content.
- Keep HTTP(S) image references as external inputs for the later normalization/security gate; do not download them during ingestion.

## Safety and fidelity

- Default maximum decoded/embedded image size: 20 MB. The later WeChat derivative limit remains deployment-specific and is usually smaller.
- Deduplicate assets by SHA-256, not filename.
- Preserve explicit image order and location as fixed instructions. Warn for floating Word images, unsupported image formats, missing local files, and malformed Base64.
- Do not silently drop source paragraphs or images. Any unsupported object must appear in `warnings` or `errors`.
