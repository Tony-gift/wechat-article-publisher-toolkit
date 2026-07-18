# WeChat Article Publisher Toolkit

A reusable Codex skill and a small HTTPS client for turning Markdown or DOCX manuscripts into validated WeChat draft articles.

## What is included

- `skill/` — the complete `wechat-article-publisher` skill, including ingestion, image directives, manifest validation, references, and examples.
- `mp_proxy/` — a session-reusing HTTPS client for a separately operated WeChat publishing proxy.
- `tools/publish_draft.py` — a generic command-line draft creator with deterministic image-token replacement and a SHA-256 upload cache.
- `examples/` — minimal article, plan, and image-manifest examples.

The repository intentionally contains no WeChat credentials, proxy endpoint, private CA certificate, upload cache, draft IDs, manuscripts, or personal photographs.

## Install

```bash
python -m venv .venv
python -m pip install -r requirements.txt
```

Copy `.env.example` values into your shell environment. Keep the real password and CA certificate outside the repository.

## Use the Codex skill

Copy `skill/` into your Codex skills directory under a name such as:

```text
wechat-article-publisher/
```

The skill ingests Markdown or DOCX, extracts embedded images, creates an article plan and image manifest, validates WeChat-compatible HTML, and gates draft creation behind explicit approval.

## Publish a validated draft

Create an HTML layout source containing semantic tokens:

```html
<img src="{{IMAGE:hero}}" alt="Members reading together">
```

Then run:

```bash
python tools/publish_draft.py \
  --title "Article title" \
  --html examples/article.html \
  --cover /path/to/cover.jpg \
  --image hero=/path/to/hero.jpg
```

The command:

1. validates the layout source;
2. reuses cached uploads by endpoint kind and SHA-256;
3. uploads the cover and inline images;
4. replaces tokens by semantic slot ID;
5. creates a WeChat draft and reads it back;
6. prints the draft media ID and verification report.

It never mass-sends or publishes an article.

## Security

See [SECURITY.md](SECURITY.md). The proxy server itself is not included; this repository contains only the client contract.

## License

No license has been granted yet. Add a license before redistributing or accepting external contributions.
