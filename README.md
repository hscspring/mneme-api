# mneme-api

A standalone Add/Search service for [Mneme](https://pypi.org/project/mnemekit/), compatible with the [Agent Memory Leaderboard API](https://agentmemoryleaderboard.ai/api-guide).

The service installs `mnemekit==0.8.0` from PyPI and calls its public interfaces. Search uses `Memory.search_evidence()` with the package's default evidence projection and an API-owned Reader budget. It does not import a research checkout, modify Mneme, or implement extraction, projection, scoring, or reranking.

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

Place the service behind your HTTPS reverse proxy for public evaluation. The command above binds only to localhost. Submit the public `/add`, `/search`, and `/health` URLs and choose Token, Bearer, or X-Api-Key authentication. The service key is distinct from the platform-issued Eval Key. Public deployment and Full submission are separate from local installation.

## Upgrade

API release 0.1.13 uses mnemekit 0.8.0 bounded evidence materialization and schema 3 disk-backed stores. The reference 2 GB deployment processes one memory operation at a time and releases its Memory object after every request, preventing a large user store from remaining resident between searches. Existing stores are migrated atomically on first access; migrate them serially before serving traffic on a constrained host. Run one Uvicorn worker as shown above. In the deployment's existing virtual environment:

```bash
git pull --ff-only
python -m pip install --index-url https://pypi.org/simple -r requirements.lock
python -m pip install --index-url https://pypi.org/simple -e '.[evaluation,test]'
python -m pytest -q
python -c "from importlib.metadata import version; print(version('mnemekit'))"
```

The last command must print `0.8.0`. Have the deployment operator restart the service using its existing process manager, preserving `MNEME_API_KEY` and `MNEME_DATA_DIR`, then recheck Health/Add/Search before resuming evaluation. The HTTP contract and launch command are unchanged.

Old 0.2.0 turns remain readable; upgrading does not retroactively extract propositions for existing records. New writes use the installed package compiler. Use fresh evaluation user IDs for a consistently ingested new-version run. Do not change the deployed version during an active platform evaluation.

## API

`GET /health` is unauthenticated. `POST /add` and `POST /search` accept `Authorization: Bearer <MNEME_API_KEY>`, `Authorization: Token <MNEME_API_KEY>`, or `X-Api-Key: <MNEME_API_KEY>`. All three use the same service key. Match the scheme selected in your AML application. API 0.1.2 adds Token and X-Api-Key support; older deployments accept only Bearer.

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

Search returns `{"data": [{"id": "...", "content": "...", "created_at": "..."}]}`. Each result represents one core EvidenceItem. Content includes its tag label and every span in core order, with source ID, UTC time, role, and text. Spans may be segments rather than whole original messages. `created_at` is the earliest span timestamp; each span retains its own time in content. Results preserve Mneme's ranking; scores are omitted. Optional `options` are accepted but do not alter the query. No matches produce `{"data": []}`.

## Memory semantics

- Each `user_id` has a separate hashed directory and Mneme store. Search spans that user's sessions only.
- Each source `session_id` maps to a stable Event through the public `event_id` argument. Messages stay in source order within each Add. Concurrent Adds for one user are serialized in lock-acquisition order; callers should submit chunks for one session sequentially.
- Each message becomes one turn: user content occupies `query`, assistant content occupies `response`. This preserves roles without inventing user/assistant pairs across request boundaries.
- Search calls `Memory.search_evidence(query, topn=top_k, budget=...)` without an explicit projection, so Mneme uses its default `TAG_GRAPH_DEDUP` projection. The API measures the exact formatted `data[].content` with `o200k_base` and sets a 100,000-token Evidence budget. Mneme returns the unchanged evidence prefix and keeps the boundary span complete, so a response can slightly exceed 100,000 tokens. Top-K is applied after projection and counts evidence items, not turns or spans.
- Request IDs are scoped to users. The same ID and validated payload is idempotent; a different payload returns 409.

A per-user SQLite request journal records each accepted Add before invoking Mneme's transactional Store. If a write is interrupted, the next Add/Search rebuilds that user's store in a new generation by replaying the journal through `Memory.remember_many()`, then switches the active generation. Recovery errors return 503; partially written generations are never searched. This handles process interruptions, not a guarantee against storage failure or machine power loss.

Each successful Search appends a diagnostic record to `MNEME_DATA_DIR/search-metrics.jsonl`. It records item, span, response-token and evidence-token counts; request-history size; load, search and formatting latency; complete source IDs within the first 100,000 evidence tokens; and source IDs on the boundary item. Token counts use `o200k_base`. The log contains no query or memory text. It measures the returned evidence payload only because platform prompt and question tokens are not visible to this API.

Per-user file locks cover Add, Search, and recovery across local processes. On the reference 2 GB deployment, the single service worker handles one memory operation and retains one user store at a time. Before reuse, it compares the cached generation and completed-request count with SQLite, reloading stale entries written by another process. There is no automatic deletion: journals and superseded recovery generations contain evaluation data and require retention management by the operator.

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
