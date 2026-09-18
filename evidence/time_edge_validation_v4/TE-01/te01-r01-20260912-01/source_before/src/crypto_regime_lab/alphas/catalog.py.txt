"""L02.1 — AST catalog of the four alphas: inputs, parameter reads, unused knobs, presets.

Everything here is static: ``ast.parse`` on the read-only snapshots. No alpha
module is imported or executed (guide L01.3), so a file that cannot even be
imported — ``hash_momentum.py`` raises ``NameError: np`` — is still catalogued.

Preset classification is schema-driven, not shape-driven: a dictionary is a
parameter preset for an alpha only when its keys overlap the parameter names the
alpha's own code actually reads.
"""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from ..safety.archive import ALPHA_IDS

# Parameter dictionaries are read through these local names in the four files.
PARAM_HOLDER_NAMES = ("params", "p")
# Frame-like locals the four files use to reach market data.
FRAME_NAMES = ("df", "data", "df_htf", "df_main_tmp", "df_htf_tmp", "merged", "frame")
# Column names that are market DATA inputs rather than parameters.
MARKET_COLUMNS = ("open", "high", "low", "close", "volume", "time", "symbol")
MIN_SCHEMA_OVERLAP = 0.5  # a preset must share at least half its keys with the schema


@dataclass
class FunctionRecord:
    name: str
    lineno: int
    end_lineno: int
    args: list[str]
    decorators: list[str]
    calls: list[str]
    docstring: str | None


@dataclass
class AlphaInventory:
    alpha_id: str
    filename: str
    sha256: str
    line_count: int
    imports: list[str] = field(default_factory=list)
    imported_names: set[str] = field(default_factory=set)
    functions: list[FunctionRecord] = field(default_factory=list)
    parameter_reads: dict[str, list[int]] = field(default_factory=dict)
    data_inputs: dict[str, list[int]] = field(default_factory=dict)
    index_uses: list[str] = field(default_factory=list)
    literal_dicts: list[dict] = field(default_factory=list)
    undefined_globals: list[str] = field(default_factory=list)
    module_level_effects: list[str] = field(default_factory=list)

    @property
    def parameter_schema(self) -> set[str]:
        return set(self.parameter_reads)

    def as_record(self) -> dict:
        return {
            "alpha_id": self.alpha_id,
            "filename": self.filename,
            "sha256": self.sha256,
            "line_count": self.line_count,
            "imports": self.imports,
            "functions": [
                {
                    "name": f.name, "lineno": f.lineno, "end_lineno": f.end_lineno,
                    "args": f.args, "decorators": f.decorators,
                    "calls": sorted(set(f.calls)), "docstring": f.docstring,
                }
                for f in self.functions
            ],
            "parameter_schema": sorted(self.parameter_schema),
            "parameter_reads": {k: sorted(v) for k, v in sorted(self.parameter_reads.items())},
            "data_inputs": {k: sorted(v) for k, v in sorted(self.data_inputs.items())},
            "required_market_columns": sorted(self.data_inputs),
            "index_uses": self.index_uses,
            "requires_datetime_index": bool(self.index_uses),
            "literal_dict_count": len(self.literal_dicts),
            "undefined_globals": self.undefined_globals,
            "module_level_effects": self.module_level_effects,
        }


