# mneme-api

A standalone, persistent Add/Search API for conversational memory.

## Install and start

Python 3.11+ and Linux are required.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.lock
pip install -e '.[evaluation,test]'

export MNEME_DATA_DIR=/path/to/local/data
read -rsp 'API key: ' MNEME_API_KEY
export MNEME_API_KEY
uvicorn mneme_api.app:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

Use a local disk for `MNEME_DATA_DIR`. Both environment variables are required.
The command binds only to localhost; use an HTTPS reverse proxy for public access.

Run one Uvicorn worker. The service serializes memory operations and uses local
file locks to protect each user's data.

## Upgrade

In the deployment's existing virtual environment:

```bash
git pull --ff-only
python -m pip install --index-url https://pypi.org/simple -r requirements.lock
python -m pip install --index-url https://pypi.org/simple -e '.[evaluation,test]'
python -m pytest -q
```

Restart the service with its existing process manager while preserving
`MNEME_API_KEY` and `MNEME_DATA_DIR`, then verify Health, Add, and Search.
Do not change the deployed code or dependencies during an active evaluation.
API 0.3 pins `mnemekit==0.10.0`. Existing schema-3 generations remain readable
without modification, but their conservative evolution index must be built by
an explicit `Memory.migrate_store()` maintenance step before successor routing
is expected. New generations build the index incrementally from each Add batch.

## Authentication

`GET /health` is unauthenticated. `POST /add` and `POST /search` accept any of:

```text
Authorization: Bearer <MNEME_API_KEY>
Authorization: Token <MNEME_API_KEY>
X-Api-Key: <MNEME_API_KEY>
```

All three schemes use the same service key.

## Add

Request:

```json
{
  "request_id": "example:chunk:0",
  "user_id": "example:user:0",
  "session_id": "example:session:0",
  "messages": [
    {
      "role": "user",
      "content": "My dog Lucky is a golden retriever.",
      "timestamp": 1704067200000
    },
    {
      "role": "assistant",
      "content": "Lucky enjoys playing with a tennis ball.",
      "timestamp": 1704067201000
    }
  ]
}
```

A successful request returns HTTP 200 with `success: true` and the original
identifiers. Add returns only after the messages are stored and searchable.
Timestamps use Unix milliseconds; missing timestamps use the persisted request
receipt time.

Request IDs are scoped to users. Repeating an ID with the same validated payload
is idempotent. Reusing it with a different payload returns HTTP 409.

## Search

Request:

```json
{
  "user_id": "example:user:0",
  "query": "What breed is Lucky?",
  "top_k": 100
}
```

Response:

```json
{
  "data": [
    {
      "id": "...",
      "content": "...",
      "created_at": "..."
    }
  ]
}
```

Results are ordered by relevance. Content preserves source identifiers, UTC
timestamps, roles, and stored text. `created_at` is the earliest source timestamp
represented by the result. Optional `options` are accepted. No matches produce
`{"data": []}`.

API 0.3 uses Mneme4 identity-bound evidence composition followed by the bounded
Mneme5-candidate successor route. Each result is one
complete original message, and `top_k` is therefore an exact source-item limit.
The first ten activated sources retain their Mneme3 order; eligible evolution
and joint queries compose the remaining evidence for the per-user `user` scope.
The service admits only whole messages whose rendered evidence keeps the result
within 100,000 `o200k_base` tokens.

## Persistence and isolation

- Each `user_id` has a separate hashed data directory.
- Search accesses only the requested user's data.
- Messages preserve source order, role, timestamp, session, and request identity.
- A per-user SQLite journal records each accepted Add before the memory write.
- After an interrupted write, the next Add or Search rebuilds a new generation
  from the journal before making it active.
- Recovery failures return HTTP 503; partially written generations are not searched.
- Stored data is not deleted automatically. Retention is the operator's responsibility.

Each successful Search appends an operational record to
`MNEME_DATA_DIR/search-metrics.jsonl`. Metrics include result sizes and phase
latencies. They do not contain the query or stored memory text.

## Local verification

```bash
python -m pytest -q
```

Tests cover authentication, role preservation, user isolation, duplicate
requests, restart persistence, result limits, and interrupted-write recovery.
Test data remains under the ignored `.runtime/tests/` directory.

## Offline replay

Install the `evaluation` extra, start the API, and provide a JSONL request file:

```jsonl
{"operation":"add","request":{"request_id":"r1","user_id":"offline:run1","session_id":"s1","messages":[{"role":"user","content":"My dog Lucky is a golden retriever."}]}}
{"operation":"search","request":{"user_id":"offline:run1","query":"What breed is Lucky?","top_k":100}}
```

```bash
python evaluation/replay.py requests.jsonl responses.jsonl --base-url http://127.0.0.1:8000
```

The output path must not already exist. Use a fresh user namespace for each
independent replay. The tool records retrieval responses only.
