import hashlib
import json
import sys

from mneme import EvidenceProjection, Memory
from mneme.activation import ActivationField
from mneme.evidence import EvidenceProjector


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
index = memory.store.network
output = []
for query in QUERIES:
    activated = ActivationField(index)(query)
    active = {item.unit.id: item for item in activated}
    evidence = EvidenceProjector(
        index, EvidenceProjection.TAG_GRAPH_DEDUP,
    )(activated, query)[:100]
    query_tags = [tag.text for tag in index.compiler.analyze(query, "user").tags]
    items = []
    for item in evidence:
        postings = index.index.get(item.label, [])
        candidates = [
            active[value]
            for value, _ in postings
            if value in active
        ]
        if not candidates:
            items.append({"item": digest(item.id), "peak": None})
            continue
        peak = max(candidates, key=lambda value: value.strength)
        semantic = [
            tag for tag in query_tags
            if peak.unit.id in index.semantic_index.get(tag, [])
        ]
        relation = [
            tag for tag in query_tags
            if peak.unit.id in {
                value for value, _ in index.relation_index.get(tag, [])
            }
        ]
        items.append({
            "item": digest(item.id),
            "peak": digest(peak.unit.id),
            "channels": item.channels,
            "semantic_query_tags": [digest(value) for value in semantic],
            "relation_query_tags": [digest(value) for value in relation],
        })
    output.append({"query": digest(query), "items": items})
    getattr(index, "clear_cache", lambda: None)()
print(json.dumps(output, sort_keys=True))
