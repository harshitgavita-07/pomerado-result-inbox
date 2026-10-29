# Sources and existing work

Checked October 29, 2026.

- [YC company and launch](https://www.ycombinator.com/companies/pomerado): Fall 2026 company, product description and public team contact.
- [Product](https://www.pomerado.ai): integration minting and deterministic website workflows.
- [Keyless trial](https://docs.pomerado.ai/quickstart/try-without-a-key.md): public read-only runs without a key.
- [Job result lifecycle](https://docs.pomerado.ai/guides/jobs/wait-for-a-result.md): `include_result=false`, result expiry and first-delivery semantics.
- [Files](https://docs.pomerado.ai/guides/files/get-a-file.md): `$file` shape, no Authorization header, single-use links, hash and expiry.
- [Backend example](https://docs.pomerado.ai/examples/backend-application.md): baseline fetch/log and webhook usage; names existing features this project builds on.
- [Webhook protocol](https://docs.pomerado.ai/guides/notifications/webhooks.md): Standard Webhooks signatures, retries and event-ID deduplication.
- [Retries and idempotency](https://docs.pomerado.ai/guides/tools/retries-and-idempotency.md): retries do not restore consumed results, ambiguous website writes require reconciliation.
- [Public source](https://github.com/Pomerado/pomerado): inspected head `755ca9d0f771a38ac0b916b1f302beef3addf15a`. Open-source package is the integration minter/Guardian, not the hosted backend.
- [Active download work](https://github.com/Pomerado/pomerado/pull/580): collecting multiple downloads from a website trigger, a different stage from client consumption of hosted result links. This repo is not a replacement for that PR.

Limits of novelty: this is a small reference adapter assembled from established durable-inbox/outbox patterns. It does not establish that Pomerado has no internal durable client, nor does the public source establish the hosted service's full implementation. The behavior in the live test matches the published contract rather than violating it.
