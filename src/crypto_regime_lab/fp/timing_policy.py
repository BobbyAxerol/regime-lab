"""FP-09 -- transition-cost-aware execution timing (guide section 21).

Mechanistic hypothesis (owner-delegated hypothesis selection, recorded in
evidence/regime_time_edge_ra_v1/owner_decisions.jsonl): regime timing has
already been tested three times in this lab's history as "does regime
information predict WHICH candidate/parameter set is better" -- LAB-08's
STATE_PLACEBO/DELAYED_STATE, RA-07's 90-day placebo and FUP-05's 12-month
placebo all found the apparent edge was a cadence artifact, reproducible on
a market-free synthetic tape. FP-09 tests a DIFFERENT mechanism instead:
does regime information predict WHEN it is cheap (low realized-volatility,
a transition-cost proxy) to EXECUTE a switch that Selector B has ALREADY
decided on -- never which candidate to pick. This reuses LAB-06's own
measured finding that switch cost (7bps) dominated the best candidate edge
(2.58bps) in the old calendar-WFO track: transition cost, not candidate
quality, is the thing regime information might plausibly predict.

The volatility-ratio signal is the SAME mechanism Selector C already
computes causally and had certified (FP-06's ``ctx_volatility_ratio``:
short-window realized vol / long-window realized vol, guide 9.3), reused
here for a genuinely different PURPOSE -- timing an already-decided switch,
not selecting a candidate -- with the SAME window lengths
(``fp.selector_c.VOL_SHORT_DAYS`` / ``VOL_LONG_DAYS``) so the two uses stay
mechanistically comparable rather than inventing a second definition of
"volatility ratio" for this phase.

Three schedules, built in this order (guide 21's own placebo requirement:
"Seed/schedule-generation policy freeze truoc evaluation"):

  1. ``SELECTOR_FIXED_CAL`` -- the base admission schedule unchanged (zero
     deferral); this IS Selector B's own FP-07 schedule, byte-identical.
  2. ``SELECTOR_REGIME_TIMING`` -- each admission event's activation is
     deferred to the FIRST bar (scanning forward, causally, from the
     origin's own admission bar, bounded by ``K_MAX_BARS``) where the
     rolling volatility ratio drops to/below ``VOL_THRESHOLD``. Never
     borrows a future bar's information: ``rolling_volatility_ratio`` uses
     only trailing (causal) windows, and the scan itself only looks
     forward through bars that will already have completed by the time
     the account could act on them.
  3. ``SELECTOR_CAL_MATCHED`` -- each admission event deferred by a bar
     count drawn independently from Uniform(0, k_max_bars) using a FIXED,
     pre-registered seed (guide 21's own explicit "Seed/schedule-
     generation policy freeze truoc evaluation" requirement) -- the SAME
     maximum budget REGIME_TIMING could have used, but chosen with ZERO
     volatility/market information.

     An earlier version of this design instead copied REGIME_TIMING's own
     REALIZED per-event deferral verbatim (``origin_bar + deferred_bars``)
     -- caught, before reporting, to be STRUCTURALLY degenerate: that is
     the exact same formula REGIME_TIMING itself uses to compute its own
     activation bar, so the two schedules were mathematically guaranteed
     to be byte-identical, not an independent control at all (confirmed
     on the real run: SELECTOR_REGIME_TIMING's own run_deployment call
     cache-HIT SELECTOR_CAL_MATCHED's just-published entry, and the
     primary contrast came out EXACTLY 0.0/CI=[0,0] -- the LAB-08
     "Arm E was a copy of Arm D" shape, in code this phase wrote itself).
     The random, seeded design below is mechanically guaranteed to differ
     from REGIME_TIMING's realized schedule except by coincidence, while
     still respecting the SAME frozen k_max_bars bound (guide's FP09-G-
     BUDGET) and using no return/equity information (FP09-G-CALIBRATION).
"""
from __future__ import annotations

VOL_THRESHOLD = 1.0   # recent (short-window) vol at or below the long-window norm
K_MAX_BARS = 30 * 1440   # 30 days of 1-minute bars, matching selector_c.VOL_SHORT_DAYS's own
                        # lookback -- a principled, already-precedented bound, never fit to this
                        # data or to REGIME_TIMING's own realized outcome
CAL_MATCHED_SEED = 20260924   # frozen before any account ran; today's date at design time, never
                              # tuned to REGIME_TIMING's own realized outcome (guide 21's own
                              # "Seed/schedule-generation policy freeze truoc evaluation")
BARS_PER_DAY = 1440


class TimingPolicyError(ValueError):
    """A timing-policy construction step was internally inconsistent."""