class _Visitor(ast.NodeVisitor):
    def __init__(self, inv: AlphaInventory) -> None:
        self.inv = inv
        self._fn_stack: list[FunctionRecord] = []

    # -- imports ---------------------------------------------------------
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.inv.imports.append(alias.name if alias.asname is None else f"{alias.name} as {alias.asname}")
            self.inv.imported_names.add((alias.asname or alias.name).split(".")[0])
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        for alias in node.names:
            self.inv.imports.append(f"from {module} import {alias.name}"
                                    + (f" as {alias.asname}" if alias.asname else ""))
            self.inv.imported_names.add(alias.asname or alias.name)
        self.generic_visit(node)

    # -- functions -------------------------------------------------------
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        record = FunctionRecord(
            name=node.name,
            lineno=node.lineno,
            end_lineno=node.end_lineno or node.lineno,
            args=[a.arg for a in node.args.args],
            decorators=[ast.unparse(d) for d in node.decorator_list],
            calls=[],
            docstring=ast.get_docstring(node),
        )
        self.inv.functions.append(record)
        self._fn_stack.append(record)
        self.generic_visit(node)
        self._fn_stack.pop()

    def visit_Call(self, node: ast.Call) -> None:
        if self._fn_stack:
            try:
                self._fn_stack[-1].calls.append(ast.unparse(node.func))
            except Exception:
                pass
        self.generic_visit(node)

    # -- parameter reads: params['x'] / p['x'] / p.get('x', ...) ---------
    def visit_Subscript(self, node: ast.Subscript) -> None:
        target = node.value
        key = node.slice
        if isinstance(target, ast.Name) and isinstance(key, ast.Constant) \
                and isinstance(key.value, str):
            if target.id in PARAM_HOLDER_NAMES:
                self.inv.parameter_reads.setdefault(key.value, []).append(node.lineno)
            elif target.id in FRAME_NAMES and key.value in MARKET_COLUMNS:
                self.inv.data_inputs.setdefault(key.value, []).append(node.lineno)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self.generic_visit(node)


