"""Shared glossary for every phase report (CLAUDE.md rule 10).

A term used without its meaning AND without the place in the lab it refers to is
not a report. Keeping the definitions here rather than inside one report script
means LAB-05 onward reuse the same wording instead of re-inventing it, and a term
whose meaning drifts between phases becomes visible immediately.

Each entry is ``(term, meaning, where it applies)``.
"""

from __future__ import annotations

Entry = tuple[str, str, str]

SAFETY: list[Entry] = [
    ("OS-level isolation",
     "running work inside a kernel namespace with the filesystem mounted read-only and the "
     "network removed, so a write or a fetch FAILS rather than being merely discouraged",
     "LAB-01 — bubblewrap; a path check alone is explicitly NOT a sandbox (guide App. C)"),
    ("EROFS / ENETUNREACH",
     "the OS error numbers for 'read-only filesystem' (30) and 'network unreachable' (101); the "
     "lab measures these rather than asserting containment",
     "LAB-01 — the preflight probe records them as evidence"),
    ("attempt ledger",
     "an append-only record of every operation tried, including the ones that failed, so a "
     "failure cannot vanish from the history",
     "LAB-01 — `evidence/.../attempts.jsonl`"),
]

ALPHAS: list[Entry] = [
    ("version tier",
     "which of the four states an alpha is in: raw_supplied (original bytes), "
     "legacy_reproduction (diagnostic only), canonical_v1 (the only tier allowed to prove edge), "
     "research_revision_N (deliberate thesis change)",
     "LAB-02 — all four are built for each of the four alphas"),
    ("semantic delta",
     "a recorded difference between two tiers, classified as packaging_fix, execution_repair, "
     "indicator_repair or thesis_change, with source lines and a reproducer",
     "LAB-02 — `configs/semantic_delta.json`; e.g. SD-HASH-01 is the missing numpy import"),
    ("certification",
     "whether an alpha's economics can actually be expressed on an available engine route; it is "
     "NOT about profitability",
     "LAB-02 — A-HASH is NOT_READY because no single route gives next-open entry + protective "
     "stop + partial reduce-only ladder together"),
    ("intent tape",
     "the array form the engine consumes: entry side/size, stop, take-profit and technical exit "
     "per bar. The adapter proposes; the engine decides",
     "LAB-02 — `quantbt_bridge/intent_tape.py`, contract `intrabar_bracket_v1`"),
    ("numba parity",
     "checking a compiled kernel against the interpreted reference bit for bit before it is "
     "allowed to ship",
     "LAB-02/04 — an accelerated kernel is admitted only while `exact` is true"),
]

DATA: list[Entry] = [
    ("read-lock",
     "re-hashing the source files a snapshot was copied from, to detect that upstream changed "
     "under a run",
     "LAB-03 — three drift classes; only a CLOSED partition of an immutable product invalidates"),
    ("open trailing partition",
     "the current period's file, which the collector is still appending to; it is expected to "
     "change and is excluded from a primary read",
     "LAB-03 — 7 partitions at last check"),
    ("rolling-window product",
     "a product that prunes and rewrites its own history by design, so it can never be part of "
     "an immutable snapshot",
     "LAB-03 — the order book keeps a 30-day window"),
    ("available_at",
     "the earliest wall-clock time a value could have been known, = bar_close + publication "
     "delay; used instead of the bar label to prevent look-ahead",
     "LAB-03 — bar_close is DERIVED as time + interval because `close_time` is unusable"),
    ("cohort",
     "the subset of symbols a feature group can actually cover, given what the collector stored",
     "LAB-03 — G3 (open interest/ratios) covers BTC+ETH only; the primary core is the 8 features "
     "covering all five symbols"),
]

