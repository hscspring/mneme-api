import argparse
import json
import math
import os
import random
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

from eval.frozen_context_eval import EvaluationItem, FrozenContextEvaluator
from eval.llm import chat_for, load_env
from eval.memops_package_contexts import READER_PROMPT


METHODS = ("mnemekit_0.9.2", "mnemekit_0.10.0")


class PackageAnswerPair:

    def __init__(
        self,
        baseline_path: Path,
        candidate_path: Path,
        benchmark: str = "memops",
    ) -> None:
        self.baseline_rows = self._load(baseline_path)
        self.candidate_rows = self._load(candidate_path)
        self.benchmark = benchmark

    def items(self) -> tuple[list[EvaluationItem], list[EvaluationItem], dict]:
        if self.baseline_rows.keys() != self.candidate_rows.keys():
            raise ValueError("package evaluations contain different question IDs")
        baseline = []
        candidate = []
        changed = 0
        for question_id in sorted(self.baseline_rows):
            left = self.baseline_rows[question_id]
            right = self.candidate_rows[question_id]
            for key in ("operation", "category", "question", "answer", "rubric"):
                if left[key] != right[key]:
                    raise ValueError(f"paired metadata mismatch for {question_id}: {key}")
            item = EvaluationItem(
                id=question_id,
                benchmark=self.benchmark,
                group=(
                    left["operation"]
                    if self.benchmark == "memops"
                    else "abstention"
                    if self.benchmark == "longmemeval"
                    and question_id.endswith("_abs")
                    else left["category"]
                ),
                question=left["question"],
                answer=left["answer"],
                context=left["context"],
                rubric={
                    name: tuple(values)
                    for name, values in left["rubric"].items()
                },
            )
            baseline.append(item)
            candidate.append(replace(item, context=right["context"]))
            changed += left["context"] != right["context"]
        return baseline, candidate, {
            "questions": len(baseline),
            "changed_contexts": changed,
            "identical_contexts": len(baseline) - changed,
            "mean_evidence_n": {
                method: sum(row["evidence_n"] for row in rows.values()) / len(rows)
                for method, rows in zip(
                    METHODS,
                    (self.baseline_rows, self.candidate_rows),
                )
            },
            "mean_source_n": {
                method: sum(row["source_n"] for row in rows.values()) / len(rows)
                for method, rows in zip(
                    METHODS,
                    (self.baseline_rows, self.candidate_rows),
                )
            },
            "max_input_tokens": {
                method: max(row["input_tokens"] for row in rows.values())
                for method, rows in zip(
                    METHODS,
                    (self.baseline_rows, self.candidate_rows),
                )
            },
        }

    @staticmethod
    def _load(path: Path) -> dict[str, dict]:
        return {
            row["id"]: row
            for line in path.open()
            if line.strip()
            for row in (json.loads(line),)
        }


