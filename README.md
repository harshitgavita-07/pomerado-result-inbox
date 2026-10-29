# Pomerado result inbox

A small backend boundary with a large consequence: a website run can succeed, its result can be delivered once, and the consumer can still crash before recording it.

Pomerado intentionally erases hosted results after delivery. This reference consumer moves the application side from `console.log(job.result)` to an fsynced local inbox with crash recovery and a downstream offer/ack ledger. It is **not a Pomerado bug fix, an official SDK, or an exactly-once delivery guarantee**.

## Real product test, not a hypothetical endpoint

On October 29, 2026, I exercised the hosted keyless read-only API against the public Goodreads book-details tool:

1. A malformed empty input was rejected, with `possible_commit: false`.
2. A corrected public book lookup succeeded. A status-only read showed `result_status: available` without consuming it.
3. This consumer saved the JSON response atomically. The remote job then showed `result_status: delivered`, `result: null`.
4. Local reads and downstream redelivery still worked without another remote result read.

The run returned The Hobbit by J.R.R. Tolkien, book ID 5907. No private website login, paid model key, or website write was used. See [evidence/live-test.md](evidence/live-test.md). The live result test covered JSON, **not a real single-use file download or a deployed webhook receiver**. File and webhook behavior is tested with deterministic fixtures.

## What is implemented

- SQLite WAL + FULL synchronous mode; exclusive claim before the destructive result read.
- Raw bytes written with file fsync, rename and directory fsync before marking captured.
- Restart recovery from the exact attempt's durable spool. An unresolved read becomes `uncertain`; it never silently retries or starts another website run.
- Local SHA-256 verification before downstream delivery; restrictive file modes.
- Independent consumer offer/ack ledgers. A repeated offer carries the same delivery token. Consumers must dedupe effects using that token.
- Single-use `$file` capture: explicitly configured download hosts, no API authorization forwarded, no redirects, public-address check, bounded response, size/hash validation, generated disk names rather than website-provided paths, and local recovery.
- Standard Webhooks signature verification, timestamp window, event-ID deduplication and durable enqueue **before** the handler acknowledges. Remote result fetch is a separate worker step.
- Fail-closed states for questions, unknown statuses, missing results, remote errors, expired results and incomplete downloads.
- No new runs, writes, answers, logins, cancellations, or automated replay of website actions.

## Try locally

Python 3.11+, Linux filesystem. No runtime dependencies.

```sh
python -m unittest discover -s tests -v
python -m pomerado_inbox --root .inbox status
# Use an existing job created by your own client/key:
python -m pomerado_inbox --root .inbox peek job_YOUR_32_HEX_ID
python -m pomerado_inbox --root .inbox capture job_YOUR_32_HEX_ID
python -m pomerado_inbox --root .inbox read job_YOUR_32_HEX_ID
python -m pomerado_inbox --root .inbox deliver job_YOUR_32_HEX_ID etl
# Only after committing/deduplicating the downstream effect:
python -m pomerado_inbox --root .inbox ack job_YOUR_32_HEX_ID etl DELIVERY_TOKEN
```

`POMERADO_API_KEY` is optional for keyless public jobs; use the same originating key for keyed jobs. Do not print or commit it. The placeholders above are intentionally invalid until replaced. `peek` uses `include_result=false`. There is no polling loop: honor the service's `Retry-After` if you schedule another read, or use signed webhooks.

After an interrupted capture:

```sh
python -m pomerado_inbox --root .inbox recover job_YOUR_32_HEX_ID
```

For a result held because it contains files, explicitly allow the actual operator-controlled file host after checking it against the service, not merely trusting a value in the result:

```sh
python -m pomerado_inbox --root .inbox files job_YOUR_32_HEX_ID --allow-host ACTUAL_DOWNLOAD_HOST
python -m pomerado_inbox --root .inbox recover-files job_YOUR_32_HEX_ID
```

The JSON job remains `needs_attention` when it contains files, even after capture. Inspect the per-file states. A file's `captured` state does not mean an application has processed its contents. The implementation does not expose a general-purpose file viewer, webhook HTTP server, or public endpoint.

## The honest limit

There is no atomic transaction spanning Pomerado's delivery acknowledgment and a consumer's local disk. If the remote side finishes delivery and this process dies before fsync, the result may be permanently lost. This tool records uncertainty and refuses to rerun the website operation. Closing that window needs an upstream retention/explicit-ack protocol, not a client claim of "exactly once."

Likewise, downstream effects must be idempotent or transactional with the consumer's acknowledgment. The local offer/ack ledger gives at-least-once redelivery until ack, not exactly-once external effects.

Local retention is a deliberate change from server-side deletion. The inbox is **not encrypted**, is not a multi-tenant service, has no retention scheduler, and requires an access-controlled disk and your own deletion/backup policy. Raw response spools can contain sensitive output and temporary file capability URLs. Never commit an inbox. Disk failure, malicious local writers and network-filesystem semantics are outside the durability guarantee. File DNS screening is defense in depth, not protection from adversarial DNS rebinding; use a fixed trusted download host and controlled egress. A job may expire before you capture it. HTTP failures conservatively become uncertain rather than being auto-retried.

## Where this fits

This addresses **hosted backend result consumption**, not local integration minting or browser download collection. Pomerado already has webhooks, idempotency keys, `include_result=false` and active download improvements. Generic durable queues can also solve much of this problem. This repo packages those application responsibilities around the actual read-once protocol and makes their failure boundary testable; it does not claim nobody else can do it or that the company lacks an internal solution.

[Design and state transitions](DESIGN.md) · [Sources and overlap](SOURCES.md)

AI-assisted implementation and tests. Independently exercised against the public hosted API. Not affiliated with Pomerado.