SELECTOR: list[Entry] = [
    ("anchor",
     "a parameter point chosen to be the CENTRE of a local panel, so probes get placed around it",
     "LAB-04 — 4 anchor slots per cutoff: 2 from the TPE ranking, 1 space-filling, 1 incumbent"),
    ("probe",
     "a parameter point placed near an anchor to measure how the result changes when the "
     "parameters move slightly; it is evaluated even when it loses money",
     "LAB-04 — 8 probes per anchor, inside a frozen radius of 0.12 schema-distance"),
    ("space-filling",
     "placing an anchor FAR from the ones already chosen, so the local panels do not all sit "
     "inside the region the sampler already favours",
     "LAB-04 — the 3rd of the 4 anchor slots; the evaluated point with the largest minimum "
     "distance to the TPE anchors (guide 7.2 step 1)"),
    ("TPE",
     "Tree-structured Parzen Estimator, the Optuna sampler that concentrates its trials where "
     "past trials scored well",
     "LAB-04 — the 64 discovery evaluations per cutoff; its top 2 points become anchors"),
    ("local panel",
     "the set {anchor + its probes} scored over the same inner episodes; it is the evidence that "
     "a parameter region is stable rather than a lucky point",
     "LAB-04 — arm B may only choose a candidate that HAS one"),
    ("inner episode",
     "a contiguous equal-length block of the training window; the score is computed per episode "
     "so a single lucky stretch cannot carry a candidate",
     "LAB-04 — 6 episodes of 30 days inside each 180-day training window"),
    ("G",
     "the 0.25 quantile of a candidate's utility across its inner episodes — its LOWER-TAIL "
     "quality, not its average",
     "LAB-04 — the economic-quality gate is G > 0"),
    ("F",
     "how much better the candidate is than its neighbours (median over episodes of the 0.75 "
     "quantile of regret); a HIGH F means the candidate is a lonely spike",
     "LAB-04 — subtracted from G, so a spike is penalised"),
    ("R",
     "the robust score, R = G − λ_F·F: lower-tail quality minus the penalty for being a spike",
     "LAB-04 — arm B selects argmax R among admissible candidates"),
    ("P_survive",
     "the share of (candidate, episode) pairs in the local panel that pass the quality and risk "
     "gates",
     "LAB-04 — registered threshold 0.60"),
    ("medoid",
     "the member of a set with the smallest total distance to the others — an actual evaluated "
     "point, unlike a centroid",
     "LAB-04 — reported as the representative; a centroid is only a proposal until it is run"),
    ("incumbent",
     "the parameter set currently deployed, carried into the next cutoff as a candidate",
     "LAB-04 — it is an anchor with the same probe budget as any challenger"),
    ("cutoff",
     "the boundary between a fold's training window and its test window; selection happens here "
     "and is frozen before the test window is touched",
     "LAB-04 — 6 cutoffs per cell, 90 across the matrix"),
    ("cell",
     "one alpha on one symbol, evaluated across the whole calendar",
     "LAB-04 — 4 alphas × 5 symbols = 20 cells"),
    ("arm A / arm B",
     "arm A selects with the installed engine's rule (argmax in-sample objective); arm B selects "
     "with the lab's robust-neighborhood rule (argmax R). Same calendar, same pool, same budget",
     "LAB-04 — the only registered difference between them is the selection rule"),
    ("retained the incumbent",
     "the selector returned nothing admissible, so the previous parameters stayed deployed. It is "
     "a valid technical pass, not a failure — but it is also not evidence about the selector",
     "LAB-04 — arm B did this at half of all cutoffs"),
]

CLAIMS: list[Entry] = [
    ("conclusion level",
     "a label from a vocabulary registered BEFORE any result, so a finding cannot be described "
     "with a word invented to fit it",
     "LAB-04 — INCONCLUSIVE_SAMPLE / DESCRIPTIVE_VALUE / NET_PARAMETER_SELECTION_EDGE / "
     "FAILED_VALIDITY and three others"),
    ("minimum economic effect",
     "the smallest daily net-return difference the lab agreed in advance to call meaningful; "
     "anything smaller sits inside the cost-stress band",
     "LAB-04 — 6.4e-05/day (0.64 bps/day), derived from cost uncertainty × turnover"),
    ("sign reversal",
     "the pooled result points one way while a subgroup points the other; averaging it away would "
     "be a false claim",
     "LAB-04 — the pooled winner is B, but A-VWAP reverses"),
    ("declared post-hoc",
     "a diagnostic decided AFTER seeing results, marked as such so it can never be mistaken for a "
     "pre-registered test and can never change a conclusion",
     "LAB-04 — the gate-bindingness grid"),
    ("NOT_READY",
     "an alpha that cannot be certified keeps all its cells with NULL metrics; booking it as "
     "PnL = 0 would bias every aggregate",
     "LAB-02/04 — A-HASH, 5 cells"),
]

