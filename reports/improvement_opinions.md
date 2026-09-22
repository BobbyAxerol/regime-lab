# Improvement opinions — WRITTEN, NOT RUN

**Status: none of this is implemented, scheduled, or assumed.** The lab builds exactly what
`QUANTBT_CRYPTO_REGIME_TIME_EDGE_LAB_FINAL_V2_VI.md` specifies (CLAUDE.md rule 11). Everything
below is an observation plus options, kept out of the results reports so it can never leak into a
conclusion. Nothing here changes an artifact, a conclusion, or a phase gate.

Each entry gives: what was measured, options, why each might work, cost, what could go wrong, and
what evidence would actually settle it.

---

## OP-01 — Arm B declined to select at half of all cutoffs

**Measured (LAB-04, v1 matrix, 90 cutoffs).** Arm B *(the lab's robust-neighborhood selector — it
picks argmax R among candidates that clear the registered gates)* retained the incumbent
*(the parameter set already deployed, carried forward as a candidate)* at **45/90 cutoffs**, every
one of them `ALL_FAIL_ECONOMIC_QUALITY`. Arm A retained at 0/90. Loosening the quality gate from
`G > 0` all the way to `G > −1.0` only moved coverage from 45/90 to 53/90, so the quality
threshold is not the whole story — the `P_survive ≥ 0.60` gate underneath it binds next.

**Why it matters.** A selector that abstains half the time is not obviously wrong — the registered
falsification commitment says zero switches is a valid technical pass — but it means half the
matrix compares a *frozen seed point* against a selector, which is a different question from the
one H1 asks.

**Options.**

1. *Leave it exactly as registered and report the abstention rate.* This is what LAB-04 does now.
   Costs nothing, keeps the pre-registration clean. Weakness: H1 is answered on a matrix where the
   treatment often did not apply.
2. *Register a second arm, B-relaxed, with a looser gate, as a NEW pre-registered contrast for a
   later phase.* Why it might work: it separates "the selector is wrong" from "the gate is strict".
   Cost: one more arm across 20 cells (~3 h). Risk: it looks like gate-shopping unless it is
   registered before it runs, with its own minimum-effect threshold.
3. *Keep the gate but let the selector fall back to the medoid of the least-bad region, recorded
   as a distinct status.* Why: abstention and "nothing was good, here is the least-bad centre" are
   different decisions and the current design collapses them. Risk: it weakens exactly the
   protection the gate exists to give.

**What would settle it.** A HOLD control on the same calendar that never re-selects after the
first cutoff. If HOLD matches arm B, arm B's advantage is abstention, not selection. This control
is already named in the LAB-06 family (`CALENDAR_MATCHED` / `RISK_ONLY`); it is not run in LAB-04.

---

## OP-02 — Arm A deploys points its own local panel rejects

**Measured (LAB-04, v1).** In **54 of 90** cutoffs, the point arm A deployed had a local panel
*(the anchor plus its 8 probes, scored on the same inner episodes)* whose verdict was
`FAILS_ECONOMIC_QUALITY` or `FAILS_SURVIVAL`. Arm A never consults that panel — its rule is argmax
in-sample objective. Notably **0** of arm A's deployments had *no* panel at all, and that is
structural rather than lucky: arm A picks the top discovery point, and top discovery points are
exactly the ones promoted to anchors.

**Why it matters.** It gives a precise mechanism for what the neighborhood selector is protecting
against, without needing an out-of-sample claim.

**Options.**

1. *Report it as a definitional difference and stop.* What LAB-04 does. Honest, costs nothing.
2. *Add a diagnostic arm A+ that keeps the argmax-objective rule but refuses a point its own panel
   rejects.* Why: it isolates "reading the panel" from "the whole robust score", which is a much
   narrower and more interpretable treatment than B−A. Cost: one more arm (~3 h). Risk: it is a
   new arm and must be registered before running, or it is post-hoc.
3. *Report the correlation between panel verdict and realised OOS outcome for arm A's picks.* Why:
   cheap, uses committed data, and directly tests whether the panel verdict carries information.
   Cost: near zero, no new backtest. Risk: correlation over 90 non-independent cutoffs is weak
   evidence and must be labelled as such.

**What would settle it.** Option 3 first, because it is free; option 2 only if 3 is suggestive.

---

## OP-03 — Terminal return and the registered endpoint disagree in magnitude

**Measured (LAB-04, v1).** Mean terminal chained return B−A was **+0.070**, which looks decisive.
The registered primary endpoint — *mean daily net-return difference on the same risk budget* — was
**5.695e-05/day** against a registered minimum economic effect of **6.4e-05/day**, i.e. below the
threshold. Excluding the four cells where arm B never selected, it falls to **4.829e-05/day**.

**Why it matters.** Reading the terminal figure would have produced the opposite conclusion. The
gap is not an error in either number; it is what happens when a compounding total is compared with
a per-day rate over a three-year horizon.

**Options.**

1. *Keep reporting both, with the endpoint decisive and the terminal figure labelled context.*
   What LAB-04 does now.
2. *Stop reporting terminal return entirely.* Why: it is the number a reader's eye goes to, and it
   is not the endpoint. Risk: it hides a real, if secondary, description of the account path.
3. *Report the terminal figure only inside the per-cell table, never in a summary line.* A middle
   position: available for inspection, never quotable as the headline.

**What would settle it.** Not an experiment — a reporting convention. Worth a decision before
LAB-07, when four arms make the temptation larger.

---

## OP-04 — Space-filling coverage costs eligibility

**Measured (LAB-04, first 5 cells of the v2 matrix vs the same 5 in v1).** Moving one of four
anchor slots from the TPE ranking to a space-filling point *(an anchor placed far from the ones
already chosen, so local panels do not all sit inside the region the sampler favours)* left the
abstention rate unchanged (23/23) and reduced eligible candidates from **73 to 60**. The
space-filling anchor sat 0.41–0.47 schema-distance from the TPE anchors, far outside the 0.12
probe radius, so it genuinely covered a different region — that region simply fails the economic
gate more often.

**Why it matters.** The spec-correct design is not automatically the better-performing one. This
is the coverage review guide §7.2 anticipates.

**Options.**

