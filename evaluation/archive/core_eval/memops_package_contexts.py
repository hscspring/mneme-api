import argparse
import hashlib
import inspect
import json
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from tokenizers import Tokenizer

import mneme
from mneme import (
    ActivationField,
    EvidenceBudget,
    EvidenceProjection,
    EvidenceProjector,
    Memory,
    RememberInput,
    SourceTrace,
)
from mneme.extract import LinguisticCompiler
from mneme.evolution import EvolutionIndex, SuccessorActivation
from mneme.network import TraceIndex


READER_PROMPT = """Answer the question using only the conversation memory below.
Before answering, internally identify the requested operation, subject, relation, category, and time scope. Keep each fact's owner, entity or event identity, value, and source separate. Apply updates before reading a current state. Exclude plans, failed or hypothetical actions, facts about another person, and duplicate mentions of the same entity or event.
If the required evidence is missing or conflicting, answer "No information". Output only the shortest final answer without reasoning.

Memory:
{ctx}

Question: {q}
Answer:"""


class PackageContextWorker:

    def __init__(
        self,
        data_root: Path,
        stores_root: Path,
        tokenizer_path: Path,
        method: str,
        input_token_budget: int,
        top_k: int,
        source_budget: int | None,
        in_memory: bool,
    ) -> None:
        self.data_root = data_root
        self.stores_root = stores_root
        self.tokenizer = Tokenizer.from_file(str(tokenizer_path))
        self.method = method
        self.input_token_budget = input_token_budget
        self.top_k = top_k
        self.source_budget = source_budget
        self.in_memory = in_memory
        self.evolution: EvolutionIndex | None = None

    def __call__(self, filename: str) -> list[dict]:
        data = json.loads((self.data_root / filename).read_text())
        if self.in_memory:
            index = self._index(filename, data["conversations"])
            return [
                self._question(index, filename, data, answer)
                for answer in data["answer"]
                if answer["evaluation_setting"] == "longitudinal_operation"
            ]
        store_root = self.stores_root / Path(filename).stem
        memory = Memory(root=str(store_root))
        marker = store_root / ".ingest-complete"
        if not marker.exists():
            if memory.store.turns:
                raise RuntimeError(f"incomplete Store already exists: {store_root}")
            self._ingest(memory, filename, data["conversations"])
            marker.write_text("complete\n")
        return [
            self._question(memory, filename, data, answer)
            for answer in data["answer"]
            if answer["evaluation_setting"] == "longitudinal_operation"
        ]

    @staticmethod
    def _round_id(session_name: str, position: int) -> int:
        identity = json.dumps([session_name, position])
        return int(hashlib.sha256(identity.encode()).hexdigest(), 16)

    def _index(self, filename: str, segments: list[dict]) -> TraceIndex:
        compiler = LinguisticCompiler()
        index = TraceIndex(compiler)
        evolution = EvolutionIndex(index)
        for segment in segments:
            session_name = segment.get(
                "session_id",
                f"{filename}:session{segment['segment_index']}",
            )
            session_id = hashlib.sha256(session_name.encode()).hexdigest()
            event_id = segment.get("event_id", session_id)
            timestamp = float(segment.get("timestamp", segment["segment_index"]))
            previous_id = None
            inherited_tags = ()
            episode_id = None
            source_ids = []
            for position, message in enumerate(segment["dialogue"]):
                role = message["role"]
                text = message["content"]
                semantic_text = message.get("semantic_content")
                turn_id = f"{session_id}:{self._round_id(session_name, position)}"
                source_id = f"{turn_id}#{role}"
                episode_id = episode_id or turn_id
                source_ids.append(source_id)
                analysis = compiler.analyze(text, role, semantic_text)
                content = semantic_text or text
                context = (
                    text[:-len(content)].strip()
                    if semantic_text and text.endswith(content)
                    else ""
                )
                index.add(SourceTrace(
                    id=source_id,
                    turn_id=turn_id,
                    event_id=event_id,
                    exchange_id=turn_id,
                    ts=timestamp,
                    role=role,
                    text=text,
                    content=content,
                    context=context,
                    tags=tuple(analysis.tags),
                    propositions=tuple(analysis.propositions),
                    participants=tuple(message.get("participants", ())),
                    inherited_tags=inherited_tags,
                    previous_id=previous_id,
                    interlocutor="assistant" if role == "user" else "user",
                ))
                previous_id = source_id
                inherited_tags = tuple(analysis.tags)
            if episode_id is not None:
                evolution.add_episode(episode_id, source_ids)
        self.evolution = evolution
        return index

    def _ingest(self, memory: Memory, filename: str, segments: list[dict]) -> None:
        for segment in segments:
            session_name = segment.get(
                "session_id",
                f"{filename}:session{segment['segment_index']}",
            )
            session_id = hashlib.sha256(session_name.encode()).hexdigest()
            event_id = segment.get("event_id", session_id)
            timestamp = float(segment.get("timestamp", segment["segment_index"]))
            items = []
            for position, message in enumerate(segment["dialogue"]):
                items.append(RememberInput(
                    query=message["content"] if message["role"] == "user" else "",
                    response=message["content"] if message["role"] == "assistant" else "",
                    session_id=session_id,
                    round_id=self._round_id(session_name, position),
                    ts=timestamp,
                    event_id=event_id,
                    participants=message.get("participants"),
                    semantic_query=message.get("semantic_content"),
                ))
            memory.remember_many(items)

    def _question(
        self,
        memory: Memory | TraceIndex,
        filename: str,
        data: dict,
        answer: dict,
    ) -> dict:
        question = answer["question"]
        budget = EvidenceBudget(
            self.input_token_budget,
            lambda items: self._prompt_tokens(question, items),
        )
        if isinstance(memory, TraceIndex):
            evidence = self._search_index(memory, question, budget)
        elif self.method == "0.8.3":
            evidence = memory.search_evidence(question, self.top_k, budget=budget)
        else:
            evidence = memory.search_composed_evidence(
                question,
                topn=self.top_k,
                budget=budget,
                scope_owner="user",
            )
        evidence, raw_input_tokens = self._fit(question, evidence)
        context = self._context(evidence)
        input_tokens = self._tokens(READER_PROMPT.format(ctx=context, q=question))
        if input_tokens > self.input_token_budget:
            raise RuntimeError(
                f"Reader budget exceeded for {filename}:{answer['question_pair_id']}"
            )
        return {
            "id": f"memops:{Path(filename).stem}:{answer['question_pair_id']}",
            "operation": data["operation_type"],
            "category": answer["evaluation_category"],
            "question": question,
            "answer": str(answer["expected_answer"]),
            "rubric": answer["judge_rubric"],
            "context": context,
            "input_tokens": input_tokens,
            "raw_input_tokens": raw_input_tokens,
            "evidence_n": len(evidence),
            "source_n": len({span.source_id for item in evidence for span in item.spans}),
            "source_ids": [
                span.source_id
                for item in evidence
                for span in item.spans
            ],
        }

    def _search_index(
        self,
        index: TraceIndex,
        question: str,
        budget: EvidenceBudget,
    ) -> list:
        activated = ActivationField(index)(question)
        if self.method == "0.8.3":
            return EvidenceProjector(
                index,
                EvidenceProjection.TAG_GRAPH_DEDUP,
            )(activated, question, self.top_k, budget)
        if self.method in ("0.10.0", "0.10.1"):
            if self.evolution is None:
                raise RuntimeError("successor activation requires an evolution index")
            activated = SuccessorActivation(index, self.evolution)(
                activated,
                question,
            )
        from mneme.composition import EvidenceComposer
        from mneme.evidence import SourceEvidenceProjector
        composition = EvidenceComposer(index, scope_owner="user")(
            activated,
            question,
            context_budget=True,
        )
        return SourceEvidenceProjector(index)(
            composition,
            activated,
            self.top_k,
            budget,
        )

    def _fit(self, question: str, evidence: list) -> tuple[list, int]:
        evidence = list(evidence)
        raw_tokens = self._prompt_tokens(question, tuple(evidence))
        while evidence and (
            self._source_count(evidence) > (self.source_budget or float("inf"))
            or self._prompt_tokens(question, tuple(evidence)) > self.input_token_budget
        ):
            item = evidence[-1]
            if len(item.spans) == 1:
                evidence.pop()
                continue
            evidence[-1] = replace(
                item,
                spans=item.spans[:-1],
                access_ids=item.access_ids[:-1],
            )
        return evidence, raw_tokens

    @staticmethod
    def _source_count(evidence: list) -> int:
        return len({span.source_id for item in evidence for span in item.spans})

    def _prompt_tokens(self, question: str, evidence: tuple) -> int:
        context = self._context(evidence)
        return self._tokens(READER_PROMPT.format(ctx=context, q=question))

    @staticmethod
    def _context(evidence: tuple | list) -> str:
        return "\n\n".join(PackageContextWorker._item(item) for item in evidence)

    @staticmethod
    def _item(item: object) -> str:
        parts = [f"[tag: {item.label}]"] if item.label else []
        for span in item.spans:
            timestamp = datetime.fromtimestamp(span.timestamp, timezone.utc).isoformat()
            parts.append(
                f"[{timestamp}] [source: {span.source_id}]\n"
                f"{span.role}: {span.text}"
            )
        return "\n".join(parts)

    def _tokens(self, text: str) -> int:
        return len(self.tokenizer.encode(text).ids)


