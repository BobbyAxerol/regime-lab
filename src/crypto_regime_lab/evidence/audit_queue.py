"""Bounded audit queue and run-commit gate (guide 11.5, test T61).

Two rules from the guide are enforced here:

  * "writer queue full must backpressure or fail explicitly — never drop";
  * "RUN_SUCCESS only after the required artifacts are committed and flushed".

Dropping a record silently would let a run look complete while its evidence is
incomplete, which is exactly the failure mode the guide forbids.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class QueueFullPolicy(str, Enum):
    BACKPRESSURE = "backpressure"   # block the producer until the writer drains
    EXPLICIT_FAIL = "explicit_fail"  # raise so the caller must handle it
    # There is deliberately no DROP policy.


class AuditQueueOverflow(RuntimeError):
    """Raised when the queue is full under EXPLICIT_FAIL. Never silently swallowed."""


class AuditQueueClosed(RuntimeError):
    """Raised when a record is offered to a closed queue."""


@dataclass
class BoundedAuditQueue:
    """A bounded, non-dropping sink for streaming audit rows."""

    sink: Callable[[list[dict]], int]
    maxsize: int = 1024
    policy: QueueFullPolicy = QueueFullPolicy.BACKPRESSURE
    backpressure_timeout_s: float = 30.0
    _q: queue.Queue = field(init=False, repr=False)
    _closed: bool = field(default=False, init=False)
    _accepted: int = field(default=0, init=False)
    _committed: int = field(default=0, init=False)
    _dropped: int = field(default=0, init=False)  # must always stay 0
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        self._q = queue.Queue(maxsize=self.maxsize)

    def offer(self, row: dict) -> None:
        if self._closed:
            raise AuditQueueClosed("queue is closed; a late record must not be discarded")
        if self.policy is QueueFullPolicy.EXPLICIT_FAIL:
            try:
                self._q.put_nowait(row)
            except queue.Full as exc:
                raise AuditQueueOverflow(
                    f"audit queue full at {self.maxsize}; caller must drain or fail the run"
                ) from exc
        else:
            try:
                self._q.put(row, timeout=self.backpressure_timeout_s)
            except queue.Full as exc:
                raise AuditQueueOverflow(
                    f"backpressure timed out after {self.backpressure_timeout_s}s; run cannot report success"
                ) from exc
        with self._lock:
            self._accepted += 1

    def pending(self) -> int:
        return self._q.qsize()

    def flush(self) -> int:
        """Drain everything to the sink. Returns rows committed by this call."""
        batch: list[dict] = []
        while True:
            try:
                batch.append(self._q.get_nowait())
            except queue.Empty:
                break
        if not batch:
            return 0
        written = self.sink(batch)
        if written != len(batch):
            raise AuditQueueOverflow(f"sink committed {written} of {len(batch)} rows; refusing to lose the rest")
        with self._lock:
            self._committed += written
        return written

    def close(self) -> dict:
        self.flush()
        self._closed = True
        return self.stats()

    def stats(self) -> dict:
        with self._lock:
            return {
                "accepted": self._accepted,
                "committed": self._committed,
                "pending": self._q.qsize(),
                "dropped": self._dropped,
                "policy": self.policy.value,
                "maxsize": self.maxsize,
                "closed": self._closed,
            }


@dataclass
class RunCommitGate:
    """RUN_SUCCESS is only reachable once every required artifact is committed."""

    required_artifacts: tuple[str, ...]
    committed: set[str] = field(default_factory=set)
    queues: list[BoundedAuditQueue] = field(default_factory=list)

    def mark_committed(self, name: str) -> None:
        self.committed.add(name)

    def register_queue(self, q: BoundedAuditQueue) -> None:
        self.queues.append(q)

    def missing(self) -> list[str]:
        return sorted(set(self.required_artifacts) - self.committed)

    def unflushed(self) -> int:
        return sum(q.pending() for q in self.queues)

    def finalize(self) -> dict:
        """Return the run status. Never returns RUN_SUCCESS with work outstanding."""
        for q in self.queues:
            q.flush()
        missing = self.missing()
        unflushed = self.unflushed()
        dropped = sum(q.stats()["dropped"] for q in self.queues)
        if missing or unflushed or dropped:
            return {
                "status": "RUN_INCOMPLETE",
                "missing_artifacts": missing,
                "unflushed_rows": unflushed,
                "dropped_rows": dropped,
            }
        return {
            "status": "RUN_SUCCESS",
            "missing_artifacts": [],
            "unflushed_rows": 0,
            "dropped_rows": 0,
            "committed_artifacts": sorted(self.committed),
        }
