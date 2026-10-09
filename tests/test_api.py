from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from mneme import Memory

import mneme_api.api as api_module
from mneme_api.app import create_app
from mneme_api.api import MemoryService
from mneme_api.data_model import AddRequest, SearchRequest


@pytest.mark.parametrize("header,value", [
    ("Authorization", "Bearer local-test-key"),
    ("Authorization", "Token local-test-key"),
    ("X-Api-Key", "local-test-key"),
])
def test_persistence_isolation_and_retries(monkeypatch: pytest.MonkeyPatch, header: str, value: str) -> None:
    root = Path(__file__).resolve().parents[1] / ".runtime" / "tests" / uuid4().hex
    monkeypatch.setenv("MNEME_API_KEY", "local-test-key")
    monkeypatch.setenv("MNEME_DATA_DIR", str(root))
    headers = {header: value}
    payload = {
        "request_id": "request:/1",
        "user_id": "user:/one",
        "session_id": "session:/one",
        "messages": [
            {"role": "user", "content": "My dog Lucky is a golden retriever.", "timestamp": 1704067200000},
            {"role": "assistant", "content": "Lucky enjoys playing with a tennis ball.", "timestamp": 1704067201000},
        ],
    }
    query = {"user_id": payload["user_id"], "query": "Lucky dog", "top_k": 100}
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
        assert client.post("/add", json=payload).status_code == 401
        assert client.post("/add", json=payload, headers={header: value + "-wrong"}).status_code == 401
        assert client.post("/add", json=payload, headers=headers).json() == {
            "success": True, **{key: payload[key] for key in ("request_id", "user_id", "session_id")}
        }
        expected = client.post("/search", json=query, headers=headers).json()
        assert len(expected["data"]) == 1
        assert expected["data"][0]["content"].count("[source: ") == 2
        assert any("assistant: Lucky" in item["content"] for item in expected["data"])
        metrics = json.loads((root / "search-metrics.jsonl").read_text().splitlines()[0])
        assert metrics["item_count"] == 1
        assert metrics["span_count"] == 2
        assert metrics["complete_prefix_span_count"] == 2
        assert metrics["complete_prefix_span_coverage"] == 1.0
        assert metrics["top_k"] == 100
        assert metrics["total_ms"] >= metrics["search_ms"]
        assert metrics["boundary_source_ids"] == []
        assert "Lucky" not in json.dumps(metrics)
        assert client.post("/add", json=payload, headers=headers).status_code == 200
        assert client.post("/search", json=query, headers=headers).json() == expected
        assert client.post("/search", json={**query, "user_id": "other"}, headers=headers).json() == {"data": []}
        grouped = client.post("/search", json={**query, "query": "Lucky", "top_k": 1}, headers=headers).json()["data"]
        assert len(grouped) == 1
        assert "user: My dog Lucky" in grouped[0]["content"]
        assert "assistant: Lucky" in grouped[0]["content"]
        assert "2024-01-01T00:00:00+00:00" in grouped[0]["content"]
        assert "2024-01-01T00:00:01+00:00" in grouped[0]["content"]
        assert grouped[0]["content"].count("[source: ") == 2
        assert client.post("/add", json={**payload, "session_id": "changed"}, headers=headers).status_code == 409

    with TestClient(create_app(), raise_server_exceptions=False) as client:
        assert client.post("/search", json=query, headers=headers).json() == expected
        interrupted = {**payload, "request_id": "request:2", "messages": [
            {"role": "user", "content": "Lucky visited Paris."},
            {"role": "assistant", "content": "Lucky visited London too."},
        ]}
        original = Memory.remember_many
        calls = 0

        def fail_after_write(self: Memory, *args: object, **kwargs: object) -> object:
            nonlocal calls
            result = original(self, *args, **kwargs)
            calls += 1
            if calls == 1:
                raise OSError("simulated interrupted package write")
            return result

        with monkeypatch.context() as patch:
            patch.setattr(Memory, "remember_many", fail_after_write)
            assert client.post("/add", json=interrupted, headers=headers).status_code == 503
        assert client.post("/add", json=interrupted, headers=headers).status_code == 200
        results = client.post("/search", json=query, headers=headers).json()["data"]
        assert len({item["id"] for item in results}) == len(results)
        content = "\n".join(item["content"] for item in results)
        assert "Lucky visited Paris." in content
        assert "Lucky visited London too." in content
        assert client.post("/add", json=payload, headers=headers).status_code == 200


def test_concurrent_user_writes() -> None:
    root = Path(__file__).resolve().parents[1] / ".runtime" / "tests" / uuid4().hex
    requests = [
        AddRequest(
            request_id=f"r{index}", user_id="shared", session_id=f"s{index}",
            messages=[{"role": "user", "content": f"Lucky visited city number {index}."}],
        )
        for index in range(4)
    ]
    services = [MemoryService(root), MemoryService(root)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(services[index % 2].add, request) for index, request in enumerate(requests)]
        for future in futures:
            assert future.result().success
    result = MemoryService(root).search(SearchRequest(user_id="shared", query="Lucky", top_k=100))
    assert len(result.data) == 1
    for index in range(4):
        assert f"Lucky visited city number {index}." in result.data[0].content


def test_releases_memory_between_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path(__file__).resolve().parents[1] / ".runtime" / "tests" / uuid4().hex
    original = Memory
    loads = 0

    def load_memory(*args: object, **kwargs: object) -> Memory:
        nonlocal loads
        loads += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(api_module, "Memory", load_memory)
    service = MemoryService(root)
    for index in range(2):
        service.add(AddRequest(
            request_id=f"r{index}", user_id="cached", session_id="session",
            messages=[{"role": "user", "content": f"Remember value {index}."}],
        ))
    service.search(SearchRequest(user_id="cached", query="value", top_k=100))
    assert loads == 3


def test_search_applies_reader_token_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path(__file__).resolve().parents[1] / ".runtime" / "tests" / uuid4().hex
    monkeypatch.setattr(api_module, "EVIDENCE_TOKEN_LIMIT", 150)
    service = MemoryService(root)
    service.add(AddRequest(
        request_id="r1",
        user_id="bounded",
        session_id="session",
        messages=[
            {
                "role": "user",
                "content": f"Tea memory number {index} is calming and green every afternoon.",
            }
            for index in range(8)
        ],
    ))

    response = service.search(SearchRequest(
        user_id="bounded",
        query="Which green tea is calming?",
        top_k=100,
    ))

    assert response.data
    assert 150 < sum(
        len(service.formatter.encoding.encode(item.content))
        for item in response.data
    ) < 300
    assert sum(item.content.count("[source: ") for item in response.data) == 2
    assert response.data[-1].content.endswith("every afternoon.")