1. *Keep 2 TPE + 1 space-filling + 1 incumbent, as the guide specifies.* What LAB-04 does.
2. *Raise the budget to 5 anchors so space-filling is added rather than substituted.* Why: the
   current design pays for coverage by removing a TPE anchor; adding a slot separates the two
   effects. Cost: +8 evaluations per cutoff, roughly +8% wall clock. Risk: it changes the
   registered 96-evaluation budget, which is a matched condition between arms and must not move
   mid-study.
3. *Keep 4 slots but choose the space-filling point as the farthest candidate that still clears the
   quality gate.* Why: coverage where the alpha can actually function. Risk: it is no longer
   space-filling — it is biased coverage, and the bias is toward what already scored well, which is
   the thing space-filling exists to counteract.

**What would settle it.** The full v1-vs-v2 matrix comparison, which is a registered sensitivity on
anchor composition and is already scripted (`scripts/compare_anchor_designs.py`).

---

## OP-05 — A-VWAP's entry gate is nearly empty at some parameters

**Measured (LAB-02/04).** On BTCUSDT over 2020-07..2021-01, A-VWAP's reversion trigger fired on 697
long and 1147 short bars, while the HTF trend filter agreed on **0** and **1** of them. The two
conditions point in opposite directions by construction: an oversold, below-band bar is
mechanically below a slow EMA. Widening the declared `htf_ema_len` bound to enclose the alpha's own
operating range (130–570) fixed the empty gate, but two A-VWAP cells still ended with arm B taking
**8 fills across three years**.

**Why it matters.** A cell with 8 fills cannot support any statistical statement, and A-VWAP is
also where the pooled sign reverses.

**Options.**

1. *Report the trade count per cell and let the reader discount it.* What LAB-04 does.
2. *Register a minimum trade count per cell below which the cell is reported as
   `INSUFFICIENT_ACTIVITY` with null metrics, like a NOT_READY alpha.* Why: it stops a near-empty
   cell from carrying the same weight as a 1000-fill cell in a sign test. Cost: near zero. Risk:
   the threshold is a new registered parameter and must be fixed before it is applied, not chosen
   once the counts are visible.
3. *Treat A-VWAP's trend filter as an indicator_repair candidate.* Why: the source may intend
   "trend agrees with the reversion direction" rather than "price is on this side of the EMA".
   Risk: **this is a thesis change, not a repair**, unless the source's own comments settle it —
   and changing it would move A-VWAP out of `canonical_v1`, which is the only tier allowed to prove
   edge.

**What would settle it.** For option 3, only the original author's intent. Absent that, option 2 is
the defensible one, registered before LAB-07.

---

## OP-06 — The behavioural OOS probe can only see the last fold

**Measured (LAB-04, L04.1).** With `window_mode="expanding"`, a later fold trains on an earlier
fold's test window, so the only region that is out of sample for *every* fold is the final test
segment. The mutation probe therefore mutates just that. A null result bounds OOS dependence; it
cannot refute it. Where the probe and the engine's own declared `oos_used_for_selection` disagree,
LAB-04 treats the declaration as authoritative.

**Why it matters.** It is the difference between "we measured that it does not use OOS" and "we
measured that we could not detect it using OOS in the one place we could look".

**Options.**

1. *Keep the declaration authoritative and state the probe's power limit.* What LAB-04 does.
2. *Run the probe per fold with a rolling window mode instead of expanding.* Why: with a rolling
   window, each fold's test segment is out of sample for that fold, so the probe regains power.
   Cost: small, synthetic fixture only. Risk: it measures a *different configuration* than the one
   the study uses, so the result would not transfer without saying so.
3. *Mutate one fold's test segment at a time and check only that fold's selected parameters.* Why:
   it isolates per-fold OOS use without changing the window mode. Cost: N runs instead of 2. Risk:
   per-fold selection only exists under the per-fold schedules, so this does not apply to the
   global schedule at all.

**What would settle it.** Option 3 for the per-fold schedules; for the global schedule the
declaration is the only available answer, and that limit should be stated rather than engineered
around.

---

## OP-07 — Three confirmed engine defects have a proposal but no upstream path

**Measured (LAB-04, L04.2).** `quantbt.optimization.candidate_selection._param_distance` normalises
by the *sampled* span, so one distant trial collapsed the distance between two unchanged points by
**98×**; a constant parameter dilutes every distance; an inactive conditional parameter
manufactures a full unit of distance. `quantbt.walkforward` is not affected and was recorded as
`VERIFIED_EXISTING_CORRECT`. A bounded proposal sits in `handoff/lab_only_patch.diff`, never
applied, with a test proving the installed wheel is untouched.

**Why it matters.** The lab does not depend on the fix — its own geometry uses declared bounds —
but anything else in the repo that uses `CandidateSelector` does.

**Options.**

1. *Leave it in `handoff/` as the deliverable, which is where the guide's scope ends.* Current
   state.
2. *Add a runnable reproducer script under `handoff/` so a maintainer can confirm it in one
   command.* Why: a diff is an assertion; a reproducer is evidence. Cost: ~30 lines. Risk: none
   that I can see, as long as it never imports from a patched path.
3. *Also measure whether any shipped code path actually reaches the defective function.* Why: the
   severity depends entirely on that, and right now nobody knows. Cost: static call-graph read of
   the installed package, no execution. Risk: a static read can miss dynamic dispatch, so a
   negative result would need to be labelled as "not found statically", not "unreachable".

**What would settle it.** Options 2 and 3 are both cheap and would make the handoff materially more
useful. Neither changes any lab result.

---

## OP-08 — A K=3 jump model emits 18 switches on pure noise

**Measured (LAB-05, L05.7).** The no-regime world *(a synthetic negative control drawn from ONE
distribution throughout, so the truth contains zero state changes)* produced **18 emitted switches**
and a best-permutation agreement of **0.007**. The model was not broken; it was doing exactly what
it is asked to do, which is partition observations into K states.

**Why it matters.** It puts a number on the false-structure rate. Any later claim of the form "the
provider identified N regimes in period P" has to be read against a baseline of ~18 switches per
600 observations arising from nothing at all.

**Options.**

1. *Report the number alongside every state count, as LAB-05 does.* Costs nothing, and it is the
   honest minimum.
2. *Calibrate a per-cell null: refit on phase-randomised or block-bootstrapped versions of the SAME
   panel and report the switch count distribution under the null.* Why it might work: it turns "18
   on a synthetic fixture" into "this many switches on THIS instrument's own null", which is the
   comparison a reader actually wants. Cost: N refits per cell, cheap at 8 features. Risk: a
   phase-randomised series destroys the volatility clustering that the features are built on, so
   the null may be too easy; block bootstrap is the safer of the two.
