"""Guide section 3 findings and the versioned semantic deltas they imply.

Every finding carries the raw source lines it was read from and the reproducer
that demonstrates it. Every change the lab makes to an alpha is a semantic delta
with an explicit ``change_kind`` (guide 5.1), so a later performance difference
can be attributed to a repair rather than silently credited to regime work.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

ChangeKind = Literal["packaging_fix", "execution_repair", "indicator_repair", "thesis_change"]
ALL_ARMS = ["A", "B", "C", "D", "E"]


@dataclass(frozen=True)
class Finding:
    id: str
    alpha_id: str
    source_lines: str
    observation: str
    handling: str
    reproducer: str


@dataclass(frozen=True)
class SemanticDelta:
    delta_id: str
    alpha_id: str
    adapter_version: str
    change_kind: ChangeKind
    before_semantics: str
    after_semantics: str
    source_line_refs: str
    reproducer: str
    expected_effect: str
    applies_to_experiment_arms: list[str] = field(default_factory=lambda: list(ALL_ARMS))
    finding_refs: list[str] = field(default_factory=list)

    def as_record(self) -> dict:
        return asdict(self)


FINDINGS: tuple[Finding, ...] = (
    # ---------------- A-HASH (guide 3.1) ----------------
    Finding("AH-01", "A-HASH", "L1, L8, L131-133",
            "uses np.* throughout but only imports njit from numba; the module cannot be imported",
            "add the import in the lab copy only; the original digest is untouched",
            "static: undefined global np@L8; dynamic: NameError on import"),
    Finding("AH-02", "A-HASH", "L21-29",
            "the variable called ATR is max(close_diff, |close_diff|) = |close-to-close move|; it never "
            "reads high/low, and atr[14] = mean(tr[1:15]) is unguarded for short input",
            "legacy keeps close_move_rma14; a true-range ATR is a separate versioned variant",
            "constant closes with a wide high/low range yield 0.0; a 10-row input raises IndexError"),
    Finding("AH-03", "A-HASH", "L64-94, L112",
            "equity accumulates realized PnL and fees only; an open position is never marked to market",
            "never used as the equity curve or an objective; the engine ledger is authoritative",
            "10 units entered at 100 with last close 110 reports equity 10000 while wallet+UPnL is 10100"),
    Finding("AH-04", "A-HASH", "L72-94",
            "the if/elif chain handles at most one TP stage per bar, and the final TP branch is only "
            "reachable once tp1_done and tp2_done are both True",
            "the canonical ladder is explicit and ordered; the stage-lock chain is a labelled legacy reproduction",
            "a bar spanning TP1, TP2 and the final TP fills only TP1: units 10 -> 5"),
    Finding("AH-05", "A-HASH", "L104, L108-125",
            "entry is booked at the same close that produced the signal; no open, latency or gap model",
            "close decision, next-open fill; SL/TP levels derive from the actual fill price",
            "the fill price equals close[t] regardless of the next bar's open"),
    Finding("AH-06", "A-HASH", "L79-89",
            "TP2 quantity is a percentage of the REMAINING units, not of the entry quantity",
            "locked as fraction_of_remaining; never silently re-based to the original quantity",
            "tp1 55% then tp2 65% of the remainder leaves 0.1575 of the entry, not 0.30 (units 10 -> 1.575)"),
    Finding("AH-07", "A-HASH", "L157-162",
            "4 of the 6 supplied presets violate tp1 < tp2 < final",
            "rejected for the canonical simultaneous ladder; the raw order is kept, never silently sorted",
            "huhu 2.4/2.1/3.2, bubu 2.9/3.8/1.1, haft 2.1/1.4/3.1, kuku 1.3/3.7/2.7"),
    # ---------------- A-VWAP (guide 3.2) ----------------
    Finding("AV-01", "A-VWAP", "L8-17, L43-53, L67-77, L193",
            "n_sma/n_rsi/n_atr index past the end for inputs shorter than their window and "
            "n_stdev silently returns zeros; new_day[0] is forced True",
            "fail fast, or return a valid no-signal warmup; never crash and never emit a silent zero",
            "a 10-row frame with SMA(50) raises IndexError"),
    Finding("AV-02", "A-VWAP", "L98-103, L176-178",
            "open_p is passed into the core but never read; the only output is a position state array",
            "the position array is an intent, not a fill; SL/TP correctness cannot be claimed from it",
            "replacing the entire open series after entry leaves pos unchanged"),
    Finding("AV-03", "A-VWAP", "L125-151",
            "the time stop is evaluated before the price stop and the take profit, although the time "
            "condition is a boundary event rather than an intrabar price event",
            "a frozen event sequence: resting protection at price phases, time stop submitted at the "
            "close or the next phase",
            "a bar that hits the stop AND satisfies the time stop exits as a time stop"),
    Finding("AV-04", "A-VWAP", "L134, L146",
            "the dynamic VWAP exit compares the same bar's high/low against that bar's completed VWAP",
            "either a resting order at the previously observed VWAP, or a close decision with a "
            "next-open market exit; a full-bar VWAP is never treated as known at the open",
            "the VWAP used at bar t depends on bar t's own volume"),
    Finding("AV-05", "A-VWAP", "L159-174",
            "entry is assumed at the close and the stop/target are derived from that assumed price",
            "next-open entry, levels from the actual fill and the ATR available at the decision",
            "a gap between close[t] and open[t+1] moves every level"),
    Finding("AV-06", "A-VWAP", "L200-217",
            "the HTF EMA is resampled, shifted by one and merged backward; availability then depends "
            "on the resample label convention and a trailing ffill",
            "closed-HTF prefix fixtures and an available_at join, not a label timestamp join",
            "a right-labelled resample makes the shift(1) correct; a left-labelled one does not"),
    Finding("AV-07", "A-VWAP", "L231-249",
            "the module-level default merges the tete preset, annotated 5m VN30F1M, with base",
            "never run the default; only an explicit config for the five crypto symbols",
            "params == {**tete, **base} at import time"),
    # ---------------- A-HMA (guide 3.3) ----------------
    Finding("HM-01", "A-HMA", "L283",
            "a comment asserts the next open equals the current close; the core never receives open",
            "the actual fill comes from the engine; no equality assumption",
            "the core signature has no open argument"),
    Finding("HM-02", "A-HMA", "L204, L214-249",
            "pos_weight[t] is the position carried INTO bar t, while exit_type/exit_price for the same "
            "index are intrabar events of bar t",
            "a pre-bar weight and a post-close target are separate fields; never summed or lagged twice",
            "an exit at bar t leaves pos_weight[t] == 1 with exit_type[t] == 1"),
    Finding("HM-03", "A-HMA", "L214-246, L284-291",
            "stop and target prices are closed inside the alpha with no gap, slippage or fill model",
            "levels are intents; the fill price is the engine's decision",
            "exit_price is set to buySL exactly, whatever the bar's open was"),
    Finding("HM-04", "A-HMA", "L332-349",
            "4 of the 13 presets have min_length > max_length",
            "raw references retained; the canonical adapter rejects them and never silently swaps",
            "hfhf 292>232, hjhj 320>204, hoho 248>200, hbhb 308>280"),
    Finding("HM-05", "A-HMA", "L136, L139, L317-320, L332-349",
            "time_ms, volume and double_up are accepted but never read, and sl_mult appears in all 13 "
            "presets while the code never reads it",
            "dropped from the active search space and flagged deprecated; never re-implemented under "
            "the old name",
            "AST: no Load of time_ms/volume/double_up; sl_mult is absent from the parameter schema"),
    Finding("HM-06", "A-HMA", "L161-162",
            "mintick is hardcoded to 0.0001 for every instrument, and the pip buffer is 10x that",
            "use instrument tick metadata; the pip-buffer semantics are versioned",
            "a 5-pip buffer is 0.005 absolute regardless of the symbol's real tick size"),
    Finding("HM-07", "A-HMA", "L45-57",
            "the RSI seed returns 50 when avg_gain and avg_loss are both zero, but every later bar "
            "returns 100 whenever avg_loss is zero, even with avg_gain zero",
            "canonical keeps flat=50 at the seed; making the recursion consistent is an indicator "
            "repair applied before any A/B",
            "a flat series seeds 50 then reports 100 on the next bar"),
    Finding("HM-08", "A-HMA", "L7-129",
            "every kernel is njit(fastmath=True) and the dynamic helpers clamp negative indices to 0, "
            "padding the start of the series with repeated values",
            "the reference oracle runs fastmath=False; warmup convergence is explicit",
            "_xhma_at_t at t=0 averages src[0] repeated"),
    Finding("HM-09", "A-HMA", "L304",
            "the epoch conversion divides by 10**6, assuming nanosecond index values",
            "convert timezone and unit explicitly; time_ms is unused so no timestamp correctness is claimed",
            "a second-resolution index would be scaled wrongly"),
    # ---------------- A-SC (guide 3.4) ----------------
    Finding("SC-01", "A-SC", "L39-48",
            "the indicator is chosen by 'novolumedata or volume missing' but the method is dispatched "
            "on novolumedata alone, so a missing volume column calls money_flow_index on an RSIIndicator",
            "resolve use_rsi once; the main crypto path requires volume and the fallback is explicit",
            "a frame with no volume column and novolumedata=False raises AttributeError"),
    Finding("SC-02", "A-SC", "L20",
            "coeff is cast with int(), so fractional search values collapse onto integers",
            "search coeff as an integer; never advertise fractional trials as distinct",
            "coeff 4.0 and 4.9 both become 4"),
    Finding("SC-03", "A-SC", "L66-69",
            "the cross test compares trend[t] against trend[t-2] and trend[t-1] against trend[t-2], "
            "which is not the conventional crossover(trend, trend.shift(2))",
            "the source convention is kept in canonical_v1; a standard crossover is an optional "
            "research revision, never a silent fix",
            "a conventional crossover compares trend[t-1] against trend[t-3]"),
    Finding("SC-04", "A-SC", "L104-110, L124-140",
            "approved (shifted) signals are computed but execution consumes the unapproved ones",
            "declare the decision timestamp and the intent timing once; never double-shift",
            "buy_signal_approved is never referenced after being assigned"),
    Finding("SC-05", "A-SC", "L119-145",
            "position takes only 0 or 2; the short branch sets 0, so the strategy is long-flat",
            "canonical stays long-flat; shorting is never enabled to improve a result",
            "the observed position path is [0, 2, 0, 0, 2] with no negative value"),
    Finding("SC-07", "A-SC", "L26, L53-57, L66-69",
            "trend is seeded at 0.0, so the FIRST bar whose condition is true ratchets it from 0 up "
            "to a real price level; that jump always satisfies (trend > trend[-2]) and "
            "(trend[-1] <= trend[-2]), manufacturing a buy_signal that carries no information",
            "warmup is not ready until the trend has been initialised and the 2-bar comparison "
            "window is clear of the seed; found by the lab, not listed in the guide",
            "on any series the first condition-true bar emits buy_signal=True regardless of price action"),
    Finding("SC-06", "A-SC", "L37-60, L79-102",
            "average_true_range() and the condition indicator are recomputed inside the loop, and the "
            "bars-since counters are rebuilt row by row",
            "may be vectorised in the lab AFTER output parity; the reset rules do not change",
            "the indicator is recomputed on every one of n iterations"),
)


SEMANTIC_DELTAS: tuple[SemanticDelta, ...] = (
    # ---- A-HASH ----
    SemanticDelta(
        "SD-HASH-01", "A-HASH", "canonical_v1", "packaging_fix",
        "module references np without importing numpy and cannot be imported",
        "the lab adapter imports numpy explicitly; the original bytes are untouched",
        "L1, L8, L131-133", "importing the raw module raises NameError: np",
        "none on decisions; the alpha simply becomes runnable", finding_refs=["AH-01"]),
    SemanticDelta(
        "SD-HASH-02", "A-HASH", "canonical_v1", "execution_repair",
        "entry booked at the signal close, protective levels derived from it",
        "close decision then next-open fill; levels derived from the actual fill price",
        "L104-125", "fixtures/gap_entry", "shifts every entry by one bar and re-prices SL/TP",
        finding_refs=["AH-05"]),
    SemanticDelta(
        "SD-HASH-03", "A-HASH", "canonical_v1", "execution_repair",
        "an if/elif chain fills at most one TP stage per bar and gates the final TP on both partials",
        "an explicit ordered ladder evaluates every level a bar actually crossed, in price order",
        "L72-94", "fixtures/all_tp_same_bar", "more complete exits on wide bars; the legacy stage-lock "
        "path is retained as legacy_reproduction", finding_refs=["AH-04"]),
    SemanticDelta(
        "SD-HASH-04", "A-HASH", "canonical_v1", "execution_repair",
        "realized-only equity inside the alpha, used as if it were the account",
        "the engine ledger owns equity; the legacy column is kept as a labelled diagnostic",
        "L48-94", "probes/HASH_EQUITY_NO_MTM", "removes a mark-to-market blind spot from any objective",
        finding_refs=["AH-03"]),
    SemanticDelta(
        "SD-HASH-05", "A-HASH", "research_revision_1", "indicator_repair",
        "the ATR variable is the absolute close-to-close move and ignores high/low",
        "a true-range ATR variant, offered as a SEPARATE version",
        "L21-29", "probes/HASH_ATR_CLOSE_ONLY",
        "changes the entry threshold scale; must never be mixed into canonical results",
        applies_to_experiment_arms=[], finding_refs=["AH-02"]),
    SemanticDelta(
        "SD-HASH-06", "A-HASH", "canonical_v1", "packaging_fix",
        "account configuration (initial_capital, trading_fee, usd_per_trade) lives inside the alpha",
        "account configuration moves to the experiment-level economic contract, identical for all arms",
        "L42-46, L139-149", "configs/study_registration.json execution.account_contract",
        "removes a per-alpha sizing degree of freedom from the search space", finding_refs=["AH-03"]),
    # ---- A-VWAP ----
    SemanticDelta(
        "SD-VWAP-01", "A-VWAP", "canonical_v1", "packaging_fix",
        "helpers index past the end of short inputs",
        "explicit warmup readiness: too-short input yields a valid no-signal state, never a crash "
        "and never a silent zero",
        "L8-17, L43-53, L67-77", "probes/VWAP_SHORT_INPUT", "no decision change after warmup",
        finding_refs=["AV-01"]),
    SemanticDelta(
        "SD-VWAP-02", "A-VWAP", "canonical_v1", "execution_repair",
        "entry at the signal close with levels from that price",
        "close decision, next-open fill, levels from the actual fill",
        "L159-174", "fixtures/gap_entry", "shifts entries by one bar", finding_refs=["AV-05", "AV-02"]),
    SemanticDelta(
        "SD-VWAP-03", "A-VWAP", "canonical_v1", "execution_repair",
        "the time stop is tested before the price stop and the take profit",
        "a frozen priority: stop, then take profit, then the time stop as a close decision",
        "L125-151", "fixtures/time_stop_vs_sl_same_bar",
        "changes which exit wins on a bar where both trigger; applied identically to every arm",
        finding_refs=["AV-03"]),
    SemanticDelta(
        "SD-VWAP-04", "A-VWAP", "canonical_v1", "execution_repair",
        "the dynamic VWAP exit uses the current bar's completed VWAP as an intrabar level",
        "exit_at_vwap is OFF in the canonical pilot; when enabled it is the resting "
        "previous-observed-VWAP variant, registered before any result is seen",
        "L134, L146", "fixtures/dynamic_vwap_not_yet_available",
        "removes a look-ahead exit; registered ahead of performance, not switched off because a "
        "backtest looked bad", finding_refs=["AV-04"]),
    SemanticDelta(
        "SD-VWAP-05", "A-VWAP", "canonical_v1", "execution_repair",
        "the HTF EMA is joined on the resample label with a trailing ffill",
        "the join is on available_at from a closed HTF bucket, with warmup convergence from the EMA "
        "span rather than a hardcoded 200 bars",
        "L200-217, L118", "fixtures/htf_closed_bucket_only",
        "removes any dependence on the resample label convention", finding_refs=["AV-06"]),
    SemanticDelta(
        "SD-VWAP-06", "A-VWAP", "canonical_v1", "packaging_fix",
        "the module default merges the VN30F1M-annotated tete preset",
        "no default is ever executed; a configuration must be supplied explicitly",
        "L231-249", "catalog/unmapped_presets.json", "prevents an accidental VN-tuned run",
        finding_refs=["AV-07"]),
    # ---- A-HMA ----
    SemanticDelta(
        "SD-HMA-01", "A-HMA", "canonical_v1", "execution_repair",
        "the comment treats the next open as equal to the current close",
        "the engine supplies the actual fill; entry-dependent levels are re-derived from it",
        "L283", "fixtures/gap_entry", "levels move whenever the next open gaps",
        finding_refs=["HM-01", "HM-03"]),
    SemanticDelta(
        "SD-HMA-02", "A-HMA", "canonical_v1", "execution_repair",
        "a single pos_weight array mixes the pre-bar position with intrabar exit events",
        "separate fields: position_entering_bar and target_after_close, plus a typed exit event",
        "L204, L214-249", "fixtures/weight_vs_target_no_double_count",
        "removes a lag/double-count ambiguity", finding_refs=["HM-02"]),
    SemanticDelta(
        "SD-HMA-03", "A-HMA", "canonical_v1", "indicator_repair",
        "the RSI recursion returns 100 whenever avg_loss is zero, even when avg_gain is also zero, "
        "while the seed returns 50 in that case",
        "the flat case stays 50 throughout the recursion, consistent with the seed",
        "L45-57", "probes/HMA_RSI_FLAT",
        "affects only flat segments; applied before any A/B and to every arm identically",
        finding_refs=["HM-07"]),
    SemanticDelta(
        "SD-HMA-04", "A-HMA", "canonical_v1", "packaging_fix",
        "mintick is hardcoded to 0.0001 for every instrument",
        "the instrument's real tick size is used; the pip buffer keeps the 10x semantics, versioned",
        "L161-162", "fixtures/instrument_tick", "changes the 48-bar high/low buffer per symbol",
        finding_refs=["HM-06"]),
    SemanticDelta(
        "SD-HMA-05", "A-HMA", "canonical_v1", "packaging_fix",
        "min_length > max_length is accepted silently in 4 presets",
        "the adapter rejects an infeasible configuration instead of swapping the bounds",
        "L332-349", "catalog/preset_catalog.json feasibility flags",
        "those four presets are not runnable as canonical configurations", finding_refs=["HM-04"]),
    SemanticDelta(
        "SD-HMA-06", "A-HMA", "canonical_v1", "packaging_fix",
        "time_ms, volume, double_up and sl_mult are carried but never read",
        "they are dropped from the active search space and recorded as deprecated/ignored",
        "L136, L139, L332-349", "catalog unused_knobs",
        "shrinks the search space without changing any decision", finding_refs=["HM-05", "HM-09"]),
    SemanticDelta(
        "SD-HMA-07", "A-HMA", "canonical_v1", "indicator_repair",
        "every kernel runs njit(fastmath=True)",
        "the reference oracle runs fastmath=False; a fastmath kernel is only accepted when it "
        "reproduces the oracle's decisions within the declared tolerance",
        "L7-129", "reference/parity", "no decision change is permitted; a difference blocks the kernel",
        finding_refs=["HM-08"]),
    # ---- A-SC ----
    SemanticDelta(
        "SD-SC-01", "A-SC", "canonical_v1", "packaging_fix",
        "the indicator choice and the method dispatch disagree when volume is absent",
        "use_rsi is resolved once and both the construction and the call follow it; the crypto "
        "primary path requires volume and a missing column is an explicit rejection",
        "L39-48", "probes/SC_FALLBACK", "removes an AttributeError path; no decision change when "
        "volume is present", finding_refs=["SC-01"]),
    SemanticDelta(
        "SD-SC-02", "A-SC", "canonical_v1", "execution_repair",
        "execution consumes the unapproved signals while the approved ones are computed and dropped",
        "one declared decision timestamp with a next-open fill; no second shift is applied",
        "L104-110, L124-140", "fixtures/no_double_shift", "fixes the intent timing without changing "
        "the signal definition", finding_refs=["SC-04"]),
    SemanticDelta(
        "SD-SC-03", "A-SC", "canonical_v1", "packaging_fix",
        "position amplitude is 2 with no account contract attached",
        "direction is normalised to 0/1 against the fixed experiment notional as sizing_mapping_v1; "
        "the legacy amplitude path is a separate labelled reproduction",
        "L133-143", "fixtures/sizing_mapping_v1", "2 is never interpreted as 2x leverage",
        finding_refs=["SC-05"]),
    SemanticDelta(
        "SD-SC-04", "A-SC", "canonical_v1", "packaging_fix",
        "the internal MFI/RSI threshold is named regime_threshold",
        "it is namespaced alpha.condition_threshold; external market state uses a different namespace",
        "L13, L24, L48", "catalog parameter schema",
        "prevents an internal indicator threshold being read as a regime-model output",
        finding_refs=["SC-01"]),
    SemanticDelta(
        "SD-SC-06", "A-SC", "canonical_v1", "execution_repair",
        "the zero-seeded trend emits a spurious buy_signal on the first condition-true bar",
        "warmup_ready stays False until 3 bars after the trend leaves its seed, so the seed jump and "
        "its comparison window can never produce a decision",
        "L26, L53-57, L66-69", "fixtures/sc_seed_jump_not_tradable",
        "removes one manufactured entry per series; identical treatment for every arm",
        finding_refs=["SC-07"]),
    SemanticDelta(
        "SD-SC-05", "A-SC", "legacy_reproduction", "thesis_change",
        "the cross formula compares trend[t] vs trend[t-2] and trend[t-1] vs trend[t-2]",
        "a conventional crossover(trend, trend.shift(2)) is available as a research revision only",
        "L66-69", "fixtures/crossover_convention",
        "changes the signal definition, so it is never mixed into canonical results",
        applies_to_experiment_arms=[], finding_refs=["SC-03"]),
)


def findings_for(alpha_id: str) -> list[Finding]:
    return [f for f in FINDINGS if f.alpha_id == alpha_id]


def deltas_for(alpha_id: str) -> list[SemanticDelta]:
    return [d for d in SEMANTIC_DELTAS if d.alpha_id == alpha_id]


def findings_index() -> dict[str, Finding]:
    return {f.id: f for f in FINDINGS}