class PackageAnswerEvaluation:

    def __init__(
        self,
        output: Path,
        workers: int,
        input_token_budget: int,
        reader_prompt: str | None = READER_PROMPT,
    ) -> None:
        self.output = output
        self.workers = workers
        self.input_token_budget = input_token_budget
        self.reader_prompt = reader_prompt

    def __call__(
        self,
        baseline: list[EvaluationItem],
        candidate: list[EvaluationItem],
        repetitions: int,
    ) -> dict:
        reports = [
            self._repetition(baseline, candidate, repetition)
            for repetition in range(repetitions)
        ]
        return {
            "repetitions": reports,
            "aggregate": self._aggregate(reports),
        }

    def _repetition(
        self,
        baseline: list[EvaluationItem],
        candidate: list[EvaluationItem],
        repetition: int,
    ) -> dict:
        items = [
            replace(item, id=f"{item.id}|{method}")
            for method, values in zip(METHODS, (baseline, candidate))
            for item in values
        ]
        random.Random(4 + repetition).shuffle(items)
        cache = self.output.parent / f"{self.output.stem}_rep{repetition}.jsonl"
        evaluator = FrozenContextEvaluator(
            chat_for("qwen", "reader"),
            chat_for("minimax", "judge"),
            cache,
            self.workers,
            input_token_budget=self.input_token_budget,
            fixed_source_context=True,
            reader_prompt=self.reader_prompt,
        )
        evaluator.run(items)
        rows = evaluator.cache
        cache.write_text("".join(
            json.dumps(rows[row_id], ensure_ascii=False) + "\n"
            for row_id in sorted(rows)
        ))
        return self._paired(rows, baseline)

    @staticmethod
    def _paired(rows: dict[str, dict], items: list[EvaluationItem]) -> dict:
        benchmark = items[0].benchmark
        accuracy_items = [
            item
            for item in items
            if benchmark != "locomo" or item.group != "5"
        ]
        f1_items = [
            item
            for item in accuracy_items
            if benchmark != "longmemeval"
            or not item.group.startswith((
                "abstention",
                "single-session-preference",
            ))
        ]
        grouped = defaultdict(list)
        deltas = []
        f1_deltas = []
        for item in items:
            left = rows[f"{item.id}|{METHODS[0]}"]
            right = rows[f"{item.id}|{METHODS[1]}"]
            grouped[item.group].append((left, right))
        for item in accuracy_items:
            left = rows[f"{item.id}|{METHODS[0]}"]
            right = rows[f"{item.id}|{METHODS[1]}"]
            deltas.append(right["judge"] - left["judge"])
        for item in f1_items:
            left = rows[f"{item.id}|{METHODS[0]}"]
            right = rows[f"{item.id}|{METHODS[1]}"]
            f1_deltas.append(right["f1"] - left["f1"])
        return {
            "n": len(accuracy_items),
            "methods": {
                method: {
                    "accuracy": sum(
                        rows[f"{item.id}|{method}"]["judge"]
                        for item in accuracy_items
                    ) / len(accuracy_items),
                    "token_f1": sum(
                        rows[f"{item.id}|{method}"]["f1"]
                        for item in f1_items
                    ) / len(f1_items),
                }
                for method in METHODS
            },
            "accuracy_delta": sum(deltas) / len(deltas),
            "token_f1_delta": sum(f1_deltas) / len(f1_deltas),
            "wins": sum(delta > 0 for delta in deltas),
            "losses": sum(delta < 0 for delta in deltas),
            "ties": sum(delta == 0 for delta in deltas),
            "sign_test_p": PackageAnswerEvaluation._sign_test(deltas),
            "groups": {
                name: {
                    "n": len(values),
                    "accuracy_delta": sum(
                        right["judge"] - left["judge"]
                        for left, right in values
                    ) / len(values),
                }
                for name, values in sorted(grouped.items())
            },
        }

    @staticmethod
    def _aggregate(reports: list[dict]) -> dict:
        accuracy_deltas = [report["accuracy_delta"] for report in reports]
        f1_deltas = [report["token_f1_delta"] for report in reports]
        accuracy_mean = sum(accuracy_deltas) / len(accuracy_deltas)
        f1_mean = sum(f1_deltas) / len(f1_deltas)
        groups = reports[0]["groups"]
        return {
            "accuracy_delta_mean": accuracy_mean,
            "accuracy_delta_std": math.sqrt(
                sum((value - accuracy_mean) ** 2 for value in accuracy_deltas)
                / len(accuracy_deltas)
            ),
            "accuracy_mean": {
                method: sum(
                    report["methods"][method]["accuracy"]
                    for report in reports
                ) / len(reports)
                for method in METHODS
            },
            "token_f1_delta_mean": f1_mean,
            "token_f1_delta_std": math.sqrt(
                sum((value - f1_mean) ** 2 for value in f1_deltas)
                / len(f1_deltas)
            ),
            "token_f1_mean": {
                method: sum(
                    report["methods"][method]["token_f1"]
                    for report in reports
                ) / len(reports)
                for method in METHODS
            },
            "groups": {
                group: {
                    "n": groups[group]["n"],
                    "accuracy_delta_mean": sum(
                        report["groups"][group]["accuracy_delta"]
                        for report in reports
                    ) / len(reports),
                }
                for group in groups
            },
            "wins_mean": sum(report["wins"] for report in reports) / len(reports),
            "losses_mean": sum(report["losses"] for report in reports) / len(reports),
        }

    @staticmethod
    def _sign_test(deltas: list[int]) -> float:
        wins = sum(delta > 0 for delta in deltas)
        losses = sum(delta < 0 for delta in deltas)
        trials = wins + losses
        if not trials:
            return 1.0
        tail = sum(
            math.comb(trials, count)
            for count in range(min(wins, losses) + 1)
        ) / 2 ** trials
        return min(1.0, 2.0 * tail)


def load_runtime_env(path: Path) -> None:
    load_env()
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            os.environ[name] = value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-contexts", type=Path, required=True)
    parser.add_argument("--candidate-contexts", type=Path, required=True)
    parser.add_argument("--env", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--benchmark",
        choices=("memops", "locomo", "longmemeval"),
        default="memops",
    )
    parser.add_argument("--input-token-budget", type=int, default=24_000)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()
    baseline, candidate, audit = PackageAnswerPair(
        args.baseline_contexts,
        args.candidate_contexts,
        args.benchmark,
    ).items()
    load_runtime_env(args.env)
    report = {
        "protocol": {
            "dataset": {
                "memops": "MemOps heldout",
                "locomo": "LoCoMo",
                "longmemeval": "LongMemEval-S",
            }[args.benchmark],
            "comparison": list(METHODS),
            "reader_input_token_budget": args.input_token_budget,
            "retrieval_top_k": 100 if args.benchmark == "memops" else 40,
            "source_admission": "complete Evidence items",
            "reader_prompt": f"{args.benchmark}_answer_v1",
            "judge_prompt": f"{args.benchmark}_judge_v1",
        },
        "context_audit": audit,
        "answer_evaluation": PackageAnswerEvaluation(
            args.output,
            args.workers,
            args.input_token_budget,
            READER_PROMPT if args.benchmark == "memops" else None,
        )(baseline, candidate, args.repetitions),
        "models": {
            "reader": os.environ["QWEN_READER_MODEL"],
            "judge": os.environ["MINIMAX_JUDGE_MODEL"],
        },
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
