"""Background tasks with a deadline, visible progress and one result path.

Every action that talks to the printer or Prusa Connect runs as a Task on a worker thread, never on
Orca's UI thread. A task has:

- a label for the UI ("Setting bed temperature"),
- a resource key: while a task holds it, the UI disables the controls that use it and a second
  request for the same key is refused instead of queued (no burst of stale jog moves),
- a deadline: when it passes the task is reported as timed out and the resource is released. Python
  can't kill the worker; a late answer is logged and dropped.

`TaskRunner` notifies listeners on every change, so the page and the agent can show what is running.
"""

from __future__ import annotations

import itertools
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

LOG = logging.getLogger("prusa_orca")

# Deadlines in seconds by kind of work. A slow Connect answer is usually 2-5 s; commands/sync waits
# for the printer to acknowledge, which can take longer.
TIMEOUTS = {
    "command": 20.0,  # Connect commands/sync (temperatures, moves, tool settings)
    "job": 15.0,  # pause/resume/stop over PrusaLink
    "query": 30.0,  # lists, lookups, thumbnails
    "upload": 0.0,  # uploads report their own progress; no deadline
}
# Shown as "slow" in the UI after this long.
SLOW_AFTER = 4.0


class TaskTimeout(Exception):
    pass


class TaskBusy(Exception):
    pass


@dataclass
class Task:
    id: int
    label: str
    kind: str
    resource: str
    started: float
    deadline: float  # 0 = none
    state: str = "running"  # running, done, failed, timeout
    quiet: bool = False  # background work the user didn't ask for: not shown as busy
    error: str = ""
    finished: float = 0.0
    result: Any = None
    on_done: Callable[[Task], None] | None = field(default=None, repr=False)
    _done: threading.Event = field(default_factory=threading.Event, repr=False)

    @property
    def elapsed(self) -> float:
        return (self.finished or time.monotonic()) - self.started

    def view(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "resource": self.resource,
            "state": self.state,
            "quiet": self.quiet,
            "elapsed": round(self.elapsed, 1),
            "slow": self.state == "running" and self.elapsed >= SLOW_AFTER,
            "error": self.error,
        }


class TaskRunner:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self._running: dict[int, Task] = {}
        self.recent: list[Task] = []  # finished, newest first
        self.listeners: list[Callable[[Task], None]] = []
        self._watchdog: threading.Thread | None = None

    def busy(self, resource: str) -> bool:
        with self._lock:
            return any(t.resource == resource for t in self._running.values())

    def running(self) -> list[Task]:
        with self._lock:
            return sorted(self._running.values(), key=lambda t: t.id)

    def submit(
        self,
        label: str,
        fn: Callable[[], Any],
        kind: str = "query",
        resource: str = "",
        on_done: Callable[[Task], None] | None = None,
        timeout: float | None = None,
        quiet: bool = False,
    ) -> Task:
        """Run fn on a worker thread. Raises TaskBusy when `resource` is already in use."""
        limit = TIMEOUTS.get(kind, 30.0) if timeout is None else timeout
        with self._lock:
            if resource and any(t.resource == resource for t in self._running.values()):
                raise TaskBusy(f"{label}: still waiting for the previous request")
            now = time.monotonic()
            task = Task(next(self._ids), label, kind, resource, now, now + limit if limit else 0.0, quiet=quiet, on_done=on_done)
            self._running[task.id] = task
        self._notify(task)

        def work() -> None:
            try:
                result = fn()
                self._finish(task, "done", result=result)
            except Exception as exc:  # reported to the UI; the traceback goes to the log
                LOG.warning("%s failed: %s", label, exc, exc_info=not isinstance(exc, (TimeoutError, OSError)))
                self._finish(task, "failed", error=reason(exc))

        threading.Thread(target=work, name=f"prusa-task-{task.id}", daemon=True).start()
        self._ensure_watchdog()
        return task

    def wait(self, task: Task, timeout: float | None = None) -> Task:
        task._done.wait(timeout)
        return task

    def _finish(self, task: Task, state: str, result: Any = None, error: str = "") -> None:
        with self._lock:
            if task.state != "running":
                # The deadline already passed: the answer came too late to matter.
                LOG.info("%s answered after its %s timeout (%s)", task.label, task.kind, state)
                return
            task.state, task.result, task.error, task.finished = state, result, error, time.monotonic()
            self._running.pop(task.id, None)
            self.recent.insert(0, task)
            del self.recent[20:]
        task._done.set()
        self._notify(task)
        if task.on_done is not None:
            try:
                task.on_done(task)
            except Exception:
                LOG.exception("%s: completion handler failed", task.label)

    def _ensure_watchdog(self) -> None:
        if self._watchdog and self._watchdog.is_alive():
            return
        self._watchdog = threading.Thread(target=self._watch, name="prusa-task-watchdog", daemon=True)
        self._watchdog.start()

    def _watch(self) -> None:
        last_slow: set[int] = set()
        while True:
            time.sleep(0.5)
            now = time.monotonic()
            with self._lock:
                tasks = list(self._running.values())
            if not tasks:
                return
            for task in tasks:
                if task.deadline and now >= task.deadline:
                    seconds = int(task.deadline - task.started)
                    self._finish(task, "timeout", error=f"no answer within {seconds} s")
                elif task.id not in last_slow and now - task.started >= SLOW_AFTER:
                    last_slow.add(task.id)
                    self._notify(task)

    def _notify(self, task: Task) -> None:
        for listener in list(self.listeners):
            try:
                listener(task)
            except Exception:
                LOG.exception("task listener failed")


def reason(exc: Exception) -> str:
    """A short, user-facing reason for a failed network call."""
    import socket
    import urllib.error

    if isinstance(exc, urllib.error.HTTPError):
        if exc.code in (401, 403):
            return "Prusa Connect refused the request; log in again"
        if exc.code == 409:
            return "the printer is busy or in the wrong state"
        if exc.code == 429:
            return "Prusa Connect asks to slow down; try again shortly"
        if exc.code >= 500:
            return f"Prusa Connect is having problems (HTTP {exc.code})"
        return f"HTTP {exc.code}"
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return "no answer in time"
    if isinstance(exc, urllib.error.URLError):
        return f"can't reach the server ({exc.reason})"
    return str(exc) or exc.__class__.__name__