REGIME: list[Entry] = [
    ("jump model (JM)",
     "a clustering of standardized features into K states, plus a penalty for every switch, so "
     "the fitted state path is persistent instead of flickering bar to bar",
     "LAB-05 — the primary state model M1 (guide 8.2)"),
    ("lambda_J / jump penalty",
     "what one state switch costs the FIT, in standardized-loss units at the sampling frequency. "
     "It is not the policy's real switching cost and cannot be carried to another frequency",
     "LAB-05 — 1.0 at a 4h observation interval"),
    ("Q_t(k)",
     "the cost of the best history that ENDS in state k at time t. It is a per-endpoint minimum, "
     "not a running total of the labels already emitted",
     "LAB-05 — the forward recurrence of guide 8.4"),
    ("forward filter / causal emission",
     "emit argmin_k Q_t(k) at time t using observations up to t only, and never revise it",
     "LAB-05 — the only labels a decision may use"),
    ("offline best path (Viterbi)",
     "walking back from the terminal argmin, which REWRITES earlier labels using data that did "
     "not exist when they were emitted",
     "LAB-05 — computed as a diagnostic and carries decision_eligible=false (guide 8.4)"),
    ("state namespace",
     "a label space belonging to ONE fit. State 2 of one fit and state 2 of the next are "
     "unrelated integers until a mapping says otherwise",
     "LAB-05 — one namespace per 28-day refit"),
    ("namespace mapping",
     "matching a new fit's states onto the previous fit's, using TRAINING centroids only. A state "
     "that cannot be matched is UNMAPPED_REFIT_STATE — a model event, not a market event",
     "LAB-05 — guide 8.4; it never triggers a parameter search"),
    ("membership score",
     "softmax(-cost) over the state costs. It sums to one, which is exactly why it must not be "
     "called a probability: nothing here calibrates it against outcomes",
     "LAB-05 — carries membership_is_calibrated=false (guide 8.5, T42)"),
    ("second-best gap",
     "how far the emitted state is from the runner-up. A small gap means the emission was nearly "
     "a coin flip",
     "LAB-05 — the ambiguity measure, reported instead of a fake confidence"),
    ("novelty / out-of-support",
     "the observation sits further from every centroid than the training residuals ever did. The "
     "inputs are PRESENT — that is what separates it from missing data",
     "LAB-05 — UNKNOWN_STATE at the 0.99 training-residual quantile (T44)"),
    ("degeneracy",
     "the model cannot discriminate: weights collapsed to zero, centroids coincide, or a state "
     "has no members. The response is UNKNOWN_STATE, never state 0 with a 1/K score",
     "LAB-05 — guide 8.3/8.5, T40"),
    ("no-regime world",
     "a synthetic negative control drawn from ONE distribution throughout. Any persistent state "
     "structure reported on it was manufactured by the model",
     "LAB-05 — L05.7; the count of emitted switches on it is the false-structure rate"),
    ("detection delay",
     "observations between a true latent switch and the first emitted state change after it, "
     "reported as a distribution because a mean hides an occasional very late detection",
     "LAB-05 — measured on the recurring-state and structural-break worlds"),
]

