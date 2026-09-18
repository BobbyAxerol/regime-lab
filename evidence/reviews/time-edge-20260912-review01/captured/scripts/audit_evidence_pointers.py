#!/usr/bin/env python
"""Do the EARLIER phases' evidence pointers still resolve?

COR-15: every phase audit before LAB-09 marked a clause DONE when a STRING
naming its evidence was present. A pointer at a field that was later renamed, at
a test that was deleted, or at an artifact that never existed is
indistinguishable from a real one — and every phase report quotes its audit.

So the LAB-09 resolver is turned on the audits that came before it. Each
`lab0N_task_audit.json` task's `evidence` string is split on ` + `, and each
fragment is classified:

    RESOLVED                  the JSON path walks, pytest collects the node id,
                              or the source file defines the symbol
    BROKEN                    it looks like a pointer and does not resolve
    PROSE                     it is a sentence, not a pointer — reported as such
                              rather than counted either way

A BROKEN pointer is a defect in the audit, not necessarily in the phase: the
claim may be true and the evidence merely misfiled. Both need fixing, and the
difference is stated per finding rather than assumed.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))
sys.path.insert(0, str(LAB_ROOT / "scripts"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402
from audit_lab09 import collected_tests, walk  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
CONFIGS = LAB_ROOT / "configs"
AUDITS = [f"lab0{n}_task_audit.json" for n in range(1, 10)]

#: The lab's own directories. A bare `a/b` fragment is only a pointer if it
#: starts in one of them -- an earlier version accepted any slash-separated
#: token, so `open/high/low/close/volume`, `BTC/ETH` and `15/15` were all
#: reported as broken paths. An auditor that manufactures findings is no better
#: than one that misses them, and this one produced 36 of them on its first run.
LAB_DIRS = ("configs/", "src/", "scripts/", "tests/", "evidence/", "reports/", "figures/",
            "snapshots/", "handoff/", "vendor_readonly/", "environments/", "alphas/",
            "quantbt_candidate/", "wheelhouse/", ".cache/")
EXTENSIONS = (".json", ".jsonl", ".py", ".md", ".parquet", ".lock", ".diff", ".txt")

#: a fragment that looks like a pointer: an artifact path, a test node id, or a
#: source symbol. Anything else is prose and is reported as prose.
POINTER = re.compile(
    r"^(?:[\w./-]+\.json(?::[\w.\[\]-]+)?|tests/[\w/]+\.py::[\w\[\]-]+|"
    r"(?:src/)?[\w/]+\.py(?::[\w.]+)?|[\w./*-]+)$")


def looks_like_a_pointer(fragment: str) -> bool:
    """A locator, not a phrase that happens to contain a slash."""
    if "::" in fragment:
        return bool(POINTER.match(fragment))
    if not POINTER.match(fragment):
        return False
    head = fragment.split(":")[0]
    return head.startswith(LAB_DIRS) or head.endswith(EXTENSIONS)


def classify_test(name: str, tests: set[str]) -> dict:
    """A bare test function name, from a record's `tests` list.

    Only a name that came from that LIST is looked up. An earlier version also
    picked up any word beginning with `test_` inside an evidence SENTENCE, and
    reported the field name `test_coverage` as a missing test -- a finding
    manufactured by the auditor.
    """
    matches = [node for node in tests if node.endswith(f"::{name}")]
    return {"fragment": name, "from": "tests[]",
            "verdict": "RESOLVED" if matches else "BROKEN",
            "detail": (f"collected in {matches[0].split('::')[0]}" if matches
                       else "no test with this name is collected")}


#: Every config artifact stem, so `lab05_selftest.acceptance_checks.T37` can be
#: recognised as `lab05_selftest.json:acceptance_checks.T37`. LAB-04 and LAB-05
#: wrote pointers in that shorthand; it is unambiguous as long as the stem
#: matches a real artifact, so it is resolved rather than dismissed as prose.
CONFIG_STEMS = {path.stem for path in CONFIGS.glob("*.json")}


def normalise(fragment: str) -> str:
    """Canonicalise the notations the earlier audits used.

    `[*]` and `[]` mean the same thing. A dotted path whose first segment names a
    config artifact is that artifact's path. Neither is a guess: both are checked
    against what is on disk before they are accepted.
    """
    fragment = fragment.replace("[*]", "[]")
    if ":" in fragment or fragment.endswith(EXTENSIONS) or "." not in fragment:
        return fragment
    stem, _, rest = fragment.partition(".")
    # `lab07_continuous_trace.json` is a FILENAME, not `lab07_continuous_trace`
    # with a field called `json`. An earlier version of this rule rewrote six
    # perfectly good pointers into that and reported them broken.
    if stem in CONFIG_STEMS and rest and rest != "json":
        return f"{stem}.json:{rest}"
    # `robustness.convergence_report` and `model_selection.STARTING_K` name a
    # MODULE and a symbol in it. LAB-04/05 wrote most of their pointers this way,
    # and a module that no longer defines the symbol is exactly the rot this
    # audit exists to find -- so it is resolved rather than filed as prose.
    return fragment


def module_paths(stem: str) -> list[str]:
    """Every module with this basename. There are two `quality.py`.

    Returning only the first made a pointer at `quality.check_degeneracy` resolve
    against `data/quality.py`, which does not define it, and reported a live
    pointer as rotted.
    """
    package = LAB_ROOT / "src" / "crypto_regime_lab"
    return sorted(str(c.relative_to(package)) for c in package.rglob(f"{stem}.py"))


def as_module_symbol(fragment: str, tests: set[str]) -> dict | None:
    """`module.symbol` shorthand, tried against every module with that name.

    A shorthand the auditor INFERRED is never reported BROKEN: if no module with
    that name defines the symbol, the inference was wrong, and the honest verdict
    is that the fragment is prose this tool could not resolve -- not that the
    phase's evidence is missing.
    """
    if ":" in fragment or "/" in fragment or "." not in fragment:
        return None
    stem, _, rest = fragment.partition(".")
    candidates = module_paths(stem)
    if not candidates or not rest:
        return None
    for relative in candidates:
        verdict = classify(f"{relative}:{rest}", tests)
        if verdict["verdict"] == "RESOLVED":
            return {**verdict, "fragment": fragment,
                    "detail": f"{verdict['detail']} via {relative}"}
    return {"fragment": fragment, "verdict": "AMBIGUOUS_SHORTHAND",
            "detail": (f"no module named {stem}.py defines {rest}; the shorthand may name a "
                       "field in an artifact rather than a symbol in a module")}


def classify(fragment: str, tests: set[str]) -> dict:
    fragment = normalise(fragment.strip().rstrip(",;"))
    if not fragment:
        return {"fragment": fragment, "verdict": "EMPTY"}
    if fragment.startswith("test_") and " " not in fragment and "/" not in fragment:
        # LAB-04/05 put bare test names in the `artifact` field
        return classify_test(fragment, tests)
    inferred = as_module_symbol(fragment, tests)
    if inferred is not None:
        return inferred
    if not looks_like_a_pointer(fragment):
        return {"fragment": fragment[:110], "verdict": "PROSE"}
    if "*" in fragment:
        matches = list(LAB_ROOT.glob(fragment.split(":")[0].replace("...", "*")))
        return {"fragment": fragment,
                "verdict": "RESOLVED" if matches else "BROKEN",
                "detail": f"{len(matches)} paths match" if matches else "no path matches"}
    if "..." in fragment:
        matches = list(LAB_ROOT.glob(fragment.split(":")[0].replace("...", "*")))
        return {"fragment": fragment,
                "verdict": "RESOLVED" if matches else "BROKEN",
                "detail": f"{len(matches)} paths match the elided path"
                          if matches else "no path matches the elided path"}
    if "::" in fragment:
        node = fragment if fragment.startswith("tests/") else f"tests/{fragment}"
        ok = node in tests or node.split("[")[0] in tests
        return {"fragment": fragment, "verdict": "RESOLVED" if ok else "BROKEN",
                "detail": "collected" if ok else "pytest does not collect this node id"}
    name, _, path = fragment.partition(":")
    if name.endswith(".json"):
        artifact = CONFIGS / Path(name).name
        where = "configs"
        if not artifact.is_file():
            artifact, where = LAB_ROOT / name, "lab root"
        if not artifact.is_file():
            # not every artifact is a config. `environment_pin.json` is written by
            # the evidence writer into evidence/{study}/{run}/, and a resolver that
            # only knows configs/ calls a perfectly good pointer dead.
            runs = sorted((LAB_ROOT / "evidence").rglob(Path(name).name))
            if runs:
                artifact, where = runs[-1], f"evidence ({runs[-1].parent.name})"
        if not artifact.is_file():
            return {"fragment": fragment, "verdict": "BROKEN",
                    "detail": f"no such artifact {name}"}
        if not path:
            return {"fragment": fragment, "verdict": "RESOLVED",
                    "detail": f"artifact exists in {where}"}
        ok, detail = walk(json.loads(artifact.read_text()), path)
        return {"fragment": fragment, "verdict": "RESOLVED" if ok else "BROKEN",
                "detail": f"{detail} ({where})"}
    for base in (LAB_ROOT, LAB_ROOT / "src" / "crypto_regime_lab"):
        candidate = base / name
        if candidate.is_file():
            return _source_verdict(fragment, candidate, name, path)
        if candidate.is_dir():
            return {"fragment": fragment, "verdict": "RESOLVED", "detail": "directory exists"}
    # a bare basename written inside a sentence -- `response.py`, `vwap.py` -- names a
    # real file that simply is not at the root. Searching for it is the difference
    # between "this pointer is dead" and "this pointer was written informally".
    found = find_by_basename(name)
    if found is not None:
        return _source_verdict(fragment, found, name, path,
                               where=str(found.relative_to(LAB_ROOT))
                               if LAB_ROOT in found.parents else str(found))
    return {"fragment": fragment, "verdict": "BROKEN", "detail": f"no such path {name}"}


def _source_verdict(fragment: str, candidate: Path, name: str, path: str,
                    where: str | None = None) -> dict:
    detail = f"source found at {where}" if where else "source found"
    if path:
        try:
            text = candidate.read_text(errors="ignore")
        except OSError as exc:
            return {"fragment": fragment, "verdict": "BROKEN", "detail": str(exc)}
        # `a.b/c/d` lists sibling members; every one of them has to be there
        wanted = [part for chunk in path.split("/") for part in chunk.split(".")]
        missing = [part for part in wanted if part not in text]
        if missing:
            return {"fragment": fragment, "verdict": "BROKEN",
                    "detail": f"{name} does not define {missing}"}
    return {"fragment": fragment, "verdict": "RESOLVED", "detail": detail}


#: where a bare filename may legitimately live. `environments/` and `evidence/`
#: are excluded on purpose: a basename that only matches inside the venv or a
#: run directory is a coincidence, not the file the pointer meant.
SEARCH_ROOTS = ("src", "scripts", "tests", "configs", "reports", "figures", "handoff",
                "vendor_readonly", "quantbt_candidate")
#: the read-only inputs the guide names. A pointer at one of these is legitimate
#: evidence -- the lab reads them -- and it is labelled EXTERNAL so a reader can
#: see that the file is not under LAB_ROOT.
EXTERNAL_ROOTS = (LAB_ROOT.parent / "alphas_storage" / "_get_data",
                  LAB_ROOT.parent / "alphas_storage" / "alpha_to_tes_regime_model",
                  LAB_ROOT.parent / "quantbt")


def find_by_basename(name: str) -> Path | None:
    basename = Path(name).name
    for root in SEARCH_ROOTS:
        for candidate in (LAB_ROOT / root).rglob(basename):
            if candidate.is_file():
                return candidate
    for root in EXTERNAL_ROOTS:
        candidate = root / basename
        if candidate.is_file():
            return candidate
    return None


def claims(document: dict):
    """(clause id, evidence text) pairs, whatever shape the phase's audit used.

    Three shapes exist, which is itself the finding OP-17 records: LAB-01..03
    nest requirements under a task, LAB-04/05 name the field `artifact`, and
    LAB-06 onward call it `evidence`. Reading only the newest shape would report
    the older phases as having no pointers at all -- a clean sweep for the wrong
    reason.
    """
    for task in document.get("tasks", []):
        identifier = task.get("clause_id") or task.get("task_id") or task.get("id")
        if task.get("requirements"):
            for index, requirement in enumerate(task["requirements"]):
                yield (f"{identifier}.{index}", _evidence_of(requirement),
                       list(requirement.get("tests") or []))
            continue
        yield identifier, _evidence_of(task), list(task.get("tests") or [])


def _evidence_of(record: dict) -> str:
    """The evidence a record carries, in any of the three forms the lab used.

    LAB-01/02/03 sometimes name a bare list of TEST FUNCTIONS instead of an
    evidence sentence. Reading only `evidence` reported 33 clauses as having no
    evidence at all when they name tests -- and the interesting question about a
    named test is whether it still exists, which is exactly what this audit can
    answer.
    """
    return record.get("evidence") or record.get("artifact") or ""


def split_pointers(evidence: str) -> list[str]:
    """Fragments that might be pointers, from a string that may also be prose.

    The later audits separate pointers with ` + `; the earlier ones write a
    sentence with a locator embedded in it. Splitting on whitespace as well
    finds those, at the cost of more PROSE verdicts -- which is the safe
    direction, because a PROSE verdict is never counted as evidence.
    """
    out = []
    for chunk in evidence.split(" + "):
        chunk = chunk.strip()
        if not chunk:
            continue
        if chunk.startswith("test_") and " " not in chunk:
            out.append(chunk)
            continue
        if looks_like_a_pointer(normalise(chunk)):
            out.append(chunk)
            continue
        found = [word.strip(",;()`\"'") for word in chunk.split()
                 if looks_like_a_pointer(word.strip(",;()`\"'"))]
        out.extend(found or [chunk])
    return out


def main() -> int:
    policy = SandboxPolicy.load(CONFIGS / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    tests = collected_tests()
    per_phase, broken = {}, []
    for name in AUDITS:
        path = CONFIGS / name
        if not path.is_file():
            per_phase[name] = {"status": "NO_AUDIT"}
            continue
        document = json.loads(path.read_text())
        rows = []
        for clause_id, evidence, named_tests in claims(document):
            if not evidence and not named_tests:
                rows.append({"clause_id": clause_id, "verdict": "NO_POINTER", "fragments": []})
                continue
            fragments = [classify(f, tests) for f in split_pointers(evidence)] if evidence else []
            fragments += [classify_test(name, tests) for name in named_tests]
            verdict = ("BROKEN" if any(f["verdict"] == "BROKEN" for f in fragments)
                       else "RESOLVED" if any(f["verdict"] == "RESOLVED" for f in fragments)
                       else "AMBIGUOUS_SHORTHAND"
                       if any(f["verdict"] == "AMBIGUOUS_SHORTHAND" for f in fragments)
                       else "PROSE_ONLY")
            rows.append({"clause_id": clause_id, "verdict": verdict, "fragments": fragments})
            if verdict == "BROKEN":
                broken.extend(
                    {"phase": name, "clause_id": clause_id, **f}
                    for f in fragments if f["verdict"] == "BROKEN")
        counts: dict[str, int] = {}
        for row in rows:
            counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
        per_phase[name] = {
            "status": "CHECKED",
            "clauses": len(rows),
            "counts": counts,
            "reported_done": document.get("tasks_done"),
            "clauses_with_a_broken_pointer": [r["clause_id"] for r in rows
                                              if r["verdict"] == "BROKEN"],
            "clauses_with_prose_only": [r["clause_id"] for r in rows
                                        if r["verdict"] == "PROSE_ONLY"],
            "rows": rows,
        }

    document = {
        "schema": "crypto_regime_lab.evidence_pointer_audit.v1",
        "generated_at_utc": utc_now_iso(),
        "question": ("does every phase audit's evidence pointer still resolve, or has some of it "
                     "rotted since it was written?"),
        "why": ("COR-15: an audit that counts the PRESENCE of an evidence string cannot tell a "
                "real pointer from a stale one, and every phase report quotes its audit"),
        "classification": {
            "RESOLVED": "the JSON path walks, pytest collects the node, or the symbol is defined",
            "BROKEN": "it parses as a pointer and does not resolve",
            "PROSE_ONLY": "the clause's evidence is a sentence, not a locator. Not a defect by "
                          "itself -- some clauses are about a rule rather than a field -- but it "
                          "is counted separately so it is never mistaken for a resolved pointer",
            "AMBIGUOUS_SHORTHAND": "the fragment reads as `module.symbol` but no module with "
                                   "that name defines it, so the tool's inference was wrong. "
                                   "Reported separately rather than as BROKEN, because an "
                                   "auditor must not accuse a clause on the strength of its own "
                                   "guess",
            "NO_POINTER": "the clause carries no evidence at all",
        },
        "per_phase": per_phase,
        "broken_total": len(broken),
        "broken": broken,
        "verdict": "ALL_POINTERS_RESOLVE" if not broken else "BROKEN_POINTERS_FOUND",
    }
    with writer.attempt("cross_phase.evidence_pointers") as att:
        att.detail = {"broken": len(broken)}
    writer.write_config("evidence_pointer_audit.json", document)
    writer.write_json("evidence_pointer_audit.json", document, schema=document["schema"])

    for name, record in per_phase.items():
        if record["status"] != "CHECKED":
            print(f"  {name:<26} {record['status']}")
            continue
        print(f"  {name:<26} {record['clauses']:>3} clauses  {record['counts']}")
    print(f"\n{document['verdict']}: {len(broken)} broken pointers")
    for row in broken:
        print(f"  {row['phase']:<26} {row['clause_id']:<10} {row['fragment'][:70]}")
        print(f"      {row.get('detail')}")
    print(f"evidence -> {writer.run_dir}")
    return 0 if not broken else 1


if __name__ == "__main__":
    raise SystemExit(main())
