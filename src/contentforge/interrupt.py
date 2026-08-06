"""Graceful stop for a long render.

A full video is hours of GPU work. If it has to be stopped part way - the
machine is needed, a mistake was spotted - killing it must not corrupt the run
or throw away the images already drawn. The stages write one finished file per
item, so the only rule needed is: **stop between items, never mid-item.**

`arm()` installs SIGINT/SIGTERM handlers that *request* a stop. The per-item
loops call `check()` at the top of each iteration; when a stop was requested it
raises `StopRequested`, which the pipeline records as a clean "stopped" status
(not a failure) and every finished item stays on disk, resumable. A second
signal restores the default handler, so a determined Ctrl-C still hard-kills.
"""
from __future__ import annotations

import signal
import threading

_stop = threading.Event()
_armed = False


class StopRequested(Exception):
    """Raised between work items after a stop was requested."""


def arm() -> None:
    """Install signal handlers that request a graceful stop.

    Safe to call more than once. In a non-main thread (some test runners)
    signal installation is skipped rather than raising.
    """
    global _armed
    _stop.clear()
    if _armed:
        return

    def handler(signum, frame):
        if _stop.is_set():
            # A second signal: the user means it - restore default and let it
            # hard-stop rather than waiting for the current item to finish.
            signal.signal(signum, signal.SIG_DFL)
            raise KeyboardInterrupt
        _stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, handler)
        except (ValueError, OSError):
            pass  # not the main thread; leave default handling in place
    _armed = True


def requested() -> bool:
    return _stop.is_set()


def check() -> None:
    """Raise StopRequested if a stop was requested. Call between work items."""
    if _stop.is_set():
        raise StopRequested()


def clear() -> None:
    """Reset the flag (used by tests, and at the start of a fresh run)."""
    _stop.clear()