POLICY: list[Entry] = [
    ("episode",
     "one (decision at T, candidate, outcome over the following horizon) row. It is the unit the "
     "response estimator learns from",
     "LAB-06 — 7-day non-overlapping windows, the registered pilot horizon"),
    ("outcome_available_at",
     "when an episode's outcome could actually be KNOWN: outcome end plus publication and "
     "processing delay. An outcome is unusable before it",
     "LAB-06 — an unfinished horizon is no outcome at all, not a small one (T45)"),
    ("candidate bank",
     "the set of parameter versions a switch may choose between, assembled only from discoveries "
     "made before the cutoff",
     "LAB-06 — 3-8 entries proposed by guide 7.4; a later discovery is rejected with a reason"),
    ("paired delta",
     "U_e(candidate) - U_e(incumbent) on the SAME episode, so the horizon, the initial state and "
     "the economics cancel instead of having to be matched",
     "LAB-06 — the quantity the estimator averages (T47)"),
    ("similarity weight",
     "how much a past episode counts now: a kernel on context distance, times a recency decay, "
     "times an eligibility flag that is 0 or 1 and never a reward for a good outcome",
     "LAB-06 — guide 9.2"),
    ("N_eff",
     "weight concentration, (sum w)^2 / sum w^2. It says how many episodes the weights spread "
     "over. It is NOT a count of independent observations",
     "LAB-06 — reported next to the contiguous-block count for exactly that reason"),
    ("contiguous block",
     "a run of episodes adjacent in time. Twelve consecutive weeks inside one market stretch are "
     "ONE piece of evidence wearing twelve hats",
     "LAB-06 — at least two blocks are required before a recommendation is made"),
    ("shrinkage",
     "pulling a local estimate toward a pooled one by a_t = N_eff/(N_eff+kappa), so thin evidence "
     "moves the answer less",
     "LAB-06 — a declared heuristic, not a calibrated posterior"),
    ("transition cost",
     "the projected cost of moving from one parameter version to another: turnover x (fees + "
     "slippage) plus residual handling, in the SAME units as the utility",
     "LAB-06 — it DECIDES; the engine charges. Subtracting it from realised PnL too would bill "
     "the same cost twice"),
    ("inaction region",
     "the band between 'clearly worse' and 'clearly better after costs', where the answer is keep "
     "the incumbent",
     "LAB-06 — without it a policy churns on noise and pays the churn in real fees"),
    ("campaign",
     "one entry and everything that follows it until flat or terminal, carrying an IMMUTABLE "
     "entry_parameter_digest",
     "LAB-06 — an open trade stays protected by the parameters it entered with (T50)"),
    ("four clocks",
     "inference (state update), switch (choose among existing candidates), bank refresh (find new "
     "ones), model retrain (refit the state model) — four separate schedules and counters",
     "LAB-06 — merging any two is what produces a recursive trigger storm (T52)"),
    ("coalesce / supersede",
     "two refit triggers close together become ONE job; a later trigger supersedes an earlier "
     "one, and the superseded job's result is discarded even if it finishes",
     "LAB-06 — deterministic, so a slow job can never activate stale work (T49)"),
    ("effective_at >= ready_at",
     "a refit takes effect no earlier than the moment it was ready. There is no backdating",
     "LAB-06 — backdating would let a decision claim knowledge it did not have (T49)"),
    ("indicator warmup",
     "an indicator must have seen enough past-only bars before its signals are acted on; it is "
     "never reset at a switch and never carried across parameter sets without a contract",
     "LAB-06 — resetting fabricates fresh signals from a cold start (T51)"),
    ("counterfactual limit",
     "a difference between the training experiment and the live deployment that no error bar can "
     "represent — for example that episodes start flat and a live switch does not",
     "LAB-06 — four are recorded by name (L06.6)"),
]

