from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from mneme import Memory

from mneme_api.app import create_app
from mneme_api.api import MemoryService
from mneme_api.data_model import AddRequest, SearchRequest


def test_persistence_isolation_and_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path(__file__).resolve().parents[1] / ".runtime" / "tests" / uuid4().hex
    monkeypatch.setenv("MNEME_API_KEY", "local-test-key")
    monkeypatch.setenv("MNEME_DATA_DIR", str(root))
    headers = {"Authorization": "Bearer local-test-key"}
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
        assert client.post("/add", json=payload, headers=headers).json() == {
            "success": True, **{key: payload[key] for key in ("request_id", "user_id", "session_id")}
        }
        expected = client.post("/search", json=query, headers=headers).json()
        assert len(expected["data"]) == 2
        assert any("assistant: Lucky" in item["content"] for item in expected["data"])
        assert client.post("/add", json=payload, headers=headers).status_code == 200
        assert client.post("/search", json=query, headers=headers).json() == expected
        assert client.post("/search", json={**query, "user_id": "other"}, headers=headers).json() == {"data": []}
        assert len(client.post("/search", json={**query, "top_k": 1}, headers=headers).json()["data"]) == 1
        assert client.post("/add", json={**payload, "session_id": "changed"}, headers=headers).status_code == 409

    with TestClient(create_app(), raise_server_exceptions=False) as client:
        assert client.post("/search", json=query, headers=headers).json() == expected
        interrupted = {**payload, "request_id": "request:2", "messages": [
            {"role": "user", "content": "Lucky visited Paris."},
            {"role": "assistant", "content": "Lucky visited London too."},
        ]}
        original = Memory.remember
        calls = 0

        def fail_after_write(self: Memory, *args: object, **kwargs: object) -> object:
            nonlocal calls
            result = original(self, *args, **kwargs)
            calls += 1
            if calls == 1:
                raise OSError("simulated interrupted package write")
            return result

        with monkeypatch.context() as patch:
            patch.setattr(Memory, "remember", fail_after_write)
            assert client.post("/add", json=interrupted, headers=headers).status_code == 503
        assert client.post("/add", json=interrupted, headers=headers).status_code == 200
        results = client.post("/search", json=query, headers=headers).json()["data"]
        assert len(results) == 4
        assert len({item["id"] for item in results}) == 4
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
    assert len(result.data) == 4
    assert len({item.id for item in result.data}) == 4
