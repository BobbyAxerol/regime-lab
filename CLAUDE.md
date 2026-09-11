# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this directory is

`lab_regime_model_quantbt/` is `LAB_ROOT` for the **QuantBT Crypto Regime & Parameter Time-Edge Lab**. It currently contains **only the implementation guide** — no code has been scaffolded yet:

- `QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md` (Vietnamese, ~1830 lines) is the **authoritative plan and source of truth**. Read §0–§4 before writing anything; §5 is the target tree, §12 the 10 phases, §13.5 the CLI contract, §14 the 64 acceptance requirements.
- It supersedes the research content of `QUANTBT_ROBUST_SELECTION_REGIME_AWARE_WFO_RESEARCH_GUIDE_V1_VI.md`. When actual source/capabilities contradict the guide, write a correction ADR and an explicit plan revision — do not silently deviate, and do not rewrite evidence from earlier runs.

The lab's falsifiable question: **does regime information select profitable+stable parameter sets and deploy them at better times than calendar WFO**, after costs, uncertainty, transition cost and compute budget? Experiments must be designed so the answer can be "no".

## Binding operating rules (set by the user, 2026-09-09)

These override any convenience default. They restate and tighten the guide.

1. **`../quantbt` is strictly read-only.** It is the user's active development repo. Do not edit, patch, `pip install -e`, build, or run any git write command in it. Read it only as reference. Any lab-only patch idea goes into `handoff/lab_only_patch.diff` as a proposal, never applied upstream.
2. **Get QuantBT from PyPI, not from the source tree.** `pip install quantbt-engine==1.1.1` into the lab's own isolated venv, import from that install, and build the regime model / logic / architecture *around* it inside the lab. The regime-aware machinery is simulated in the lab layer; QuantBT stays an unmodified dependency.
3. **Never touch the shared parent venv** `/root/bobby/pool_alpha/.venv` (it holds quantbt-engine 1.1.0 for other projects). The lab uses `environments/lab_venv/` only.
4. **Transparency is mandatory.** Report what actually ran, what failed, and what was skipped. No fabricated numbers, no silently dropped failures, no "success" summary over a partial run. If something is blocked, say `BLOCKED` with the reason.
5. **Test thoroughly.** Every behavioural claim needs a runnable test or a committed evidence artifact. Map tests back to the T01–T64 IDs in guide §14 and record which of the 64 are covered, which are not, and why.
6. **Follow the guide's method, and understand the intent behind it.** When the guide and reality disagree (e.g. an API that does not exist), record the gap explicitly and propose a revision — do not improvise a substitute and call it the plan.
7. **Report in detail at the end of each LAB phase** — what was built, what was tested, what passed/failed, what is still open, and the honest status of the phase exit gate.
8. **This is a test/research stage: no local git yet.** Do not `git init`, stage, or commit inside the lab unless the user asks. Evidence lives in files under `evidence/`, not in commits.
9. **Every phase that runs tests or evaluates a hypothesis MUST have a markdown report with the
   REAL measured numbers** (set by the user, 2026-09-10). `reports/lab0N_report.md` is written by a
   `scripts/write_lab0N_report.py` that reads only committed artifacts and never reruns an
   optimizer. The report is not a summary of intentions — it must carry:
   - the measured figures themselves, in tables, not prose claims about them;
   - the registered hypothesis ID the phase evaluates (`configs/hypothesis_registry.json`) with its
     question and registration timestamp, when the phase evaluates one;
   - the **registered primary endpoint** from `configs/study_registration.json` — not a more
     convenient statistic — measured, and compared against the minimum economic effect in
     `configs/minimum_economic_effect.json`;
   - a `conclusion_level` drawn ONLY from the registered vocabulary, with every blocker that
     prevented a stronger one;
   - which falsification commitments were exercised;
   - the corrections made during the phase, including ones that invalidate an earlier claim.
   A test asserts the numbers actually appear in the markdown, so a report cannot drift from the
   artifact it came from. Precedence for the conclusion: incomplete matrix → `FAILED_VALIDITY`;
   effect inside the cost-stress band → `INCONCLUSIVE_SAMPLE`; blockers cap it at
   `DESCRIPTIVE_VALUE`; only a clean above-threshold result may be called an edge.

10. **Define every technical term in place, every time you report** (set by the user,
    2026-09-10). When a progress or results report uses a term like *space-filling*, *medoid*,
    *plateau*, *episode*, *anchor*, *probe*, *P_survive*, *conclusion level*, write the meaning in
    parentheses immediately after it AND say which part of the lab it refers to — e.g.
    "space-filling (đặt anchor ở vùng xa mode của TPE để panel cục bộ không dồn hết vào chỗ sampler
    đã ưu tiên — đây là anchor thứ 3 trong 4 suất ở L04.3)". A term used without its meaning and
    its context is not a report. `reports/lab0N_report.md` carries a glossary section for the same
    reason, and a test checks that every term the report uses is defined in it.

11. **Build exactly what the guide specifies, LAB-00 through LAB-10 — and write your own
    opinion down separately** (set by the user, 2026-09-10). The guide is the plan; deviating from
    it "because it seems better" is not allowed. But when something looks improvable, record it in
    `reports/improvement_opinions.md` as a numbered entry with: the observation and the measurement
    behind it, 2–3 feasible options, why each might work, what it would cost, what could go wrong,
    and what evidence would settle it. **Write, do not run.** Nothing there is implemented,
    scheduled or assumed until the user picks it. An opinion never changes an artifact, a
    conclusion or a phase gate, and it is never mixed into a results report.

