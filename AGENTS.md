# AGENTS.md — QuantBT Crypto Regime & Parameter Time-Edge Lab

Research lab (not a product) around a pinned, unmodified `quantbt-engine==1.1.1`. It asks whether
regime information selects parameters and times their deployment better than calendar WFO. The
five-phase corrective study RF-01…RF-05 is complete (`REGIME_LAB_MODE4_CAUSAL_REBUTTAL_REPAIR_5_PHASES_FINAL_VI.md`,
Vietnamese, ~13.5k lines; `CLAUDE.md` is the English digest). **The current authority is the RA
guide** `REGIME_LAB_MODE4_CORRECTIVE_AGENT_PHASE_GUIDE_VI.md` (RA-GUIDE-1.0, phases RA-01…RA-08,
per-phase owner approval). `QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md` applies only where
not superseded. Read the active guide before changing anything.

## Current state (verify, don't assume)

- Historical study LAB-01 … LAB-09 is complete and its conclusion is **`FAILED_VALIDITY`**
  (`reports/lab09_report.md`). LAB-10 is folded into the corrective phases below — there is no
  separate LAB-10 run. `evidence/crypto_regime_timeedge_v2/` is append-only and never edited.
- The authoritative plan is the five-phase corrective study **RF-01 … RF-05** on branch
  `mode4-corrective` (`study_id=corrective_mode4_v3`, stable dirs under
  `evidence/corrective_mode4_v3/`). Registered spec:
  `evidence/corrective_mode4_v3/RF-01/corrective_study_spec.json`. Historical claim verdicts are
  superseded to `NOT_EVALUABLE` in `historical_invalidation.json` without editing any historical
  artifact.
- **RF-01 … RF-05 are complete.** RF-01 = identity/binding/invalidation and the then-failing
  before-repair probes; RF-02 = real-snapshot event account and public Mode 4 baseline; RF-03 =
  causal regime controller; RF-04 = 10-cell event-route paired discovery
  (`RF-04/paired_discovery_full.json`) plus design freeze, decay and controls; RF-05 = freeze,
  recompute, claims, integrity and handoff (`RF-05/report.md`, `claim_report.json`, etc.).
  Coverage is **10 of 20 planned cells executed**; A-VWAP/A-HASH stay `BLOCKED_CAPABILITY` with
  null metrics + reasons, never zero-filled.
- **RF-05 claim**: `TECHNICALLY_VALID_WITH_PARTIAL_COVERAGE`, economic `INCONCLUSIVE`. Paired
  common-date daily `M4_REGIME - M4_CAL` aggregate (10 cells): mean −0.1123 bps/day, block
  bootstrap (5 days, 2000 draws, seed 20260911) 95% CI [−0.4940, +0.1907]; `M4_REGIME −
  M4_CAL_MATCHED` (1 evaluable cell, A-HMA/BTCUSDT; A-SC endpoint is `DEVIATED`): +0.1620
  [−0.2142, +0.6154]. Holm over {TIMING, BUDGET_AWARE} (m=2) → both `INCONCLUSIVE` against the
  frozen MDE 0.0371 bps/day; A-SC/SOLUSDT is `NEGATIVE_WITHIN_SCOPE` at cell level. No `POSITIVE`.
  Contamination `NESTED_RETROSPECTIVE` (no untouched holdout);
  `RF-05/prospective_protocol.json` is `SPECIFIED_NOT_EXECUTED` and must not be run here.
- **RA-01 is COMPLETE and its verifier recorded `overall: PASS`** (2026-09-18,
  run `ra01-20260918T093759Z-e72c0dd9`; independent verify exit 0; all five gates G01-ID/MIG/
  VERIFY/BUDGET/REPORT pass). All G01 gates + 14 tests in `tests/ra_corrective/` are green.
  Key facts locked: branch `mode4-corrective`, engine 1.1.1/native 0.4.2 (pip, no direct_url),
  endpoint sha installed==protected; ledger `TE02-PILOT-R03` charged 165457.9s / 300000s with the
  RUNNING row `bc9d8951…` classified `ORPHAN_NO_LIVE_PROCESS` (recovery belongs to the TE
  supervisor, not RA-01); 7-row protocol migration (incl. T02 run-output-dedup scoping); 4-arm
  registration with M4_CAL_MATCHED as canonical CAL_BUDGET and economic fields
  `PENDING_CALIBRATION`. Approvals in RA-01's OWN frozen `registration.json` stay `PENDING`
  forever by design (`ra/verifier.py` enforces this — a script cannot self-approve its own
  phase). Two earlier attempts (08:33Z FAIL — verifier did not read the nested identity schema;
  09:36Z PASS) are kept append-only. RA-01 code/artifacts are committed (commits `b2a58af`, `fa3be63`).
