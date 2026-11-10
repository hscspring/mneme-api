import hashlib
import json
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "results/manifest.json").read_text())
    for row in manifest["included"]:
        path = root / row["archive_path"]
        assert path.stat().st_size == row["bytes"], path
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"], path
        if path.suffix == ".json":
            json.loads(path.read_text())
        if path.suffix == ".jsonl":
            for line in path.open():
                json.loads(line)
    for benchmark in ("lme", "memops"):
        stem = f"competition-0.10.1-{benchmark}-answer"
        report = json.loads((root / f"results/aml/runtime/{stem}.json").read_text())
        for repetition, expected in enumerate(report["answer_evaluation"]["repetitions"]):
            path = root / f"results/competition/{stem}_rep{repetition}.jsonl"
            rows = [json.loads(line) for line in path.open()]
            for method, metrics in expected["methods"].items():
                values = [row for row in rows if row["id"].endswith("|" + method)]
                assert len(values) == expected["n"], (path, method)
                for key, field in (("accuracy", "judge"), ("token_f1", "f1")):
                    scored = values
                    if benchmark == "lme" and key == "token_f1":
                        scored = [row for row in values if not row["group"].startswith(("abstention", "single-session-preference")) and not row["id"].rsplit("|", 1)[0].endswith("_abs")]
                    actual = sum(row[field] for row in scored) / len(scored)
                    assert abs(actual - metrics[key]) < 1e-10, (path, method, key)
    summary = json.loads((root / "results/official-summary.json").read_text())
    for run in summary["runs"]:
        expected = (5609 * run["textual_score"] + 3993 * run["streaming_score"]) / 9602
        assert abs(expected - run["overall_score"]) < 1e-10
    metrics = [json.loads(line) for line in (root / "results/aml/full2-search-metrics.jsonl").open()]
    stats = json.loads((root / "results/aml/full2-search-summary.json").read_text())
    assert len(metrics) == stats["rows"] == 10292
    assert max(row["evidence_tokens"] for row in metrics) == stats["max_evidence_tokens"] == 100000
    print(f"PASS: {len(manifest['included'])} artifact checksums, JSON parsing, six paired prediction files and Full score arithmetic")


if __name__ == "__main__":
    main()
