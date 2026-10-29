# States and failure boundaries

```
pending -> receiving -> captured -> local offers -> local ack
                   -> pending (still-running response)
                   -> needs_attention (question, unknown, file)
                   -> failed / unavailable
                   -> uncertain (any unresolved read)
```

The exclusive SQLite transaction commits `receiving` before a remote read. Concurrent processes observe that claim and stop. No lease expiry allows another reader to consume a possibly delivered result. An operator must call recover. This sacrifices automatic liveness for an honest delivery boundary.

`responses/job-ID-attempt.json` is generated locally. Its bytes are flushed, renamed and directory-fsynced before SQLite references them. If the process stops between the file commit and SQLite update, recovery uses that exact attempt's filename. Partial and unrelated attempts are not selected. If bytes are absent, there is no guess and no automatic retry. The store checks remote job identity before using the body. A null JSON result is accepted only when the remote state explicitly says it was available.

File descriptors are held separately. The full descriptor set is validated before any download. Each file has an exclusive pre-download claim; size and SHA-256 must match before capture. No redirects, API credentials, server filenames or arbitrary hosts are used. Missing/incorrect local bytes stay uncertain. Completing some files does not imply completing the entire job.

A signed webhook is committed to the inbox before returning success to the HTTP handler. Unknown events are acknowledged and ignored; repeated IDs are deduplicated; the same ID with different content is rejected. The separate drain worker reuses the exclusive capture claim. This avoids the sample pattern of acknowledging a webhook and only then fetching/logging its read-once result with no durable work record. Webhook verification and worker behavior are fixture-tested, not deployed/live-tested.

Consumer offers persist a stable token before returning the captured result. A crash after applying an external effect but before ack can redeliver, so the consumer must dedupe with that token. An ack is scoped to consumer, job and exact token. Different consumers have independent progress.

Tests include real competing OS processes, subprocess hard exit, missing spool, corrupted bytes, malformed JSON, file URL policy, file crashes, duplicate/reordered webhook handling, and no-replay states. These tests are not proof against all power loss or filesystem faults.