def rolling_volatility_ratio(frame, *, short_days: int, long_days: int):
    """Causal (trailing-window) short/long realized-vol ratio at EVERY bar.

    Same formula as ``fp.selector_c.compute_context_features``'s
    ``ctx_volatility_ratio`` (short std / long std of close-to-close
    returns), evaluated continuously rather than once per quarterly
    origin. Bar i's value uses returns up to and including bar i only --
    ``pandas.Series.rolling`` is trailing by construction, never centered.
    """
    import numpy as np

    returns = frame["close"].pct_change()
    short_std = returns.rolling(short_days * BARS_PER_DAY,
                                min_periods=short_days * BARS_PER_DAY).std()
    long_std = returns.rolling(long_days * BARS_PER_DAY,
                               min_periods=long_days * BARS_PER_DAY).std()
    ratio = short_std / long_std
    return ratio.replace([np.inf, -np.inf], np.nan)


def derive_regime_timing_schedule(base_schedule: list[dict], vol_ratio, *,
                                  threshold: float = VOL_THRESHOLD,
                                  k_max_bars: int = K_MAX_BARS,
                                  n_bars: int) -> tuple[list[dict], list[dict]]:
    """For each admission event, defer activation to the first bar in
    [requested_at_bar, requested_at_bar + k_max_bars] where the rolling
    volatility ratio is <= threshold (a real, causal, per-bar scan --
    never a single origin-level snapshot). Falls back to the bounded
    k_max_bars ceiling, never an unbounded wait, when the ratio never
    crosses threshold in that window (including when the ratio is NaN
    throughout, e.g. too early in the frame for a full long-window).

    Returns (new_schedule, diagnostics) -- diagnostics carries, per event,
    whether the threshold was actually hit and the realized deferral in
    bars, which SELECTOR_CAL_MATCHED's construction consumes directly.
    """
    if not base_schedule:
        raise TimingPolicyError("cannot derive a timing schedule from an empty base schedule")
    new_schedule, diagnostics = [], []
    for entry in sorted(base_schedule, key=lambda r: r["requested_at_bar"]):
        origin_bar = int(entry["requested_at_bar"])
        if origin_bar < 0:
            raise TimingPolicyError(f"{entry.get('activation_id')}: negative requested_at_bar "
                                    "is not a real admission event")
        scan_end = min(origin_bar + k_max_bars, n_bars - 1)
        hit_bar = None
        for bar in range(origin_bar, scan_end + 1):
            value = vol_ratio.iloc[bar]
            if value == value and value <= threshold:   # value == value excludes NaN, no import needed
                hit_bar = bar
                break
        activation_bar = hit_bar if hit_bar is not None else scan_end
        deferred_bars = activation_bar - origin_bar
        new_schedule.append({**entry, "requested_at_bar": activation_bar})
        diagnostics.append({
            "activation_id": entry["activation_id"], "origin_bar": origin_bar,
            "activation_bar": activation_bar, "deferred_bars": deferred_bars,
            "hit_threshold": hit_bar is not None,
            "reason": ("volatility ratio crossed <= threshold within the bounded window"
                      if hit_bar is not None else
                      "threshold never reached within k_max_bars -- bounded fallback applied"),
        })
    return new_schedule, diagnostics


def derive_cal_matched_schedule(base_schedule: list[dict], *, k_max_bars: int = K_MAX_BARS,
                                seed: int = CAL_MATCHED_SEED, n_bars: int) -> tuple[list[dict], list[dict]]:
    """Defers each admission event by a bar count drawn independently from
    Uniform(0, k_max_bars) using a FIXED, pre-registered seed -- the SAME
    maximum budget REGIME_TIMING could have used, chosen with ZERO
    volatility or market information, and taking NO input at all from
    REGIME_TIMING's own realized schedule (guide 21's FP09-G-CALIBRATION:
    no future comparator/control calibration from outcome information).
    Returns (new_schedule, diagnostics) in the same shape
    ``derive_regime_timing_schedule`` returns, for report-rendering
    symmetry."""
    import numpy as np

    if not base_schedule:
        raise TimingPolicyError("cannot derive a timing schedule from an empty base schedule")
    rng = np.random.default_rng(seed)
    new_schedule, diagnostics = [], []
    for entry in sorted(base_schedule, key=lambda r: r["requested_at_bar"]):
        origin_bar = int(entry["requested_at_bar"])
        if origin_bar < 0:
            raise TimingPolicyError(f"{entry.get('activation_id')}: negative requested_at_bar "
                                    "is not a real admission event")
        deferred = int(rng.integers(0, k_max_bars + 1))
        activation_bar = min(origin_bar + deferred, n_bars - 1)
        new_schedule.append({**entry, "requested_at_bar": activation_bar})
        diagnostics.append({
            "activation_id": entry["activation_id"], "origin_bar": origin_bar,
            "activation_bar": activation_bar, "deferred_bars": activation_bar - origin_bar,
            "reason": f"drawn from Uniform(0, {k_max_bars}) with fixed seed={seed}, no market "
                     "data consulted",
        })
    return new_schedule, diagnostics
