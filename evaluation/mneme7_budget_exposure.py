import argparse
import hashlib
import json
from pathlib import Path


DEFAULT_BUDGETS = (8_000, 16_000, 24_000, 48_000, 100_000)


class BudgetExposureAudit:

    def __init__(self, rows: list[dict], budgets: tuple[int, ...]):
        self.rows = rows
        self.budgets = budgets

    def __call__(self) -> dict:
        return {
            "rows": len(self.rows),
            "evidence_tokens": self._distribution("evidence_tokens"),
            "item_count": self._distribution("item_count"),
            "item_cap": self._item_cap(),
            "evolution_route": self._route_summary(),
            "budgets": {
                str(budget): self._budget_summary(budget)
                for budget in self.budgets
            },
        }

    def _distribution(self, key: str) -> dict:
        values = sorted(row[key] for row in self.rows)
        return {
            "min": values[0],
            "p25": self._quantile(values, 0.25),
            "p50": self._quantile(values, 0.50),
            "p75": self._quantile(values, 0.75),
            "p90": self._quantile(values, 0.90),
            "p95": self._quantile(values, 0.95),
            "max": values[-1],
            "mean": sum(values) / len(values),
        }

    def _item_cap(self) -> dict:
        capped = sum(row["item_count"] == row["top_k"] for row in self.rows)
        return {"n": capped, "rate": capped / len(self.rows)}

    def _route_summary(self) -> dict:
        routed = [row for row in self.rows if row.get("evolution_route", False)]
        return {
            "n": len(routed),
            "rate": len(routed) / len(self.rows),
            "evidence_tokens": self._distribution_for(routed, "evidence_tokens"),
        }

    def _budget_summary(self, budget: int) -> dict:
        affected = [row for row in self.rows if row["evidence_tokens"] > budget]
        total = sum(row["evidence_tokens"] for row in self.rows)
        retained = sum(min(row["evidence_tokens"], budget) for row in self.rows)
        routed = [row for row in self.rows if row.get("evolution_route", False)]
        plain = [row for row in self.rows if not row.get("evolution_route", False)]
        return {
            "affected_n": len(affected),
            "affected_rate": len(affected) / len(self.rows),
            "hypothetical_token_reduction": 1 - retained / total,
            "route_affected_rate": self._affected_rate(routed, budget),
            "non_route_affected_rate": self._affected_rate(plain, budget),
        }

    def _distribution_for(self, rows: list[dict], key: str) -> dict:
        values = sorted(row[key] for row in rows)
        return {
            "p50": self._quantile(values, 0.50),
            "p90": self._quantile(values, 0.90),
            "p95": self._quantile(values, 0.95),
            "mean": sum(values) / len(values),
        }

    @staticmethod
    def _affected_rate(rows: list[dict], budget: int) -> float:
        return sum(row["evidence_tokens"] > budget for row in rows) / len(rows)

    @staticmethod
    def _quantile(values: list[int], fraction: float) -> float:
        position = (len(values) - 1) * fraction
        lower = int(position)
        upper = min(lower + 1, len(values) - 1)
        return values[lower] + (values[upper] - values[lower]) * (position - lower)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--budgets", nargs="+", type=int, default=DEFAULT_BUDGETS)
    args = parser.parse_args()
    raw = args.source.read_bytes()
    rows = [json.loads(line) for line in raw.splitlines()]
    report = {
        "status": "development exposure audit; no quality conclusion",
        "source": str(args.source),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        **BudgetExposureAudit(rows, tuple(args.budgets))(),
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
