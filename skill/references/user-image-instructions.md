# User-facing image instructions

Use inline cards as the preferred format because their physical location in the manuscript is the anchor. Users may leave fields blank for the Agent to infer.

## Quick form

```text
【插图：读书会合影.jpg｜样式：通栏｜图注：共读让相遇有了回声｜约束：固定】
```

Use this for one ordinary image. The image appears where the line is placed.

## Full card

```text
【插图】
文件：读书会合影.jpg
位置：此处
用途：对应上文读书会活动
样式：通栏
裁剪：保留全图
焦点：中间三位人物
图注：共读让相遇有了回声
替代文字：社团成员围坐共读
约束：固定
【/插图】
```

Supported card types:

- `封面`: message cover; not inserted into body.
- `插图`: one body image.
- `图组`: multiple ordered images; typically grid or horizontal gallery.
- `对比图`: before/after or front/back interactive layers.
- `长图`: expandable or ordinary long image.

## Fields

- `文件`: exact filename or image label assigned by the Agent. Multiple files use Chinese commas.
- `位置`: normally `此处`. If a centralized list is unavoidable, use `在“原文短句”之后` or `某节标题之后`, not paragraph numbers.
- `用途`: editorial reason for the image.
- `样式`: `自动`, `通栏`, `卡片`, `左右并排`, `横滑`, `九宫格`, `点击切换`, or `点击展开`.
- `裁剪`: `自动`, `保留全图`, an aspect ratio, or a precise crop request.
- `焦点`: subject that must remain visible during cropping.
- `图注`: visible caption; write `无` to explicitly omit it.
- `替代文字`: optional accessibility text; the Agent generates it when omitted.
- `约束`: `固定` means do not change without asking; `可调整` means optimize as needed.

## Central table fallback

Use only when inline editing is inconvenient:

| 文件 | 位置锚点 | 样式 | 裁剪/焦点 | 图注 | 约束 |
|---|---|---|---|---|---|
| 读书会.jpg | 在“第一次共读活动”段后 | 通栏 | 保留全图 | 共读时刻 | 固定 |

## Resolution priority

1. Inline fixed card.
2. Fixed centralized-table instruction anchored by quoted text/heading.
3. Inline adjustable card.
4. General natural-language preference.
5. Agent inference.

Report conflicts instead of guessing. If an image filename is unclear, first number the supplied images and show a contact sheet or inventory table so the user can refer to `图01`, `图02`, and so on.
