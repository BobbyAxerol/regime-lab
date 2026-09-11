# LAB-01 — Isolated workspace, pinned baseline, preregistration

**Status: PASS — all 6 sub-tasks complete against the guide text. 43/43 requirements DONE, 0 deferred.** Awaiting user approval before LAB-02. `SAFE_TO_RUN_SYNTHETIC = true`, `OS_ISOLATION = true`, market execution disabled by design.
**Date:** 2026-09-09 · **Study:** `crypto_regime_timeedge_v2` · **Guide:** `QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md`

## 1. What was built

| Task | Delivered |
|---|---|
| L01.1 Resolve allowed paths | `configs/sandbox_policy.json`, `safety/paths.py` — canonical realpath guards, 3 protected roots, 15 forbidden-read roots, read guard + write guard |
| L01.2 Snapshot sources | **Original archive ingested**: `vendor_readonly/alpha_zip_original.zip` → inspected → extracted → digests re-verified → read-only copies in `vendor_readonly/alphas_raw/` |
| L01.3 Environment isolation | `environments/lab_venv/` with **quantbt-engine 1.1.1 + quantbt-native 0.4.2**; 30 wheels pinned; baseline wheels retained in `vendor_readonly/quantbt_1_1_1_dist/`; `quantbt_candidate/` (208 .py) unpacked **from the wheel** |
| L01.4 Evidence + write guard | `evidence/manifest.py` (atomic, strict JSON, attempt ledger) + `evidence/audit_queue.py` (bounded non-dropping queue, run-commit gate) |
| L01.5 Preregistration | `configs/study_registration.json`, `configs/hypothesis_registry.json` — 20 cells, arms A–E, 7 controls, 5 primary contrasts, frozen costs |
| L01.6 Actual API map | `configs/api_binding_map.json` — 6/6 bridge operations bound to real installed symbols, 0 unresolved |
| **Containment** | `safety/sandbox.py` — bubblewrap mount/net/pid namespaces, **measured** at every preflight |

## 2. Technical debt from the first pass — what changed

| # | Debt | Now |
|---|---|---|
| 1 | No OS-level isolation; containment was hygiene only | **CLOSED.** bubblewrap 0.6.1: `--ro-bind /` with `LAB_ROOT` re-bound writable. Write to a protected path fails with **errno 30 (EROFS)** — refused by the kernel, not by our code. All three protected roots verified read-only via the worker's own `/proc/self/mountinfo`. |
| 2 | Network "off" was advisory (proxy vars only) | **CLOSED.** `--unshare-net` gives an empty netns: connect fails **errno 101 (ENETUNREACH)**, DNS fails. Acquisition is a separate opt-in stage (`network=True`), proven by test. |
| 3 | Original archive absent; T03/T04 on synthetic fixtures only | **CLOSED.** User supplied `alpha_to_tes_regime_model.zip`; SHA-256 `57406dbb…6701ae` **matches guide §1.1 exactly**. 10 entries, 0 rejections. Full provenance chain: archive → digest verified → inspected → extracted → digest re-verified → read-only. The loose files in `alphas_storage` are confirmed **byte-identical** to the archive members. |
| 4 | RLIMIT enforcement never exercised | **CLOSED.** An over-budget worker under a 1 GiB cap dies with `MemoryError` (rc≠0) while the parent survives — run as a test, not asserted. |
| 5 | No disk quota accounting | **CLOSED.** `disk_usage_report`: 1.02 GiB used of a 20 GiB quota, 18.98 GiB headroom; checked in T07. |
| 6 | T61 only half covered (no queue/backpressure) | **CLOSED.** `BoundedAuditQueue` has **no drop policy at all** — only `backpressure` (blocks the producer) or `explicit_fail` (raises). A partial sink commit raises. `RunCommitGate` cannot return `RUN_SUCCESS` while artifacts are missing or rows unflushed. |
| 7 | `quantbt_candidate/` and `quantbt_1_1_1_dist/` empty | **CLOSED.** Baseline wheels retained (read-only); candidate unpacked from the wheel with 0 symlinks / 0 hardlinks. `../quantbt` was **not read** for this step. |
| 8 | Isolation status was a static `false` in config | **CLOSED.** The config now refuses to carry a static claim (`"availability": "MEASURED_AT_PREFLIGHT"`, `"static_claim_forbidden": true`); availability comes only from the probe and is written to evidence each run. |

## 2b. Second audit against the guide text — 16 further gaps found and closed

The first "PASS" was declared against the phase *gate*, not against every sub-task sentence in L01.1–L01.6. Re-reading the spec line by line found 16 requirements that were never delivered. All are now closed; `configs/lab01_task_audit.json` records each one with its evidence and test.

