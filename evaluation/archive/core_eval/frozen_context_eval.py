import argparse
import json
import random
import threading
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import asdict, dataclass
from enum import Enum
from itertools import repeat
from pathlib import Path

from eval.candidate_funnel import (
    DATA_DIR,
    RESULTS_DIR,
    LoCoMoFunnelAudit,
    LongMemEvalFunnelQuestion,
)
from eval.aml_longmemeval import LongMemEvalProtocol
from eval.dialogue_context import DialogueContext
from eval.evidence_projection import EvidenceProjection
from eval.llm import Chat, chat_for
from eval.locomo import (
    ABSTAIN,
    CAT_NAME,
    JUDGE_PROMPT,
    READER_PROMPT,
    judge_hit,
    token_f1,
)
from eval.locomo_data import format_locomo_turn
from eval.longmemeval import (
    JUDGE_CRIT,
    JUDGE_DEFAULT,
    JUDGE_TMPL,
    READER,
)


FRAME_NAME = "speaker_discourse_activation_bound_ontology_frame"
REINSTATEMENT_NAME = f"{FRAME_NAME}_coactive_reinstatement"
EXCHANGE_NAME = f"{FRAME_NAME}_exchange"
TAG_NAME = f"{FRAME_NAME}_tag_evidence"
ACTIVATION_PACKET_NAME = (
    f"{REINSTATEMENT_NAME}_tag_responsibility_evidence_activation_packet"
)
ACTIVATION_PRESERVING_PACKET_NAME = (
    f"{REINSTATEMENT_NAME}_tag_responsibility_evidence_"
    "activation_preserving_packet"
)
READER_MAX_TOKENS = 512
CHAT_TEMPLATE_RESERVE = 32
ACTIVATION_POOL_DEPTH = 40
MEMOPS_JUDGE_PROMPT = """Judge whether the prediction correctly answers the question under the supplied rubric.
Treat acceptable paraphrases as correct. Harmless extra information does not hurt. A prediction is incorrect if it omits required information, contradicts the reference, includes forbidden information, or contains harmful extra information.
Output exactly one word: yes or no.
Question: {q}
Reference: {gold}
Rubric: {rubric}
Prediction: {pred}
One word:"""


class DiscourseCompletion(str, Enum):
    NONE = "none"
    EXCHANGE = "exchange"
    ACTIVATION_BOUNDED = "activation_bounded"


@dataclass(frozen=True)
class RetrievalVariant:
    artifact_name: str
    candidate_suffix: str
    resolve_speaker: bool
    discourse_access: bool
    activation_field: bool
    bound_ontology: bool
    frame_activation: bool
    discourse_reinstatement: bool
    discourse_completion: DiscourseCompletion
    evidence_projection: EvidenceProjection | None = None

    @property
    def options(self) -> dict[str, object]:
        return {
            "resolve_speaker": self.resolve_speaker,
            "discourse_access": self.discourse_access,
            "activation_field": self.activation_field,
            "bound_ontology": self.bound_ontology,
            "frame_activation": self.frame_activation,
            "discourse_reinstatement": self.discourse_reinstatement,
            "evidence_projection": self.evidence_projection,
        }


