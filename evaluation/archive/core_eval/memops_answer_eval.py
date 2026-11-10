import argparse
import json
import math
import os
import random
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

from tokenizers import Tokenizer

from eval.external_recall import FrameRecall
from eval.frozen_context_eval import EvaluationItem, FrozenContextEvaluator
from eval.llm import chat_for, load_env
from eval.memops_recall import MemOpsConversation, MemOpsLoader
from mneme.activation import ActivationField
from mneme.composition import EvidenceComposer


READER_PROMPT = """Answer the question using only the conversation memory below.
Before answering, internally identify the requested operation, subject, relation, category, and time scope. Keep each fact's owner, entity or event identity, value, and source separate. Apply updates before reading a current state. Exclude plans, failed or hypothetical actions, facts about another person, and duplicate mentions of the same entity or event.
If the required evidence is missing or conflicting, answer "No information". Output only the shortest final answer without reasoning.

Memory:
{ctx}

Question: {q}
Answer:"""
METHODS = ("mneme3_frozen", "mneme4_0.9.2")


class MemOpsAnswerPair:

    def __init__(
        self,
        frozen_rows: Path,
        tokenizer_path: Path,
        input_token_budget: int,
    ) -> None:
        self.frozen = {
            row["question_id"]: row
            for line in frozen_rows.read_text().splitlines()
            if line.strip()
            for row in (json.loads(line),)
        }
        self.tokenizer = Tokenizer.from_file(str(tokenizer_path))
        self.input_token_budget = input_token_budget
        self.builder = FrameRecall((40,))

    def items(
        self,
        conversations: list[MemOpsConversation],
    ) -> tuple[list[EvaluationItem], list[EvaluationItem], dict]:
        baseline = []
        composed = []
        audits = []
        for position, conversation in enumerate(conversations, 1):
            left, right, rows = self._conversation(conversation)
            baseline.extend(left)
            composed.extend(right)
            audits.extend(rows)
            print(
                f"froze MemOps answer contexts {position}/{len(conversations)}",
                flush=True,
            )
        return baseline, composed, self._audit(audits)

    def _conversation(
        self,
        conversation: MemOpsConversation,
    ) -> tuple[list[EvaluationItem], list[EvaluationItem], list[dict]]:
        index = self.builder.build_index(conversation.turns)
        activation = ActivationField(index)
        composer = EvidenceComposer(index, scope_owner="user")
        baseline = []
        composed = []
        audits = []
        for question in conversation.questions:
            if not question.answer or not question.judge_rubric:
                raise ValueError(f"missing answer metadata for {question.id}")
            active = activation(question.text)
            direct_ids = list(dict.fromkeys(
                item.unit.source_id
                for item in active
            ))
            composed_ids = list(composer(active, question.text).source_ids)
            self._assert_frozen(question.id, direct_ids, composed_ids)
            left_context, left_ids, left_tokens = self._admit(
                question.text,
                direct_ids,
                index.source_texts,
            )
            right_context, right_ids, right_tokens = self._admit(
                question.text,
                composed_ids,
                index.source_texts,
            )
            item = EvaluationItem(
                id=question.id,
                benchmark="memops",
                group=question.operation,
                question=question.text,
                answer=question.answer,
                context=left_context,
                rubric=question.judge_rubric,
            )
            baseline.append(item)
            composed.append(replace(item, context=right_context))
            audits.append({
                "id": question.id,
                "operation": question.operation,
                "category": question.category,
                "baseline_source_n": len(left_ids),
                "composed_source_n": len(right_ids),
                "baseline_tokens": left_tokens,
                "composed_tokens": right_tokens,
                "contexts_identical": left_ids == right_ids,
            })
        return baseline, composed, audits

    def _admit(
        self,
        question: str,
        source_ids: list[str],
        source_texts: dict[str, str],
    ) -> tuple[str, tuple[str, ...], int]:
        selected = []
        context = ""
        used = self._tokens(READER_PROMPT.format(ctx="", q=question))
        for source_id in source_ids:
            block = source_texts[source_id]
            separator = "" if not context else "\n\n"
            block_tokens = self._tokens(separator + block)
            if used + block_tokens > self.input_token_budget:
                continue
            context += separator + block
            selected.append(source_id)
            used += block_tokens
            if len(selected) % 32 == 0:
                used = self._prompt_tokens(context, question)
        used = self._prompt_tokens(context, question)
        while used > self.input_token_budget:
            selected.pop()
            context = "\n\n".join(source_texts[source_id] for source_id in selected)
            used = self._prompt_tokens(context, question)
        return context, tuple(selected), used

    def _assert_frozen(
        self,
        question_id: str,
        baseline: list[str],
        composed: list[str],
    ) -> None:
        row = self.frozen[question_id]
        if baseline[:40] != row["baseline_source_ids"]:
            raise ValueError(f"Mneme3 frozen sequence mismatch for {question_id}")
        if composed[:40] != row["composed_source_ids"]:
            raise ValueError(f"Mneme4 frozen sequence mismatch for {question_id}")

    def _prompt_tokens(self, context: str, question: str) -> int:
        return self._tokens(READER_PROMPT.format(ctx=context, q=question))

    def _tokens(self, text: str) -> int:
        return len(self.tokenizer.encode(text).ids)

    @staticmethod
    def _audit(rows: list[dict]) -> dict:
        return {
            "questions": len(rows),
            "changed_contexts": sum(not row["contexts_identical"] for row in rows),
            "identical_contexts": sum(row["contexts_identical"] for row in rows),
            "mean_source_n": {
                method: sum(row[f"{prefix}_source_n"] for row in rows) / len(rows)
                for method, prefix in zip(METHODS, ("baseline", "composed"))
            },
            "max_input_tokens": {
                method: max(row[f"{prefix}_tokens"] for row in rows)
                for method, prefix in zip(METHODS, ("baseline", "composed"))
            },
        }