| Task | Gap found on re-audit | Closed by |
|---|---|---|
| L01.1 | "LAB_ROOT must be new or carry a marker for the SAME study" was never enforced — the constant existed, the check did not | `validate_lab_marker()` + 3 tests; rejects a foreign study id and refuses to adopt an occupied unmarked directory |
| L01.3 | No **dependency lock** | `configs/requirements.lock`, 31 packages, every line `--hash=sha256`, zero `UNPINNED_LOCAL_ARTIFACT` |
| L01.3 | **Numba compiler flags** not recorded | fingerprint now carries numba/llvmlite versions, threading layer, `NUMBA_NUM_THREADS`, `DISABLE_JIT`, cache dir, and the fastmath policy for L02.2 |
| L01.3 | **Thread metadata** only partial | `OMP/OPENBLAS/MKL/NUMEXPR/NUMBA_NUM_THREADS` + `sched_getaffinity` |
| L01.3 | **Baseline vs candidate as separate processes** never demonstrated | `process_separation = SEPARATED`: distinct import origins, each in its own pid namespace, neither from a protected root |
| L01.3 | **Native capability never probed** — only an import attempt | matrix `full-contract-v2-0.4`, fingerprint `601d639f…`, 20 capabilities; **0 of the 12 guide-§4.4 required ones missing** (oco, amend, cancel, limit, market, funding, liquidation, multi_symbol, ioc, fok, gtc, gtd) |
| L01.4 | Process-group ownership was **defined but never called** | `become_process_group_leader()` invoked by the bootstrap and pin scripts; `process_group.status = OWNED` |
| L01.5 | No **freeze/holdout policy** artifact | `configs/freeze_holdout_policy.json`: two-stage information, freeze procedure and frozen-object list, holdout status, access logging, unlock gates |
| L01.5 | No **quarantined preset catalog** | `configs/preset_quarantine_catalog.json`: 36 literal dictionaries, every one flagged not-eligible for warm start / primary bank / OOS claim |
| L01.6 | **WFO modes** absent from the map | all 5 modes read from installed source; causality resolved per (mode, schedule) by `resolve_causality_schedule_v2` rather than guessed from names |
| L01.6 | **Command classes** absent | 15/15 bound |
| L01.6 | **Callbacks** absent | 14/14 bound |
| L01.6 | **Parent/OCO** absent | 16/16 lifecycle+OCO bound; native matrix confirms `oco` |
| L01.6 | **Result exports** absent | 20/20 bound |
| L01.6 | **No test column** in the map | every operation carries `tests[]`; all six `COVERED` |
| L01.6 | **Loader never mapped** | `ast.parse` of the snapshot: 20 classes, 10 crypto readers, module never imported |

Exit-gate item "API/data unknowns listed" is now real: **0 API unknowns, 5 named data unknowns** (`instrument_registry_digest`, `funding_history_coverage`, `perp_listing_dates`, `orderbook_snapshot_coverage`, `data_roles`) each with a handling rule.

`scripts/run_lab01.py` reruns the entire phase in dependency order and reports the gate — LAB-01 is reproducible from one command.

### Preset quarantine — one honest discrepancy with the guide

Guide appendix A.1 lists literal-dictionary counts 6 / 13 / 15 / 1. Static AST of the read-only snapshots finds 6 / **14** / 15 / 1. The extra dictionary in `adaptive_hma_cpp.py` is `sl_mode_map` at line 311 — a 4-entry SL-mode lookup table carrying none of the 12 parameter keys. The guide's 13 counts parameter dictionaries; this scan is simply broader. **No parameter preset is missing or extra.** The `vwap.py` modal group of 9 is a grouping hint only — the guide's own reading is that 4 dictionaries carry VWAP keys plus `base` with HTF, and the authoritative schema split is LAB-02 L02.1 work.

### A note on the supplied archive

The zip you added at `LAB_ROOT/alpha_to_tes_regime_model.zip` is no longer at that path. My code did not delete it — the only deletion calls in this lab are `rmtree(quantbt_candidate)`, an `unlink` of a *failed* extraction target, and removal of the isolation probe's own temp file. The read-only copy retained at `vendor_readonly/alpha_zip_original.zip` carries the exact guide digest `57406dbb…6701ae`, and ingestion now falls back to it so the phase stays reproducible; the digest gate still applies, so a substituted archive would still stop the phase.

## 2c. Third pass — archive unpacked in place, last deferral closed, import guard hardened