3. *Require a state to persist a minimum dwell before it is emitted.* Why: it would cut the noise
   switches directly. Risk: it is a second, hidden jump penalty. λ_J already controls persistence
   and adding a dwell filter on top means two knobs doing one job, with the second one not in the
   objective the fit minimises.

**What would settle it.** Option 2. It is the only one that produces a null for the actual data
rather than for a fixture.

---

## OP-09 — A quarter of refits produce a state that cannot be matched

**Measured (LAB-05, L05.5).** Across 40 fits at the registered 28-day cadence, **10 of 39**
consecutive namespace mappings *(matching a new fit's states onto the previous fit's, using TRAINING
centroids only)* contained at least one `UNMAPPED_REFIT_STATE`. The mapping threshold is a declared
0.5 relative distance, measured against the median spread between the old model's own states.

**Why it matters.** Downstream, a policy that keys off state identity has to handle a vocabulary
that partly changes every four weeks. That is a real operational property, not a bug — but it is
large enough to shape any policy built on top.

**Options.**

1. *Leave the threshold as registered and report the rate.* Current state.
2. *Warm-start each refit from the previous centroids instead of k-means++.* Why it might work:
   the fit would tend to land near the previous solution and the permutation problem would mostly
   disappear. Risk: it makes each model depend on its predecessor, so a bad fit propagates forward,
   and the "independent refit" property that makes the mapping check meaningful is lost. It also
   changes what the multi-start diagnostic means.
3. *Map on economic descriptors as well as centroids* — guide 8.4 explicitly allows "training
   centroids/economic descriptors". Why: two states can be close in feature space yet behave
   differently, and vice versa. Cost: needs a descriptor set defined and registered first. Risk: a
   descriptor computed from outcomes would import exactly the contamination the mapping is designed
   to avoid; it would have to be a training-window descriptor only.

**What would settle it.** Option 2 and option 1 can be compared directly: refit both ways over the
same 40 cutoffs and count unmapped states. That is a cheap, self-contained experiment.

---

## OP-10 — The greedy labeller switches four to ten times more often

**Measured (LAB-05, L05.2).** At λ_J = 0.5 the endpoint DP emitted 37 switches where the greedy
labeller emitted 160; at λ_J = 2.0, 14 versus 102; at λ_J = 6.0, 21 versus 204. Label agreement fell
to 0.333 at the largest penalty. They coincide only at λ_J = 0.

**Why it matters.** λ_J is currently a single registered number (1.0 at a 4h interval) with no
sensitivity around it. The spread above shows the emitted tape is extremely sensitive to it, and the
policy's switching cost is paid on that tape.

**Options.**

1. *Keep λ_J = 1.0 as registered and report the algorithm comparison.* Current state.
2. *Register a λ_J sensitivity the way LAB-04 registered a probe radius* — declare {0.5, 1.0, 2.0}
   before running, keep 1.0 primary, and report how the emitted switch count moves. Why: it makes
   the sensitivity visible without letting it be tuned. Cost: three fit passes instead of one. Risk:
   none that I can see, provided the primary is fixed in advance.
3. *Choose λ_J on the inner criterion, like K.* Why: it is a model hyperparameter and the machinery
   already exists. Risk: the inner objective CONTAINS λ_J, so lower λ_J mechanically lowers the
   objective; selecting on it would drive λ_J to zero and turn the model into the greedy labeller.
   This option is a trap and I would not take it without a different criterion.

**What would settle it.** Option 2. Option 3 needs a criterion that does not contain the penalty —
for example switch-count stability across inner folds — and that would have to be registered before
it is looked at.

---

## OP-11 — The lab uses one symbol for the regime model

**Measured (LAB-05).** The fits run on BTCUSDT only. The feature panel supports five symbols and the
primary core was built precisely because those 8 features cover all five.

**Why it matters.** The guide's regime states are meant to describe market structure, and a
one-symbol state vocabulary may be describing BTC rather than the market.

**Options.**

1. *Fit per symbol, five independent state vocabularies.* Why: simple, and each cell's policy reads
   its own instrument. Risk: five namespaces to map, and "the market is in state 2" stops meaning
   anything across cells.
2. *Fit one model on pooled cross-sectional features.* Why: the G5 group (dispersion, breadth,
   residual return) is already cross-sectional, so a pooled model is closer to what those features
   describe. Cost: modest. Risk: pooling assumes the states mean the same thing for DOGE and BTC,
   which is exactly what would need testing rather than assuming.
3. *Fit on BTC and apply to all, as now, but MEASURE the residual per symbol* to see whether the BTC
   vocabulary is out of support elsewhere. Why: cheap, uses the novelty machinery that already
   exists, and it answers whether option 1 or 2 is even needed. Cost: near zero.

**What would settle it.** Option 3 first. If the other four symbols sit inside BTC's training
support, the one-symbol vocabulary is defensible; if they do not, that is the argument for option 1
or 2, decided on evidence rather than preference.

---

## OP-12 — The registered 8-feature core does not earn its blocks out of fold

**Measured (LAB-05, guide 8.3 group ablation, BTCUSDT 2020-01..2021-12, held-out inner blocks).**
Adding feature blocks made state resolution WORSE, on both measures:

| feature blocks | features | variance resolved out of fold |
|---|---|---|
| G1 (price/path) | 3 | **+0.341** |
| G1 + G2 (flow) | 5 | +0.123 |
| G1 + G2 + G5 (market coordination) | 8 | **−0.021** |

*Variance resolved* is one minus within-state over total weighted variance, so it means the same
thing at 3 features and at 8 — unlike the fit objective, which is a different function for each
feature set. At the full registered core the number is NEGATIVE: on held-out blocks the state
assignment removes less variance than the grand mean does.

**Why it matters.** Guide 8.3 requires the ablation to DEMONSTRATE that flow and market-coordination
features contribute beyond price/volatility. It does not. That is a real negative result about the
registered core, not a bug.

**What was deliberately NOT done.** The core was not switched to G1-only. Choosing a feature set
because an ablation preferred it is selecting the model on a result, and the core was registered in
LAB-03 from coverage, before any of this ran.

**Options.**

1. *Report the ablation and keep the registered core.* Current state. Costs nothing and keeps the
   pre-registration intact. Weakness: the model carries five features that, on this evidence, are
   noise for state resolution.
