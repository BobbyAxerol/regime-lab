#!/usr/bin/env python
"""Does the suite actually GUARD what the reports claim? Break it and find out.

Running the tests tells you they pass. It does not tell you which claims they
would catch being false. This mutates one recorded invariant at a time, re-runs
the tests that ought to notice, and restores the artifact.

First run: **6 of 13 caught**. The seven misses were claims recorded and never
checked -- including the two most load-bearing in the lab, since a phase audit
could report every clause DONE with empty evidence and a coverage file could
mark a requirement COVERED with no tests. Guards for all seven now live in
tests/test_contingency_paths.py.

Artifacts are restored from an in-memory copy of the original bytes even when a
test run fails, so an interrupted run cannot leave a mutated artifact behind.
Re-run this after adding any new reported invariant.
"""
import json, pathlib, subprocess, sys

LAB = pathlib.Path(__file__).resolve().parent.parent
PY_BIN = pathlib.Path(sys.executable)

CASES = [
    ("configs/lab07_continuous_trace.json",
     lambda d: d["continuous_account"].__setitem__("account_resets", 3),
     "the trace reports an account reset"),
    ("configs/lab07_continuous_trace.json",
     lambda d: d["continuous_account"].__setitem__("spliced_from_independent_runs", True),
     "the trace says the account was spliced"),
    ("configs/lab07_continuous_trace.json",
     lambda d: d["prefix_stability"].__setitem__("prefix_survives_future_mutation", False),
     "the prefix stops surviving a future mutation"),
    ("configs/lab07_continuous_trace.json",
     lambda d: d["regime_information_isolation"]["activation_sources"].__setitem__(
         "act-fold1", "regime_observation"),
     "an activation becomes regime-driven"),
    ("configs/lab07_continuous_trace.json",
     lambda d: d["training_jobs"]["benchmark"].__setitem__("source", "guessed"),
     "the refit latency loses its provenance"),
    ("configs/lab07_continuous_trace.json",
     lambda d: d["continuous_account"].__setitem__("exit_fixed_point_converged", False),
     "the exit fixed point stops converging"),
    ("configs/lab07_continuous_trace.json",
     lambda d: d["failures"].__setitem__("modes_never_exercised", ["LIQUIDATION"]),
     "a failure mode goes unexercised"),
    ("configs/lab06_decision_ledger.json",
     lambda d: d.__setitem__("every_decision_has_a_reason", False),
     "a decision loses its reason"),
    ("configs/lab06_decision_ledger.json",
     lambda d: d["verdicts"]["every_decision_has_a_reason"].__setitem__("checked", 0),
     "a real verdict silently becomes vacuous"),
    ("configs/operational_segments.json",
     lambda d: d.__setitem__("open_segment_has_null_end", False),
     "an open segment gains an end"),
    ("configs/acceptance_test_coverage.json",
     lambda d: (d["requirements"][0].__setitem__("status", "COVERED"),
                d["requirements"][0].__setitem__("tests", [])),
     "a requirement is COVERED with no tests"),
    ("configs/lab07_task_audit.json",
     lambda d: (d["tasks"][0].__setitem__("evidence", ""),
                d["tasks"][0].__setitem__("status", "DONE")),
     "a checklist clause is DONE with no evidence"),
    ("configs/assertion_vacuity_audit.json",
     lambda d: d.__setitem__("undeclared", ["somewhere.py:1"]),
     "an undeclared unreachable assertion appears"),
]

def main() -> int:
    results = []
    for rel, mutate, label in CASES:
        path = LAB / rel
        if not path.is_file():
            print(f"  skipped      {label} ({rel} missing)", flush=True)
            continue
        backup = path.read_bytes()
        try:
            document = json.loads(path.read_text())
            mutate(document)
            path.write_text(json.dumps(document, indent=2) + "\n")
            # the WHOLE suite, not a guessed subset. The first version passed a
            # per-case selector, which encoded a belief about which test ought to
            # notice -- and the guards written in response to its own findings
            # lived in a file it never ran.
            proc = subprocess.run([str(PY_BIN), "-m", "pytest", str(LAB / "tests"), "-q", "-x",
                                   "-p", "no:cacheprovider"],
                                  cwd=str(LAB), capture_output=True, text=True)
        finally:
            path.write_bytes(backup)          # restored even if the run blew up
        caught = proc.returncode != 0
        results.append({"invariant": label, "artifact": rel, "caught": caught,
                        "first_failure": next(
                            (ln for ln in proc.stdout.splitlines() if ln.startswith("FAILED")),
                            None)})
        print(f"  {'caught      ' if caught else 'NOT CAUGHT  '} {label}", flush=True)

    missed = [r["invariant"] for r in results if not r["caught"]]
    document = {
        "schema": "crypto_regime_lab.guard_strength_audit.v1",
        "mutations": results,
        "mutations_total": len(results),
        "mutations_caught": sum(1 for r in results if r["caught"]),
        "unguarded_invariants": missed,
        "rule": ("a recorded claim that survives being falsified is not evidence. Every "
                 "invariant a report quotes must have a test that fails when it is broken"),
        "method": ("mutate one recorded invariant, run the ENTIRE suite, restore the artifact "
                   "from its original bytes. Running a guessed subset is how the first version "
                   "missed guards that existed"),
    }
    (LAB / "configs" / "guard_strength_audit.json").write_text(
        json.dumps(document, indent=2) + "\n")

    print(f"\n{document['mutations_caught']}/{document['mutations_total']} mutations caught")
    if missed:
        print("UNGUARDED INVARIANTS:")
        for label in missed:
            print(f"   {label}")
    return 0 if not missed else 1


if __name__ == "__main__":
    raise SystemExit(main())