VARIANTS = {
    "frame": RetrievalVariant(
        FRAME_NAME,
        FRAME_NAME,
        True,
        True,
        True,
        True,
        True,
        False,
        DiscourseCompletion.NONE,
        None,
    ),
    "reinstatement": RetrievalVariant(
        REINSTATEMENT_NAME,
        REINSTATEMENT_NAME,
        True,
        True,
        True,
        True,
        True,
        True,
        DiscourseCompletion.NONE,
        None,
    ),
    "exchange": RetrievalVariant(
        EXCHANGE_NAME,
        FRAME_NAME,
        True,
        True,
        True,
        True,
        True,
        False,
        DiscourseCompletion.EXCHANGE,
        None,
    ),
    "bounded_exchange": RetrievalVariant(
        f"{FRAME_NAME}_activation_bounded_exchange",
        FRAME_NAME,
        True,
        True,
        True,
        True,
        True,
        False,
        DiscourseCompletion.ACTIVATION_BOUNDED,
        None,
    ),
    "v1": RetrievalVariant(
        "grouped_v1",
        "",
        False,
        False,
        False,
        False,
        False,
        False,
        DiscourseCompletion.NONE,
        None,
    ),
    "segment": RetrievalVariant(
        f"{FRAME_NAME}_segment_evidence",
        f"{FRAME_NAME}_segment_evidence",
        True,
        True,
        True,
        True,
        True,
        False,
        DiscourseCompletion.NONE,
        EvidenceProjection.SEGMENT,
    ),
    "interaction": RetrievalVariant(
        f"{FRAME_NAME}_interaction_evidence",
        f"{FRAME_NAME}_interaction_evidence",
        True,
        True,
        True,
        True,
        True,
        False,
        DiscourseCompletion.NONE,
        EvidenceProjection.INTERACTION,
    ),
    "tag": RetrievalVariant(
        TAG_NAME,
        TAG_NAME,
        True,
        True,
        True,
        True,
        True,
        False,
        DiscourseCompletion.NONE,
        EvidenceProjection.TAG,
    ),
    "tag_dedup": RetrievalVariant(
        f"{FRAME_NAME}_tag_dedup_evidence",
        f"{FRAME_NAME}_tag_dedup_evidence",
        True,
        True,
        True,
        True,
        True,
        False,
        DiscourseCompletion.NONE,
        EvidenceProjection.TAG_DEDUP,
    ),
    "tag_graph_dedup": RetrievalVariant(
        f"{FRAME_NAME}_tag_graph_dedup_evidence",
        f"{FRAME_NAME}_tag_graph_dedup_evidence",
        True,
        True,
        True,
        True,
        True,
        False,
        DiscourseCompletion.NONE,
        EvidenceProjection.TAG_GRAPH_DEDUP,
    ),
    "activation_packet": RetrievalVariant(
        ACTIVATION_PACKET_NAME,
        ACTIVATION_PACKET_NAME,
        True,
        True,
        True,
        True,
        True,
        True,
        DiscourseCompletion.NONE,
        EvidenceProjection.TAG_RESPONSIBILITY,
    ),
    "activation_preserving_packet": RetrievalVariant(
        ACTIVATION_PRESERVING_PACKET_NAME,
        ACTIVATION_PRESERVING_PACKET_NAME,
        True,
        True,
        True,
        True,
        True,
        True,
        DiscourseCompletion.NONE,
        EvidenceProjection.TAG_RESPONSIBILITY,
    ),
}


def read_jsonl(path: Path) -> list[dict]:
    with path.open() as source:
        return [
            json.loads(line)
            for line in source
            if line.strip()
        ]


@dataclass(frozen=True)
class EvaluationItem:
    id: str
    benchmark: str
    group: str
    question: str
    answer: str
    context: str
    fallback_context: str = ""
    rubric: dict[str, tuple[str, ...]] | None = None