2. *Register a G1-only arm as a NEW pre-registered comparator for LAB-06.* Why it might work: it
   makes "fewer features resolve states better" falsifiable at the decision level rather than at
   the fit level. Cost: one more state vocabulary and its emissions. Risk: it must be registered
   before it runs, with its own threshold, or it is post-hoc feature selection wearing a comparator
   costume.
3. *Re-check the weighting rather than the feature set.* `w_j = ω_g/d_g` gives G2 a per-feature
   weight of 0.167 against G1's 0.111 because G2 has fewer members — so the two flow features carry
   MORE weight each than any price feature. Why it might matter: the ablation may be measuring the
   weighting scheme rather than the features. Cost: near zero, re-run the ablation with equal
   per-feature weights as a diagnostic. Risk: none, provided it is labelled a diagnostic and the
   registered weights do not move.
4. *Test it on the other four symbols before concluding anything.* Why: this is one symbol and one
   window. Cost: four more ablations, cheap. Risk: none.

**What would settle it.** Option 4 first, then option 3 — both are cheap and both could change the
reading. Option 2 only if the finding survives them, and only registered in advance.

**Related.** This interacts with OP-11: if the state vocabulary is being carried by three price/path
features, the case for a per-symbol model is weaker than it looked, because those three features are
the ones most likely to mean the same thing across instruments.

---

## OP-13 — The registered K and the registered selection method disagree

**Measured (LAB-05, L05.4, BTCUSDT, training window ending 2020-12-31).** On held-out inner
chronological blocks, K=2 scored **0.615641** and K=3 scored **0.627411** — the *smaller* K is
better by **1.9%**. The lab deployed the registered starting **K=3** and recorded the disagreement.

**Why this is not obvious.** The guide supports both readings and they point different ways:

- §8.1: "Primary starting `K=3`; ... `K=2` là parsimonious alternative" — K=3 is where you start,
  K=2 is a registered fallback.
- §8.3: "Regularization, feature ranking và K được chọn trong nested development, không bằng
  holdout" — nested development IS the registered selection method, and it chose K=2.

The usual warning ("a larger K fits better almost by construction") does not apply, because here
the larger K scored *worse*. So the standard reason for distrusting a K comparison is absent.

**Options.**

1. *Keep K=3, report the disagreement.* Current state. Switching after seeing a score — even a
   nested-development score — is still choosing the model on a result. Weakness: it also ignores
   the selection method the guide registers.
2. *Adopt K=2 as the selection method's output.* Why it might be right: §8.3 names nested
   development as the method, both candidates were pre-registered, and no holdout was touched. Cost:
   refit and re-emit, ~10 minutes. Risk: a 1.9% margin on one symbol and one window is thin
   evidence to move a registered primary on.
3. *Decide K per fit rather than once.* Why: the training window moves every 28 days and the
   preferred K may move with it. Risk: the state vocabulary size would change mid-study, which
   makes namespace mapping harder and makes "the model has 3 states" untrue as a description.
4. *Check whether the disagreement is stable* — re-run the inner criterion at several cutoffs and on
   the other four symbols before treating it as a finding at all. Cost: cheap.

**What would settle it.** Option 4 first. A 1.9% margin at a single cutoff is not enough to move a
registered choice in either direction, and it may not even be stable across cutoffs.

**Note on how this surfaced.** The K comparison first reported agreement with K=3. That was from an
earlier, wrong fit cadence (cutoffs six months apart, first window ending 2022-01-01). Correcting the
cadence to the registered 28 days moved the first training window to 2020-12-31, and the preferred K
moved with it. The selection is deterministic — three consecutive runs give identical scores — so
this is a window effect, not non-determinism.

---

## OP-14 — The registered 7-day horizon is under-powered for A-SC

**Measured (LAB-06, A-SC/BTCUSDT, 1530 episodes over 10 candidates).** In **774 of 1377**
(candidate, episode) pairs — **56%** — the paired delta is EXACTLY zero: both the candidate and
the incumbent did nothing that week. One bank candidate was flat in 92% of its episodes
(median trades 0).

The horizon check passed on its own terms: 7 days covers the measured mean holding of 3.92 days.
But covering the holding period is not the same as containing enough trades to tell two parameter
sets apart, and that is the question the response estimator has to answer.

**Why it matters.** It changes what "zero switches" means. The decision ledger shows 30
`KEEP_INCUMBENT` decisions where the best challenger's lower bound came within 0.000577 of the
0.0007 threshold — which reads like "no edge". The informativeness number says something weaker
and more honest: **more than half the evidence could not have shown an edge at any weighting**.

**Options.**

1. *Keep the registered horizon and report the informativeness share.* Current state. The horizon
   was registered before the estimator ran and retuning it now would be selecting the experiment on
   its own result.
2. *Register a longer horizon for a later phase* — 28 days, say, matching the bank refresh cadence.
   Why it might work: A-SC trades roughly once a week, so a 28-day episode would carry about four
   trades instead of one. Cost: fewer non-overlapping episodes (about a quarter as many), so
   support gets thinner even as each episode gets more informative. Risk: the two effects pull in
   opposite directions and the net could be worse; it must be registered before it is measured.
3. *Weight episodes by how informative they are.* Why NOT: `q_e` is an eligibility flag precisely
   so that nothing outcome-shaped enters the weights, and "this episode had trades" is one step
   from "this episode had a result". Guide 9.2 forbids the direction. I would not take this option.
4. *Select the horizon per alpha from its trade frequency rather than globally.* Why: A-HMA holds
   for days and A-SC trades weekly; one horizon cannot suit both. Cost: a registered rule such as
   "the horizon is the window containing at least N median trades", fixed before use. Risk: it
   becomes a tuned parameter unless the rule, not the value, is what gets registered.

**What would settle it.** Option 4's RULE, registered in advance, then measured on all four alphas.
Option 2 alone would just move the problem.

**Related.** This also bounds OP-01: arm B's frequent abstention in LAB-04 and the response
estimator's frequent insufficiency here may both be symptoms of episodes that are too short to
carry a comparison, rather than two independent findings.

---

## OP-15 — The loader endpoint truncates volume, and the truncation hides on the symbols you would test first

