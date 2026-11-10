import json
import resource
import sqlite3
import sys
import time
from pathlib import Path

from mneme import Memory


db_path = Path(sys.argv[1])
with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as db:
    generation = db.execute("SELECT generation FROM state").fetchone()[0]
    requests = db.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
root = db_path.parent / generation
if (root / "store.sqlite3").exists():
    print(json.dumps({"user": db_path.parent.name[:12], "requests": requests, "status": "already_sqlite"}))
    raise SystemExit
started = time.perf_counter()
memory = Memory(str(root))
loaded = time.perf_counter()
counts = [len(memory.store.turns), len(memory.store.events), len(memory.store.sources)]
memory.migrate_store()
finished = time.perf_counter()
print(json.dumps({
    "user": db_path.parent.name[:12],
    "requests": requests,
    "status": "migrated",
    "counts": counts,
    "load_s": round(loaded - started, 3),
    "migrate_s": round(finished - loaded, 3),
    "max_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
}), flush=True)