12. **Report the `../quantbt` status in EVERY reply.** The user has forbidden any modification of `/root/bobby/pool_alpha/quantbt`. At the end of each response, state honestly whether anything there was touched — verified, not assumed: run `git -C /root/bobby/pool_alpha/quantbt status --porcelain` (and compare digests where relevant) and report the result. If something *was* touched, say so immediately and plainly rather than burying it.

## Current state (LAB-04 … LAB-08 all COMPLETE — 2026-09-11)

`pytest tests -q` → **696 tests**; `pyflakes` → **0** outside `alphas/raw-supplied/`.
Audits: **LAB-04 64/64**, **LAB-05 53/53**, **LAB-06 79/79**, **LAB-07 75/75**, **LAB-08 74/74**.
Coverage: **60 COVERED / 1 PARTIAL / 3 NOT_YET_IMPLEMENTED** of the 64 guide requirements.

### LAB-06 — the join, and a zero-switch result that means something specific

LAB-06 is the layer that connects LAB-05's states to LAB-04's candidate utilities. Its exit gate is
that **every keep/switch carries evidence, cutoffs and consistent units** — not that switches
happen. Guide L06 says zero switches from insufficient edge is a valid result, and that is what
came out.

**6566 decisions** at every 4h regime observation: `{"FALLBACK_NOVEL_STATE": 101, "KEEP_INCUMBENT": 1322, "NO_SUPPORTED_CANDIDATE": 5143}`.
**0 switches.** The best challenger ever seen was worth **+2.58 bps** over the
horizon (SE 1.35 bps, so a conservative lower bound of +1.23 bps) against a switch cost of
**7 bps**. It never came closer than 5.8 bps short. The inaction region genuinely bound.

**But the honest reading is weaker than "no edge".** In **774 of
1377** (candidate, episode) pairs — **56%** — the paired
delta is EXACTLY zero because both the candidate and the incumbent were flat that week. One bank
candidate was flat in 92% of its episodes. The registered 7-day horizon covers A-SC's 3.92-day mean
holding, but covering the holding period is not the same as containing enough trades to tell two
parameter sets apart. More than half the evidence could not have shown an edge at any weighting.
The horizon was NOT retuned in response — that would be selecting the experiment on its own result.
Recorded as OP-14.

**Method note that matters going forward.** A checklist of all 79 clauses (LAB-06 tasks, guide
9.1-9.5, 7.4, T45-T52, outputs, exit) was written to `configs/lab06_checklist.json` BEFORE any
policy code existed, and `scripts/audit_lab06.py` reads that file. An audit that is written after
the code becomes a list of what happened to get built.

**Four defects found by self-review, not by being asked:**

1. A leaked loop variable gave every bank entry the LAST discovery's timestamp — the filter was
   right but the lineage field T46 protects was wrong on all of them. Symptom: banks of size
   [0,0,0,0,0,8]. It surfaced only because `admissible()` re-checks instead of trusting the build.
2. The contiguous-block support gate was structurally dead: blocks were counted over every episode
   with weight > 1e-9, and a Gaussian kernel never reaches zero, so everything looked like one
   unbroken run — 1 block for all 400 sampled estimates, every recommendation refused for the wrong
   reason. Blocks are now counted over the SUPPORT SET (smallest group carrying 90% of the weight)
   with the episode's true position in time.
3. Switch assessment ran on the 7-day episode boundary instead of the registered 4h regime
   observation, which tied the switch clock to the response clock — two of the four clocks guide
   9.4 insists on separating. Fixed: 155 decisions became 6566.
4. `pooled_delta_from` was written and never wired; the reachability gate built in LAB-05 caught it.

### Still true

LAB-04: registered endpoint 5.5674e-05/day against a 6.4e-05/day minimum → `INCONCLUSIVE_SAMPLE`,
with three blockers (sign reversal inside A-VWAP, asymmetric switching rates, four cells where an
arm never selected). LAB-05: a technical pass only — the forward filter is not Viterbi (differs in
7 of 8 sequences), greedy and endpoint-DP are two models (14 vs 102 switches at λ_J=2), a K=3 model
on pure noise still emits 18 state changes, and the guide 8.3 group ablation FAILS (variance
resolved +0.335 → +0.095 → −0.036 as blocks are added).

`reports/metrics_reference.md` groups every metric by the question it answers; most of the 696 tests
are binary correctness gates, not performance metrics. `reports/improvement_opinions.md` holds 17
entries, written and NOT run.

### Data provenance is now stated by every phase that reads the snapshot (2026-09-10)

`reports/data_sources_used.md` is the audit view: which products, how much of each, what is absent
and why, the read-lock verdict, and how the bytes are read. LAB-04/05/06 reports each carry a
**Data provenance** section generated from artifacts, plus an explicit scope line (LAB-06 is **1 of
the 20 primary cells** — A-SC/BTCUSDT; LAB-05 is 1 symbol).

**The lab never calls `data_loader.py`.** It pins a read-only copy, parses it STATICALLY for path
routing, and reads the byte-copied parquet directly. That is measured, not asserted:
`scripts/verify_loader_parity.py` calls the pinned loader on 15 partitions across all five symbols
and diffs it against the same bytes — **10 of 15 disagree**, always on `volume`, because
`MarketDataLoaderBase._normalize` casts to int64 and BTC/ETH/BNB store fractional quantities.
Worst measured: BTCUSDT 2026-08 loses 0.515% of total volume and sends **41 bars with real trades
to volume 0**, which in G2 would be missing observations, not blurred ones. DOGE is int64 in
storage and shows zero difference — the defect hides on the symbol you would spot-check first.
Recorded as OP-15 (write, do not run: `../alphas_storage` is read-only).

