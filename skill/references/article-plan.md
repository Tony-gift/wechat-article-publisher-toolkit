# Article plan from raw materials

The user supplies prose and images. Build the plan internally before generating HTML.

## Canonical structure

```json
{
  "version": 1,
  "source": "manuscript.md",
  "title": "红楼社团年度小结",
  "draft_title": "红楼社团年度小结",
  "audience": "社团成员与校园读者",
  "tone": ["温暖", "克制", "有文学感"],
  "sections": [
    {
      "id": "intro",
      "heading": "因爱相聚，向暖而行",
      "blocks": [
        {"id": "intro-p01", "type": "paragraph", "text": "过去一年……"},
        {"id": "intro-p02", "type": "paragraph", "text": "从读书会到团建……"}
      ]
    }
  ],
  "media": [
    {
      "slot": "hero",
      "anchor": {"after_block": "intro-p02"},
      "purpose": "建立社团共同体氛围",
      "presentation": "full-width",
      "caption": "花影与书页之间"
    }
  ]
}
```

## Planning rules

- Store the complete source title in `title`. Add `draft_title` only when the WeChat list title must be shortened to fit the 64-byte UTF-8 limit; never overwrite the complete literary title.
- Preserve every substantive source block or explicitly mark it as merged, shortened, moved, or omitted with a reason.
- Assign stable section and block IDs before placing images.
- Use semantic anchors: `before_section`, `after_heading`, `before_block`, `after_block`, `gallery_in_section`, or a named SVG layer. Never use “image 3” or raw DOM indexes.
- Match images using visible subject, chronology, emotional role, orientation, resolution, and visual diversity.
- Distinguish editorial purpose: evidence, atmosphere, explanation, transition, comparison, gallery, long summary, or cover.
- Keep an image unassigned when the match is weak. Do not force every supplied image into the article.
- Present uncertain matches as alternatives in the storyboard before rendering.

## User-facing storyboard

Show prose, not JSON:

| Article position | Content anchor | Suggested image | Why it fits | Treatment | Confidence |
|---|---|---|---|---|---|

The user confirms this plan; the skill then creates tokens, HTML, derivatives, and upload mappings internally.
