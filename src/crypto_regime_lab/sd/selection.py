"""SD-01: candidate selection rule (guide SS3.3-3.4).

Replaces two confirmed-PRESENT defects in fp/locked_study.py (see
configs/sharpe_decay_sd_v1/protocol_migration.json's finding_dispositions
for the exact line-level evidence each was verified against):

  * F03a -- the old runner picked ``max(predicted_forward_utility)``, not a
    decay-minimizing rule. This module picks ``min(Y_hat)`` among eligible
    candidates instead (guide SS3.4 steps 5-7).
  * F05 -- the old ``walk_forward_c_selection`` short-circuited to
    ``FALLBACK_TO_A`` whenever B itself had fallen back, so C was never
    independently evaluated. This module has NO concept of "B" or "C" at
    all -- it is the SAME selection function called twice by the caller,
    once per arm, with each arm's own scored candidates. There is no
    shared or gating state between the two calls, so the F05 shape cannot
    recur structurally, not just by convention.

Model fitting/prediction (the actual Y_hat numbers) is SD-02's job
(guide SS9.2); this module only implements the guard + minY decision over
an ALREADY-scored candidate set, per guide SS3.4's own step decomposition
(steps 1-3 -- support check, prediction, Q_hat -- happen before a caller
ever calls this module; steps 5-7 -- anchor-zero reference, minY, tie-break
-- are what this module owns).
"""
from __future__ import annotations

PREDICTION_GUARD_MARGIN = -0.10   # guide SS2.6 / SS3.4 step 4, Sharpe points
TIE_EPSILON = 1e-6                # guide SS5.8's own tie tolerance, reused here


class SelectionError(ValueError):
    """A selection input was internally inconsistent -- never silently patched."""


def q_hat_identity(sr_is_candidate: float, sr_is_anchor: float, y_hat: float) -> float:
    """Q_hat = SR_IS(candidate) - SR_IS(anchor) - Y_hat (guide SS3.3's own
    guard identity). Never requires a predicted absolute stock OOS Sharpe."""
    return sr_is_candidate - sr_is_anchor - y_hat


def eligible_candidates(scored: list[dict], *, guard_margin: float = PREDICTION_GUARD_MARGIN) -> list[dict]:
    """Step 4: eligible iff common safety/data checks passed AND
    Q_hat >= guard_margin. Every row must already carry ``candidate_id``,
    ``y_hat`` and ``q_hat``; a row missing either raises rather than being
    silently treated as ineligible."""
    out = []
    for row in scored:
        for field in ("candidate_id", "y_hat", "q_hat"):
            if field not in row:
                raise SelectionError(f"{row.get('candidate_id', '<unknown>')}: missing {field!r}")
        eligible = bool(row.get("safety_ok", True)) and row["q_hat"] >= guard_margin
        out.append({**row, "eligible": eligible})
    return out


def select_min_y(scored_eligible: list[dict], *, anchor_id: str, schema=None) -> dict:
    """Steps 5-7. ``scored_eligible`` MUST already include the anchor as one
    row (``candidate_id == anchor_id``, ``y_hat == 0.0`` by construction --
    guide SS3.3: anchor's own label is 0, forced structurally, never by a
    lucky intercept) and it MUST be eligible (Q_hat(anchor) = 0 by identity,
    which always clears any guard_margin <= 0). A caller that omits the
    anchor, or one whose anchor Y_hat isn't exactly 0, gets a raised error
    here -- never a silent substitute.

    Picks the LOWEST y_hat among eligible rows (never the anchor winning by
    special-casing -- it wins only when nothing eligible beats 0). Ties
    within TIE_EPSILON break by schema distance to the anchor's own params
    (smaller wins) when ``schema``/``params``/``anchor_params`` are given,
    else by stable ``candidate_id`` -- deterministic either way, never by
    outcome.
    """
    anchor_rows = [r for r in scored_eligible if r["candidate_id"] == anchor_id]
    if not anchor_rows:
        raise SelectionError("anchor row missing from scored_eligible -- guide SS3.4 step 5 "
                             "requires the anchor present as the contrast-zero reference")
    anchor_row = anchor_rows[0]
    if abs(anchor_row["y_hat"]) > TIE_EPSILON:
        raise SelectionError(f"anchor y_hat must be 0.0 by construction, got {anchor_row['y_hat']}")
    eligible = [r for r in scored_eligible if r.get("eligible")]
    if not eligible:
        raise SelectionError("no eligible candidates, not even the anchor -- the anchor must "
                             "always be eligible by construction (q_hat=0 >= any guard <= 0)")
    best_y = min(r["y_hat"] for r in eligible)
    tied = [r for r in eligible if abs(r["y_hat"] - best_y) <= TIE_EPSILON]
    if len(tied) == 1:
        winner = tied[0]
    elif schema is not None and all("params" in r and "anchor_params" in r for r in tied):
        tied_sorted = sorted(tied, key=lambda r: (schema.distance(r["params"], r["anchor_params"]),
                                                   r["candidate_id"]))
        winner = tied_sorted[0]
    else:
        winner = sorted(tied, key=lambda r: r["candidate_id"])[0]
    return {"decision": "CANDIDATE_SELECTED", "winner_id": winner["candidate_id"],
           "y_hat": winner["y_hat"], "is_anchor": winner["candidate_id"] == anchor_id,
           "tie_broken": len(tied) > 1, "n_eligible": len(eligible)}