**Supplied archive (`src/crypto_regime_lab/alphas/`).** Digest `57406dbb…6701ae` re-verified against guide §1.1, inspected (0 rejections), extracted to `src/crypto_regime_lab/alphas/raw-supplied/` as four read-only `.py` files, cross-checked byte-for-byte against `vendor_readonly/alphas_raw/`, then the zip was deleted as instructed. Deletion was gated on a verified retained copy existing at `vendor_readonly/alpha_zip_original.zip`, so provenance survives. Re-running LAB-01 is idempotent: it verifies the four files and falls back to the retained archive if any drifted.

**Import guard — two weaker guards were measured insufficient before the real one.**

| Attempt | Result |
|---|---|
| Directory `raw_supplied/` with no `__init__.py` | **Still importable** — PEP 420 implicit namespace packages resolved `crypto_regime_lab.alphas.raw_supplied.vwap` |
| Directory renamed `raw-supplied/` (invalid identifier) | Blocks the `import` *statement* only; `importlib.import_module("...raw-supplied.vwap")` **still succeeded** |
| `raw-supplied/__init__.py` that raises `ImportError` | **Blocked** — every import path raises |

While measuring the second attempt, `vwap.py` was imported once outside containment. Static AST confirms `vwap.py` has no module-level statements beyond imports, `def`s and literal assignments, so only definitions ran and nothing executed. It is disclosed here rather than left in the transcript, and a test now asserts the same property for all four files plus that no alpha module is resident in `sys.modules`.

**L01.4's last deferral is closed.** `configs/data_readlock_policy.json` registers the mutable-partition policy LAB-01 owes: never run a collector; a partition enters only as a snapshot under `LAB_ROOT/snapshots/{id}/` with a per-file digest manifest; the manifest *is* the read-lock, re-verified before and after a run; digest drift invalidates the run as `EXTERNAL_DATA_DRIFT` rather than continuing on new bytes; only closed partitions are primary-eligible; a failed partition read becomes explicit missing coverage, never a backtest on "the rest" reported as a full sample. LAB-03 executes it.

**L01.2's source boundary is now recorded, not asserted.** `source_boundary.json` captures both upstream repos. Every git read ran with `GIT_OPTIONAL_LOCKS=0`, and each repository's `.git/index` digest is recorded **before and after** the probe — both unchanged, so "we only read" is proven. `../quantbt` is clean on `fix/public-native-consumer-proof-contract`; `alphas_storage` is dirty in `TA/` and `standardize_simulation/`, which is pre-existing user work the lab never touched. The record also states the boundary that matters: the lab consumes the PyPI wheels, so upstream working-tree state — dirty or clean — cannot influence any lab result.

`pytest tests -q` → **97 passed**. `scripts/run_lab01.py` → **STATUS = PASS**.

## 3. Preflight gate — 9/9 PASS, kernel-backed

```
ISO  PASS  OS-level worker containment (bubblewrap namespaces)
T01  PASS  LAB_ROOT inside protected repo is rejected
T02  PASS  editable copies are physical, not aliases
T03  PASS  zip traversal/absolute/symlink/duplicate rejected before extract
T04  PASS  four-file allowlist and digests
T05  PASS  worker caches redirected; protected-path write refused by the kernel
T06  PASS  no live credentials in a replay worker; network unreachable at OS level
T07  PASS  over-budget worker dies alone, cancel scoped, disk within quota
T08  PASS  protected-source integrity manifest
```

`pytest tests -q` → **97 passed** (31 → 60 → 85 → 97 across the passes). Coverage: **9 COVERED, 1 PARTIAL, 54 NOT_YET_IMPLEMENTED** of the 64 guide requirements, plus the extra `ISO` gate.

## 4. Baseline pinned — matches the guide exactly

| | Guide target | Lab venv | Shared parent venv | `../quantbt` source |
|---|---|---|---|---|
| core | 1.1.1 | **1.1.1** | 1.1.0 (untouched) | 1.1.1 (untouched) |
| native | 0.4.2 | **0.4.2** | 0.4.1 (untouched) | — |

A test asserts `quantbt.__file__` is inside `environments/lab_venv/` and **not** under `/pool_alpha/quantbt/`. The guide's primary clock `event_lifecycle_v3_next_open` is present in `EXECUTION_CONTRACT_REGISTRY` — verified, not assumed.

## 5. Finding: QuantBT 1.1.1 already ships a regime notion — not the one this lab needs

`volatility_regime_labels(returns, regime_count=3, lookback=20)`, plus `WalkForwardConfig.regime_count/regime_lookback/regime_weights`. Characterised by reproducer (`evidence/.../incumbent_regime_probe.json`, `tests/test_incumbent_regime_surface.py`):

| Probe | Observed |
|---|---|
| Tail-only mutation of 400 bars | **97/300 prefix labels changed (32.3%)** → quantile cuts are in-sample to the whole array |
| Sign-flipped returns | Identical labels → direction-blind |
| Label frequency | Exactly 200/200/200 → equal-frequency by construction |
| Constant (zero-vol) series | All labels = **2**, the *highest* bucket |