class CandidateContextLoader:

    def __init__(
        self,
        variant: RetrievalVariant,
        top_k: int,
        source_budget: int | None = None,
        build_workers: int = 16,
    ):
        self.variant = variant
        self.top_k = top_k
        self.source_budget = source_budget
        self.build_workers = build_workers

    def load(self, benchmark: str) -> list[EvaluationItem]:
        if benchmark == "locomo":
            return self._locomo()
        if benchmark == "longmemeval":
            return self._longmemeval()
        raise ValueError(f"unsupported benchmark: {benchmark}")

    def _locomo(self) -> list[EvaluationItem]:
        data = json.loads((DATA_DIR / "locomo10.json").read_text())
        ranked = self._ranked("locomo")
        audit = LoCoMoFunnelAudit(
            DATA_DIR / "locomo10.json",
            Path("/nonexistent"),
            **self.variant.options,
        )
        items = []
        for ci, conversation in enumerate(data):
            dialogue = self._locomo_dialogue(conversation)
            missing = any(
                f"{ci}:{qi}" not in ranked
                for qi in range(len(conversation["qa"]))
            )
            index = audit._build(conversation) if missing else None
            for qi, qa in enumerate(conversation["qa"]):
                question_id = f"{ci}:{qi}"
                candidates = ranked.get(question_id)
                if candidates is None:
                    if index is None:
                        raise RuntimeError(f"missing index for {question_id}")
                    candidates = audit.funnel._candidates(index, qa["question"])
                candidates = candidates[:max(
                    self.top_k,
                    ACTIVATION_POOL_DEPTH,
                )]
                turn_ids = [item["turn_id"] for item in candidates]
                anchors = turn_ids[:self.top_k]
                baseline_context = dialogue.render_anchors(anchors)
                context = self._context(dialogue, candidates)
                items.append(EvaluationItem(
                    id=question_id,
                    benchmark="locomo",
                    group=str(qa["category"]),
                    question=qa["question"],
                    answer=str(qa.get("answer", "")),
                    context=context,
                    fallback_context=(
                        baseline_context
                        if self.variant.discourse_completion != DiscourseCompletion.NONE
                        else ""
                    ),
                ))
            print(f"froze LoCoMo {ci + 1}/{len(data)}", flush=True)
        return items

    def _longmemeval(self) -> list[EvaluationItem]:
        data = json.loads((DATA_DIR / "lme_s.json").read_text())
        ranked = self._ranked("longmemeval")
        missing_rows = [row for row in data if row["question_id"] not in ranked]
        if missing_rows:
            with ProcessPoolExecutor(max_workers=self.build_workers) as pool:
                built = pool.map(
                    _build_lme_context,
                    missing_rows,
                    repeat(self.variant),
                    repeat(self.top_k),
                    chunksize=1,
                )
                ranked.update(dict(built))
        items = []
        for row in data:
            question_id = row["question_id"]
            candidates = ranked[question_id]
            turn_ids = [item["turn_id"] for item in candidates]
            dialogue = self._lme_dialogue(row)
            anchors = turn_ids[:self.top_k]
            baseline_context = dialogue.render_anchors(anchors)
            context = self._context(dialogue, candidates)
            items.append(EvaluationItem(
                id=question_id,
                benchmark="longmemeval",
                group=(
                    "abstention"
                    if question_id.endswith("_abs")
                    else row["question_type"]
                ),
                question=row["question"],
                answer=str(row["answer"]),
                context=context,
                fallback_context=(
                    baseline_context
                    if self.variant.discourse_completion != DiscourseCompletion.NONE
                    else ""
                ),
            ))
        return items

    def _ranked(self, benchmark: str) -> dict[str, list[dict]]:
        suffix = f"_{self.variant.candidate_suffix}" if self.variant.candidate_suffix else ""
        path = RESULTS_DIR / f"candidate_funnel_{benchmark}{suffix}.jsonl"
        return {
            row["question_id"]: row["candidates"][:max(
                    self.top_k,
                    ACTIVATION_POOL_DEPTH,
                )]
            for row in read_jsonl(path)
        }

    def _context(
        self,
        dialogue: DialogueContext,
        candidates: list[dict],
    ) -> str:
        if self.variant.evidence_projection is not None:
            if self.source_budget is not None:
                return self._render_sources(candidates)
            return "\n\n".join(
                item["content"]
                for item in candidates[:self.top_k]
            )
        turn_ids = [item["turn_id"] for item in candidates]
        return self._render(
            dialogue,
            turn_ids[:self.top_k],
            turn_ids,
        )

    def _render_sources(self, candidates: list[dict]) -> str:
        seen = set()
        sources = []
        for candidate in candidates[:self.top_k]:
            for span in candidate["spans"]:
                if span["source_id"] in seen:
                    continue
                seen.add(span["source_id"])
                sources.append(span["text"])
                if len(sources) == self.source_budget:
                    return "\n".join(sources)
        return "\n".join(sources)

    def _render(
        self,
        dialogue: DialogueContext,
        anchors: list[str],
        activated: list[str],
    ) -> str:
        completion = self.variant.discourse_completion
        if completion == DiscourseCompletion.NONE:
            return dialogue.render_anchors(anchors)
        if completion == DiscourseCompletion.EXCHANGE:
            return dialogue.render_exchange(anchors)
        return dialogue.render_exchange(
            anchors,
            activated[:ACTIVATION_POOL_DEPTH],
        )

    def _locomo_dialogue(self, conversation: dict) -> DialogueContext:
        sessions = conversation["conversation"]
        turns = []
        for key in sorted(
            (
                key
                for key in sessions
                if key.startswith("session_")
                and not key.endswith("_date_time")
            ),
            key=lambda key: int(key.split("_")[1]),
        ):
            date = sessions[f"{key}_date_time"]
            for position, utterance in enumerate(sessions[key]):
                turns.append((
                    utterance["dia_id"],
                    f"{key}:x{position // 2}",
                    format_locomo_turn(date, utterance),
                ))
        return DialogueContext(turns)

    def _lme_dialogue(self, row: dict) -> DialogueContext:
        turns = []
        for session_id, date, session in zip(
            row["haystack_session_ids"],
            row["haystack_dates"],
            row["haystack_sessions"],
        ):
            exchange_position = -1
            exchange_id = None
            for position, turn in enumerate(session):
                if exchange_id is None or turn["role"] == "user":
                    exchange_position += 1
                    exchange_id = f"{session_id}:x{exchange_position}"
                turns.append((
                    f"{session_id}:{position}",
                    exchange_id,
                    f"[{date}] {turn['role']}: {turn['content']}",
                ))
        return DialogueContext(turns)