**Measured (2026-09-10, `configs/loader_endpoint_parity.json`, 15 partitions across all five
symbols).** `MarketDataLoaderBase._normalize` in `data_loader.py` ends with
`df["volume"] = pd.to_numeric(...).fillna(0).astype("int64")`. Binance USD-M stores fractional
contract quantities for BTCUSDT, ETHUSDT and BNBUSDT, so the endpoint truncates every fractional
bar. Measured on BTCUSDT 2026-08: **44,594 of 44,640 bars differ, 0.515% of the partition's total
volume is lost, and 41 bars with real trades come back as `volume = 0`**. DOGEUSDT is stored
int64 throughout and shows **zero** difference; SOLUSDT shows zero until its quantity step changes
and a difference afterwards. So the defect is invisible on the cheapest symbols to spot-check and
appears only where the quantity step is fine — which is the opposite of how one would usually
sample.

This lab is not exposed: it parses the loader statically for path routing and reads the parquet
directly (`reports/data_sources_used.md`, guide 6.1). The exposure is for **any other consumer of
that endpoint**, and `../alphas_storage` is read-only to this lab, so this is written and not run.

**Why it matters beyond precision.** A `volume = 0` bar is not a rounding error in the feature
layer. `g2_log_activity_30` takes a log and `g2_taker_imbalance` masks a zero denominator rather
than adding an epsilon, so a truncated bar becomes a *missing observation*, not a slightly wrong
one. Truncation removes data points; it does not merely blur them.

**Options.**

1. *Leave the endpoint alone; document the behaviour.* Current state, and correct for this lab.
   Cost: every other consumer keeps inheriting it silently. Risk: the next project reads the
   endpoint, sees plausible-looking integers, and never learns the fraction existed.
2. *Cast to float64 instead of int64 in `_normalize`.* Why it might work: the stored dtype is
   already float64 for three of five symbols, so this preserves what is there rather than adding
   anything. Cost: a dtype change in a shared loader ripples into every downstream consumer that
   assumed an integer, including anything that formats or hashes the column. Risk: a silent
   behaviour change in someone else's pipeline is worse than a documented defect. Would need the
   owner's decision, not a patch from here.
3. *Keep int64 but refuse the cast when it would lose information* — raise or warn when
   `(volume % 1 != 0).any()`. Why: it converts a silent corruption into a visible failure at the
   only point that can still see both values. Cost: existing callers on BTC/ETH/BNB would start
   failing immediately, which is the point and also the objection.
4. *Per-product dtype declaration* rather than one class-level `RESAMPLE_VOLUME_DTYPE`. Note that
   `CryptoBinanceSpot1m` already overrides `_normalize` and sets `RESAMPLE_VOLUME_DTYPE =
   "float64"` — the loader's own author already hit this and fixed it for spot only. Extending the
   fix to the futures reader is the smallest change consistent with existing intent.

**What would settle it.** Option 4, measured the way `verify_loader_parity.py` measures it: diff
the endpoint against the parquet for every product and symbol, and show the diff is empty. Until
the storage owner decides, this stays an observation.

**Related.** The int64/float64 split is the same defect surface as the recorded SOL and DOGE dtype
variation; [[OP-15]] is the endpoint half of what `panel.normalize_numeric_dtypes` already handles
on the read side.

---

## OP-16 — A file digest cannot tell a re-ingest from a revision, and the read-lock was reporting the stronger verdict

**Measured (2026-09-10).** 23 CLOSED `crypto_binance_futures_metrics_5m` partitions spanning
2020-09 to 2025-08 changed upstream after the snapshot was taken. The read-lock compares SHA-256
digests, so it declared `EXTERNAL_DATA_DRIFT` and invalidated the G3 cohort. Reading both files
shows **every measured column is identical**; only `ingested_at` moved (2026-09-09 15:53 →
2026-09-10 10:31, and again on the next check). The collector re-ingests closed months, which
rewrites the vintage stamp on every row.

That is now fixed rather than merely noted — `classify_source_drift` reads both files and the
verdict is `EXTERNAL_VINTAGE_RESTAMP_ONLY`. The opinion below is about what remains.

**What remains.** The classification is *reactive*: it runs after a digest moves, and it costs a
full read of both files. On a large drift that is expensive, and on a product with a wide schema
the "measured column" set is defined by exclusion (`VINTAGE_COLUMNS`), which is a denylist. A
denylist of vintage columns is exactly the shape that fails quietly when a new metadata column
appears upstream and gets treated as a measurement.

**Options.**

1. *Keep the denylist, keep it short.* Current state. Cost: a new metadata column upstream turns
   every re-ingest into a false `CONTENT_REVISION`. That fails in the safe direction — it
   over-invalidates — which is why it is acceptable as the default.
2. *Record a content digest at snapshot time*: a second SHA-256 over the measured columns only,
   stored in the manifest. Why it might work: drift classification becomes a hash comparison
   instead of two full reads, and the manifest carries the answer rather than deriving it. Cost:
   the manifest must be rebuilt, which re-registers the read-lock — and re-registering the lock to
   make the lock more convenient is the kind of move that deserves suspicion. Risk: the content
   digest depends on a serialisation choice (column order, float formatting), so a digest mismatch
   could mean "pandas version changed", which is worse than no digest.
3. *Declare the measured columns per product as an allowlist* in `inventory.PRODUCTS`, so a new
   upstream column is unknown rather than assumed to be a measurement. Why: it inverts the failure
   mode from "silently treated as data" to "explicitly unrecognised". Cost: the schema must be
   maintained alongside the collector's.

**What would settle it.** Option 3 first — it is cheap and it removes the denylist's failure mode.
Option 2 only becomes worth its risk if closed-partition drift becomes frequent enough that the
read cost matters, which on this storage it is not.

---

## OP-17 — The early phase audits are an order of magnitude coarser than the later ones

**Measured (2026-09-10, `configs/lab0N_task_audit.json`).** LAB-01, LAB-02 and LAB-03 are audited
at **one row per L0N.M task**: 6, 8 and 7 rows. LAB-04, LAB-05 and LAB-06 are audited at **one row
per guide clause**: 64, 53 and 79 rows. All six report DONE.

A task row like "L01.5 — Preregister claims và contamination: DONE" asserts a sentence of the guide
that contains at least seven separable requirements (hypothesis registry, 20-cell matrix,
baselines/variant IDs, primary timeframes, cost/risk setup, **compute budgets**, freeze/holdout
policy). The compute-budget contract was the one of those seven that was never built, and the
LAB-01 audit passed anyway — not because it lied, but because at task granularity there was no row
for it to fail.