**Three defects found in this review, all fixed:**

1. **The read-lock could not tell a re-ingest from a revision.** 23 CLOSED
   `binance_futures_metrics_5m` partitions drifted upstream, so the digest check declared
   `EXTERNAL_DATA_DRIFT` and invalidated the G3 cohort. Reading both files proves **every measured
   column identical** — only `ingested_at` moved, because the user's collector re-ingests closed
   months. `classify_source_drift` + `verify_snapshot(deep=True)` now read before they judge;
   status is `EXTERNAL_VINTAGE_RESTAMP_ONLY`, 0 content revisions. Shallow stays fail-closed, and
   a partition is cleared only when proven benign. OP-16 covers what remains.
2. **`configs/data_eligibility.json` did not come from the manifest it named.** It was written from
   the 20:03:51 snapshot pass while the study pins 20:15:47, under-counting every symbol by 7-9
   rows in the open trailing partition. No closed partition differed and no result moves, but an
   artifact that misreports its own inputs is the same defect class as LAB-04's `_observed_budget`.
   Fixed by `scripts/refresh_data_eligibility.py`; the document now carries
   `manifest_ingest_finished_utc` and two tests check it against the manifest AND the parquet
   footers.
3. **No phase report stated its data inputs.** A reader could not audit the raw data from a phase
   report. Fixed as above.

Nothing here changed a LAB-04/05/06 result: all three read `crypto_binance_futures_1m` only, via
the 8 primary-core features, entirely inside the development role (2020-01-01 → 2023-12-31). The
drifted metrics product feeds G3, which no phase reads.

### Guide re-inspection before LAB-07 (2026-09-10)

`reports/guide_compliance_inspection.md`. The phase audits ask *did every L0N.M task get done*;
all six pass. This asked **does the guide require anything no L0N.M task owns** — and found three,
all now closed with tests (`tests/test_guide_contracts.py`, 17 tests).

