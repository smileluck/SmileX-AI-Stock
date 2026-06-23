import threading
import time

import pytest

from app.services import llm


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, delay: float, peak_holder: dict, peak_lock: threading.Lock):
        self._delay = delay
        self._peak_holder = peak_holder
        self._peak_lock = peak_lock

    def create(self, **kwargs):
        stats = llm.get_concurrency_stats()
        with self._peak_lock:
            if stats["active"] > self._peak_holder["active"]:
                self._peak_holder["active"] = stats["active"]
        time.sleep(self._delay)
        return _FakeResponse("ok")


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


class _FakeClient:
    def __init__(self, completions):
        self.chat = _FakeChat(completions)


@pytest.fixture
def fake_client(monkeypatch):
    peak_holder = {"active": 0}
    peak_lock = threading.Lock()
    completions = _FakeCompletions(delay=0.3, peak_holder=peak_holder, peak_lock=peak_lock)
    client = _FakeClient(completions)
    monkeypatch.setattr(llm, "_get_client", lambda: client)
    return peak_holder


def test_chat_respects_concurrency_limit(fake_client):
    max_concurrency = llm.LLM_MAX_CONCURRENCY
    n_threads = max_concurrency * 3

    results: list = []
    results_lock = threading.Lock()

    def call():
        try:
            r = llm.chat([{"role": "user", "content": "hi"}])
            with results_lock:
                results.append(("ok", r))
        except Exception as e:
            with results_lock:
                results.append(("err", str(e)))

    threads = [threading.Thread(target=call) for _ in range(n_threads)]
    t0 = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.monotonic() - t0

    assert all(r[0] == "ok" for r in results), f"some calls failed: {results}"
    assert fake_client["active"] <= max_concurrency, (
        f"peak active {fake_client['active']} exceeded limit {max_concurrency}"
    )
    expected_min_batches = (n_threads + max_concurrency - 1) // max_concurrency
    assert elapsed >= expected_min_batches * 0.3 - 0.05


def test_stats_zero_after_completion(fake_client):
    llm.chat([{"role": "user", "content": "hi"}])
    stats = llm.get_concurrency_stats()
    assert stats["active"] == 0
    assert stats["waiting"] == 0
    assert stats["max"] == llm.LLM_MAX_CONCURRENCY


def test_queue_timeout_raises(monkeypatch):
    peak_holder = {"active": 0}
    peak_lock = threading.Lock()
    completions = _FakeCompletions(delay=2.0, peak_holder=peak_holder, peak_lock=peak_lock)
    client = _FakeClient(completions)
    monkeypatch.setattr(llm, "_get_client", lambda: client)
    monkeypatch.setattr(llm, "LLM_QUEUE_TIMEOUT", 0.5)

    blocker_done = threading.Event()

    def blocker():
        llm.chat([{"role": "user", "content": "block"}])
        blocker_done.set()

    max_concurrency = llm.LLM_MAX_CONCURRENCY
    blockers = [threading.Thread(target=blocker) for _ in range(max_concurrency)]
    for t in blockers:
        t.start()
    time.sleep(0.1)

    with pytest.raises(TimeoutError):
        llm.chat([{"role": "user", "content": "queued"}])

    blocker_done.wait(timeout=5)
    for t in blockers:
        t.join(timeout=5)