_WORKER = None


def initialize_worker(config: dict) -> None:
    global _WORKER
    _WORKER = PackageContextWorker(**config)


def build_contexts(filename: str) -> list[dict]:
    if _WORKER is None:
        raise RuntimeError("worker is not initialized")
    return _WORKER(filename)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--stores-root", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument(
        "--method",
        choices=("0.8.3", "0.9.2", "0.10.0", "0.10.1"),
        required=True,
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--input-token-budget", type=int, default=24_000)
    parser.add_argument("--top-k", type=int, default=100)
    parser.add_argument("--source-budget", type=int)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--in-memory", action="store_true")
    args = parser.parse_args()
    if args.source_budget is not None and args.source_budget < 1:
        raise ValueError("source budget must be positive")
    package_root = args.package_root.resolve()
    loaded_root = Path(inspect.getfile(mneme)).resolve().parent.parent
    if loaded_root != package_root:
        raise RuntimeError(f"loaded mneme from {loaded_root}, expected {package_root}")
    groups = frozenset(json.loads(args.split_manifest.read_text())["heldout_groups"])
    data_root = args.data_root / "4-inject_evidence_with_distractors"
    filenames = sorted(
        path.name
        for path in data_root.glob("*.json")
        if path.name.split("_", 1)[0] in groups
    )[:args.limit]
    config = {
        "data_root": data_root,
        "stores_root": args.stores_root,
        "tokenizer_path": args.tokenizer,
        "method": args.method,
        "input_token_budget": args.input_token_budget,
        "top_k": args.top_k,
        "source_budget": args.source_budget,
        "in_memory": args.in_memory,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    completed = 0
    with args.output.open("w") as output:
        with ProcessPoolExecutor(
            max_workers=args.workers,
            initializer=initialize_worker,
            initargs=(config,),
        ) as pool:
            for rows in pool.map(build_contexts, filenames, chunksize=1):
                for row in rows:
                    output.write(json.dumps(row, ensure_ascii=False) + "\n")
                output.flush()
                completed += 1
                print(f"{args.method} contexts {completed}/{len(filenames)}", flush=True)
    print(json.dumps({
        "method": args.method,
        "package_root": str(package_root),
        "files": len(filenames),
        "questions": sum(
            1 for line in args.output.open() if line.strip()
        ),
    }, indent=2))


if __name__ == "__main__":
    main()
