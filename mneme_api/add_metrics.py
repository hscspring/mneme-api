import fcntl
import hashlib
import json
import logging
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)


class AddProfile:

    def __init__(self, user_id: str, message_count: int) -> None:
        self.user_hash = hashlib.sha256(user_id.encode()).hexdigest()
        self.message_count = message_count
        self.started = time.perf_counter()
        self.phases: dict[str, float] = {}
        self.core_phases: dict[str, float] = {}

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            elapsed = (time.perf_counter() - started) * 1000
            self.phases[name] = self.phases.get(name, 0.0) + elapsed

    def include_core(self, phases: object) -> None:
        if not isinstance(phases, dict):
            return
        self.core_phases = {
            str(name): float(duration)
            for name, duration in phases.items()
            if isinstance(duration, int | float)
        }

    def entry(self, error: BaseException | None) -> dict[str, object]:
        return {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "user_hash": self.user_hash,
            "message_count": self.message_count,
            "success": error is None,
            "error_type": None if error is None else type(error).__name__,
            "phases_ms": {
                name: round(duration, 3)
                for name, duration in self.phases.items()
            },
            "core_phases_ms": {
                name: round(duration, 3)
                for name, duration in self.core_phases.items()
            },
            "total_ms": round((time.perf_counter() - self.started) * 1000, 3),
        }


class AddMetrics:

    ENVIRONMENT_PATH = "MNEME_ADD_METRICS_PATH"

    def __init__(self, root: Path) -> None:
        configured = os.environ.get(self.ENVIRONMENT_PATH)
        self.path = Path(configured).resolve() if configured else None
        self.lock_path = root / "add-metrics.lock"

    def profile(self, user_id: str, message_count: int) -> AddProfile:
        return AddProfile(user_id, message_count)

    def record(self, profile: AddProfile, error: BaseException | None) -> None:
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.lock_path.open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                with self.path.open("a") as output:
                    output.write(json.dumps(profile.entry(error), ensure_ascii=False) + "\n")
        except OSError as metrics_error:
            logger.error("Failed to record Add metrics: %s", metrics_error)