class FrozenContextEvaluator:

    def __init__(
        self,
        reader: Chat,
        judge: Chat,
        cache_path: Path,
        workers: int,
        input_token_budget: int | None = None,
        token_counter: Chat | None = None,
        reader_context_limit: int | None = None,
        aml_protocol: LongMemEvalProtocol | None = None,
        fixed_source_context: bool = False,
        reader_prompt: str | None = None,
    ):
        self.reader = reader
        self.judge = judge
        self.cache_path = cache_path
        self.workers = workers
        self.input_token_budget = input_token_budget
        self.token_counter = token_counter
        self.reader_context_limit = reader_context_limit
        self.aml_protocol = aml_protocol
        self.fixed_source_context = fixed_source_context
        self.reader_prompt = reader_prompt
        self.cache = self._load_cache()
        self.lock = threading.Lock()

    def run(self, items: list[EvaluationItem]) -> dict:
        rows_by_id = {}
        pending = items
        for attempt in range(1, 6):
            failed = []
            with ThreadPoolExecutor(max_workers=self.workers) as pool:
                results = pool.map(self._safe_score, pending)
                for position, (item, row, error) in enumerate(
                    results,
                    1,
                ):
                    if error is None:
                        rows_by_id[item.id] = row
                    else:
                        failed.append(item)
                        print(f"deferred {item.id}: {error}", flush=True)
                    if position % 25 == 0 or position == len(pending):
                        print(
                            f"evaluated {position}/{len(pending)} "
                            f"(attempt {attempt})",
                            flush=True,
                        )
            if not failed:
                break
            if attempt == 5:
                ids = ", ".join(item.id for item in failed)
                raise RuntimeError(f"evaluation failed after 5 attempts: {ids}")
            print(f"retrying {len(failed)} deferred items", flush=True)
            pending = failed
            time.sleep(10 * attempt)
        rows = [rows_by_id[item.id] for item in items]
        return self._report(items, rows)

    def _safe_score(
        self,
        item: EvaluationItem,
    ) -> tuple[EvaluationItem, dict | None, str | None]:
        try:
            return item, self._score(item), None
        except Exception as error:
            return item, None, f"{type(error).__name__}: {error}"

    def _score(self, item: EvaluationItem) -> dict:
        if item.id in self.cache:
            return self.cache[item.id]
        prompt, context_chars = self._fit_reader_prompt(item)
        prediction = self.reader(
            prompt,
            max_tokens=READER_MAX_TOKENS,
        )
        judge, f1 = self._judge(item, prediction)
        row = {
            "id": item.id,
            "benchmark": item.benchmark,
            "group": item.group,
            "prediction": prediction,
            "judge": judge,
            "f1": f1,
            "context_chars": context_chars,
        }
        with self.lock:
            self.cache[item.id] = row
            with self.cache_path.open("a") as output:
                output.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row

    def _fit_reader_prompt(self, item: EvaluationItem) -> tuple[str, int]:
        template = self._reader_prompt(item)
        if self.fixed_source_context:
            return template.format(ctx=item.context, q=item.question), len(item.context)
        render = lambda context: template.format(ctx=context, q=item.question)
        prompt = render(item.context)
        counter = self.token_counter or self.reader
        count, reported_limit = counter.token_count(prompt)
        limit = self.reader_context_limit or reported_limit
        budget = self.input_token_budget or (
            limit - READER_MAX_TOKENS - CHAT_TEMPLATE_RESERVE
        )
        if budget > limit:
            raise RuntimeError(
                f"reader context limit {limit} is below input budget {budget}"
            )
        if count <= budget:
            return prompt, len(item.context)
        context = item.fallback_context or item.context
        prompt = render(context)
        count, _ = counter.token_count(prompt)
        if count <= budget:
            return prompt, len(context)
        low, high = 0, len(context)
        while low < high:
            middle = (low + high + 1) // 2
            count, _ = counter.token_count(render(context[:middle]))
            if count <= budget:
                low = middle
            else:
                high = middle - 1
        boundary = context.rfind("\n", 0, low + 1)
        fitted = context[:boundary if boundary > 0 else low]
        print(
            f"trimmed {item.id} context from {len(item.context)} "
            f"to {len(fitted)} chars",
            flush=True,
        )
        return render(fitted), len(fitted)

    def _judge(self, item: EvaluationItem, prediction: str) -> tuple[int, float]:
        if self._is_abstention(item) and self.aml_protocol is None:
            return int(any(marker in prediction.lower() for marker in ABSTAIN)), 0.0
        if item.benchmark == "memops":
            if item.rubric is None:
                raise ValueError(f"missing MemOps judge rubric for {item.id}")
            prompt = MEMOPS_JUDGE_PROMPT.format(
                q=item.question,
                gold=item.answer,
                rubric=json.dumps(
                    item.rubric,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                pred=prediction,
            )
        elif item.benchmark == "locomo":
            prompt = JUDGE_PROMPT.format(
                q=item.question,
                gold=item.answer,
                pred=prediction,
            )
        else:
            if self.aml_protocol is not None:
                prompt = self.aml_protocol.accuracy_prompt(
                    item.question,
                    item.answer,
                    prediction,
                )
            else:
                criterion = JUDGE_CRIT.get(item.group, JUDGE_DEFAULT)
                prompt = JUDGE_TMPL.format(
                    crit=criterion,
                    q=item.question,
                    gold=item.answer,
                    pred=prediction,
                )
        verdict = self.judge(prompt, max_tokens=256)
        f1 = (
            0.0
            if item.group.startswith("single-session-preference")
            else token_f1(prediction, item.answer)
        )
        hit = (
            self.aml_protocol.judge_hit(verdict)
            if self.aml_protocol is not None and item.benchmark == "longmemeval"
            else self._memops_judge_hit(verdict)
            if item.benchmark == "memops"
            else judge_hit(verdict)
        )
        return hit, f1

    @staticmethod
    def _memops_judge_hit(verdict: str) -> int:
        final_line = verdict.strip().lower().splitlines()[-1].rstrip(".")
        return judge_hit(final_line)

    def _reader_prompt(self, item: EvaluationItem) -> str:
        if self.reader_prompt is not None:
            return self.reader_prompt
        if self.aml_protocol is not None and item.benchmark == "longmemeval":
            return self.aml_protocol.answer_prompt("{ctx}", "{q}")
        return READER_PROMPT if item.benchmark == "locomo" else READER

    def _is_abstention(self, item: EvaluationItem) -> bool:
        return (
            item.benchmark == "locomo"
            and item.group == "5"
        ) or item.group.startswith("abstention") or item.id.endswith("_abs")

    def _load_cache(self) -> dict[str, dict]:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.cache_path.exists():
            return {}
        return {
            row["id"]: row
            for row in read_jsonl(self.cache_path)
        }

    def _report(
        self,
        items: list[EvaluationItem],
        rows: list[dict],
    ) -> dict:
        if not items:
            return {}
        grouped = defaultdict(list)
        for item, row in zip(items, rows):
            grouped[item.group].append(row)
        locomo = items[0].benchmark == "locomo"
        report = {}
        for group, values in sorted(grouped.items()):
            label = CAT_NAME[int(group)] if locomo else group
            report[label] = self._group_report(group, values)
        overall_label = "overall_1to4" if locomo else "overall"
        report[overall_label] = self._overall(items, rows)
        return report

    def _group_report(self, group: str, rows: list[dict]) -> dict:
        report = {
            "acc": round(sum(row["judge"] for row in rows) / len(rows), 4),
            "n": len(rows),
        }
        if group != "5" and not group.startswith((
            "abstention",
            "single-session-preference",
        )):
            report["f1"] = round(
                sum(row["f1"] for row in rows) / len(rows),
                4,
            )
        return report

    def _overall(
        self,
        items: list[EvaluationItem],
        rows: list[dict],
    ) -> dict:
        if items[0].benchmark == "locomo":
            pairs = [
                (item, row)
                for item, row in zip(items, rows)
                if item.group != "5"
            ]
            return {
                "acc": round(sum(row["judge"] for _, row in pairs) / len(pairs), 4),
                "f1": round(sum(row["f1"] for _, row in pairs) / len(pairs), 4),
                "n": len(pairs),
            }
        f1_rows = [
            row
            for item, row in zip(items, rows)
            if not item.group.startswith((
                "abstention",
                "single-session-preference",
            ))
        ]
        return {
            "acc": round(sum(row["judge"] for row in rows) / len(rows), 4),
            "f1": round(sum(row["f1"] for row in f1_rows) / len(f1_rows), 4),
            "n": len(rows),
        }


def _build_lme_context(
    row: dict,
    variant: RetrievalVariant,
    top_k: int,
) -> tuple[str, list[dict]]:
    evaluator = LongMemEvalFunnelQuestion(**variant.options)
    index, _ = evaluator.build(row)
    candidates = evaluator.funnel._candidates(index, row["question"])
    depth = max(top_k, ACTIVATION_POOL_DEPTH)
    return row["question_id"], candidates[:depth]


def freeze(items: list[EvaluationItem], path: Path) -> None:
    with path.open("w") as output:
        for item in items:
            output.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")


def thaw(path: Path) -> list[EvaluationItem]:
    return [
        EvaluationItem(**row)
        for row in read_jsonl(path)
    ]


def model_slug(model: str) -> str:
    return "".join(
        character.lower() if character.isalnum() else "_"
        for character in model.rsplit("/", 1)[-1]
    ).strip("_")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--benchmark",
        choices=("locomo", "longmemeval", "both"),
        default="both",
    )
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--build-workers", type=int, default=16)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--sample-size", type=int)
    parser.add_argument("--sample-seed", type=int, default=42)
    parser.add_argument("--run-tag", default="")
    parser.add_argument("--freeze-only", action="store_true")
    parser.add_argument("--refresh-context", action="store_true")
    parser.add_argument("--variant", choices=tuple(VARIANTS), default="frame")
    parser.add_argument("--top-k", type=int, choices=range(1, 101), default=10)
    parser.add_argument("--source-budget", type=int)
    parser.add_argument("--input-token-budget", type=int)
    parser.add_argument(
        "--reader-provider",
        choices=("qwen", "minimax", "deepseek"),
        default="qwen",
    )
    parser.add_argument(
        "--token-provider",
        choices=("qwen", "minimax", "deepseek"),
    )
    parser.add_argument("--reader-context-limit", type=int)
    parser.add_argument("--aml-prompts", action="store_true")
    parser.add_argument("--paper1-harness", action="store_true")
    args = parser.parse_args()
    benchmarks = (
        ("locomo", "longmemeval")
        if args.benchmark == "both"
        else (args.benchmark,)
    )
    variant = VARIANTS[args.variant]
    artifact_name = (
        variant.artifact_name
        if args.top_k == 10
        else f"{variant.artifact_name}_top{args.top_k}"
    )
    if args.source_budget is not None:
        if variant.evidence_projection is None or args.source_budget < 1:
            raise ValueError("source budget requires an evidence projection")
        artifact_name = f"{artifact_name}_source{args.source_budget}"
    if args.paper1_harness and (
        args.reader_provider != "minimax" or args.source_budget != 40
    ):
        raise ValueError("Paper1 harness requires MiniMax and source budget 40")
    loader = CandidateContextLoader(
        variant,
        args.top_k,
        args.source_budget,
        args.build_workers,
    )
    reader = None if args.freeze_only else chat_for(args.reader_provider, "reader")
    counter = (
        None
        if args.freeze_only or args.paper1_harness
        else chat_for(args.token_provider or args.reader_provider, "reader")
    )
    judge_role = "enrich" if args.paper1_harness else "judge"
    judge = None if args.freeze_only else chat_for("minimax", judge_role)
    reports = {}
    for benchmark in benchmarks:
        context_path = RESULTS_DIR / (
            f"frozen_context_{benchmark}_{artifact_name}.jsonl"
        )
        if context_path.exists() and not args.refresh_context:
            items = thaw(context_path)
        else:
            items = loader.load(benchmark)
            freeze(items, context_path)
        if args.sample_size is not None:
            if args.sample_size > len(items):
                raise ValueError(
                    f"sample size {args.sample_size} exceeds {len(items)} items"
                )
            selected = random.Random(args.sample_seed).sample(
                items,
                args.sample_size,
            )
        else:
            selected = items[:args.limit]
        if args.freeze_only:
            reports[benchmark] = {"n": len(selected)}
            continue
        reader_name = model_slug(reader.model)
        judge_name = model_slug(judge.model)
        protocol_slug = "_aml" if args.aml_prompts else ""
        budget_slug = (
            f"_in{args.input_token_budget}"
            if args.input_token_budget
            else ""
        )
        sample_slug = (
            f"_sample{args.sample_size}_seed{args.sample_seed}"
            if args.sample_size is not None
            else ""
        )
        run_slug = f"_{args.run_tag}" if args.run_tag else ""
        cache_path = RESULTS_DIR / (
            f"frozen_eval_{benchmark}_{artifact_name}_"
            f"{reader_name}_{judge_name}{protocol_slug}{budget_slug}"
            f"{run_slug}.jsonl"
        )
        aml_protocol = LongMemEvalProtocol() if args.aml_prompts else None
        evaluator = FrozenContextEvaluator(
            reader,
            judge,
            cache_path,
            args.workers,
            args.input_token_budget,
            counter,
            args.reader_context_limit,
            aml_protocol,
            args.paper1_harness,
        )
        report = evaluator.run(selected)
        reports[benchmark] = report
        report_path = RESULTS_DIR / (
            f"frozen_eval_{benchmark}_{artifact_name}_"
            f"{reader_name}_{judge_name}{protocol_slug}{budget_slug}"
            f"{run_slug}{sample_slug}_report.json"
        )
        if args.sample_size is not None:
            manifest_path = report_path.with_name(
                report_path.name.replace("_report.json", "_ids.json")
            )
            manifest_path.write_text(
                json.dumps([item.id for item in selected], indent=2) + "\n"
            )
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        )
    print(json.dumps(reports, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
