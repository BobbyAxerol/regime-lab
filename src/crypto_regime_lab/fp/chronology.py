"""Guide FP01.2 finding 7: chronological matured-label split.

The dormant hazard (guide §8.4, source [I1, A08]): rows sorted by time and fit
with temporal-blocked or leave-one-out cross validation can still train on
FUTURE origins when the label (a forward/matured outcome) was not available at
the validation decision time. RA-06's ridge ladder was never fit
(support=5 < MIN_SUPPORT_FOR_MODEL_FIT=8), so the hazard class stayed dormant:
no guard existed anywhere to refuse a future-label training row.

This module is the guard FP-05 must pass through. A training row is usable only
when its label was available BEFORE the validation decision time; blocked rows
are reported with reasons, never silently dropped; and a naive time-sorted LOO
task over the same fixture is shown to leak, proving the guard can go red.
"""
from __future__ import annotations

import pandas as pd

from .availability import ChronologyViolation


def chronological_split(rows, *, decision_time, label_field: str = "label",
                        available_field: str = "label_available_at") -> dict:
    """Split ``rows`` into usable training rows and blocked future-label rows.

    A row is usable iff its label value is finite and was available strictly
    before ``decision_time``. Returns both sides with per-row reasons so a
    100%-blocked split is visible evidence, never an empty training matrix
    discovered downstream.
    """
    moment = pd.Timestamp(decision_time)
    usable, blocked = [], []
    for position, row in enumerate(rows):
        value = row.get(label_field)
        available = row.get(available_field)
        if available is None:
            raise ChronologyViolation(
                f"row {position} has no {available_field!r}: availability cannot be "
                "proven, so the row cannot train (refusal, not assumption)")
        try:
            published = pd.Timestamp(available)
        except (TypeError, ValueError) as exc:
            raise ChronologyViolation(
                f"row {position} has no usable {available_field!r}: "
                "availability cannot be proven") from exc
        if value is None or (isinstance(value, float) and value != value):
            blocked.append({"position": position, "row": row,
                            "reason": "label missing/NaN at split time"})
        elif published >= moment:
            blocked.append({"position": position, "row": row,
                            "reason": (f"label available {published.isoformat()}, "
                                       f"at/after decision {moment.isoformat()}")})
        else:
            usable.append(row)
    return {
        "schema": "regime_lab.fp_chronological_split.v1",
        "decision_time": moment.isoformat(),
        "n_usable": len(usable),
        "n_blocked": len(blocked),
        "usable": usable,
        "blocked": blocked,
    }


def naive_time_sorted_loo_train(rows, *, held: int) -> list:
    """The hazardous baseline: time-sorted rows with row ``held`` left out.

    Kept ONLY as the "before" control for FP01-T07-adjacent tests: it returns
    whatever remains, including origins whose labels postdate the held origin's
    decision time. A chronology guard must refuse its output whenever a returned
    row fails ``chronological_split`` against that decision time.
    """
    ordered = sorted(rows, key=lambda row: pd.Timestamp(row["origin_time"]))
    return [row for position, row in enumerate(ordered) if position != held]
