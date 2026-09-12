"""Immutable artifacts and crash-conservative total budgets across CLI resumes."""
from contextlib import contextmanager
from datetime import datetime, timezone
import dataclasses
import fcntl
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import uuid


class EvidenceError(ValueError):
    pass


def jsonable(value):
    """Boundary serializer for engine objects (dataclasses, numpy arrays).

    The worker receives real QuantBT result objects (e.g. a frozen
    ``CompactFillLedger`` dataclass of numpy arrays) and must store them as
    evidence. Unknown objects still fail closed: this is a conversion for known
    shapes, not a blanket ``str()`` fallback.
    """
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return jsonable(dataclasses.asdict(value))
    if hasattr(value, "as_record"):
        return jsonable(value.as_record())
    if hasattr(value, "to_dict"):
        return jsonable(value.to_dict())
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if type(value).__module__ == "decimal":
        return float(value)
    if hasattr(value, "value") and hasattr(value, "name"):
        return jsonable(value.value)
    if hasattr(value, "tolist"):
        return jsonable(value.tolist())
    if hasattr(value, "item"):
        return jsonable(value.item())
    raise TypeError(f"{type(value).__name__} is not JSON serialisable; "
                    "give it an explicit schema field")


def canonical(value):
    return json.dumps(jsonable(value), sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(4*1024*1024), b""):
            h.update(b)
    return h.hexdigest()


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    """Publish complete bytes once, with no overwrite even on a concurrent writer."""
    path = Path(path)
    data = canonical(value) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise EvidenceError(f"immutable artifact drift: {path}")
        return file_digest(path)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    import os
    try:
        with temp.open("xb") as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        try:
            os.link(temp, path)  # local atomic publication, never links protected source
        except FileExistsError:
            if path.read_bytes() != data:
                raise EvidenceError("concurrent immutable publication differs")
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        temp.unlink(missing_ok=True)
    return file_digest(path)


def read(path):
    def nonfinite(value):
        raise EvidenceError("nonfinite JSON: " + value)
    return json.loads(Path(path).read_bytes(), parse_constant=nonfinite)


class Ledger:
    """One study budget; in-flight/crashed work reserves its full registered cap.

    A cache key includes study source/data/economic identity. Failure is a real
    charged attempt, never a cached successful result. SQLite provides durable
    transactions; the CLI holds a nonblocking process lock across a worker run.
    """
    def __init__(self, root, identity, total_seconds):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        if not math.isfinite(total_seconds) or total_seconds <= 0:
            raise EvidenceError("positive finite total wall allocation required")
        self.db = sqlite3.connect(self.root / "ledger.sqlite", timeout=1)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS study(identity TEXT NOT NULL, budget REAL NOT NULL);
          CREATE TABLE IF NOT EXISTS attempt(id TEXT PRIMARY KEY, task TEXT NOT NULL,
            started TEXT NOT NULL, ended TEXT, status TEXT NOT NULL, reserved REAL NOT NULL,
            wall REAL, result_path TEXT, result_hash TEXT, reason TEXT);
          CREATE INDEX IF NOT EXISTS task_attempt ON attempt(task, status);
        """)
        with self.db:
            row = self.db.execute("SELECT * FROM study").fetchone()
            key = digest(identity)
            if row is None:
                self.db.execute("INSERT INTO study VALUES (?,?)", (key,total_seconds))
            elif row["identity"] != key or row["budget"] != total_seconds:
                raise EvidenceError("resume identity/budget drift; create a registered new run")
        self.identity = identity
        self.total = float(total_seconds)

    @contextmanager
    def lock(self):
        with (self.root / "worker.lock").open("a") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise EvidenceError("another worker owns this run") from exc
            try:
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def spent(self):
        return float(self.db.execute("SELECT COALESCE(SUM(COALESCE(wall,reserved)),0) FROM attempt").fetchone()[0])

    def begin(self, task, cap):
        if not math.isfinite(cap) or cap <= 0:
            raise EvidenceError("positive task cap required")
        key = digest({"identity": self.identity, "task":task})
        self.db.execute("BEGIN IMMEDIATE")
        try:
            if self.spent() + cap > self.total + 1e-9:
                raise EvidenceError("TOTAL_BUDGET_EXHAUSTED")
            if self.db.execute("SELECT 1 FROM attempt WHERE task=? AND status='RUNNING'", (key,)).fetchone():
                raise EvidenceError("unreconciled task attempt")
            attempt_id = uuid.uuid4().hex
            self.db.execute("INSERT INTO attempt(id,task,started,status,reserved) VALUES(?,?,?,?,?)",
                            (attempt_id,key,utcnow(),"RUNNING",cap))
            self.db.commit()
        except BaseException:
            self.db.rollback(); raise
        return attempt_id

    def finish(self, attempt_id, *, status, wall, result=None, reason=None):
        if status not in ("COMPLETE", "FAILED", "TIMED_OUT", "CANCELLED", "BLOCKED"):
            raise EvidenceError("invalid attempt terminal status")
        if not math.isfinite(wall) or wall < 0:
            raise EvidenceError("invalid measured duration")
        if status == "COMPLETE" and result is None:
            raise EvidenceError("successful attempt needs an artifact")
        path, h = None, None
        if result is not None:
            path = f"attempts/{attempt_id}/result.json"
            h = save(self.root/path, result)
        with self.db:
            changed = self.db.execute("UPDATE attempt SET ended=?,status=?,wall=?,result_path=?,result_hash=?,reason=? WHERE id=? AND status='RUNNING'",
                                     (utcnow(),status,wall,path,h,reason,attempt_id)).rowcount
            if changed != 1:
                raise EvidenceError("attempt absent or already closed")

    def recover_interrupted(self):
        """Call only while owning lock; unknown duration retains full reservation."""
        with self.db:
            return self.db.execute("UPDATE attempt SET status='INTERRUPTED',ended=?,reason='unknown duration charged at reserved cap' WHERE status='RUNNING'", (utcnow(),)).rowcount

    def cached(self, task):
        key = digest({"identity":self.identity,"task":task})
        row = self.db.execute("SELECT * FROM attempt WHERE task=? AND status='COMPLETE' ORDER BY started DESC LIMIT 1",(key,)).fetchone()
        if row is None:
            return None
        p = self.root/row["result_path"]
        if not p.is_file() or file_digest(p) != row["result_hash"]:
            raise EvidenceError("cached result missing or hash drift")
        return read(p)

    def status(self):
        return {"identity":digest(self.identity),"allocated_wall_seconds":self.total,
                "charged_wall_seconds":self.spent(),"remaining_wall_seconds":max(0,self.total-self.spent()),
                "attempts":[dict(r) for r in self.db.execute("SELECT * FROM attempt ORDER BY started")]}

    def close(self):
        self.db.close()