Its docstring's "does not inspect future OOS bars" is accurate *with respect to OOS* when the caller passes an IS-only window, which is how the WFO objective uses it. The lab-relevant point is narrower and still true: **within the array it receives, a label at `t` depends on observations after `t`**. Valid in-sample descriptor and registered M0 comparator; not an online causal state estimator; must carry `decision_eligible=false` outside an IS scoring window.

## 6. Preregistered before any performance was observed

20 cells (4 alphas × 5 symbols), pilot order A-SC → A-HMA → A-VWAP → A-HASH, timeframes per guide §10.4. Arms A/B/C/D primary + E extension; 7 controls. Contrasts B−A, C−A, D−B, D−C, (D−C)−(B−A), Holm-type adjustment, block bootstrap. Frozen for all arms and never tuned: 20 000 USDT capital, 2 000 notional, leverage cap 1, taker 4 bps, slippage 1 bp, cost stress 1×/1.5×/2×. Contamination level `RETROSPECTIVE_NESTED_CAUSAL_RESEARCH`.

## 7. What LAB-01 still does *not* establish — honest remainder

0. **Per-task status: 43 of 43 guide requirements DONE, nothing deferred.** Full breakdown in `configs/lab01_task_audit.json`. Two items pass *forward* by design rather than being incomplete: the schema split of quarantined presets is LAB-02 L02.1 work, and `data_roles` / `instrument_registry_digest` / `minimum_economic_effect` are the nulls guide §13.2 expects until the LAB-03 data pin.
1. **Containment covers workers launched through `safety.sandbox`.** The orchestrator process itself runs uncontained (it writes only through the path guard). Once LAB-02 runs alpha code, that execution goes through the sandbox wrapper — this is a rule to keep, not a property already proven for future code.
2. **54 of 64 requirements are not implemented.** They belong to LAB-02…LAB-10 and are listed with their owning phase in `configs/acceptance_test_coverage.json`. This is the plan, not hidden debt — but nothing among them is assumed passing.
3. **T59 is PARTIAL.** The non-dropping retention path is proven; retention of real Optuna pruned/failed trials needs LAB-08 workloads.
4. **Three registration fields remain `null` with named blockers** — `data_roles`, `instrument_registry_digest`, `minimum_economic_effect`. All three need the LAB-03 data inventory. Status is `DRAFT_REQUIRES_LAB03_DATA_PIN`, not `FROZEN`.
5. **`quantbt_candidate/` is unpacked but never exercised.** It exists so LAB-07 has somewhere to hold lab-only patches; no patch exists and no candidate run has happened.
6. **No numeric parity work yet.** `ta`, Numba `fastmath`, and Wilder/EMA conventions are untested — that is L02.2.
7. **No market data was read, no backtest run, no alpha executed.** Zero statements about edge, PnL or regime value exist.

## 8. Protected trees verified untouched

- `../quantbt`: `git status --porcelain` empty; branch `fix/public-native-consumer-proof-contract` unchanged; not read during candidate materialisation.
- Shared parent venv: still quantbt-engine 1.1.0 / native 0.4.1.
- Four alpha sources: digests unchanged; `verify-source-integrity` → `UNCHANGED`.
- Nothing written anywhere under `/root/bobby/pool_alpha` outside `lab_regime_model_quantbt/`.

## 9. Exit gate

`SAFE_TO_RUN_SYNTHETIC = true` · `OS_ISOLATION = true` · `safe_to_run_market_execution = false` (unlocks after LAB-02 certification **and** LAB-03 data qualification).

**Next:** LAB-02 — four-alpha canonical adaptation and domain certification (T09–T20). **Not started: the user must approve LAB-01 first.**

## Glossary — what each term means and where it applies

| term | meaning | where it applies in this lab |
|---|---|---|
| **OS-level isolation** | running work inside a kernel namespace with the filesystem mounted read-only and the network removed, so a write or a fetch FAILS rather than being merely discouraged | LAB-01 — bubblewrap; a path check alone is explicitly NOT a sandbox (guide App. C) |
| **EROFS / ENETUNREACH** | the OS error numbers for 'read-only filesystem' (30) and 'network unreachable' (101); the lab measures these rather than asserting containment | LAB-01 — the preflight probe records them as evidence |
| **attempt ledger** | an append-only record of every operation tried, including the ones that failed, so a failure cannot vanish from the history | LAB-01 — `evidence/.../attempts.jsonl` |
| **NOT_READY** | an alpha that cannot be certified keeps all its cells with NULL metrics; booking it as PnL = 0 would bias every aggregate | LAB-02/04 — A-HASH, 5 cells |