#: Terms the "Data provenance" section uses. Every phase that reads the snapshot
#: now states its inputs, so every such phase has to define the words it states
#: them in -- a term explained only in the phase that invented it is not defined
#: for the reader of the phase that uses it.
PROVENANCE: list[Entry] = [
    ("read-lock",
     "re-hashing the source files a snapshot was copied from, to detect that upstream changed "
     "under a run",
     "LAB-03 onward — the snapshot manifest IS the lock; every phase re-verifies it before it "
     "runs"),
    ("open trailing partition",
     "the current period's file, which the collector is still appending to; it is expected to "
     "change and is excluded from a primary read",
     "LAB-03 onward — 9 of 627 files; a primary run reads closed partitions only"),
    ("ingest re-stamp",
     "an upstream file rewritten with a new `ingested_at` on every row while every MEASURED "
     "column stays identical — the digest moves, the numbers do not",
     "LAB-04/05/06 read-lock — 23 closed `binance_futures_metrics_5m` partitions on 2026-09-10, "
     "read and proven unchanged, so no cohort is invalidated"),
    ("content revision",
     "an upstream change that a read cannot prove benign — a changed value, row count or schema, "
     "or a file that will not open. It still invalidates every cohort reading that product",
     "LAB-04/05/06 read-lock — 0 measured; the benign verdict carries the burden of proof, "
     "never the invalidating one"),
    ("primary core",
     "the products and features a primary run actually consumes — the perpetual 1m bars and the "
     "8 features covering all five symbols (G1×3, G2×2, G5×3)",
     "guide 6.2 / LAB-03 — drift in a product outside it can invalidate a cohort but never the "
     "primary run"),
    ("data role",
     "the declared purpose of a date window: `development` permits fitting and design choices, "
     "`outer_evaluation` permits only a frozen-protocol run",
     "development 2020-01-01→2023-12-31; LAB-04/05/06 stay inside it"),
]

INTEGRATION: list[Entry] = [
    ("availability event bus",
     "one ordered stream carrying bar completions, regime observations, refit request/start/ready, "
     "activations and fills, each with observed_at, available_at and a sequence number",
     "LAB-07 L07.2 — ordering is (available_at, causal rank, arrival); millisecond equality is "
     "never an ordering"),
    ("activation delay",
     "the gap between when a switch was REQUESTED and when it actually took effect, caused by an "
     "open campaign or by indicators that are not yet warm",
     "LAB-07 L07.4 — measured on the real account: 64 to 368 bars across the five switches"),
    ("operational segment",
     "the stretch during which one parameter version was effective. Its end is written only when "
     "the NEXT activation exists, so a running segment has no length",
     "LAB-07 L07.5 — 6 segments, the last one open with a null end"),
    ("no-change trigger",
     "a refresh that fired and changed nothing. It is recorded, because dropping it would make "
     "the refresh cadence look like the switch rate",
     "LAB-07 L07.5 — 6,566 of them against 5 activations"),
    ("disabled versus inert hooks",
     "DISABLED means the experimental layer is not consulted; INERT means it is consulted and "
     "declines. Both must give the baseline path, or merely asking has a side effect",
     "LAB-07 L07.1 — three runs compared, not two"),
    ("continuous account",
     "ONE chronological account whose parameter version changes at activation boundaries: one "
     "engine pass, one equity curve, no reset and no splice at a boundary",
     "LAB-07 T56 / guide 10.3 — 105,120 bars, 0 resets"),
    ("training account contract",
     "the reset/flat account a candidate is EVALUATED under, deliberately different from the "
     "deployment account it would be deployed into",
     "LAB-07 L07.3 / guide 10.3 — the refit runner cannot reach the deployment account at all"),
    ("refit latency",
     "how long a refit takes before its result may be activated, taken from a measured benchmark "
     "rather than assumed",
     "LAB-07 L07.3 — 0.387s per fit measured; a latency of zero is refused because it would be a "
     "free option on the bars in between"),
]

