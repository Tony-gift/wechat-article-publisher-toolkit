# Validation rules

Run three independent gates: image plan, layout source, and exact final HTML. Do not substitute a browser preview for deterministic checks.

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
