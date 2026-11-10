import hashlib
import json
import sys

from mneme import EvidenceProjection, Memory


QUERIES = (
    "What happened?",
    "What do you remember about the user?",
    "When did this happen?",
    "What are the user's preferences?",
    "Who was involved?",
    "What changed over time?",
)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


memory = Memory(sys.argv[1])
output = []
for query in QUERIES:
    evidence = memory.search_evidence(
        query,
        topn=100,
        projection=EvidenceProjection.TAG_GRAPH_DEDUP,
    )
    items = []
    for item in evidence:
        items.append({
            "id": digest(item.id),
            "event": digest(item.event_id),
            "exchange": digest(item.exchange_id),
            "label": digest(item.label or ""),
            "strength": item.strength,
            "channels": item.channels,
            "access": [digest(value) for value in item.access_ids],
            "spans": [
                {
                    "source": digest(span.source_id),
                    "role": span.role,
                    "timestamp": span.timestamp,
                    "text": digest(span.text),
                }
                for span in item.spans
            ],
        })
    output.append({"query": digest(query), "items": items})
print(json.dumps(output, sort_keys=True))
