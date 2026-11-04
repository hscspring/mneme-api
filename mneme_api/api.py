import fcntl
import gc
import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from pathlib import Path
from threading import BoundedSemaphore
from typing import Iterator
from uuid import uuid4

import tiktoken
from mneme import EvidenceBudget, EvidenceItem, Memory, RememberInput

from mneme_api.add_metrics import AddMetrics, AddProfile
from mneme_api.data_model import AddRequest, AddResponse, Evidence, SearchRequest, SearchResponse
from mneme_api.search_metrics import SearchMetrics

EVIDENCE_TOKEN_LIMIT = 100_000


class EvidenceFormatter:

    def __init__(self) -> None:
        self.encoding = tiktoken.get_encoding("o200k_base")

    def item(self, item: EvidenceItem) -> Evidence:
        parts = [f"[tag: {item.label}]"] if item.label else []
        for span in item.spans:
            timestamp = datetime.fromtimestamp(span.timestamp, timezone.utc).isoformat()
            parts.append(f"[{timestamp}] [source: {span.source_id}]\n{span.role}: {span.text}")
        return Evidence(
            id=item.id,
            content="\n".join(parts),
            created_at=datetime.fromtimestamp(
                min(span.timestamp for span in item.spans), timezone.utc,
            ).isoformat(),
        )

    def response(self, items: list[EvidenceItem]) -> SearchResponse:
        return SearchResponse(data=[self.item(item) for item in items])

    def tokens(self, items: tuple[EvidenceItem, ...]) -> int:
        return sum(self.item_tokens(item) for item in items)

    def item_tokens(self, item: EvidenceItem) -> int:
        return len(self.encoding.encode_ordinary(self.item(item).content))


class RequestConflict(ValueError):
    pass


