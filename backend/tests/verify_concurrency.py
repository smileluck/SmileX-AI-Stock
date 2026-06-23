"""临时验证脚本：确认 chat() 的全局并发信号量生效。验证完可删。"""
import threading
import time

from app.services import llm


class _FakeResp:
    def __init__(self):
        self.choices = [type("C", (), {"message": type("M", (), {"content": "ok"})()})()]


def _fake_create(**kwargs):
    stats = llm.get_concurrency_stats()
    with _peak_lock:
        if stats["active"] > _peak["active"]:
            _peak["active"] = stats["active"]
    _observed.append(stats["active"])
    time.sleep(0.3)
    return _FakeResp()


_peak = {"active": 0}
_peak_lock = threading.Lock()
_observed: list[int] = []

llm._get_client = lambda: type(
    "Client",
    (),
    {"chat": type("Chat", (), {"completions": type("Comp", (), {"create": _fake_create})()})()},
)()

N = 10
results = []
results_lock = threading.Lock()


def call(i):
    try:
        llm.chat([{"role": "user", "content": f"hi {i}"}])
        with results_lock:
            results.append(("ok", i))
    except Exception as e:
        with results_lock:
            results.append(("err", i, str(e)))


threads = [threading.Thread(target=call, args=(i,)) for i in range(N)]
t0 = time.monotonic()
for t in threads:
    t.start()
for t in threads:
    t.join()
elapsed = time.monotonic() - t0

print(f"max_concurrency = {llm.LLM_MAX_CONCURRENCY}")
print(f"threads = {N}")
print(f"peak active observed = {_peak['active']}")
print(f"elapsed = {elapsed:.2f}s")
print(f"successes = {sum(1 for r in results if r[0]=='ok')}/{N}")
print(f"final stats = {llm.get_concurrency_stats()}")

assert _peak["active"] <= llm.LLM_MAX_CONCURRENCY, f"peak {_peak['active']} exceeded limit"
assert all(r[0] == "ok" for r in results), f"failures: {results}"
expected_min_batches = (N + llm.LLM_MAX_CONCURRENCY - 1) // llm.LLM_MAX_CONCURRENCY
assert elapsed >= expected_min_batches * 0.3 - 0.1, f"too fast: {elapsed}s, expected >= {expected_min_batches * 0.3}s"
print("OK: concurrency limit enforced, no failures, elapsed consistent with batching")
