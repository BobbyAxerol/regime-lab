# AGENTS.md — QuantBT Crypto Regime & Parameter Time-Edge Lab

Research lab (not a product) around a pinned, unmodified `quantbt-engine==1.1.1`. It asks whether
regime information selects parameters and times their deployment better than calendar WFO. The
authoritative plan is `QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md` (Vietnamese, ~1830
lines). `CLAUDE.md` is the English digest of its binding rules — read both before changing
anything. `CLAUDE.md`'s "Current state" section is stale (it ends at LAB-08); the artifacts below
are the executable truth.

## Current state (verify, don't assume)

- LAB-00 … LAB-09 complete; **LAB-10 not started**. `reports/lab01_report.md` … `lab09_report.md`
  are the measured results; `configs/*_task_audit.json` are the clause audits.
- LAB-09 conclusion: **`FAILED_VALIDITY`**. Root cause COR-13: the registered one-way fee was
  passed into the engine's `fee` parameter, which quantbt documents as a legacy ROUND-TRIP fee and
  halves — every account was charged 0.0002 instead of 0.0004. This is a **design** defect (one
  of twelve re-selected arm/cutoff choices changed at the registered fee), not just accounting.
- `reports/improvement_opinions.md` = opinions that are **written, never run**, and never mixed
  into results. Do not implement them without the user picking one.
- Lab git: repo on `main`, remote `regime-lab`. **Standing rule (user): commit every finished
  piece of work**, not only at phase ends. Before each commit run `git status` + `git diff`, stage
  only the intended files, and keep one scoped purpose per commit. Never commit the venv or
  secrets. Push only when explicitly asked.

## Environment and commands

Run from the lab root. Use only the lab venv — never the shared `/root/bobby/pool_alpha/.venv`.

```bash
LAB=/root/bobby/pool_alpha/lab_regime_model_quantbt
$LAB/environments/lab_venv/bin/python -m pytest $LAB/tests -q            # full suite (~786 tests)
$LAB/environments/lab_venv/bin/python -m pytest $LAB/tests/test_x.py::test_y -q
$LAB/environments/lab_venv/bin/python -m pyflakes src scripts tests     # clean except src/.../alphas/raw-supplied/
PYTHONPATH=src $LAB/environments/lab_venv/bin/python -m crypto_regime_lab.cli <stage> --lab-root $LAB
$LAB/environments/lab_venv/bin/python scripts/<runner>.py               # scripts insert src/ themselves
```

- `python -m crypto_regime_lab.cli` needs `PYTHONPATH=src`; pytest gets it from `tests/conftest.py`.
- Rebuild the venv with `scripts/bootstrap_lab.py` + `configs/requirements.lock`; `environments/`
  and `wheelhouse/` are gitignored and machine-specific.
- Audits that gate the reports: `scripts/audit_assertion_vacuity.py`,
  `scripts/audit_guard_strength.py`, `scripts/audit_forbidden_claims.py`,
  `scripts/audit_evidence_pointers.py`, `scripts/audit_lab09.py`.
- **Report `git -C /root/bobby/pool_alpha/quantbt status --porcelain` at the end of every reply**
  (user rule 12). State the result plainly; if anything was touched, say so immediately.

## Hard boundaries (violating these invalidates the lab)

- **All writes stay inside `LAB_ROOT`.** `../quantbt`, `../alphas_storage` (loader + storage), and
  the four supplied alpha files are strictly read-only: no edits, no `pip install -e`, no builds,
  no git write commands, no `chmod`/`sudo`. Lab-only patch ideas go in `handoff/lab_only_patch.diff`
  as proposals.
- QuantBT comes from the lab venv install. Never invent an endpoint — map it in
  `configs/api_binding_map.json` or record `BLOCKED_CAPABILITY`.
- Network is off during `run`/`certify`/`report`. Missing data is reported as missing, never fetched
  or zero-filled.
- **Never call `data_loader.py` at run time.** The lab parses it statically for path routing and
  reads its own byte-copied parquet under `snapshots/` directly; the pinned loader's int64 volume
  cast corrupts fractional-volume symbols (measured in `reports/data_sources_used.md`).
- Point every cache inside the lab; set `PYTHONDONTWRITEBYTECODE=1` in processes touching protected
  source.

## Repo conventions an agent would otherwise get wrong

- **Reports are generated, not written.** `scripts/write_lab0N_report.py` renders
  `reports/lab0N_report.md` from committed artifacts only; never hand-edit a number. Tests assert
  the figures appear in the markdown, every report has a glossary defining its terms, and the
  registered primary endpoint (`configs/study_registration.json`) + minimum economic effect
  (`configs/minimum_economic_effect.json`) are used — not a more convenient statistic.
- **Registrations precede runs.** Hypothesis IDs, contrasts, conclusion-level vocabulary, seeds,
  cost multipliers and budgets are fixed in `configs/` before measurements; check timestamps
  (`registered_at_utc`) when adding anything. A conclusion level must come from the registered
  vocabulary; a blocker caps the claim.
- **Evidence is append-only and strict JSON**, `lab_run_id` on every artifact, `null` + reason for
  missing metrics. A `NOT_READY` alpha keeps null metrics — never PnL = 0. Corrections are recorded
  in `configs/correction_ledger.json`, and a superseding run must be later, not nicer.
- **Checklists are written before code** (`configs/lab0N_checklist.json`); audits read them.
  Keep tests mapped to the T01–T64 acceptance IDs; `tests/` are the acceptance gates.
- **A green gate is not proof.** Most past defects were checks that passed because nothing
  happened: `all([]) == True`, a key defaulting to `0.0`, a probe handed its own answer. New
  verdicts must carry a denominator and a way to go red. Use the `lab_tmp` fixture for scratch
  files that go through the read guard — pytest's `tmp_path` is outside `LAB_ROOT` and is refused.
- **quantbt cost binding**: `fee` is round-trip; pass the one-way rate as `fee_rate=` (or
  `fee=2*one_way`). The fee defect above cost the whole study its validity.
- The deflated corners: `src/crypto_regime_lab/alphas/raw-supplied/` fails pyflakes by design;
  `snapshots/**/*.parquet`, `environments/`, `wheelhouse/`, `.cache/` are gitignored but
  regenerable.

## Architecture in one paragraph

`src/crypto_regime_lab/` layers: `safety` (path guards, sandbox, source integrity), `data`
(byte-copied parquet panels), `alphas` (4 adapters × version tiers, raw-supplied bytes are
provenance-only), `selector` (robust neighborhood + candidate bank), `regime` (sparse jump-model
state inference), `response` (parameter-response), `policy` (four-clock activation), `experiments`
(factorial arms A–E), `integration` (continuous-account delivery), `quantbt_bridge` (the lab-owned
facade over the installed engine), `evidence` (atomic JSON writer). Arms: A = installed WFO +
calendar, B = neighborhood selector + calendar, C = installed selector + regime-triggered refresh,
D = both, E = bank + response policy. Primary matrix = 4 alphas × 5 symbols = 20 cells; A-HASH is
NOT_READY in all 5.