The clause-level audits introduced at LAB-04 exist precisely because that granularity can hold a
requirement. LAB-06 went further and wrote its 79 clauses BEFORE any policy code, so the audit
could not become a list of what happened to get built.

**Options.**

1. *Leave the early audits as they are.* Current state. Cost: LAB-01–03 remain the phases where a
   sub-clause can hide, and they are the phases everything else rests on. Risk: the next gap found
   there will also be one no row covered.
2. *Re-audit LAB-01–03 at clause granularity, retrospectively.* Why it might work: it is a read of
   the guide against existing artifacts — no phase re-runs, no measurement moves, and it would
   have caught Gap 1 the day L01.5 was signed off. Cost: roughly 60–80 new clause rows to write and
   evidence-point, comparable to one LAB-06 checklist. Risk: an audit written after the code is
   exactly the failure mode LAB-06's checklist-first rule was created to avoid — the reader must be
   told these three were reconstructed, not pre-registered, or the clause count implies a rigour
   the process did not have.
3. *Only re-audit the clauses that later phases depend on* — the preregistration content (L01.5),
   the execution contract (L02.7/L02.8) and the availability rules (L03.3). Why: those are the ones
   whose failure propagates. Cost: perhaps 25 rows. Risk: choosing which clauses matter is itself a
   judgement made after seeing which ones held.

**What would settle it.** Option 2, with every reconstructed row explicitly flagged
`audited_retrospectively: true` so the count cannot be read as pre-registration. Option 3 is
cheaper but decides in advance where the gaps are, which is the assumption that produced this one.

**Related.** Gap 1 in `reports/guide_compliance_inspection.md` is the concrete instance; [[OP-16]]
is the same shape one layer down — a check whose granularity could not express what it was
checking.

---

## OP-18 — The account has been charged half its registered taker fee since LAB-04, and the fix costs a full re-run

**Measured (2026-09-11).** `scripts/verify_cost_binding.py` runs one real account and divides each
fill's recorded fee by its notional. The implied **one-way fee** is `0.0002`. The study registered
`0.0004` at LAB-01, provenance "Binance USD-M standard taker rate". The ratio is exactly `0.5`, on
every fill, at every cost multiplier.

The cause is in the installed engine's own documentation, not in its behaviour:

> `fee`: Legacy compatibility **round-trip** fee. It is converted to canonical one-way `fee_rate`
> at the endpoint boundary when explicit `fee_rate` is omitted.
> `fee_rate`: Canonical **one-way** fee. If supplied, it has priority over `fee`.

`quantbt_bridge/intent_tape.py` calls `run_intrabar(..., fee=ACCOUNT["taker_fee_rate"], ...)`, so
the registered one-way rate is halved. The engine's default for `fee` is also `0.0004`, so the call
reads correctly, matches the registered number, and raises nothing. LAB-01 recorded the *signature*
in `api_binding_map.json` and never probed the *semantic* — the exact failure the guide's "never
assume a signature the guide describes" rule names.

**Direction and size.** Flattering: every account paid less than declared. Round trip, the account
charged `0.0004` fee + `0.0002` slippage = **6 bps**, where the registered contract implies
`0.0008` + `0.0002` = **10 bps**. `configs/minimum_economic_effect.json` derived its 6.4e-05/day
threshold from the 10 bps figure, so the threshold is the conservative one — it was never made
easier by the defect.

**What was already done.** The deployment accounting is corrected without changing the binding:
`scripts/replay_lab08_development.py` re-runs every development arm at the registered fee, and
`scripts/run_lab09_stress.py` adds an `AS_DECLARED` level to the cost panel. On development the
registered contrasts move by at most ~5% and none crosses the minimum economic effect, so the
NO_PROMISING_DESIGN conclusion is unchanged. Recorded as COR-13.

**What remains, and why it is an opinion rather than a change.** The SELECTIONS were made under the
halved fee. Every candidate in LAB-04 and LAB-08 was scored with a net objective that understated
cost, and a selector that rescored at the registered fee could have chosen differently — plausibly
towards lower turnover, which is the direction that would matter. Correcting that is not an
accounting adjustment; it is a re-run of the search.

**Options.**

1. *Leave the binding as it is and keep reporting the AS_DECLARED panel.* Why it might work: the
   comparison between arms is unaffected to first order because every arm pays the same fee, and
   the measured contrast shift is small. Cost: the lab's absolute returns are not the returns of
   the contract it registered, and every future phase inherits that. What could go wrong: a
   turnover-heavy design would look better than it is, and the arms that differ most in turnover
   are exactly the dynamic ones.
2. *Change `run_intrabar` to pass `fee_rate=` and re-run everything from LAB-04.* Why it might
   work: the lab would then measure the contract it registered, with no footnote. Cost: LAB-04
   (~7 h), LAB-06 (~10 min), LAB-07, LAB-08 (~3 h) and LAB-09's confirmation (~6 h) — call it
   twenty hours of sequential compute at the registered one-worker budget — plus a protocol
   revision, because the economics would change between a frozen discovery and its confirmation.
3. *Change the binding and re-run LAB-08 and LAB-09 only, leaving LAB-04's candidate bank as it
   is.* Why it might work: it corrects the phases whose numbers carry the conclusion, at about a
   third of the cost. What could go wrong: the candidate bank would still have been discovered
   under the wrong fee, so the correction would be partial in a way that is harder to describe than
   either extreme.
4. *Register the 6 bps round trip as the contract and correct the documentation instead.* Why it
   might work: nothing re-runs, and 2 bps one-way is defensible as a maker-ish or VIP-tier rate.
   What could go wrong: it is choosing the cost assumption after seeing the results, which is the
   one thing the minimum-economic-effect registration exists to prevent. Listed for completeness
   and **not recommended**.

**It was settled, and the answer is the unwelcome one.** `scripts/probe_fee_sensitivity.py`
re-selected A-SC/BTCUSDT at the registered fee, with the sampler seed fixed so the trial POINTS are
identical and only the objective values move. **One of twelve arm-selections changed:**

| cutoff | arm | at the charged fee (0.0002) | at the registered fee (0.0004) |
|---|---|---|---|
| 2021-06-30 | A | `AP=36, threshold=55, coeff=4` | `AP=41, threshold=50, coeff=4` |

