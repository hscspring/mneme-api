import argparse
import hashlib
import json
import resource
import time
from dataclasses import asdict

from mneme import EvidenceProjection, Memory


QUERIES = (
    "What happened?",
    "What do you remember about the user?",
    "When did this happen?",
    "What are the user's preferences?",
    "Who was involved?",
    "What changed over time?",
)


def evidence_digest(memory: Memory) -> list[dict[str, object]]:
    results = []
    for query in QUERIES:
        started = time.perf_counter()
        evidence = memory.search_evidence(
            query,
            topn=100,
            projection=EvidenceProjection.TAG_GRAPH_DEDUP,
        )
        payload = json.dumps(
            [asdict(item) for item in evidence],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        results.append({
            "query_sha256": hashlib.sha256(query.encode()).hexdigest(),
            "evidence_sha256": hashlib.sha256(payload).hexdigest(),
            "items": len(evidence),
            "spans": sum(len(item.spans) for item in evidence),
            "seconds": round(time.perf_counter() - started, 6),
        })
    return results


parser = argparse.ArgumentParser()
parser.add_argument("root")
parser.add_argument("--migrate", action="store_true")
parser.add_argument("--append", action="store_true")
args = parser.parse_args()
started = time.perf_counter()
memory = Memory(args.root)
opened = time.perf_counter() - started
legacy = memory.store.legacy
migrated = 0.0
if args.migrate:
    started = time.perf_counter()
    memory.migrate_store()
    migrated = time.perf_counter() - started
if args.append:
    memory.remember("Synthetic gate record.", "Synthetic gate response.", session_id="gate", round_id=1)
print(json.dumps({
    "open_seconds": round(opened, 6),
    "legacy_on_open": legacy,
    "migrate": args.migrate,
    "migrate_seconds": round(migrated, 6),
    "append": args.append,
    "evidence": evidence_digest(memory),
    "rss_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 3),
}, sort_keys=True))
