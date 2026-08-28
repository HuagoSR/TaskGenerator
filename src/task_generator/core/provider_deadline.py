"""Hard, process-level deadlines for provider exchanges in Linux production."""

from __future__ import annotations

import os
import multiprocessing
import queue
from typing import Callable, TypeVar

T = TypeVar("T")


def run_provider_exchange(call: Callable[[], T], timeout_seconds: int) -> T:
    """Run one Linux provider exchange in a child that can be terminated.

    Fork keeps credentials in memory only; neither the callable nor secrets are
    serialized or persisted. Windows retains the finite SDK timeout for local
    tests, while governed production runs Linux/amd64.
    """
    if os.name == "nt":
        return call()
    context = multiprocessing.get_context("fork")
    results = context.Queue(maxsize=1)

    def worker() -> None:
        try:
            results.put(("ok", call()))
        except BaseException as exc:
            results.put(("error", type(exc).__name__, str(exc)[:1000]))

    process = context.Process(target=worker, daemon=True)
    process.start()
    try:
        try:
            result = results.get(timeout=timeout_seconds)
        except queue.Empty as exc:
            raise TimeoutError("provider_timeout_deadline_exceeded") from exc
        if result[0] == "ok":
            return result[1]
        raise RuntimeError(f"provider_child_{result[1]}: {result[2]}")
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
            if process.is_alive():
                process.kill()
        process.join(timeout=1)
        results.close()
