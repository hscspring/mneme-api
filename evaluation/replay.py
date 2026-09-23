import argparse
import json
import os
from pathlib import Path

import httpx


class Replay:

    def __init__(self, base_url: str, source: Path, output: Path):
        self.base_url = base_url.rstrip("/")
        self.source = source
        self.output = output

    def __call__(self) -> None:
        headers = {"Authorization": f"Bearer {os.environ['MNEME_API_KEY']}"}
        with httpx.Client(base_url=self.base_url, headers=headers, timeout=1800) as client:
            with self.source.open() as source, self.output.open("x") as output:
                for line in source:
                    operation = json.loads(line)
                    if operation["operation"] not in {"add", "search"}:
                        raise ValueError("operation must be add or search")
                    response = client.post(f"/{operation['operation']}", json=operation["request"])
                    response.raise_for_status()
                    output.write(json.dumps({"operation": operation["operation"], "response": response.json()}, ensure_ascii=False) + "\n")
                    output.flush()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    Replay(args.base_url, args.source, args.output)()


if __name__ == "__main__":
    main()
