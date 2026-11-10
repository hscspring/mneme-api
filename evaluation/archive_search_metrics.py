import argparse
import hashlib
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    rows = []
    digest = hashlib.sha256()
    with args.source.open("rb") as source, args.output.open("x") as output:
        for line in source:
            digest.update(line)
            row = json.loads(line)
            row = {k: v for k, v in row.items() if isinstance(v, (int, float, bool)) or k == "recorded_at"}
            rows.append(row)
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
    values = sorted(row["total_ms"] for row in rows)
    quantiles = {}
    for fraction in (0.5, 0.95, 0.99):
        position = (len(values) - 1) * fraction
        lower = int(position)
        upper = min(lower + 1, len(values) - 1)
        quantiles[str(fraction)] = values[lower] + (values[upper] - values[lower]) * (position - lower)
    print(json.dumps({
        "source": str(args.source),
        "source_sha256": digest.hexdigest(),
        "records": len(rows),
        "first": rows[0]["recorded_at"],
        "last": rows[-1]["recorded_at"],
        "total_ms_quantiles": quantiles,
        "max_total_ms": max(values),
        "max_evidence_tokens": max(row["evidence_tokens"] for row in rows),
        "max_response_tokens": max(row["response_tokens"] for row in rows),
        "evolution_calls": sum(row.get("evolution_route", False) for row in rows),
        "evolution_route_recorded": any("evolution_route" in row for row in rows),
        "evolution_sources": sum(row.get("evolution_source_count", 0) for row in rows),
    }, indent=2))


if __name__ == "__main__":
    main()