Eleven of twelve were identical. One was not, and one is enough: the selector IS fee-sensitive, so
this is a **design** defect and not only an accounting one. The candidate bank LAB-04 built — and
therefore every arm LAB-08 and LAB-09 compared — was chosen under a cost the study did not register.

**Option 1 is therefore no longer defensible.** The AS_DECLARED panel corrects the deployment
accounting and cannot correct the selection. The honest paths are option 2 (re-run everything from
LAB-04 at `fee_rate=`, ~20 h) or option 3 (re-run LAB-08 and LAB-09 only, leaving LAB-04's bank as
it is, and describing the partial correction precisely).

This is a decision for the user, not for the lab: it is hours of compute and a protocol revision,
and guide L09's exit already records the consequence of not taking it — `FAILED_VALIDITY`, the
affected runs invalidated, and no headline kept.

**Still not run.** The binding is unchanged, and the confirmation was run on the same economics as
the discovery it confirms, so the two remain comparable to each other even though neither matches
the registered contract.

---

## OP-19 — The protocol declares 1-minute execution bars and the account resolves protection on the decision bar

**Measured (2026-09-11).** `scripts/verify_execution_resolution.py`. `configs/lab08_pilot_protocol.json`
declares `execution_bars: "1m"` for all four alphas. `integration/continuous_account.py` and
`experiments/evaluator.py` both build `engine_frame = frame[["open","high","low","close","volume"]]`
from the DECISION-bar frame and hand that to `run_intrabar`; no 1-minute frame is constructed
anywhere in the account path. So a stop and a take-profit that both sit inside one 15-minute bar are
resolved by the engine's intrabar ordering rule against that bar's high and low, not along the
minute path within it.

Exposure, measured by counting protective fills on a six-month probe (BTCUSDT, seed parameters):

| alpha | fills | protective | share | exposed |
|---|---|---|---|---|
| A-SC | 48 | 0 | 0% | **no** — every exit is technical |
| A-HMA | 60 | 16 (7 stops, 9 TPs) | 27% | yes |
| A-VWAP | 2 | 1 | 50% | yes |
| A-HASH | — | — | — | NOT_READY |

**What it does and does not threaten.** Every arm, every control and both selectors run through the
same engine on the same frame, so the resolution cancels in `B-A`, `C-A`, `D-B` and `D-C`. It is a
LEVEL effect, not a contrast effect — which is exactly the distinction guide 4.3 draws when it warns
against attributing a fill-fidelity gain to a regime edge. Recorded as COR-17.

**Options.**

1. *Declare the decision-bar resolution and change the protocol's `execution_bars` to match.* Why it
   might work: nothing re-runs, and the contract would then describe the lab. Cost: the protocol is
   frozen and immutable by design; editing it after results exist is the one thing the freeze
   prevents. It would have to be a protocol REVISION with its own stamp, not an edit. What could go
   wrong: 15-minute protection is coarser than the guide contemplates, and declaring it does not make
   it more faithful.
2. *Build the two cohorts guide 4.3 asks for.* Re-index every decision-bar intent onto a 1-minute
   frame, run both, and report the pair. Why it might work: it is what the guide actually asks for,
   and the difference between them is the fill-fidelity effect measured rather than argued. Cost: the
   intent tape is indexed to decision bars, so every intent needs mapping to the minute bar at its
   decision close + 1, and the exit oracle needs the minute frame too; then every account re-runs on
   ~15× the bars. Call it a day of implementation and several hours of compute. What could go wrong:
   1-minute bars are still not a tick path — guide 4.3 says so in its first line — so the corrected
   cohort is less wrong, not right.
3. *Measure the sensitivity on one cell instead of building the cohort.* Run A-HMA/BTCUSDT's arm A
   with protection resolved on 5-minute bars as an intermediate, and report how much the level moves
   between 15m and 5m. Why it might work: it bounds the effect for a fraction of option 2's cost and
   would say whether option 2 is worth it. What could go wrong: an intermediate resolution is not one
   of the two cohorts the guide names, so it informs the decision without discharging the clause.

**What would settle it.** Option 3, then option 2 only if the 15m→5m move is comparable to the
minimum economic effect. If the level barely moves on the most exposed alpha, the honest disclosure
plus a protocol revision (option 1) is proportionate.

**Not run.** Nothing above is implemented. The lab reports the discrepancy, the per-alpha exposure and
the reason contrasts are unaffected, and leaves the choice to the user.

## OP-20 — Each worker is capped at 4 GiB on a 9.7 GiB shared host, so the cap that actually fires is the kernel's

**Measured (2026-09-15).** `evidence/time_edge_validation_v4/operations/oom-incident-20260915-02.json`,
written by `scripts/record_oom_incident.py` from the run receipts, the kernel ring buffer and `/proc`.

Both BTC structural-control shards of `te-host-controls-btc-02` were SIGKILLed ~26 minutes into their
first attempt. The receipts say `isolated child exited 137` — 128 + SIGKILL(9) — and nothing more.
The kernel ring buffer says what the receipts cannot: `Out of memory: Killed process 1549135 (python)
anon-rss:1569912kB` at 11:10:52 and `1549126` at 11:12:31, both `constraint=CONSTRAINT_NONE,
global_oom`.

Each kill is linked to its attempt by arithmetic, not by label: the kill timestamp minus that
attempt's independently measured `wall_seconds` reproduces the second the runtime wrote its request
file, with residuals of **−0.571s** and **−3.16s** while the runner-up candidate sits **98s** and
**102s** away. The linkage refuses to claim a match when two kills fall inside the window, so it can
go red.

| | measured |
|---|---|
| peak worker RSS at kill | 1.50 GiB and 1.45 GiB |
| registered per-worker limit | 4 GiB (`RLIMIT_AS`, `time_edge/workers.py::require_isolated`) |
| workers registered for this run | 2 → an 8 GiB aggregate ceiling |
| host | 9.72 GiB, **0 swap**, 4 CPUs |
| other agent tool on the same host | `opencode`, itself OOM-killed at 10:49:28, 12:00:01, 12:07:46 and 12:10:24 holding 2.29–3.04 GiB |

Neither worker came close to its own budget. The per-worker limit is enforced and measured; the
**host-level aggregate is neither**, and with no swap the kernel's only move is to kill. No evidence
was lost — every nested stage seals and publishes to the identity-keyed compute cache before the next
begins, and the 11:47 retry replayed trials 1–27 of the 32-trial search from cache in under a second.
The cost was ~26 minutes of wall per shard, twice.

