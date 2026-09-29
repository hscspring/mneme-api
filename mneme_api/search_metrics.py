import fcntl
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import tiktoken
from mneme.evidence import EvidenceItem

from mneme_api.data_model import SearchResponse

logger = logging.getLogger(__name__)

PREFIX_TOKENS = 100_000


class SearchMetrics:

    def __init__(self, root: Path):
        self.path = root / "search-metrics.jsonl"
        self.lock_path = root / "search-metrics.lock"
        self.encoding = tiktoken.get_encoding("o200k_base")

    def record(
        self,
        user_id: str,
        items: list[EvidenceItem],
        response: SearchResponse,
        top_k: int,
        history_requests: int,
        load_ms: float,
        search_ms: float,
        format_ms: float,
        total_ms: float,
    ) -> None:
        item_tokens = [len(self.encoding.encode(item.content)) for item in response.data]
        prefix_tokens = 0
        prefix_items = []
        prefix_sources = []
        boundary_sources = []
        for item, tokens in zip(items, item_tokens):
            if prefix_tokens + tokens > PREFIX_TOKENS:
                boundary_sources = list(item.source_ids)
                break
            prefix_tokens += tokens
            prefix_items.append(len(item.spans))
            prefix_sources.extend(item.source_ids)
        span_count = sum(len(item.spans) for item in items)
        evidence_tokens = sum(item_tokens)
        entry = {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "user_hash": hashlib.sha256(user_id.encode()).hexdigest(),
            "history_requests": history_requests,
            "top_k": top_k,
            "item_count": len(items),
            "span_count": span_count,
            "response_tokens": len(self.encoding.encode(response.model_dump_json())),
            "evidence_tokens": evidence_tokens,
            "prefix_token_limit": PREFIX_TOKENS,
            "complete_prefix_tokens": prefix_tokens,
            "complete_prefix_item_count": len(prefix_items),
            "complete_prefix_span_count": sum(prefix_items),
            "complete_prefix_item_coverage": len(prefix_items) / len(items) if items else 1.0,
            "complete_prefix_span_coverage": sum(prefix_items) / span_count if span_count else 1.0,
            "complete_prefix_token_coverage": prefix_tokens / evidence_tokens if evidence_tokens else 1.0,
            "complete_prefix_source_ids": list(dict.fromkeys(prefix_sources)),
            "boundary_source_ids": boundary_sources,
            "load_ms": round(load_ms, 3),
            "search_ms": round(search_ms, 3),
            "format_ms": round(format_ms, 3),
            "total_ms": round(total_ms, 3),
        }
        try:
            with self.lock_path.open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                with self.path.open("a") as output:
                    output.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as error:
            logger.error("Failed to record Search metrics: %s", error)