- **Owner approved RA-01→RA-02 on 2026-09-18** — recorded, not inferred, in
  `evidence/regime_time_edge_ra_v1/owner_decisions.jsonl` (append-only; `scripts/
  record_owner_decision.py` writes it, never overwrites a `decision_id`). This is a SEPARATE
  ledger from any phase's own frozen gate — RA-01/RA-02's own `phase_gate.json`/`registration.json`
  correctly keep reading `PENDING`/`false`; the decision ledger is what the *next* phase's
  admission must consult. Before recording, verify the ledger's last entry actually covers the
  transition you are about to start — do not assume today's approval extends past RA-02.
- **RA-02 is COMPLETE, technical_gate PASS, 5/5 gates** (run `ra02-20260918T134757Z-76c16f60`,
  2026-09-18; two earlier same-day drafts FAILED on real bugs then were fixed — see their kept
  `phase_gate.json`s — a third draft already reached 5/5 before this run). 1 real QuantBT
  engine call (1440 bars), cross-run reuse HIT with 0 new engine runs and a byte-equal payload,
  resume-parity PASS with the red control (tell-dropping restart) actually diverging — proving
  the parity check isn't vacuous. Ledger `TE02-PILOT-R03` unchanged by the phase (RA-02 charges
  nothing to the shared TE budget). Commits `2819fbd6` (implementation), `91c3591b` (evidence,
  4 runs kept). `research_status: NOT_ASSESSED` — no economic/market claim.
- **Test suite (2026-09-18, 1092 collected): 1089 passed, 3 failed** (full run ≈3m53s). All
  three pre-exist RA-02 and are unrelated to it (confirmed: none touch `src/crypto_regime_lab/ra/`
  or `tests/ra_corrective/`); do not fix them as a side effect of an unrelated phase without the
  owner's separate say-so (R-17):
  - `test_guide_publishing_discipline.py::test_all_nine_forbidden_claims_are_checked` +
    `test_each_check_names_the_evidence_the_claim_would_need` — forbidden-claims check #1
    ("regime works") now structurally FAILs because `acceptance_test_coverage.json` marks
    T62/T63 `COVERED` since the LAB-09 close-out (commit `ac01a8d`, 2026-09-11) while the LAB-05
    group ablation FAILED out of fold. Flagged `REVIEW_REQUIRED` for the owner in commit
    `161c34a`'s message; still open, still the owner's call, still not silently edited.
  - `test_contingency_paths.py::test_no_assertion_in_the_suite_is_unreached_without_a_declared_reason`
    — `configs/assertion_vacuity_audit.json` lists 21 unreached-and-undeclared assert lines, all
    in `test_rf04_decay_and_controls.py`, `test_rf04_scaling.py`, `test_rf05_claims.py` and
    `test_te03_7.py` (none in RA-02's own tests). None of these five test names ever appeared in
    `scripts/audit_assertion_vacuity.py`'s `ACCEPTED` dict, so this predates today's RA-02 work
    and is most likely TE-03.7's stalled funnel state (still never reaching `MEASURED` — see the
    TE study note below) rather than a regression; not independently re-diagnosed this session —
    re-run `scripts/audit_assertion_vacuity.py` and read each of the 21 lines before deciding
    whether to declare or fix.
  Before-repair tests in `tests/mode4_corrective/` are green — never delete or weaken them.
  RF-05 guards live in `tests/mode4_corrective/test_rf05_claims.py`.