FACTORIAL: list[Entry] = [
    ("arm",
     "one complete way of running the study: a selector paired with a refresh schedule, "
     "delivered on its own continuous account",
     "LAB-08 — A/B/C/D are the core factorial; E is an extension, never a substitute for C or D"),
    ("registered contrast",
     "a difference between two arms named BEFORE any of them ran, so the comparison cannot be "
     "chosen after seeing which one won",
     "LAB-08 — B-A, C-A, D-B, D-C and the interaction (D-C)-(B-A)"),
    ("compute-matched",
     "two arms given the same number of searches and the same training memory, so neither can "
     "buy an advantage by being allowed to look more often",
     "LAB-08 — the dynamic arms get the calendar's refresh COUNT; only the timing differs"),
    ("control",
     "a run designed to produce the same headline as the method for a DIFFERENT reason, so that "
     "reason can be ruled out. None is dropped for beating the proposal",
     "LAB-08 / guide 10.2 — seven of them, staged rather than run as a Cartesian product"),
    ("placebo fidelity",
     "whether a fake state tape actually matches the real one's dwell and switch frequency. A "
     "placebo that switches more often loses on costs alone, and beating it proves nothing",
     "LAB-08 — 37 real switches against 34 placebo, a ratio of 0.92"),
    ("comparable interval",
     "the span every cohort in a comparison covers. Scoring each on its own longest window would "
     "credit a feature group for the period it happens to reach",
     "LAB-08 L08.4 — the derivatives and liquidity cohorts cover far less than the core"),
    ("variance resolved out of fold",
     "the share of weighted variance a state assignment removes on data the fit never saw; "
     "scale-free, so it means the same thing for 8 features or 11",
     "LAB-08 — negative for most cohorts, meaning the states resolve nothing held-out"),
    ("Holm adjustment",
     "a step-down correction over a family of comparisons fixed in advance, so testing five "
     "contrasts does not manufacture one significant result",
     "LAB-08 / guide 11.3 — applied to the registered contrast family"),
    ("NO_PROMISING_DESIGN",
     "a valid way for discovery to end. The exit gate does not require profit and forbids "
     "relabelling a negative result as a technical failure to justify a re-run",
     "LAB-08 exit — one of exactly two permitted outcomes"),
]