class MemOpsAnswerEvaluation:

    def __init__(self, output: Path, workers: int, input_token_budget: int) -> None:
        self.output = output
        self.workers = workers
        self.input_token_budget = input_token_budget

    def __call__(
        self,
        baseline: list[EvaluationItem],
        composed: list[EvaluationItem],
        repetitions: int,
    ) -> dict:
        reports = []
        for repetition in range(repetitions):
            reports.append(self._repetition(baseline, composed, repetition))
        return {
            "repetitions": reports,
            "aggregate": self._aggregate(reports),
        }

    def _repetition(
        self,
        baseline: list[EvaluationItem],
        composed: list[EvaluationItem],
        repetition: int,
    ) -> dict:
        items = [
            replace(item, id=f"{item.id}|{method}")
            for method, values in zip(METHODS, (baseline, composed))
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
            reader_prompt=READER_PROMPT,
        )
        evaluator.run(items)
        rows = {
            row["id"]: row
            for line in cache.read_text().splitlines()
            if line.strip()
            for row in (json.loads(line),)
        }
        return self._paired(rows, baseline)

    @staticmethod
    def _paired(rows: dict[str, dict], items: list[EvaluationItem]) -> dict:
        grouped = defaultdict(list)
        deltas = []
        f1_deltas = []
        for item in items:
            left = rows[f"{item.id}|{METHODS[0]}"]
            right = rows[f"{item.id}|{METHODS[1]}"]
            delta = right["judge"] - left["judge"]
            deltas.append(delta)
            f1_deltas.append(right["f1"] - left["f1"])
            grouped[item.group].append((left, right))
        return {
            "n": len(items),
            "methods": {
                method: {
                    "accuracy": sum(rows[f"{item.id}|{method}"]["judge"] for item in items) / len(items),
                    "token_f1": sum(rows[f"{item.id}|{method}"]["f1"] for item in items) / len(items),
                }
                for method in METHODS
            },
            "accuracy_delta": sum(deltas) / len(deltas),
            "token_f1_delta": sum(f1_deltas) / len(f1_deltas),
            "wins": sum(delta > 0 for delta in deltas),
            "losses": sum(delta < 0 for delta in deltas),
            "ties": sum(delta == 0 for delta in deltas),
            "sign_test_p": MemOpsAnswerEvaluation._sign_test(deltas),
            "operations": {
                name: {
                    "n": len(values),
                    "accuracy_delta": sum(right["judge"] - left["judge"] for left, right in values) / len(values),
                }
                for name, values in sorted(grouped.items())
            },
        }

    @staticmethod
    def _aggregate(reports: list[dict]) -> dict:
        values = [report["accuracy_delta"] for report in reports]
        mean = sum(values) / len(values)
        return {
            "accuracy_delta_mean": mean,
            "accuracy_delta_std": math.sqrt(
                sum((value - mean) ** 2 for value in values) / len(values)
            ),
            "mneme3_accuracy_mean": sum(report["methods"][METHODS[0]]["accuracy"] for report in reports) / len(reports),
            "mneme4_accuracy_mean": sum(report["methods"][METHODS[1]]["accuracy"] for report in reports) / len(reports),
            "wins_mean": sum(report["wins"] for report in reports) / len(reports),
            "losses_mean": sum(report["losses"] for report in reports) / len(reports),
        }

    @staticmethod
    def _sign_test(deltas: list[int]) -> float:
        wins = sum(delta > 0 for delta in deltas)
        losses = sum(delta < 0 for delta in deltas)
        trials = wins + losses
        if trials == 0:
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
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--frozen-rows", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--env", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--input-token-budget", type=int, default=24_000)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--freeze-only", action="store_true")
    args = parser.parse_args()
    conversations = list(MemOpsLoader(args.data_root, "heldout").load(limit=args.limit))
    baseline, composed, audit = MemOpsAnswerPair(
        args.frozen_rows,
        args.tokenizer,
        args.input_token_budget,
    ).items(conversations)
    report = {
        "protocol": {
            "dataset": "MemOps heldout",
            "comparison": list(METHODS),
            "reader_input_token_budget": args.input_token_budget,
            "source_admission": "complete atomic sources",
            "reader_prompt": "memops_answer_v1",
            "judge_prompt": "memops_released_rubric_v1",
        },
        "context_audit": audit,
    }
    if not args.freeze_only:
        load_runtime_env(args.env)
        report["answer_evaluation"] = MemOpsAnswerEvaluation(
            args.output,
            args.workers,
            args.input_token_budget,
        )(baseline, composed, args.repetitions)
        report["models"] = {
            "reader": os.environ["QWEN_READER_MODEL"],
            "judge": os.environ["MINIMAX_JUDGE_MODEL"],
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
