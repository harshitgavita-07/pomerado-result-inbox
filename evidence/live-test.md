# Hosted API evidence, October 29, 2026

Public read-only Goodreads tool, anonymous/keyless, no personal data or website write.

| Check | Observed |
|---|---|
| Catalog | HTTP 200, tool effect `read`, book_id accepts numeric string |
| Empty input | failed, `input_rejected`, `possible_commit: false` |
| Corrected input | public book_id `5907`; succeeded |
| Status-only read before capture | `result_status: available`, `result: null` |
| Client capture | `captured`; atomic raw JSON spool and SHA-256 in local SQLite |
| Status-only read after capture | `result_status: delivered`, `result: null` |
| Local result read | title The Hobbit, or There and Back Again; author J.R.R. Tolkien; book_id5907 |

The recorded remote job IDs and complete result are kept out of this public proof. The public test does not disclose a private dashboard, account, login, API key or single-use capability. Goodreads' full synopsis is not republished. The test was run once for valid input plus one rejected malformed input, not as a load test.

Do not treat this one run as a reliability benchmark or a demonstration of permanent crash safety. Deterministic tests separately inject failures at local boundaries. Files and signed webhooks have fixture tests only.
