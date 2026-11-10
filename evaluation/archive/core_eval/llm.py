import os
import re
import json
import time
import threading
import urllib.request
import urllib.error
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from mneme.schema import Tag, TagSource
from mneme.extract import Enricher

ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
ENRICH_SYS = "Extract the key entities and topic keywords from the text for memory retrieval. Output only the words, comma-separated, at most 6, no explanation."


def load_env() -> None:
    if not os.path.exists(ENV_PATH):
        return
    for line in open(ENV_PATH):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)


class Chat:

    def __init__(
        self,
        base_url: str,
        key: str,
        model: str,
        interval: float = 0.8,
        thinking: str = "",
        qwen_no_think: bool = False,
    ) -> None:
        self.model = model
        self._url = base_url + "/chat/completions"
        self._tokenize_url = base_url.removesuffix("/v1") + "/tokenize"
        self._key = key
        self._interval = interval
        self._thinking = thinking
        self._qwen_no_think = qwen_no_think
        self._last = 0.0
        self._lock = threading.Lock()

    def token_count(self, prompt: str) -> tuple[int, int]:
        body = json.dumps({"model": self.model, "prompt": prompt}).encode()
        request = urllib.request.Request(
            self._tokenize_url,
            data=body,
            headers={
                "Authorization": f"Bearer {self._key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.loads(response.read())
        return result["count"], result["max_model_len"]

    def token_count_messages(
        self,
        prompt: str,
        system: str = "",
    ) -> tuple[int, int]:
        messages = self._messages(prompt, system)
        body = json.dumps({"model": self.model, "messages": messages}).encode()
        request = urllib.request.Request(
            self._tokenize_url,
            data=body,
            headers={
                "Authorization": f"Bearer {self._key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.loads(response.read())
        return result["count"], result["max_model_len"]

    def _throttle(self) -> None:
        with self._lock:
            wait = self._interval - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()

    @staticmethod
    def _messages(prompt: str, system: str) -> list[dict[str, str]]:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    def complete(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 256,
        *,
        temperature: float = 0.1,
        top_p: float = 1.0,
        max_attempts: int = 8,
    ) -> "ChatResponse":
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self._throttle()
        payload = {
            "model": self.model,
            "messages": self._messages(prompt, system),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }
        if self._thinking:
            payload["thinking"] = {"type": self._thinking}
        if self._qwen_no_think:
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            self._url,
            data=body,
            headers={"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"},
        )
        attempts = []
        started = time.monotonic()
        for attempt in range(max_attempts):
            attempt_started = time.monotonic()
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    result = json.loads(r.read())
                attempts.append(ChatAttempt(
                    status="ok",
                    latency_ms=round((time.monotonic() - attempt_started) * 1000),
                ))
                usage = result.get("usage") or {}
                return ChatResponse(
                    content=result["choices"][0]["message"]["content"].strip(),
                    returned_model=result.get("model"),
                    input_tokens=usage.get("prompt_tokens", usage.get("input_tokens")),
                    output_tokens=usage.get(
                        "completion_tokens", usage.get("output_tokens")
                    ),
                    latency_ms=round((time.monotonic() - started) * 1000),
                    attempts=tuple(attempts),
                )
            except urllib.error.HTTPError as e:
                attempts.append(ChatAttempt(
                    status="http_error",
                    latency_ms=round((time.monotonic() - attempt_started) * 1000),
                    http_status=e.code,
                    error_class=type(e).__name__,
                ))
                if e.code not in (429, 500, 502, 503, 504, 529) or attempt == max_attempts - 1:
                    e.chat_attempts = tuple(attempts)
                    raise
                time.sleep(2 ** attempt)
            except (urllib.error.URLError, TimeoutError) as e:
                attempts.append(ChatAttempt(
                    status="transport_error",
                    latency_ms=round((time.monotonic() - attempt_started) * 1000),
                    error_class=type(e).__name__,
                ))
                if attempt == max_attempts - 1:
                    e.chat_attempts = tuple(attempts)
                    raise
                time.sleep(2 ** attempt)

    def __call__(self, prompt: str, system: str = "", max_tokens: int = 256) -> str:
        return self.complete(prompt, system, max_tokens).content


@dataclass(frozen=True)
class ChatAttempt:
    status: str
    latency_ms: int
    http_status: int | None = None
    error_class: str | None = None


@dataclass(frozen=True)
class ChatResponse:
    content: str
    returned_model: str | None
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int
    attempts: tuple[ChatAttempt, ...]


class TrackedChat:

    def __init__(
        self,
        chat: Chat,
        cache_path: Path,
        ledger_path: Path,
        *,
        provider: str,
        role: str,
        repetition: int,
        temperature: float = 0.0,
        top_p: float = 1.0,
        max_attempts: int = 3,
        tokenizer_identity: str = "",
        manifest_sha256: str = "",
        prompt_name: str | None = None,
        input_price_per_million: float | None = None,
        output_price_per_million: float | None = None,
        expected_returned_model: str | None = None,
        expected_endpoint_hash: str | None = None,
        input_token_limit: int | None = None,
        require_usage: bool = False,
    ) -> None:
        self.chat = chat
        self.cache_path = cache_path
        self.ledger_path = ledger_path
        self.provider = provider
        self.role = role
        self.repetition = repetition
        self.temperature = temperature
        self.top_p = top_p
        self.max_attempts = max_attempts
        self.tokenizer_identity = tokenizer_identity
        self.manifest_sha256 = manifest_sha256
        self.prompt_name = prompt_name or role
        self.input_price_per_million = input_price_per_million
        self.output_price_per_million = output_price_per_million
        self.expected_returned_model = expected_returned_model
        self.expected_endpoint_hash = expected_endpoint_hash
        self.input_token_limit = input_token_limit
        self.require_usage = require_usage
        self.question_id: str | None = None
        self._lock = threading.Lock()
        self._cache = self._load_cache()
        self.last_call_id: str | None = None
        self.logical_calls = 0
        self.failed_calls = 0
        actual_endpoint_hash = sha256(self.chat._url.encode()).hexdigest()
        if (
            self.expected_endpoint_hash is not None
            and actual_endpoint_hash != self.expected_endpoint_hash
        ):
            raise ValueError(
                f"endpoint hash mismatch: {actual_endpoint_hash} != "
                f"{self.expected_endpoint_hash}"
            )

    def set_question_id(self, question_id: str) -> None:
        self.question_id = question_id

    def __call__(self, prompt: str, system: str = "", max_tokens: int = 256) -> str:
        return self.complete(prompt, system, max_tokens).content

    def complete(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 256,
    ) -> ChatResponse:
        self.logical_calls += 1
        identity = {
            "provider": self.provider,
            "endpoint_hash": sha256(self.chat._url.encode()).hexdigest(),
            "requested_model": self.chat.model,
            "role": self.role,
            "repetition": self.repetition,
            "system": system,
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "thinking": self.chat._thinking,
            "qwen_no_think": self.chat._qwen_no_think,
            "tokenizer_identity": self.tokenizer_identity,
        }
        cache_key = _hash_json(identity)
        with self._lock:
            cached = self._cache.get(cache_key)
        if cached is not None:
            response = self._response_from_dict(cached["response"])
            self._validate_or_record_failure(
                identity, cache_key, response, True, max_tokens
            )
            self.last_call_id = self._record(
                identity, cache_key, response, True
            )
            return response
        try:
            response = self.chat.complete(
                prompt,
                system,
                max_tokens,
                temperature=self.temperature,
                top_p=self.top_p,
                max_attempts=self.max_attempts,
            )
        except Exception as error:
            self.failed_calls += 1
            self.last_call_id = self._record_failure(identity, cache_key, error)
            raise
        self._validate_or_record_failure(
            identity, cache_key, response, False, max_tokens
        )
        cache_row = {"cache_key": cache_key, "response": asdict(response)}
        with self._lock:
            existing = self._cache.get(cache_key)
            if existing is None:
                self._append(self.cache_path, cache_row)
                self._cache[cache_key] = cache_row
            else:
                response = self._response_from_dict(existing["response"])
                self._validate_or_record_failure(
                    identity, cache_key, response, True, max_tokens
                )
        self.last_call_id = self._record(identity, cache_key, response, False)
        return response

    def _validate_or_record_failure(
        self,
        identity: dict[str, Any],
        cache_key: str,
        response: ChatResponse,
        cache_hit: bool,
        max_output_tokens: int,
    ) -> None:
        try:
            self._validate_response(response, max_output_tokens)
        except Exception as error:
            self.failed_calls += 1
            self.last_call_id = self._record(
                identity,
                cache_key,
                response,
                cache_hit,
                status="failed",
                failure_class=type(error).__name__,
            )
            raise
    def _validate_response(
        self,
        response: ChatResponse,
        max_output_tokens: int,
    ) -> None:
        if (
            self.expected_returned_model is not None
            and response.returned_model != self.expected_returned_model
        ):
            raise ValueError(
                "returned model mismatch: "
                f"{response.returned_model} != {self.expected_returned_model}"
            )
        if self.require_usage and (
            response.input_tokens is None or response.output_tokens is None
        ):
            raise ValueError("provider response omitted required token usage")
        if (
            self.input_token_limit is not None
            and response.input_tokens is not None
            and response.input_tokens > self.input_token_limit
        ):
            raise ValueError(
                f"provider input usage {response.input_tokens} exceeds "
                f"{self.input_token_limit}"
            )
        if (
            response.output_tokens is not None
            and response.output_tokens > max_output_tokens
        ):
            raise ValueError(
                f"provider output usage {response.output_tokens} exceeds "
                f"{max_output_tokens}"
            )

    def token_count_messages(
        self,
        prompt: str,
        system: str = "",
    ) -> tuple[int, int]:
        return self.chat.token_count_messages(prompt, system)

    def _load_cache(self) -> dict[str, dict[str, Any]]:
        if not self.cache_path.exists():
            return {}
        rows = {}
        with self.cache_path.open(encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                key = row["cache_key"]
                if key in rows and rows[key] != row:
                    raise ValueError(f"conflicting cache rows for {key}")
                rows[key] = row
        return rows

    def _record(
        self,
        identity: dict[str, Any],
        cache_key: str,
        response: ChatResponse,
        cache_hit: bool,
        *,
        status: str = "ok",
        failure_class: str | None = None,
    ) -> str:
        response_sha256 = sha256(response.content.encode()).hexdigest()
        attempts = () if cache_hit else response.attempts
        row = {
            "question_id": self.question_id,
            "manifest_sha256": self.manifest_sha256,
            "repetition": self.repetition,
            "role": self.role,
            "provider": self.provider,
            "endpoint_hash": identity["endpoint_hash"],
            "requested_model": self.chat.model,
            "returned_model": response.returned_model,
            "tokenizer_identity": self.tokenizer_identity,
            "prompt_name": self.prompt_name,
            "prompt_sha256": sha256(
                (identity["system"] + "\n" + identity["prompt"]).encode()
            ).hexdigest(),
            "request_sha256": _hash_json(identity),
            "cache_key": cache_key,
            "cache_hit": cache_hit,
            "thinking": self.chat._thinking,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_output_tokens": identity["max_tokens"],
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "latency_ms": response.latency_ms,
            "attempts": len(attempts),
            "attempt_statuses": [asdict(attempt) for attempt in attempts],
            "status": status,
            "failure_class": failure_class,
            "response_sha256": response_sha256,
            "estimated_cost_usd": self._estimated_cost(response),
        }
        with self._lock:
            row["call_id"] = self._call_id(cache_key, cache_hit)
            self._append(self.ledger_path, row)
        return row["call_id"]

    def _record_failure(
        self,
        identity: dict[str, Any],
        cache_key: str,
        error: Exception,
    ) -> str:
        attempts = getattr(error, "chat_attempts", ())
        row = {
            "question_id": self.question_id,
            "manifest_sha256": self.manifest_sha256,
            "repetition": self.repetition,
            "role": self.role,
            "provider": self.provider,
            "endpoint_hash": identity["endpoint_hash"],
            "requested_model": self.chat.model,
            "returned_model": None,
            "tokenizer_identity": self.tokenizer_identity,
            "prompt_name": self.prompt_name,
            "prompt_sha256": sha256(
                (identity["system"] + "\n" + identity["prompt"]).encode()
            ).hexdigest(),
            "request_sha256": _hash_json(identity),
            "cache_key": cache_key,
            "cache_hit": False,
            "thinking": self.chat._thinking,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_output_tokens": identity["max_tokens"],
            "input_tokens": None,
            "output_tokens": None,
            "latency_ms": sum(attempt.latency_ms for attempt in attempts),
            "attempts": len(attempts),
            "attempt_statuses": [asdict(attempt) for attempt in attempts],
            "status": "failed",
            "failure_class": type(error).__name__,
            "response_sha256": None,
            "estimated_cost_usd": None,
        }
        with self._lock:
            row["call_id"] = self._call_id(cache_key, False)
            self._append(self.ledger_path, row)
        return row["call_id"]

    def _estimated_cost(self, response: ChatResponse) -> float | None:
        if (
            response.input_tokens is None
            or response.output_tokens is None
            or self.input_price_per_million is None
            or self.output_price_per_million is None
        ):
            return None
        return (
            response.input_tokens * self.input_price_per_million
            + response.output_tokens * self.output_price_per_million
        ) / 1_000_000

    def _call_id(self, cache_key: str, cache_hit: bool) -> str:
        return _hash_json({
            "cache_key": cache_key,
            "cache_hit": cache_hit,
            "ledger_position": self.ledger_path.stat().st_size
            if self.ledger_path.exists() else 0,
        })

    @staticmethod
    def _append(path: Path, row: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(_canonical_json(row) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    @staticmethod
    def _response_from_dict(value: dict[str, Any]) -> ChatResponse:
        return ChatResponse(
            content=value["content"],
            returned_model=value["returned_model"],
            input_tokens=value["input_tokens"],
            output_tokens=value["output_tokens"],
            latency_ms=value["latency_ms"],
            attempts=tuple(ChatAttempt(**attempt) for attempt in value["attempts"]),
        )


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _hash_json(value: object) -> str:
    return sha256(_canonical_json(value).encode()).hexdigest()


def chat_for(provider: str, role: str) -> Chat:
    load_env()
    provider = provider.lower()
    p = provider.upper()
    model_key = f"{p}_{role.upper()}_MODEL"
    interval = float(os.environ.get(f"{p}_THROTTLE", "0.8"))
    thinking = ""
    if provider == "deepseek":
        thinking = "enabled" if role == "reader" else "disabled"
    elif provider == "minimax" and role == "judge":
        thinking = "disabled"
    return Chat(
        os.environ[f"{p}_BASE_URL"],
        os.environ[f"{p}_API_KEY"],
        os.environ[model_key],
        interval,
        thinking,
        qwen_no_think=provider == "qwen",
    )


def make_enricher(llm: Chat) -> Enricher:
    def enrich(text: str, source: TagSource, tags: list[Tag]) -> list[Tag]:
        have = {t.text for t in tags}
        for w in re.split(r"[,，、\s]+", llm(text, system=ENRICH_SYS, max_tokens=64)):
            w = w.strip().lower()
            if w and w not in have:
                tags.append(Tag(w, source, "term", 1.0))
                have.add(w)
        return tags
    return enrich