1. **Compute-budget contract never registered (§10.5 + L01.5).** `resource_budget` pinned 1 worker
   / 2 CPU / 4 GiB — the OS budget, not the comparison contract. `MATCHED_TOTAL_COMPUTE` and
   `OPERATIONAL_POLICY` appeared nowhere, nor did the experiment-search ledger §10.5 requires over
   K, λ_J, response bandwidth, switching thresholds and alpha revisions ("Không chỉ log Optuna
   alpha trials"). Registered NOW because LAB-07 builds the refit scheduler: once its cost is
   visible, "matched compute" could be defined to suit it. `configs/compute_budget_registration.json`
   opens the ledger with what LAB-04/05/06 measurably spent.
2. **CLI stage status had gone stale (§13.5).** `cli.py` froze `IMPLEMENTED` at LAB-01, so after
   LAB-02/03 landed, `certify-alphas` and `snapshot-data` still answered "the phase has not
   landed". Availability is now read from `configs/lab0N_task_audit.json`, and refusals separate
   `PHASE_NOT_LANDED` from `RUNNER_NOT_WIRED_YET`. Two consequences: `verify-causality` had no
   runner at all (now `scripts/verify_causality.py`, all four layers CAUSAL with the leaky control
   caught), and `snapshot-data` would have silently re-pinned the study — it now refuses without
   `--repin`.
3. **Identity taxonomy was 7 of 12 (§13.1).** `probe_design_id`, `execution_id` and
   `observation_id` were owed by COMPLETED phases. Added as derivations from existing records, so
   nothing re-runs and no measurement moves. `experiment_id` / `activation_id` stay OWED by
   LAB-08 / LAB-07. The audit's first run reported 12/12 by grepping its own output; the scan now
   excludes self-referential files and a test fails if everything reports present.

Verified correct against the guide text (not against the audits): ZIP oversize/compression-bomb
guards, the LAB-01 environment pin, 13/13 execution fixtures, Python/Rust intent parity, funding as
a declared MISSING stream, all five installed WFO modes traced, multi-start seed selection on the
TRAIN objective only, M1S declared deliberately unbuilt per §8.3, detection delay and noise
sensitivity measured, and every L06.1–L06.6 clause. **No LAB-04/05/06 result changed.**

### LAB-07 — the integration, and two gates that passed because nothing happened

LAB-07 asks one question: can LAB-04/05/06's decisions be **delivered on one account that never
restarts**? It claims no edge and compares no arms — that is LAB-08's.

**75/75 clauses**, from `configs/lab07_checklist.json` written before `src/crypto_regime_lab/
integration/` existed. **46 LAB-07 tests.** T55, T56 and T57 move to COVERED; T53 and T54 stay
PARTIAL because arms C/D/E do not exist and there is no arm comparison to label.

**The run**: A-SC / BTCUSDT, **105,120 real 15-minute bars** (the alpha's registered primary
interval), driven by arm A's OWN six LAB-04 selections. 75 entries, 150 engine fills, equity
20,000 → **20,034.34 (+0.17%)**, **0 account resets**, **0 splices**, one engine pass.

**No switch was instant.** Each of the five waited for a flat book and warm indicators —
**64 to 368 bars** of activation delay. Guide §9.5's contract, priced in bars.

**T55 measured, not asserted**: the account's daily Sharpe is **0.0342**; the unweighted mean of
per-segment Sharpes is **0.0753** — **2.2×** on the same trades, because segments differ in length
(177–193 days) and the mean weights them equally.

**Two defects found by self-review, both the same shape — a gate passing on an empty run:**

1. **The first run traded nothing.** Driven from the 4h panel with no signals: 0 fills, flat
   equity, 1 segment, null Sharpe — and every gate passed. `all_fills_from_engine` was true over
   an empty list. Rebuilt on real 15m bars with the real adapter.
2. **The intent tape was built from the FINAL adapter's decision list.** Each version's adapter
   holds only the bars it personally saw, so every trade under an earlier version vanished from
   the tape while still counting as an entry. Symptom: **75 entries, 18 fills**, reported return
   **+2.11%**. Assembling from the ACTIVE adapter per bar gives 150 fills and **+0.17%**. The
   wrong number would have been published.

The reachability gate caught a third (`prefix_stability` left behind as a weaker duplicate —
deleted), and a new test caught a fourth (`daily_account_comparison` raised on mixed tz-awareness;
boundaries are now aligned inside the function). A fifth was a test of my own that asserted
`lab07_task_audit.json` did not exist — true when written, false once LAB-07 shipped; it now
compares timestamps so the property cannot expire.

### Leakage re-audit of LAB-07 and everything it inherits (2026-09-10)

`scripts/audit_lab07_leakage.py` → **CLEAN 10/10**, `configs/lab07_leakage_audit.json`. It asks
one question — *can information from after a decision reach that decision, through this phase or
anything it inherited from LAB-03..06* — and records for each probe whether it **had something to
detect**, because every defect found in LAB-06 and LAB-07 was a gate that passed on an empty run.

Verified: window inside the development role (outer holdout untouched); every version trained to
at/before its own cutoff and requested at that cutoff bar; the future-mutation probe holds with
**74 trades already in the prefix**; no activation carries its own end; no decision carries its
segment's length; refits pay a measured latency and cannot reach the deployment account; the
four-layer causality gate is CAUSAL with the leaky control caught; snapshot bytes intact.

**Six more defects found, all fixed:**

3. **The warm-up gate was a magic number that moves results.** `WARM_BARS = 64` was mine. Measured:
   0 / derived / 512 bars → **+0.45% / +0.45% / −3.07%** — an unregistered free parameter of the
   switching policy (guide §10.5 puts these in the search ledger). Now **derived from each
   adapter's own `warmup_bars()`** (39/36/60/61/33 = its `AP+3`). Headline return moved
   **+0.17% → +0.45%**.
4. **The gate did not do what the report said.** A-SC precomputes indicators causally over the
   whole slice, so values are already correct when the shadow adapter is built. The gate is a
   **policy delay**, now reported as one, not as an accuracy claim.
5. **The exit fixed point was missing.** `run_candidate` iterates protective exits until the
   whole-window run agrees; the integration did one pass. Harmless for A-SC (which rests no
   protection at all — 119 entries, 119 technical exits, 0 stops) and silently wrong for A-HMA /
   A-VWAP / A-HASH, which LAB-08 runs through the same function. Added and verified against
   `run_candidate` on A-HMA (26 protective exits, converged, identical).
6. **The future-mutation probe left `volume` untouched** while A-SC feeds volume into an MFI.
   Every readable column is now mutated — which is also the empirical proof that the whole-slice
   precomputation is causal.
7. **The trace mixed two arms.** Labelled arm A (guide §10.1: *no regime information*) while
   carrying 6,566 `REGIME_OBSERVATION_READY` events, which L07.2 requires the stream to carry.
   Every activation now names its source; `regime_information_reached_a_decision` is **False**,
   checked not asserted.
8. **The event bus crashed on a mixed-timezone stream** — storage is naive UTC, engine frames are
   aware, and one naive timestamp raised `TypeError` on the first sort. Normalised at publish.

Two follow-throughs on contracts registered earlier: the compute-budget ledger now carries
**LAB-07's measured operational cost** (it owed it), with `registered_at_utc` preserved so the
contract still provably pre-dates the arm it governs; and `activation_id` is now PRESENT, leaving
only LAB-08's `experiment_id` owed.

Two of my own tests had **expiring assertions** — one asserted `lab07_task_audit.json` did not
exist, one hardcoded the owed-identity set. Both now derive from which phases have landed.

### Second leakage pass before LAB-08 (2026-09-10)

`audit_lab07_leakage.py` → **CLEAN 12/12** (two probes added). Six more defects, and **every one
was a check that could not fail**:

9. **The regime-isolation check was circular.** The runner built
   `{activation_id: "calendar_cutoff"}` and handed it to the function that verified every source
   was `calendar_cutoff`. Sources are now DERIVED from the tape against LAB-04's cutoffs — and the
   moment they were, **the check failed**: activations publish at their EFFECTIVE time, and one
   lands on a 4h regime observation by coincidence. Attribution now keys on the REQUEST time.
10. **Two of four parity surfaces were trivial.** `metrics` compared only final equity (§13.6
    forbids that as a standalone claim, and `account` already implies it); `selection` counted a
    constant true by construction with an empty schedule. Now: the whole reported metric set, and
    a no-op activation to the SAME parameters that must change nothing.
11. **The inert-hook parity compared three empty accounts** — digest `4f53cda18c2baa0c`, the
    SHA-256 of an empty list, in all three runs. Now driven by real fills, and the function
    **refuses** a signal column that never trades.
12. **The replay consumer read a key that does not exist.** `payload.get("quantity", 0.0)` on a
    fill whose key is `qty` → **0.0 for every fill**. Raises on a missing key now.
13. **T57 was COVERED by tests that do not test it** — three about refit-latency rounding, for a
    requirement about sequential-vs-adaptive-batch semantics. Replaced with five real ones. Two
    intermediate versions grepped prose and flagged T57's own title, then its own negation; the
    final one is structural.
14. **The regime publication lag was invented** — `+1 minute` where bars are left-labelled and
    LAB-05's own emission tape says **+4h**. 15× too early. Inert in this calendar arm, but
    LAB-08's arms C/D/E consume these observations. Now derived from `panel.REGIME_INTERVAL` and
    cross-checked against LAB-05.

Also disambiguated: `modes_exercised` means the handler was **driven**, not that the failure
occurred — `observed_during_the_run` is now a separate, empty field.

**Standing lesson for LAB-08:** every defect found in LAB-06 and LAB-07 was a gate that passed
because nothing happened — an empty list, a missing key defaulting to zero, a constant compared
with itself, a probe handed its own answer. Before trusting any green check, ask what it would
take for it to go red. `lab07_leakage_audit.json` records, per probe, whether it **had something
to detect**.

### Third pass: auditing the AUDITS, extended to every lab (2026-09-10)

Passing tests say the claims hold. They do not say the claims are CHECKED. Two new audits answer
that, and both are permanent gates.

**`scripts/audit_assertion_vacuity.py`** traces the whole suite under `sys.monitoring` and records
every assert line never reached. **1,592 tracked, 1,587 reached.** The 5 remaining are contingency
branches (a drift state not occurring, a stronger conclusion not claimed) — each now DECLARED with
where its rule is exercised instead, in `tests/test_contingency_paths.py`. A sixth was a genuine
vacuity: `test_the_tape_is_built_from_the_active_adapter_at_every_bar`, written to guard LAB-07's
worst defect, ran `if run.entries:` on a synthetic fixture producing **zero entries** — it asserted
nothing. All trading tests now use real bars and assert that trades happened.

**`scripts/audit_guard_strength.py`** breaks one recorded invariant at a time and re-runs the
ENTIRE suite. First run: **6 of 13 caught** — seven claims recorded and never verified:

- the trace could report an account reset, or claim it was spliced, unnoticed
- the exit fixed point could stop converging, unnoticed
- **a phase audit could report every clause DONE with empty evidence**
- **a coverage file could mark a requirement COVERED with no tests**
- a verdict's population could silently drop to zero
- a headline field could diverge from its own detailed verdict

Those are the most load-bearing claims in the lab — every phase report quotes its audit. Now
**13/13**, each naming the test that catches it.

**Two more defects fixed on the way:**

15. **`every_switch_has_supporting_episodes: True` over ZERO switches** (LAB-06). `all(...)` on an
    empty population is True and reads exactly like a verified claim — and the report quoted it as
    evidence that every switch carried its evidence. Verdicts now carry their denominator:
    `holds / checked / vacuous`, and the report prints **VACUOUS** where it applies.
16. **`f.get("quantity", 0.0)` in the parity key** — the engine's key is `qty`, so the quantity
    component was 0.0 on both sides and two runs with different fill sizes would have matched. The
    third instance of this exact slip. The lab now has ONE fill shape and a missing field raises.

An earlier version of the mutation harness passed a per-case test selector — encoding a guess about
which test ought to notice — and missed guards that existed. It runs the whole suite now.

### Fourth pass: the guide sections no L0N.M task owns (2026-09-10)

§13.6, §13.7 and §11.5 belong to no phase task — the same shape as the three gaps found earlier
(compute budgets, the CLI, the ID taxonomy). All three are now audited and gated.

**§13.6 — the nine claims the lab may not publish.** `scripts/audit_forbidden_claims.py` → **9/9,
NO_FORBIDDEN_CLAIM_IS_SUPPORTED**. Each is checked STRUCTURALLY: does the evidence the guide
demands exist, and is the lab making the claim at all. The strongest evidence that no edge is
claimed is the failures kept — the §8.3 group ablation FAILED out of fold, LAB-04's verdict is
*no separation*, A-HASH is still NOT_READY, and "production safe" rests on a measured `EROFS`
refusal against a FAKE fixture with market execution disabled.

**§13.7 — invalidate what a validity failure killed.** Corrections were narrated in prose in four
reports; prose cannot be checked. `configs/correction_ledger.json` records **12 corrections**, and
the numeric history is **DERIVED** from every evidence run that ever wrote the artifact, matched to
each defect by a signature rather than typed. The evidence tree is append-only, so the run that
produced the wrong number is still there:

| defect | change | superseded run |
|---|---|---|
| the run traded nothing | none → +2.1052% | `run-20260910T115825Z` |
| the tape came from the FINAL adapter | +2.1052% → +0.1717% (fills 18 → 150) | `run-20260910T120600Z` |
| the warm-bar requirement was a magic 64 | +0.1717% → **+0.4524%** | `run-20260910T122902Z` |

A test asserts each replacement came from a **later** run, not a nicer one.

**§11.5 — artifact discipline.** 67 config + 531 evidence artifacts: **all strict JSON, zero
NaN/Inf, every one carries a schema version**. The writer's bounded queue backpressures or fails
explicitly and `dropped` is asserted to stay 0.

§11.3 (paired uncertainty, block bootstrap, Holm adjustment) and §11.4 (transition diagnostics) are
LAB-08/09's and are not claimed here.

One finding was my own auditor's: the §13.6 check read `preflight["checks"]` where the field is
`results`, and reported a FAIL that did not exist. An auditor that misreads a field manufactures
findings as easily as it misses them.

### LAB-08 — controlled discovery, and a negative answer the controls earned

**74/74 clauses** from `configs/lab08_checklist.json`, written before `factorial.py`,
`controls.py` or `regime_schedule.py` existed. T53, T58, T59 and T60 move to COVERED.

Protocol frozen **before any arm ran** (14:50:28), and the freeze script refuses to overwrite.
**15 of 20 cells ran**; A-HASH's five keep null metrics and stay in the denominator.
**10,942s** of factorial across 90 dynamic refreshes and 9,136 unique strategy executions.

**Outcome: `NO_PROMISING_DESIGN`** — one of the two exits the guide permits, and it does not
require profit.

| contrast | mean daily | sign test | Holm |
|---|---|---|---|
| B−A | +4.6e-05 | 10+/4− p=0.18 | 0.90 |
| C−A | +3.8e-05 | 9+/6− p=0.61 | 1.00 |
| D−B | −1.3e-05 | 4+/9− | 1.00 |
| D−C | −0.4e-05 | 8+/7− | 1.00 |
| **(D−C)−(B−A)** | **−5.0e-05** | **3+/12− p=0.035** | — |

Nothing clears the **6.4e-05/day** minimum registered in LAB-01. The only nominally significant
result is the **interaction, and it is negative**: regime timing adds *less* to the new selector
than to the old one.

**The control that can sink the method, does.** STATE_PLACEBO and DELAYED_STATE run as ARMS
mirroring D — same selector, same refresh count, same training memory, only the tape differs. A
placebo with matched dwell (37 real switches vs 34) **matched or beat arm D in 2 of 3 staged
cells**, and a one-observation delay left D **unchanged in 2 of 3**. The dynamic arms were
refreshing on a persistent signal at a cadence; the regime model supplied the cadence, not the
information. Guide 10.2 forbids dropping a control for beating the proposal, so it is reported as
it came out.

**L08.4**: no data cohort beats the server core on any symbol (gains −0.008 to −0.121). The
order-book cohort is structurally unavailable everywhere — a rolling 30-day window cannot
accumulate history.

**Arm A is `A_legacy_selection_adjusted`**: LAB-04 read the engine's own metadata and
`optimization_mode='none'` — the public default — declares OOS-adjusted selection. Every contrast
is measured against an arm that is **not** an untouched baseline (T54).

**Five defects, two found by the pilot that exists to find them:**

1. **The state tape covered a sixth of the window.** LAB-05 persisted 1,099 emissions from one
   namespace while summarising 6,571 across forty, so every dynamic refresh landed in the last six
   months. The fitter now writes the full tape and a cell whose tape does not span its window has
   no dynamic arm.
2. **Dynamic training windows were a fifth of the calendar's** — 868 bars against 4,320. A
   selector with a fifth of the history is not the same selector.
3. **A cell where the selector never selected crashed the run**, taking nine completed cells with
   it. Arm B rejected every candidate at all six cutoffs on A-SC/BNBUSDT. A selector that declines
   is a result; the arm now holds the incumbent and the run checkpoints each cell.
4. **The trigger rule concentrated every refresh at the front** — the mirror of defect 1. Triggers
   are now one per period; a period with no transition refuses rather than padding.
5. **The liquidity cohort scored an impact proxy and called it the order book.** `g4_log_amihud_30`
   comes from perp bars; `g4_spread_bps` is the only order-book feature and has 127 rows on BTC and
   zero elsewhere. Matching on the `g4` prefix merged them.

LAB-08 also minted `experiment_id`, the last identity still owed: **9 present, 3 derivable,
0 owed** of guide §13.1's twelve.

### LAB-08 re-audit: five more defects, none needing a re-run (2026-09-11)

All five were in the ANALYSIS layer or a control, so the 3-hour factorial stood. Every arm
number is unchanged; what changed is what the numbers were allowed to claim.

1. **Arm E was a copy of arm D in 15/15 cells**, printed as a fifth column. LAB-06 measured zero
   switches, so the response policy never overrode D's schedule. Now flagged `degenerate`, and
   `E-B` is marked as equal to `D-B` by construction.
2. **`E-B` used a different statistic from every other contrast** — total-return ÷ days, where the
   rest use a true paired daily difference. Two contrasts between IDENTICAL arms and the same B
   came out different (−2.18e-05 vs −1.25e-05), which is how it surfaced. Now the same statistic,
   and the two agree exactly.
3. **`E-B` was inside the Holm family**, making it six when the registered family is five, so
   every adjusted p was more conservative than the registration allows. Corrected: B−A went
   0.898 → **0.718**, D−B 1.00 → **0.801**.
4. **`budget_exceeded: False` and `workers_used: 1` were asserted**, not measured. Now read from
   the OS: 1 worker, **0.127 GiB** peak RSS against a 4 GiB budget.
5. **RISK_ONLY was vacuous and looked like a result.** A per-state scale must be fitted on one
   window and applied later, but the model refits every 28 days and LAB-05 declares
   cross-namespace translation diagnostic only — so only **1.64%** of scoring observations carry
   a state key seen during calibration (18 of 89). The other 98% fell back to a scale of 1.0 and
   the control returned the baseline path while printing a number. Now
   **`BLOCKED_BY_STATE_NAMESPACING` on all 15 cells**, with the measurement and what would
   unblock it. Guide 10.2 forbids dropping a control, so it is named rather than removed.

**A correction to what I reported.** I highlighted the interaction's sign test at **p=0.035**.
Holm-adjusted over the registered family it is **p=0.176** — not significant. The adjusted number
is the one that counts, and the report now leads with it.

The outcome is unchanged: **`NO_PROMISING_DESIGN`**, and it is now supported by fewer claims than
before rather than more.

Next: **LAB-09 only after explicit user approval.**

## Hard boundaries (guide §0.2, Appendix C)

These are not style preferences — violating them invalidates the lab.

- **All writes stay inside `LAB_ROOT`.** Read-only inputs: the QuantBT repo (`../quantbt`), the historical-data loader code and storage (`../alphas_storage/_get_data/`), and the four supplied alpha files. Any other alpha/strategy directory: do not read to hunt for extra strategies, do not edit, do not import.
- **Never** run `git checkout|reset|clean|worktree add|gc`, `pip install`, `poetry update`, `uv sync`, or a build inside `../quantbt` or other protected repos. Use a **physical copy / read-only export snapshot** into `quantbt_candidate/`, then `git init` independently in the lab if change tracking is needed. No hardlinks for editable copies, no writable symlinks back to sources, no `chmod`/`chown` on sources, no `sudo`, no touching services/cron/systemd/ports.
- **Path guards are not a sandbox.** Real simulation workers need OS-level isolation (read-only mounts, writable `LAB_ROOT`, no credentials, no network during fit/replay). Without that isolation, only scaffold/audit/read-only review — never claim writes are impossible.
- Point every cache into the lab (`NUMBA_CACHE_DIR`, Matplotlib config, tmp, model cache) and set `PYTHONDONTWRITEBYTECODE=1` in any process that imports protected source.
- Network acquisition, if needed, is a **separate allowlisted stage** writing into the lab. Never download while a backtest replays; never call the data collectors, trading adapters or scheduler services to fetch history.
- Initial resource budget: 1 worker, ≤2 CPU, ≤4 GiB working set, configured disk quota. Read storage in partitions/chunks with backpressure. Kill/cancel only children of `lab_run_id`.
- Deliverables stop at evidence + `handoff/` (bounded patch proposals + reproduction bundle). **Never merge into main QuantBT, never go live.**

## Environment and commands

The lab has **its own** virtualenv — it never installs into, upgrades, or imports from the shared parent env.

```bash
LAB=/root/bobby/pool_alpha/lab_regime_model_quantbt
$LAB/environments/lab_venv/bin/python -m pytest $LAB/tests -q          # lab tests
$LAB/environments/lab_venv/bin/python -m pytest $LAB/tests/test_x.py::test_y -q   # one test
```

**Version reality:** the guide's baseline is `quantbt-engine==1.1.1` / `quantbt-native==0.4.2`. The shared parent venv has 1.1.0 / 0.4.1 and `../quantbt` source sits at 1.1.1 on branch `fix/public-native-consumer-proof-contract` — none of that is the lab baseline. The lab pins **1.1.1 from PyPI** in its own venv, and LAB-01 records the actual resolved wheel digests, `quantbt.__file__`, native version and Python/OS metadata into `configs/study_registration.json` + `evidence/`. Never assume a signature the guide describes; probe the installed package (`api_binding_map.json`).

Everything runs as `.py` + CLI. Notebooks are not the harness and not a source of truth. Figures are generated by `.py` from committed artifacts.

### CLI contract to implement (guide §13.5 — none of this exists yet)

```bash
python -m crypto_regime_lab.cli preflight --lab-root "$LAB_ROOT"
python -m crypto_regime_lab.cli certify-alphas --registry "$LAB_ROOT/configs/alpha_registry.json"
python -m crypto_regime_lab.cli snapshot-data --study "$LAB_ROOT/configs/study_registration.json"
python -m crypto_regime_lab.cli verify-causality --study ...
python -m crypto_regime_lab.cli run --stage discovery|confirmation --study ...
python -m crypto_regime_lab.cli freeze --study ...
python -m crypto_regime_lab.cli report --from-artifacts "$LAB_ROOT/evidence"
python -m crypto_regime_lab.cli verify-source-integrity --lab-root "$LAB_ROOT"
```

The CLI must refuse a phase whose prerequisites, `.lab_marker.json` or sandbox policy are missing. `report` only reads committed artifacts — it never silently reruns the optimizer. Network is off during `run`/`certify`/`report`.

## Architecture the lab must build

Target tree (guide §5): `configs/`, `vendor_readonly/` (original zip + 4 raw alphas + QuantBT and loader snapshots), `quantbt_candidate/` (independent editable copy), `wheelhouse/`, `environments/`, `src/crypto_regime_lab/{safety,data,alphas,selector,regime,response,policy,quantbt_bridge,experiments,evidence}/`, `tests/`, `scripts/`, `snapshots/`, `evidence/{study_id}/{run_id}/`, `reports/`, `figures/`, `.cache/`.

Layer responsibilities:

- **`quantbt_bridge/`** — a `QuantbtBridge` facade owned *by the lab*: `inspect_installed_contracts`, `prepare_market`, `evaluate_candidate`, `run_continuous`, `replay_fixed_intents`, `export_required_artifacts`. These are lab operations mapped onto **verified installed** QuantBT endpoints via `api_binding_map.json` — never invent a QuantBT API and call it existing. Unsupported capabilities are recorded as `BLOCKED_CAPABILITY`, never silently downgraded to different economics.
- **`alphas/`** — four adapters for the four supplied alphas, each in four version tiers: `raw_supplied` (bytes, provenance only) → `legacy_reproduction` (diagnostic/in-sample only) → `canonical_v1` (the only tier eligible to prove regime edge; identical across all arms) → `research_revision_N` (deliberate thesis changes, kept separate). Every change records `change_kind = packaging_fix | execution_repair | indicator_repair | thesis_change` in `semantic_delta.json` with before/after semantics, source line refs, reproducer and affected arms.
- **`selector/`, `regime/`, `response/`, `policy/`** — deliberately separate: robust-neighborhood selection, persistent (sparse) jump-model regime inference, conditional parameter-response estimation, and the four-clock activation policy. A regime change must not implicitly trigger model retraining or a full Optuna search; inference, parameter switching, candidate-bank refresh and model retraining are four distinct clocks.
- **`evidence/`** — strict atomic JSON writer, append-only attempt ledger, `lab_run_id` on every artifact, `null` + reason for missing metrics.

Strategy/model/features stay in the Python research layer; QuantBT owns simulation/accounting and provides WFO/evaluation. Do not add features into QuantBT core, and do not build a second matching/accounting engine.

## The four alphas

Present on disk at `../alphas_storage/alpha_to_tes_regime_model/`, SHA-256 verified against the archive manifest in guide §1.1:

| ID | File | SHA-256 (prefix) |
|---|---|---|
| A-VWAP | `vwap.py` | `ef9e7e8a…` |
| A-HASH | `hash_momentum.py` | `ab35d906…` |
| A-HMA | `adaptive_hma_cpp.py` | `86c88f38…` |
| A-SC | `signal_combine.py` | `d540deef…` |

Only these four files are admissible input. `adaptive_hma_cpp.py` is Python/Numba despite its name. Per-alpha findings and required adaptations are enumerated in guide §3 (e.g. A-HASH's ATR is a close-to-close move, its `equity` column ignores open positions, TP2 is a fraction *of remaining*; §3.1 AH-01…AH-07). The `cetp_*` / `keke` / VN30F1M dictionaries inside `vwap.py` are **not** a fifth alpha — filter preset keys by schema and park the rest in `unmapped_presets.json`.

Supplied presets are tagged `provenance = user_full_sample_tpe`: usable as retrospective reference only, never as warm start, primary candidate bank, or an OOS claim.

## Data

Loader: `../alphas_storage/_get_data/data_loader.py`; storage: `../alphas_storage/_get_data/storage/` (~2.6 GB, Parquet). Relevant readers are `CryptoBinance1m` (`crypto/binance_futures/1m`), `CryptoBinanceSpot1m` (`crypto/binance_spot/1m`), `BinanceFuturesMetrics5m`, `BinanceOrderBookSnapshot1h`, `CryptoDailyMatrix`. Timestamps are naive UTC; `columns="full"` disables projection.

Symbols: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, DOGEUSDT. Spot from `2020-01-01` is treated as clean by user confirmation — run only operational checks (timestamps, units, gaps, availability, reproducibility); do not reopen pre-2020 repair as a blocker. Build `data_product_inventory.json` from **actual** files/classes/hashes, not assumed class names, and record `bar_timestamp_convention` / `available_at_rule` per product. A failed partition read becomes explicit missing coverage — never a "full sample" run over what happened to load.

## Execution contract and experiment design

- A signal observed at a bar close cannot fill at that same close. Primary clock: execution bars complete → strategy observes the completed alpha bar → regime observation available → decision → earliest next execution boundary → fill/accounting. Same-timestamp events need sequence IDs, not millisecond equality.
- Account config (capital, notional, leverage cap, fee/funding/slippage) is **experiment-level and frozen once in LAB-01** for all arms — never TPE-tuned, never chosen for prettier returns.
- Arms (§10.1): **A** installed WFO selector + frozen calendar (baseline), **B** neighborhood selector + same calendar, **C** current selector + regime-triggered refresh, **D** both, **E** selector + bank + response policy (extension, not a substitute for C/D). Compare `B-A`, `C-A`, `D-B`, `D-C` and interaction `(D-C)-(B-A)`.
- Mandatory controls: `RISK_ONLY`, `CALENDAR_MATCHED`, `BANK_CALENDAR`, `STATE_PLACEBO`, `DELAYED_STATE`, `EXPOST_DIAGNOSTIC`, `USER_PRESET_REFERENCE`. Never drop a control because it beats the proposed method.
- Primary matrix is 4 alphas × 5 symbols = 20 cells; each arm holds one continuous chronological account (no equity reset at fold/regime boundaries, no stitching best segments). Pilot order: A-SC → A-HMA → A-VWAP → A-HASH; all 20 cell statuses get reported regardless.

## Research-record and reporting discipline

- Keep the ID taxonomy distinct (§13.1): `study_id`, `experiment_id`, `trial_id`, `candidate_id`, `execution_id`, `probe_design_id`, `model_id`, `observation_id`, `response_id`, `selection_id`, `activation_id`, `attempt_id`. `reused_from` never changes a data role or cutoff.
- A blocked alpha is `NOT_READY` with `null` metrics + reason — **never PnL = 0**, which biases aggregates. Negative and inconclusive runs are committed like any other.
- `null` in a registration means visibly missing information; a validator must not promote a study to `FROZEN` with required fields null.
- Claims that are forbidden without the matching evidence (§13.6): "regime works" from full-sample-fit state correlation; "no leakage" from a `.shift(1)`; "out-of-sample" for full-set presets or a holdout already used to tune policy; "better on every dimension" from one metric; "Rust parity" from close final equity; "all 4 alphas certified" from a successful AST parse; "absolutely production-safe" from path naming without OS-level isolation.

## Surrounding repository

`/root/bobby/pool_alpha` is the parent git repo (branch `dev`, this lab dir is untracked). `quantbt/`, `alphas_storage/`, `lean/`, `MLops/*/` and `Arbops/*/` are **nested standalone repos excluded via `.gitignore`** to avoid double-tracking; each has its own branch and its own `AGENTS.md`. Workspace safety rules from `../.agents/AGENTS.md` apply here too: always check `git status` before any git command, never run `checkout`/`reset --hard`/`clean` with uncommitted changes, and never let a git command in this lab touch another project's repo.
