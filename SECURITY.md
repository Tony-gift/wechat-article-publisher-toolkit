# Security

## Never commit

- `MP_PROXY_PASSWORD` or other credentials;
- private proxy URLs or usernames;
- private CA certificates or TLS keys;
- WeChat `media_id`, draft IDs, or upload caches;
- unpublished manuscripts or personal photographs.

The included `.gitignore` blocks common local secret and artifact files. Run a secret scan before every release.

## TLS

Use a trusted public certificate or supply a narrowly scoped CA certificate with `MP_PROXY_CA_CERT`. Do not disable TLS verification.

## Reporting

Report security issues privately to the repository owner rather than opening a public issue.