def _collect_index_uses(tree: ast.AST, inv: AlphaInventory) -> None:
    """Record every use of the frame index: these force a DatetimeIndex requirement."""
    uses: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "index" and \
                isinstance(node.value, ast.Name) and node.value.id in FRAME_NAMES:
            uses.append(f"{node.value.id}.index@L{node.lineno}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and \
                node.func.attr in ("resample", "tz_convert", "tz_localize", "normalize"):
            uses.append(f"{node.func.attr}@L{node.lineno}")
    inv.index_uses = sorted(set(uses))


def _collect_get_calls(tree: ast.AST, inv: AlphaInventory) -> None:
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get" and isinstance(node.func.value, ast.Name)
                and node.func.value.id in PARAM_HOLDER_NAMES and node.args
                and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
            inv.parameter_reads.setdefault(node.args[0].value, []).append(node.lineno)


def _collect_literal_dicts(tree: ast.AST, inv: AlphaInventory) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
            continue
        try:
            payload = ast.literal_eval(node.value)
        except (ValueError, SyntaxError, TypeError):
            continue
        if not isinstance(payload, dict):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                typed = json.dumps(payload, sort_keys=True, default=str)
                inv.literal_dicts.append({
                    "name": target.id,
                    "lineno": node.lineno,
                    "keys": sorted(str(k) for k in payload),
                    "values": payload,
                    "values_digest": hashlib.sha256(typed.encode()).hexdigest(),
                })


BUILTIN_NAMES = set(dir(__builtins__)) if isinstance(__builtins__, dict) else set(dir(__builtins__))


def _collect_undefined_globals(tree: ast.AST, inv: AlphaInventory) -> None:
    """Names used at module scope that are neither imported, defined, nor builtins.

    This is how ``hash_momentum.py``'s missing numpy import is found without
    importing it (finding AH-01).
    """
    defined: set[str] = set(inv.imported_names)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    defined.add(target.id)
        elif isinstance(node, (ast.For, ast.comprehension)):
            target = getattr(node, "target", None)
            if isinstance(target, ast.Name):
                defined.add(target.id)
        elif isinstance(node, ast.arg):
            defined.add(node.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            defined.add(node.id)
    import builtins

    used: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used.setdefault(node.id, node.lineno)
    inv.undefined_globals = sorted(
        f"{name}@L{line}" for name, line in used.items()
        if name not in defined and not hasattr(builtins, name)
    )


def _collect_module_effects(tree: ast.Module, inv: AlphaInventory) -> None:
    inert = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Import, ast.ImportFrom)
    literal = (ast.Constant, ast.Dict, ast.List, ast.Tuple, ast.Name)
    for node in tree.body:
        if isinstance(node, inert):
            continue
        if isinstance(node, ast.Assign) and isinstance(node.value, literal):
            continue
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            inv.module_level_effects.append(f"L{node.lineno} call at module scope")
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue  # bare string / docstring
        inv.module_level_effects.append(f"L{node.lineno} {type(node).__name__}")


def inventory_file(path: Path, sha256: str) -> AlphaInventory:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    inv = AlphaInventory(
        alpha_id=ALPHA_IDS[path.name],
        filename=path.name,
        sha256=sha256,
        line_count=len(source.splitlines()),
    )
    _Visitor(inv).visit(tree)
    _collect_get_calls(tree, inv)
    _collect_index_uses(tree, inv)
    _collect_literal_dicts(tree, inv)
    _collect_undefined_globals(tree, inv)
    _collect_module_effects(tree, inv)
    return inv


def classify_presets(inventories: dict[str, AlphaInventory]) -> tuple[list[dict], list[dict]]:
    """Split every literal dictionary into (preset_catalog, unmapped_presets).

    A dictionary maps to an alpha when at least ``MIN_SCHEMA_OVERLAP`` of its keys
    are parameter names that alpha actually reads. Nothing is assigned by shape,
    by name, or by which file it happens to sit in.
    """
    schemas = {inv.alpha_id: inv.parameter_schema for inv in inventories.values()}
    catalog: list[dict] = []
    unmapped: list[dict] = []
    for inv in inventories.values():
        for entry in inv.literal_dicts:
            keys = set(entry["keys"])
            overlaps = {
                alpha_id: len(keys & schema) / len(keys) if keys else 0.0
                for alpha_id, schema in schemas.items()
            }
            best_alpha = max(overlaps, key=lambda a: overlaps[a])
            best_ratio = overlaps[best_alpha]
            own_ratio = overlaps[inv.alpha_id]
            record = {
                "preset_id": f"{inv.alpha_id}|{inv.sha256[:12]}|{entry['name']}|{entry['values_digest'][:12]}",
                "declared_in_alpha": inv.alpha_id,
                "declared_in_file": inv.filename,
                "dictionary_name": entry["name"],
                "source_line": entry["lineno"],
                "key_count": len(entry["keys"]),
                "keys": entry["keys"],
                "values": entry["values"],
                "values_digest": entry["values_digest"],
                "schema_overlap_own_alpha": round(own_ratio, 4),
                "schema_overlap_best_alpha": best_alpha,
                "schema_overlap_best_ratio": round(best_ratio, 4),
                "keys_in_own_schema": sorted(keys & schemas[inv.alpha_id]),
                "keys_outside_own_schema": sorted(keys - schemas[inv.alpha_id]),
                "provenance": "user_full_sample_tpe",
                "eligible_for_retrospective_reference": True,
                "eligible_for_early_fold_warm_start": False,
                "eligible_for_primary_candidate_bank": False,
                "eligible_for_independent_oos_claim": False,
            }
            if own_ratio >= MIN_SCHEMA_OVERLAP:
                record["classification"] = "PARAMETER_PRESET"
                record["missing_schema_keys"] = sorted(schemas[inv.alpha_id] - keys)
                catalog.append(record)
            else:
                record["classification"] = "UNMAPPED"
                record["reason"] = (
                    f"only {own_ratio:.0%} of its keys are read by {inv.alpha_id}; "
                    "not a valid search space for that alpha and never executed"
                )
                record["eligible_for_retrospective_reference"] = False
                unmapped.append(record)
    return catalog, unmapped


def unused_knobs(inv: AlphaInventory, source: str) -> dict:
    """Parameters accepted or declared but never used in a decision.

    Reported per finding HM-05 (``time_ms``, ``volume``, ``double_up``, ``sl_mult``).
    """
    tree = ast.parse(source)
    # Scope matters: a name that is unused inside one function may be a local in
    # another. Counting module-wide Loads hid `time_ms`, which the wrapper passes
    # through but the core never reads.
    unused_args: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        loads: set[str] = set()
        for child in ast.walk(node):
            if child is node:
                continue
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child is not node:
                continue  # a nested def has its own scope
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                loads.add(child.id)
        dead = [a.arg for a in node.args.args if a.arg not in loads]
        if dead:
            unused_args[node.name] = dead
    preset_keys: set[str] = set()
    for entry in inv.literal_dicts:
        preset_keys |= set(entry["keys"])
    never_read = sorted(preset_keys - inv.parameter_schema)
    return {
        "unused_function_arguments": unused_args,
        "preset_keys_never_read_by_the_alpha": never_read,
        "note": (
            "an unused argument or an unread preset key must be dropped from the active search "
            "space and flagged deprecated, never re-implemented under the old name (guide HM-05)"
        ),
    }
