# mnemekit 0.6.0 deployment

Date: 2026-10-05 UTC

The API was upgraded to `mneme-api 0.1.11` and the published
`mnemekit 0.6.0` package. Local and deployed API suites each passed all five
tests. The service remained stopped while production Stores were migrated.

## Production migration

All 119 current generations were migrated serially in separate processes.
Schema verification reopened every current generation with mnemekit 0.6.0 and
reported 119 current Stores and zero legacy Stores.

| Metric | Result |
| --- | ---: |
| Stores | 119 |
| Total schema-v1 bytes | 475,471,872 |
| Total schema-v2 bytes | 2,552,741,888 |
| Maximum migration RSS | 842.8 MiB |
| Maximum legacy load | 280.536 s |
| Maximum migration write | 41.632 s |

The known largest Store grew from 39,067,648 to 226,762,752 bytes. Its legacy
load took 133.477 seconds, migration write took 41.632 seconds, and peak RSS was
842.8 MiB.

One request left pending by the earlier interrupted service was recovered by the
normal journal replay path. Recovery completed in 149.856 seconds and the final
production check reported zero pending requests.

The migration initially ran as root, so newly replaced SQLite files inherited
root ownership. Initial platform Add retries returned 503 with SQLite's
`attempt to write a readonly database`. Ownership was restored recursively to
the service account, and a `BEGIN IMMEDIATE` plus rollback write probe passed as
that account. Subsequent platform Add calls returned 200 without restarting the
service.

## Deployment validation

- Internal and public Health returned HTTP 200.
- A targeted Search against the largest migrated Store returned HTTP 200 in
  4.914 seconds with five evidence items.
- The service started at about 129 MiB RSS and stabilized near 485 MiB while the
  resumed evaluation was active.
- No legacy Stores or pending journal requests remained before Full resumed.

Full task `teval_9abcb4ed9849697f` resumed as attempt 6 using the existing
checkpoint, so it did not consume another Full submission. After retry backoff,
progress advanced from 2,615 to 2,616 completed units with no task-level error.