- **Disk cleanup (2026-09-18)**: `git gc --prune=now` (832M→661M .git), removed regenerable
  `.cache/lab0{4,8,9}_*`/`numba`/`te_*` intermediate caches for COMPLETED historical phases
  (70M→13M, gitignored, regenerates on demand — never rerun those phases though), and
  hardlink-deduplicated byte-identical files inside `evidence/time_edge_validation_v4/runs/`
  (mostly the same synthetic 5-symbol world parquet copied across many timed-out shard attempts
  before the identity-keyed compute cache existed) — verified by sha256 before linking, same
  inode after, zero bytes deleted, ~2.0 GB reclaimed. All targets were gitignored; nothing
  git-tracked changed. Host disk: 6.7G→8.8G free. Do not delete (only dedupe) anything under
  `evidence/` — hardlinking is fine (content/path/hash unchanged); the explicit rule below still
  says never delete a large evidence tree.
- The lab marker keeps `study_id=crypto_regime_timeedge_v2` (LAB-01 bootstrap evidence; not
  rewritten).
- **Time-Edge study (TE, `study_id=time_edge_validation_v4`)** runs between RF-05 and RA:
  registration in `configs/time_edge_validation_v4/`, code in
  `src/crypto_regime_lab/time_edge/` + `experiments/dynamic_fold_provider.py`, evidence under
  `evidence/time_edge_validation_v4/`, handoffs `handoff/SESSION_TE_CURRENT.md`,
  `TE_MASTER_PLAN_V1.md/.json`, `TE_PHASE_PLAN_V1.md`, `TE_CLI_RUNBOOK.md`. Ledger
  `TE02-PILOT-R03` had budget 300000s with ~134542s remaining at RA-01 lock (2026-09-18); the
  orphan RUNNING row (`bc9d8951…`) was then reconciled as FAILED at its reservation (commit
  `7d1b2e5a`), so spent is now 193557.8s, **~106442s remaining**. Reread the ledger before
  admitting any new job — do not reuse either number without checking it live. Its binary/run
  outputs are largely gitignored (manifests, ledgers and small JSON stay in git); large untracked
  evidence trees are left alone, not committed wholesale and **never deleted — dedup by hardlink
  is fine (content/path/hash unchanged), delete is not**.
- **RA study (`study_id=regime_time_edge_ra_v1`, new namespace)**: current phase work per
  RA-GUIDE-1.0. Evidence dirs `evidence/regime_time_edge_ra_v1/<run_id>/`; code
  `src/crypto_regime_lab/ra/`; tests `tests/ra_corrective/` (37 tests, green: 14 RA-01 + 10
  C01-C10 cache cases + 13 RA-02 gate-mutation tests). RA-01 and RA-02 both complete; **RA-03
  needs its own owner approval before starting** (R-18 — the RA-01→RA-02 approval in
  `owner_decisions.jsonl` does not extend to RA-03). Sequence:
  RA-01 lock → RA-02 semantic cache (done) → RA-03 memory/fast routes → RA-04 Mode 4 support/admission →
  RA-05 4-arm discovery (STATIC, M4_CAL, M4_CAL_MATCHED=CAL_BUDGET canonical, M4_REGIME; primary
  H-BUDGET) → RA-06 panel/refit-vs-keep → RA-07 replication/falsification → RA-08 freeze/claims.
  `handoff/RA_EXECUTION_PLAN_V1.md` is the committed plan (written when only RA-01 was approved;
  RA-01 and RA-02 are now both done — the file's own prose is stale on that point, its per-phase
  task lists are not). Still one phase finished → report → owner review before the next, per
  R-18. Reuse `M4_CAL_MATCHED`
  as the canonical CAL_BUDGET arm id — do not create a second economically identical arm.
  Raw financial artifacts at TE paths are referenced by path/hash, not copied.
- `reports/improvement_opinions.md` = opinions that are **written, never run**, and never mixed
  into results. Do not implement them without the user picking one.
- Lab git: repo on `main`, remote `regime-lab`; corrective work is on **`mode4-corrective`**.
  **Standing rule (user): commit every finished piece of work**, not only at phase ends. Before
  each commit run `git status` + `git diff`, stage only the intended files, and keep one scoped
  purpose per commit. Never commit the venv or secrets. Push only when explicitly asked.

