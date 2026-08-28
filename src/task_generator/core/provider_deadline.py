"""Bounded provider-exchange deadline for governed Linux production calls."""

from __future__ import annotations

import os
import signal
import threading
from contextlib import contextmanager
from typing import Iterator


@contextmanager
def provider_deadline(timeout_seconds: int) -> Iterator[None]:
    """Interrupt a Linux main-thread provider call at its contractual deadline.

    SDK I/O timeouts do not impose an end-to-end deadline.  Windows and worker
    threads retain their explicit SDK timeout because ``SIGALRM`` is unavailable
    or unsafe there; governed server calls run in the Linux main thread.
    """
    enabled = bool(
        os.name != "nt"
        and threading.current_thread() is threading.main_thread()
        and hasattr(signal, "SIGALRM")
        and hasattr(signal, "setitimer")
    )
    if not enabled:
        yield
        return

    previous_handler = signal.getsignal(signal.SIGALRM)

    def _deadline_exceeded(signum: int, frame: object) -> None:
        del signum, frame
        raise TimeoutError("provider_timeout_deadline_exceeded")

    signal.signal(signal.SIGALRM, _deadline_exceeded)
    signal.setitimer(signal.ITIMER_REAL, float(timeout_seconds))
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
