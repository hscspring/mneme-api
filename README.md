# mneme-api

A standalone, persistent Add/Search API for conversational memory.

## Agent Memory Challenge release

This repository is the participant-hosted API wrapper for Mneme in the 2026
Agent Memory Challenge Textual track, Open-source Methods division. The fixed
submission is:

- [`mneme-api` v0.3.0](https://github.com/hscspring/mneme-api/tree/v0.3.0),
  commit [`6cd9420b612f52c8f78d5e973ae5d7cca6468003`](https://github.com/hscspring/mneme-api/commit/6cd9420b612f52c8f78d5e973ae5d7cca6468003)
- [`mnemekit` v0.10.1](https://github.com/FTP2026/Mneme/tree/v0.10.1),
  commit [`9d8d170ebf3575494c02ccb16378f60768b39a78`](https://github.com/FTP2026/Mneme/commit/9d8d170ebf3575494c02ccb16378f60768b39a78)
- Core method: Mneme5 directional successor recall (`ALG-DDR-1`)

The core method is authored and maintained in the
[`FTP2026/Mneme`](https://github.com/FTP2026/Mneme) repository. This wrapper
imports its published package without forking the retrieval algorithm. It adds
the challenge Add/Search contract, per-user persistence and isolation,
request-level idempotency and recovery, and token-exact evidence admission.

The memory path does not call an LLM, retrieval embedding model, vector
database, or learned reranker. It uses the fixed `en_core_web_sm==3.8.0` spaCy
pipeline for English POS tagging, lemmatization, named-entity recognition, and
dependency parsing. Chinese segmentation uses `jieba`. Both dependencies are
declared in `pyproject.toml` and locked in `requirements.lock`.

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

API 0.3 uses Mneme5 directional successor recall and identity-bound evidence
composition through `search_composed_evidence()`. Each result preserves complete
original messages with source identifiers, roles, and timestamps. Directly
activated evidence keeps its stable order; a strongly activated earlier episode
may contribute a bounded later successor before tail composition. The API fixes
`scope_owner="user"`, requests at most 100 items, and admits only whole evidence
whose rendered content keeps the response within 100,000 `o200k_base` tokens.

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