**Options.**

1. *Record the kernel reason in the receipt.* When a child's return code is `-9`/`137`, read
   `/proc/pressure/memory` and the ring buffer and write `killed_by=OOM` with the measured peak
   alongside the existing reason. Why it might work: today a reader cannot tell an OOM from a
   segfault from a manual kill, and all three are "exited 137" or near it — the same class of defect
   as a `.get("quantity", 0.0)` that silently reads zero. Cost: a few lines in `runtime.py`. What
   could go wrong: the ring buffer is not always readable, so the field must be `null` + reason
   rather than a guess, and `runtime.py` is inside `source_identity` — it cannot be touched while a
   run is in flight without invalidating the run.
2. *Add a host-level admission check before dispatch.* At plan time, refuse to start `workers × 4 GiB`
   unless `MemAvailable` plus swap covers it with a registered headroom, and record the reading in
   the allocation. Why it might work: it turns an unregistered assumption into a measured
   precondition, which is what every other budget in this lab already does. Cost: small, but it is a
   new gate that can refuse a run the user wants to start. What could go wrong: `MemAvailable` at
   dispatch does not bound what another tool allocates ten minutes later, so this narrows the window
   rather than closing it.
3. *Lower the per-worker `RLIMIT_AS` to fit the host.* Two workers at 3 GiB fit inside 9.72 GiB with
   room for the editor and the collectors. Why it might work: the observed peak is 1.5 GiB, so 3 GiB
   is still double the measurement. Cost: none in compute. What could go wrong: the 4 GiB figure is
   the **registered** resource budget from LAB-01 (guide §0.3); changing it is a budget revision with
   its own stamp, not an edit — and a worker that legitimately needs 3.5 GiB on a later stage would
   then die inside its own limit, which is a worse failure than dying outside it.

**What would settle it.** Option 1 alone, first: until the receipt says *why* a worker died, every
argument about options 2 and 3 rests on a ring buffer that rotates. Then option 2, with the headroom
registered rather than chosen. Option 3 only if a measured stage peak ever approaches 3 GiB.

**Operationally, and separately from all three:** the proximate cause was two agent tools on one
9.72 GiB host. The lab's own budget did not fail; it was never the binding constraint. That is not a
code change and is not recorded as one.

**Not run.** Nothing above is implemented. `runtime.py`, `workers.py` and
`configs/time_edge_validation_v4/` are all inside the live run's `source_identity`
(`e5807d05…`, verified identical to the working tree at 12:22) and must not change while
`te-host-controls-btc-02` is in flight.

---

## OP-21 — every phase runner's `--pytest-xml` input lives outside `LAB_ROOT`, by an established pattern, not a new defect

**Measured (FP-01, 2026-09-22).** `src/crypto_regime_lab/fp/verifier_fp01.py::verify_fp01` genuinely
re-parses the JUnit XML it is given *(`_check_tests` calls `ET.parse` on the path and cross-checks
node IDs/failures against `test_registry.json` — a real behavioral check, not a token match)*, which
is correct. But the path it was given for FP-01's own PASS run was `/tmp/fp01_junit.xml` — outside
`LAB_ROOT`, unversioned, not run-scoped (the filename has no `lab_run_id` in it), and gone the moment
`/tmp` is cleared. This is not unique to FP-01: `scripts/run_ra01.py` through `run_ra07.py` all take
the identical `--pytest-xml <path>` contract, and grepping their own usage lines shows the same
`/tmp`-rooted convention across all seven — the lab has been doing this since RA-01. Guide §0.2 /
Appendix C ("All writes stay inside `LAB_ROOT`") is inherited by the new FP guide via source I2, so
the convention sits on the wrong side of a hard boundary the lab has otherwise held to strictly.

**Why it matters, and why it is filed as an opinion rather than a blocker.** The gate's own PASS
verdict is genuinely re-derived from that file at verify time, so nothing here is a fabricated
receipt — the risk is reproducibility and boundary discipline, not a false PASS today. And because
the pattern is seven phases deep and none of them flagged it in their own extensive self-review
passes (LAB-06/07's "gate that passed because nothing happened" audits, RA's guard-strength audits),
fixing it now would mean touching already-PASSED, already-owner-reviewed gate receipts across RA-01
through RA-07, which is a much larger blast radius than finishing FP-01 calls for.

**Options.**

1. *Leave the CLI contract as `--pytest-xml <path>` (caller supplies it, caller's choice where),
   but change the convention every runner script's own docstring/example recommends to a path under
   `LAB_ROOT/.cache/pytest_junit/<lab_run_id>.xml`.* Why it might work: zero change to the verifier
   or its behavioral check, just where the next invocation happens to point it; run-scoped, so two
   runs cannot collide or overwrite each other. Cost: a one-line docstring/example edit per script
   (8 files). Risk: none — it changes a convention, not a contract; old runs' receipts are untouched.
2. *Have each runner copy the supplied JUnit XML into its own evidence dir before handing the path
   to the verifier* (e.g. `evidence/<study>/<run_id>/pytest_junit.xml`), so the append-only evidence
   tree is self-contained and a future re-verify does not depend on `/tmp` surviving. Why it might
   work: makes `FP02-G-...`-style "re-verify from committed artifacts only" claims literally true
   for the test evidence, not just the JSON summaries. Cost: ~10 lines per runner (copy + path
   rewrite in the receipt); touches 8 already-PASSED scripts. Risk: a receipt that recorded the old
   `/tmp` path stays correct for what it *measured*, but would read stale once the convention moves —
   needs `verified_reuse_of`/`recomputed_from` framing per §24.4, not a silent overwrite.
3. *Do nothing now; note it once, here.* Correct for today's actual risk (the check is real, only
   reproducibility is at stake), and keeps FP-01's scope to what the guide actually asked this phase
   to fix (§13, FP01.2's nine named findings — this was not one of them).

**What would settle it.** Whether option 1 or 2 is worth doing depends on whether a FUTURE phase
(FP-02's `FP02-G-CACHE`/`FP02-G-RESUME`, or FP-10's frozen replay) ever needs to re-verify a PASSED
FP gate from committed artifacts alone, with no live `/tmp` state — at that point this stops being
cosmetic. Until then, option 3.

**Not run.** No runner script, verifier, or evidence path was changed for this entry.
