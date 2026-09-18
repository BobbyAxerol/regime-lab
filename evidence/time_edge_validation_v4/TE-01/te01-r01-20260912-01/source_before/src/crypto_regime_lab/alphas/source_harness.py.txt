"""Load individual functions out of the raw alpha sources without importing them.

The guide's own review used this approach (appendix B): parse the file, drop the
``@njit`` decorators and the import lines, then exec ONLY the requested function
definitions in a private namespace with NumPy/Pandas injected where the source
documents them.

Why not import the module: ``hash_momentum.py`` raises ``NameError: np`` at the
first call, ``signal_combine.py`` pulls in ``ta`` at import time, and guide L01.3
forbids executing the originals outside containment. Callers must run this inside
``safety.sandbox``.

Dropping ``@njit`` is itself a semantic choice and is recorded: the harness runs
the pure-Python body, so a Numba-specific behaviour (``fastmath`` reassociation,
integer overflow) is NOT exercised here. That is the point — the oracle is
fastmath-free (finding HM-08, delta SD-HMA-07).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

DECORATORS_DROPPED = ("njit", "jit", "numba.njit", "numba.jit", "vectorize", "guvectorize")


@dataclass
class HarnessResult:
    namespace: dict[str, Any]
    loaded: list[str]
    dropped_decorators: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def __getitem__(self, name: str) -> Callable:
        return self.namespace[name]


def _decorator_name(node: ast.expr) -> str:
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return ast.unparse(node)


def load_functions(
    source_path: str | Path,
    names: tuple[str, ...] | None = None,
    inject: dict[str, Any] | None = None,
    keep_decorators: bool = False,
) -> HarnessResult:
    """Exec the named function definitions from ``source_path`` in a private namespace.

    ``names=None`` loads every top-level function. Imports and module-level
    statements are never executed; ``inject`` supplies the names the source
    expects to find (typically ``np`` and ``pd``).

    ``keep_decorators=True`` KEEPS ``@njit`` (and its ``fastmath`` argument), so
    the caller gets the actually-compiled kernel. That is how the lab measures
    whether Numba and ``fastmath=True`` change a decision (finding HM-08); the
    caller must inject ``njit`` itself.
    """
    path = Path(source_path)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    wanted = set(names) if names else None
    keep: list[ast.stmt] = []
    dropped: list[str] = []
    skipped: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        if wanted is not None and node.name not in wanted:
            continue
        clean = list(node.decorator_list)
        if not keep_decorators:
            node.decorator_list = [
                d for d in clean
                if _decorator_name(d).split(".")[-1] not in DECORATORS_DROPPED
            ]
            for d in clean:
                if d not in node.decorator_list:
                    dropped.append(f"{node.name}:@{_decorator_name(d)}")
        keep.append(node)

    if wanted is not None:
        found = {n.name for n in keep}
        skipped = sorted(wanted - found)

    namespace: dict[str, Any] = {"__name__": f"harness_{path.stem}"}
    namespace.update(inject or {})
    module = ast.Module(body=keep, type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, filename=f"<harness:{path.name}>", mode="exec"), namespace)  # noqa: S102
    return HarnessResult(
        namespace=namespace,
        loaded=[n.name for n in keep],
        dropped_decorators=dropped,
        skipped=skipped,
    )


def default_injection() -> dict[str, Any]:
    """NumPy and Pandas, the two names the sources expect at module scope."""
    import numpy as np
    import pandas as pd

    return {"np": np, "pd": pd}


def numba_injection() -> dict[str, Any]:
    """NumPy, Pandas and the real ``njit``, for loading COMPILED source kernels."""
    from numba import njit

    inject = default_injection()
    inject["njit"] = njit
    return inject