## Environment and commands

Run from the lab root. Use only the lab venv — never the shared `/root/bobby/pool_alpha/.venv`.

```bash
LAB=/root/bobby/pool_alpha/lab_regime_model_quantbt
$LAB/environments/lab_venv/bin/python -m pytest $LAB/tests -q            # currently 862 passed
$LAB/environments/lab_venv/bin/python -m pytest $LAB/tests/test_x.py::test_y -q
$LAB/environments/lab_venv/bin/python -m pytest $LAB/tests/mode4_corrective -q   # 76 passed (RF guards)
$LAB/environments/lab_venv/bin/python -m pyflakes src scripts tests     # clean except src/.../alphas/raw-supplied/
PYTHONPATH=src $LAB/environments/lab_venv/bin/python -m crypto_regime_lab.cli <stage> --lab-root $LAB
$LAB/environments/lab_venv/bin/python scripts/<runner>.py               # scripts insert src/ themselves
$LAB/environments/lab_venv/bin/python $LAB/scripts/run_rf01.py           # regenerate RF-01 artifacts (--force to supersede)
$LAB/environments/lab_venv/bin/python $LAB/scripts/run_rf01_regressions.py --full
$LAB/environments/lab_venv/bin/python $LAB/scripts/write_rf01_report.py  # renders evidence/corrective_mode4_v3/RF-01/report.md
$LAB/environments/lab_venv/bin/python $LAB/scripts/run_rf05.py --force   # RF-05 freeze/recompute/claims/integrity/handoff (no engine call)
$LAB/environments/lab_venv/bin/python $LAB/scripts/write_rf05_report.py --force  # report.md/json + integrity/repro refresh
$LAB/environments/lab_venv/bin/python $LAB/scripts/run_ra01.py           # RA-01 baseline lock (writes evidence/regime_time_edge_ra_v1/<run_id>/)
$LAB/environments/lab_venv/bin/python $LAB/scripts/verify_ra01.py        # thin verifier over the RA-01 run dir
$LAB/environments/lab_venv/bin/python $LAB/scripts/check_p0_gate.py      # P0 gate from handoff/te_specs
$LAB/environments/lab_venv/bin/python $LAB/scripts/supervise_te_controls.py  # TE controls supervisor (charges the ledger)
```

- The full suite takes ~4–5 minutes; run long jobs in the background and read the log.
- The latest authority for runbooks is `handoff/TE_CLI_RUNBOOK.md` and
  `handoff/RA_EXECUTION_PLAN_V1.md` (RA phases); the RF/LAB scripts above remain valid for
  regeneration and audits (`scripts/audit_*.py`).

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
- Gitignore policy (commit 4ab071c): **all binary data files are ignored repo-wide** (`*.parquet`,
  sqlite side-files, run-output market data over the GitHub size limit); manifests, ledgers,
  receipts and small JSON stay in git. Never force-add large binaries; record the path/hash instead.

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
- **Separate the four validity axes** (RA guide §0.2): technical validity, scientific support,
  economic evidence and owner approval are independent; a positive ranking-IC, switches > 0 or
  positive PnL is never a condition for opening technical discovery. Gate redesign goes through
  `protocol_migration` (old rule → new rule → reason → affected claims/tests); never edit the
  acceptance of an old run to make it green. Keep historical runs, invalidations, costs and
  previous negative/null results raw and untouched.
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
(factorial arms A–E + `dynamic_fold_provider.py`), `time_edge` (Time-Edge v4 study: allocations,
controls, discovery, funnel), `ra` (RA study: admission rules + thin phase verifier),
`integration` (continuous-account delivery), `quantbt_bridge` (the lab-owned
facade over the installed engine), `evidence` (atomic JSON writer). Arms: A = installed WFO +
calendar, B = neighborhood selector + calendar, C = installed selector + regime-triggered refresh,
D = both, E = bank + response policy. Primary matrix = 4 alphas × 5 symbols = 20 cells; A-HASH is
NOT_READY in all 5.
