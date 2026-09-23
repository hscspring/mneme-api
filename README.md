# mneme-api

A standalone Add/Search service for [Mneme](https://pypi.org/project/mnemekit/), compatible with the [Agent Memory Leaderboard API](https://agentmemoryleaderboard.ai/api-guide).

The service installs `mnemekit==0.2.0` from PyPI and calls its public interfaces. It does not import a research checkout, modify Mneme, or implement extraction, scoring, or reranking. Research-only v2 features are not part of this release.

## Install and start

Python 3.11+ and Linux are required. From this repository:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.lock
pip install -e '.[evaluation,test]'

export MNEME_DATA_DIR=/mnt/sv0/sean/research/mneme-api/.runtime/data
read -rsp 'API key: ' MNEME_API_KEY
export MNEME_API_KEY
uvicorn mneme_api.app:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

The lock file records the tested Python 3.13 environment, including the English model.

Use a local disk for `MNEME_DATA_DIR`. Both environment variables are required. Startup checks the English model and initializes the package extractor. Chinese segmentation is included via `mnemekit[zh]`.

Place the service behind your HTTPS reverse proxy for public evaluation. The command above binds only to localhost. Submit the public `/add`, `/search`, and `/health` URLs and choose Bearer authentication. The service key is distinct from the platform-issued Eval Key. Public deployment and Full submission are separate from local installation.

## API

`GET /health` is unauthenticated. `POST /add` and `POST /search` require `Authorization: Bearer <MNEME_API_KEY>`.

Add request:

```json
{
  "request_id": "example:chunk:0",
  "user_id": "example:user:0",
  "session_id": "example:session:0",
  "messages": [
    {"role": "user", "content": "My dog Lucky is a golden retriever.", "timestamp": 1704067200000},
    {"role": "assistant", "content": "Lucky enjoys playing with a tennis ball.", "timestamp": 1704067201000}
  ]
}
```

Success is HTTP 200 with `success: true` and the three original identifiers. Add returns only after the messages are stored and searchable. Timestamps use Unix milliseconds; missing timestamps use the persisted request receipt time.

Search request:

```json
{"user_id": "example:user:0", "query": "What breed is Lucky?", "top_k": 100}
```

Search returns `{"data": [{"id": "...", "content": "...", "created_at": "..."}]}`. Content includes source time, role, and the full original message. Results preserve Mneme's order. Optional `options` are accepted but do not alter the query. Scores are omitted because the public `Memory.recall()` interface returns turns, not scores. No matches produce `{"data": []}`.

## Memory semantics

- Each `user_id` has a separate hashed directory and Mneme store. Search spans that user's sessions only.
- Each source `session_id` maps to a stable Event through the public `event_id` argument. Messages stay in source order within each Add. Concurrent Adds for one user are serialized in lock-acquisition order; callers should submit chunks for one session sequentially.
- Each message becomes one turn: user content occupies `query`, assistant content occupies `response`. This preserves roles without inventing user/assistant pairs across request boundaries.
- Search calls `Memory.recall(query, topn=top_k)` with the published default behavior: lexical recall, `assoc_n=0`. This is a service baseline, not the research paper's configured hybrid retrieval.
- Request IDs are scoped to users. The same ID and validated payload is idempotent; a different payload returns 409.

The package writes multiple JSON files without a transaction. A per-user SQLite request journal records each accepted Add before invoking Mneme. If a write is interrupted, the next Add/Search rebuilds that user's store in a new generation by replaying the journal through `Memory.remember()`, then switches the active generation. Recovery errors return 503; partially written generations are never searched. This handles process interruptions, not a guarantee against storage failure or machine power loss.

Per-user file locks cover Add, Search, and recovery across local processes. Each operation reloads the current store, avoiding stale worker state. This prioritizes correctness; loading latency grows with user history. Capacity must be measured before Full. There is no automatic deletion: journals and superseded recovery generations contain evaluation data and require retention management by the operator.

## Local verification

```bash
python -m pytest -q
```

Regression tests use the real installed Mneme package and spaCy model. They cover HTTP authentication, role preservation, isolation, duplicate requests, restart persistence, result limits, and recovery after an interrupted package write. Test stores remain under ignored `.runtime/tests/` for inspection.

## Offline evaluation

Install the `evaluation` extra and run the API. A JSONL file can replay Add/Search traffic through the same HTTP boundary used in deployment:

```jsonl
{"operation":"add","request":{"request_id":"r1","user_id":"offline:run1","session_id":"s1","messages":[{"role":"user","content":"My dog Lucky is a golden retriever."}]}}
{"operation":"search","request":{"user_id":"offline:run1","query":"What breed is Lucky?","top_k":100}}
```

```bash
python evaluation/replay.py requests.jsonl responses.jsonl --base-url http://127.0.0.1:8000
```

The output must not already exist. Use a fresh user namespace for each independent experiment. This tool records retrieval responses; it does not generate answers, invoke a judge, or claim an AML score.

AML publishes some evaluation contracts and scoring modules in its [official repository](https://github.com/AML-memory/agent-memory-leaderboard), but does not distribute the complete formal data bundle or production orchestration. Local public-dataset runs must record the exact dataset revision, adapter, reader/judge, and budget before comparison. Original LoCoMo is not LoCoMo-Refined. Public Smoke and Full remain platform operations.
