import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from tokenizers import Tokenizer


READER_PROMPT = """Answer the question using only the memory below. If the memory does not contain enough information, answer \"No information\". Output only the answer without reasoning.

Memory:
{ctx}

Question: {q}
Answer:"""


class LongMemEvalContextProjector:

    _block_boundary = re.compile(r"\n\n(?=\[[^\n]+\] \[source: )")
    _source_id = re.compile(r"\[source: ([^\]]+)\]")

    def __init__(
        self,
        data: Path,
        baseline_contexts: Path,
        baseline_retrieval: Path,
        candidate_retrieval: Path,
        tokenizer: Path,
        output: Path,
        input_token_budget: int,
    ) -> None:
        self.rows = json.loads(data.read_text())
        self.contexts = self._jsonl(baseline_contexts, "id")
        self.baseline = self._jsonl(baseline_retrieval, "question_id")
        self.candidate = self._jsonl(candidate_retrieval, "question_id")
        self.tokenizer = Tokenizer.from_file(str(tokenizer))
        self.output = output
        self.input_token_budget = input_token_budget

    def __call__(self) -> dict:
        if self.baseline.keys() != self.candidate.keys():
            raise ValueError("baseline and candidate retrieval populations differ")
        changed = 0
        reused_blocks = 0
        new_blocks = 0
        with self.output.open("w") as output:
            for row in self.rows:
                stored = self._context(row["question_id"])
                if row["question_id"] not in self.candidate:
                    output.write(json.dumps(stored, ensure_ascii=False) + "\n")
                    continue
                baseline_ranked = self.baseline[row["question_id"]][
                    "ranked_source_ids"
                ]
                candidate_ranked = self.candidate[row["question_id"]][
                    "ranked_source_ids"
                ]
                if baseline_ranked == candidate_ranked:
                    output.write(json.dumps(stored, ensure_ascii=False) + "\n")
                    continue
                source_blocks = self._source_blocks(row)
                baseline_blocks = self._baseline_blocks(stored, source_blocks)
                ranked = candidate_ranked[:40]
                blocks = []
                for source_id in ranked:
                    if source_id in baseline_blocks:
                        blocks.append(baseline_blocks[source_id])
                        reused_blocks += 1
                    else:
                        blocks.append(source_blocks[source_id])
                        new_blocks += 1
                context, source_ids, raw_tokens = self._admit(row["question"], blocks)
                candidate = {
                    **stored,
                    "context": context,
                    "input_tokens": self._prompt_tokens(context, row["question"]),
                    "raw_input_tokens": raw_tokens,
                    "evidence_n": len(source_ids),
                    "source_n": len(source_ids),
                    "source_ids": source_ids,
                }
                changed += candidate["context"] != stored["context"]
                output.write(json.dumps(candidate, ensure_ascii=False) + "\n")
        return {
            "questions": len(self.rows),
            "retrieval_questions": len(self.candidate),
            "changed_contexts": changed,
            "reused_blocks": reused_blocks,
            "new_blocks": new_blocks,
            "output": str(self.output),
        }

    def _context(self, question_id: str) -> dict:
        suffix = f":{question_id}"
        matches = [row for key, row in self.contexts.items() if key.endswith(suffix)]
        if len(matches) != 1:
            raise ValueError(f"expected one baseline context for {question_id}")
        return matches[0]

    def _source_blocks(self, row: dict) -> dict[str, str]:
        blocks = {}
        for session_id, date, session in zip(
            row["haystack_session_ids"],
            row["haystack_dates"],
            row["haystack_sessions"],
        ):
            timestamp = datetime.strptime(date, "%Y/%m/%d (%a) %H:%M").replace(
                tzinfo=timezone.utc,
            ).isoformat()
            for position, item in enumerate(session):
                source_id = f"{session_id}:{position}"
                text = f"[{date}] {item['role']}: {item['content']}"
                blocks[source_id] = (
                    f"[{timestamp}] [source: {source_id}]\n{item['role']}: {text}"
                )
        return blocks

    def _baseline_blocks(
        self,
        stored: dict,
        source_blocks: dict[str, str],
    ) -> dict[str, str]:
        blocks = self._block_boundary.split(stored["context"])
        rendered = {
            self._inner_text(block): block
            for block in blocks
        }
        mapped = {}
        for source_id, block in source_blocks.items():
            content = self._inner_text(block)
            if content in rendered:
                mapped[source_id] = rendered[content]
        return mapped

    @staticmethod
    def _inner_text(block: str) -> str:
        content = block.split("\n", 1)[-1]
        return content.split(": ", 1)[-1]

    def _admit(
        self,
        question: str,
        blocks: list[str],
    ) -> tuple[str, list[str], int]:
        raw_context = "\n\n".join(blocks)
        raw_tokens = self._prompt_tokens(raw_context, question)
        selected = []
        source_ids = []
        for block in blocks:
            candidate = "\n\n".join((*selected, block))
            if self._prompt_tokens(candidate, question) > self.input_token_budget:
                continue
            selected.append(block)
            match = self._source_id.search(block)
            if match is None:
                raise ValueError("context block is missing source ID")
            source_ids.append(match.group(1))
        return "\n\n".join(selected), source_ids, raw_tokens

    def _prompt_tokens(self, context: str, question: str) -> int:
        return len(self.tokenizer.encode(READER_PROMPT.format(ctx=context, q=question)).ids)

    @staticmethod
    def _jsonl(path: Path, key: str) -> dict[str, dict]:
        return {
            row[key]: row
            for line in path.open()
            if line.strip()
            for row in (json.loads(line),)
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--baseline-contexts", type=Path, required=True)
    parser.add_argument("--baseline-retrieval", type=Path, required=True)
    parser.add_argument("--candidate-retrieval", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--input-token-budget", type=int, default=24_000)
    args = parser.parse_args()
    print(json.dumps(LongMemEvalContextProjector(
        args.data,
        args.baseline_contexts,
        args.baseline_retrieval,
        args.candidate_retrieval,
        args.tokenizer,
        args.output,
        args.input_token_budget,
    )(), indent=2))


if __name__ == "__main__":
    main()