CONFIRMATION: list[Entry] = [
    ("frozen confirmation",
     "running a protocol that was fixed in advance on an interval the design was not built on, "
     "with nothing adjustable left",
     "LAB-09 — the LAB-08 protocol, unchanged, on 2024-01-01→2026-08-31"),
    ("nested retrospective",
     "an interval that no phase of THIS lab consumed but that still cannot support an "
     "out-of-sample claim, because something it depends on was tuned over the whole sample",
     "L09.1 — the supplied presets were TPE-tuned on the full sample with an unknown cutoff, so "
     "no interval of this dataset is an untouched holdout"),
    ("prospective protocol",
     "a specification for an observation that would begin AFTER the protocol was frozen, so no "
     "tuning could have seen it. Written, deliberately not executed",
     "L09.1 — configs/lab09_confirmation_spec.json prospective_protocol"),
    ("paired daily difference",
     "two arms compared day by day on the days BOTH were live, rather than by their mean returns",
     "L09.3 — the registered primary endpoint; days where either arm was absent are excluded, "
     "never filled with a zero"),
    ("block bootstrap",
     "resampling contiguous RUNS of days instead of single days, so the autocorrelation and the "
     "volatility clustering in the series survive the resample",
     "L09.3 — moving blocks whose length is chosen on development and applied unchanged"),
    ("common shock",
     "a market-wide move that hits every symbol on the same day. Resampling symbols "
     "independently destroys it and shrinks the interval for free",
     "L09.3 / T63 — one date sequence is drawn per bootstrap draw and applied to every cell"),
    ("concentration",
     "the share of a result carried by its few largest days, measured on the ABSOLUTE daily "
     "contribution so that two offsetting days still count as two large days",
     "L09.3 / guide 11.4 — a result carried by a handful of days is a statement about those days"),
    ("Holm step-down",
     "a multiple-comparison adjustment applied to a family of contrasts named before the results, "
     "which raises each p-value by how many comparisons were made",
     "L09.3 — over the five registered contrasts; E-B is excluded as an extension"),
    ("exploratory contrast",
     "a comparison reported outside the registered family and labelled as such, so it cannot "
     "quietly borrow the family's error control",
     "L09.3.7 — E-B, which is arm D's schedule under another name wherever the policy never "
     "switched"),
    ("cost stress",
     "re-running the same deployment with transaction costs multiplied, to see how much of a "
     "result survives a worse fill than the one assumed",
     "L09.4 — the registered 1x / 1.5x / 2x grid, applied to the account and not to the "
     "selection"),
    ("one-way fee",
     "the fee charged on a single trade side. A round-trip fee is two of them",
     "L09.6 — the study registered a one-way rate of 0.0004 and the engine was handed it in a "
     "parameter documented as round-trip, so it charged half"),
    ("AS_DECLARED",
     "the cost level that reproduces the account the study registered, as opposed to the account "
     "it actually ran",
     "L09.4 — fee x2 and slippage x1, because only the fee binding was wrong"),
    ("stale feed",
     "a provider that stops updating and then catches up in one step. The catch-up looks like a "
     "transition to any arm that acts on one",
     "L09.4.4 — six one-week freezes injected into the state tape"),
    ("missing enrichment",
     "observations the provider never delivered, DROPPED rather than filled with a value",
     "L09.4.5 — a fabricated zero would tell the arm something false instead of nothing"),
    ("mislabelled transition",
     "a state change dated at the wrong time while the sequence of states is untouched, which "
     "isolates timing error from labelling error",
     "L09.4.3 — half the transitions moved by one day in either direction"),
    ("label permutation",
     "shuffling the arbitrary integer ids of the states within a fit. A schedule built from "
     "WHERE the state changes must be unaffected",
     "L09.5.3 — the control that must change nothing; a difference would mean a decision reads "
     "the integer"),
    ("novelty threshold",
     "the fit residual beyond which a model declares it has not seen this before, fitted on each "
     "training window",
     "L09.5.1 — UNKNOWN_STATE emissions on the confirmation interval"),
    ("cash identity",
     "equity change equals minus the signed cash paid out minus the fees; it closes only if the "
     "fills, the fees and the equity describe the same account",
     "L09.6.1 — checked on every arm of every cell"),
    ("parameter-version lifecycle",
     "every parameter version an account requested, which of them took effect, and how many bars "
     "each one traded",
     "L09.6.2 — a version requested and never deployed is the warm-up or flat-book gate working"),
    ("search cardinality",
     "how many unique strategy evaluations a cutoff actually spent against the registered ceiling",
     "L09.6.3 — a probe landing on an already-evaluated point is not re-evaluated"),
    ("replay",
     "re-running a committed decision with today's code and comparing the result to what was "
     "recorded",
     "L09.6.5 — the development accounts and the 1.0x level of the confirmation cost panel"),
]


BY_PHASE = {
    "LAB-01": SAFETY + CLAIMS[-1:],
    "LAB-02": ALPHAS + CLAIMS[-1:],
    "LAB-03": DATA,
    "LAB-04": SELECTOR + CLAIMS + PROVENANCE,
    "LAB-05": REGIME + CLAIMS[:1] + CLAIMS[-1:] + PROVENANCE,
    "LAB-06": POLICY + CLAIMS[:1] + PROVENANCE,
    "LAB-07": INTEGRATION + CLAIMS[:1] + PROVENANCE,
    "LAB-08": FACTORIAL + CLAIMS + PROVENANCE,
    # `second-best gap` is defined once, in REGIME, and borrowed here rather than
    # redefined: a term with two definitions is a term that will drift.
    "LAB-09": CONFIRMATION + [e for e in REGIME if e[0] == "second-best gap"]
              + CLAIMS + PROVENANCE[-1:],
}


def render(entries: list[Entry]) -> list[str]:
    """The glossary section as markdown lines."""
    lines = ["## Glossary — what each term means and where it applies", "",
             "| term | meaning | where it applies in this lab |", "|---|---|---|"]
    for term, meaning, where in entries:
        lines.append(f"| **{term}** | {meaning} | {where} |")
    lines.append("")
    return lines