class MemoryService:

    def __init__(self, root: Path, max_concurrency: int = 1):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.metrics = SearchMetrics(self.root)
        self.add_metrics = AddMetrics(self.root)
        self.formatter = EvidenceFormatter()
        self.evidence_budget = EvidenceBudget(
            EVIDENCE_TOKEN_LIMIT,
            self.formatter.tokens,
            item_measure=self.formatter.item_tokens,
        )
        self._capacity = BoundedSemaphore(max_concurrency)

    def add(self, request: AddRequest) -> AddResponse:
        profile = self.add_metrics.profile(request.user_id, len(request.messages))
        error: BaseException | None = None
        acquired = False
        try:
            with profile.phase("capacity_wait_ms"):
                self._capacity.acquire()
                acquired = True
            return self._add(request, profile)
        except BaseException as caught:
            error = caught
            raise
        finally:
            if acquired:
                with profile.phase("gc_ms"):
                    gc.collect()
                self._capacity.release()
            self.add_metrics.record(profile, error)

    def _add(self, request: AddRequest, profile: AddProfile) -> AddResponse:
        payload = request.model_dump_json()
        with self._user(request.user_id, profile) as (directory, db):
            with profile.phase("idempotency_query_ms"):
                previous = db.execute(
                    "SELECT payload FROM requests WHERE id = ?", (request.request_id,)
                ).fetchone()
            if previous is not None and previous[0] != payload:
                raise RequestConflict("request_id already belongs to a different payload")
            with profile.phase("recovery_ms"):
                self._recover(request.user_id, directory, db, profile)
            if previous is None:
                received = time.time()
                if hasattr(Memory, "remember_idempotent"):
                    memory = self._memory(directory, db, profile)
                    status = self._remember_idempotent(
                        memory,
                        request,
                        payload,
                        received,
                        profile,
                    )
                    if status == "conflict":
                        raise RequestConflict(
                            "request_id already belongs to a different payload"
                        )
                else:
                    self._remember_legacy(
                        directory,
                        request,
                        payload,
                        received,
                        db,
                        profile,
                    )
        return AddResponse(
            request_id=request.request_id,
            user_id=request.user_id,
            session_id=request.session_id,
        )

    def search(self, request: SearchRequest) -> SearchResponse:
        with self._capacity:
            try:
                return self._search(request)
            finally:
                gc.collect()

    def _search(self, request: SearchRequest) -> SearchResponse:
        started = time.perf_counter()
        with self._user(request.user_id) as (directory, db):
            self._recover(request.user_id, directory, db)
            memory = self._memory(directory, db)
            loaded = time.perf_counter()
            items = memory.search_composed_evidence(
                request.query,
                topn=request.top_k,
                budget=self.evidence_budget,
                scope_owner="user",
            )
            searched = time.perf_counter()
            response = self.formatter.response(items)
            formatted = time.perf_counter()
            history_requests = db.execute(
                "SELECT COUNT(*) FROM requests WHERE done = 1"
            ).fetchone()[0]
            request_count = getattr(memory, "idempotent_request_count", None)
            if request_count is not None:
                history_requests += request_count()
        self.metrics.record(
            request.user_id,
            items,
            response,
            memory.last_evolution_source_count,
            request.top_k,
            history_requests,
            (loaded - started) * 1000,
            (searched - loaded) * 1000,
            (formatted - searched) * 1000,
            (formatted - started) * 1000,
        )
        return response

    @contextmanager
    def _user(
        self,
        user_id: str,
        profile: AddProfile | None = None,
    ) -> Iterator[tuple[Path, sqlite3.Connection]]:
        directory = self.root / hashlib.sha256(user_id.encode()).hexdigest()
        directory.mkdir(exist_ok=True)
        with (directory / "lock").open("a") as lock:
            lock_context = profile.phase("user_lock_wait_ms") if profile else nullcontext()
            with lock_context:
                fcntl.flock(lock, fcntl.LOCK_EX)
            open_context = profile.phase("request_db_open_ms") if profile else nullcontext()
            with open_context:
                db = sqlite3.connect(directory / "requests.sqlite3")
            try:
                schema_context = profile.phase("request_schema_ms") if profile else nullcontext()
                with schema_context:
                    with db:
                        db.execute(
                            "CREATE TABLE IF NOT EXISTS requests "
                            "(id TEXT PRIMARY KEY, payload TEXT NOT NULL, received REAL NOT NULL, "
                            "done INTEGER NOT NULL)"
                        )
                        db.execute("CREATE TABLE IF NOT EXISTS state (generation TEXT NOT NULL)")
                        if db.execute("SELECT generation FROM state").fetchone() is None:
                            db.execute("INSERT INTO state VALUES (?)", (uuid4().hex,))
                yield directory, db
            finally:
                close_context = profile.phase("request_db_close_ms") if profile else nullcontext()
                with close_context:
                    db.close()

    def _memory(
        self,
        directory: Path,
        db: sqlite3.Connection,
        profile: AddProfile | None = None,
    ) -> Memory:
        open_context = profile.phase("store_open_ms") if profile else nullcontext()
        with open_context:
            generation = db.execute("SELECT generation FROM state").fetchone()[0]
            memory = Memory(root=str(directory / generation))
            if memory.store.legacy:
                memory.migrate_store()
            return memory

    def _recover(
        self,
        user_id: str,
        directory: Path,
        db: sqlite3.Connection,
        profile: AddProfile | None = None,
    ) -> None:
        if db.execute("SELECT 1 FROM requests WHERE done = 0 LIMIT 1").fetchone() is None:
            return
        generation = uuid4().hex
        memory = Memory(root=str(directory / generation))
        for payload, received in db.execute("SELECT payload, received FROM requests ORDER BY rowid"):
            self._remember(memory, AddRequest.model_validate_json(payload), received)
            if profile is not None:
                profile.include_core(getattr(memory, "last_remember_profile", None))
        with db:
            db.execute("UPDATE state SET generation = ?", (generation,))
            db.execute("UPDATE requests SET done = 1")

    def _remember(self, memory: Memory, request: AddRequest, received: float) -> None:
        memory.remember_many(self._remember_inputs(request, received))

    def _remember_idempotent(
        self,
        memory: Memory,
        request: AddRequest,
        payload: str,
        received: float,
        profile: AddProfile,
    ) -> str:
        with profile.phase("remember_ms"):
            status = memory.remember_idempotent(
                request.request_id,
                hashlib.sha256(payload.encode()).hexdigest(),
                received,
                self._remember_inputs(request, received),
            )
        profile.include_core(getattr(memory, "last_remember_profile", None))
        return status

    def _remember_legacy(
        self,
        directory: Path,
        request: AddRequest,
        payload: str,
        received: float,
        db: sqlite3.Connection,
        profile: AddProfile,
    ) -> None:
        with profile.phase("pending_commit_ms"):
            with db:
                db.execute(
                    "INSERT INTO requests(id, payload, received, done) VALUES (?, ?, ?, 0)",
                    (request.request_id, payload, received),
                )
        memory = self._memory(directory, db, profile)
        with profile.phase("remember_ms"):
            self._remember(memory, request, received)
        profile.include_core(getattr(memory, "last_remember_profile", None))
        with profile.phase("done_commit_ms"):
            with db:
                db.execute("UPDATE requests SET done = 1 WHERE id = ?", (request.request_id,))

    def _remember_inputs(
        self,
        request: AddRequest,
        received: float,
    ) -> list[RememberInput]:
        session = hashlib.sha256(request.session_id.encode()).hexdigest()
        items = []
        for index, message in enumerate(request.messages):
            identity = json.dumps([request.request_id, index], ensure_ascii=False)
            round_id = int(hashlib.sha256(identity.encode()).hexdigest(), 16)
            items.append(RememberInput(
                query=message.content if message.role == "user" else "",
                response=message.content if message.role == "assistant" else "",
                session_id=session,
                round_id=round_id,
                ts=message.timestamp / 1000 if message.timestamp is not None else received,
                event_id=session,
            ))
        return items
