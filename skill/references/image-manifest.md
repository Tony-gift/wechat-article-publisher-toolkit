# Image manifest

Use one manifest per article. Resolve relative paths from `assets_root`, which itself is resolved relative to the manifest file.

## Schema

```json
{
  "version": 1,
  "article": "article.html",
  "assets_root": ".",
  "max_upload_bytes": 2097152,
  "cover": {
    "id": "cover",
    "source_file": "photos/original-cover.jpg",
    "file": "processed/cover.jpg",
    "placement": "公众号消息封面，不进入正文",
    "target": "cover",
    "layout": "2.35:1 cover crop",
    "alt": ""
  },
  "slots": [
    {
      "id": "hero",
      "source_file": "photos/group.jpg",
      "file": "processed/hero.jpg",
      "placement": "导语之后、年度亮点之前",
      "target": "html-img",
      "layout": "full-width",
      "alt": "社团成员在园林中共读",
      "caption": "花影与书页之间",
      "expected_occurrences": 1,
      "expected_ratio": 1.5,
      "ratio_tolerance": 0.15
    }
  ]
}
```

## Slot rules

- `id`: stable semantic name using lowercase letters, digits, and hyphens.
- `file`: exact upload derivative. Use `source_file` to retain provenance when preprocessing occurred.
- `placement`: reader-facing article position, not a DOM index. Examples: “标题卡后、导语前”, “活动回顾横滑区第 2 张”, “协作对比交互的前景层”.
- `target`: one of `html-img`, `svg-image`, `svg-foreignobject`, `css-background`, or `cover`.
- `layout`: intended treatment such as `full-width`, `gallery-card`, `1:1 crop`, `compare-layer`, or `long-image`.
- `alt`: required for body images. Describe content, not the interaction implementation.
- `expected_occurrences`: defaults to 1. Set greater than 1 only for intentional reuse.
- `expected_ratio` and `ratio_tolerance`: optional numeric crop guard.

## Tokens

Use the exact token `{{IMAGE:slot-id}}` in source HTML:

```html
<img src="{{IMAGE:hero}}" alt="社团成员在园林中共读">
<foreignObject><img src="{{IMAGE:compare-after}}" alt="活动完成后的合影"></foreignObject>
<section style="background-image:url('{{IMAGE:paper-texture}}')"></section>
```

Tokens exist only in layout source. Local preview resolution replaces them with derivative paths; upload resolution replaces them with cached or newly returned WeChat URLs. Final HTML must contain no tokens.

## Placement review table

Before layout, show:

| Order | Slot | File/thumbnail | Dimensions | Placement | Target | Layout/crop | Caption/alt |
|---:|---|---|---:|---|---|---|---|

Do not proceed when “which image goes where” remains ambiguous.
