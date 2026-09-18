"""A16 — fail-closed claim hierarchy for the corrective Mode 4 study.

Execution validity, implementation fidelity and statistical evidence are separate
dimensions (merged plan section 12.2). A contrast whose pipeline is not valid may
only be reported as NOT_EVALUABLE; RULED_OUT belongs to a valid experiment with
the correct threshold and enough evidence. This module is the single place where
that rule is encoded, so the invalidation manifest, the phase reports and the
final claim report cannot each invent their own gate.
"""

from __future__ import annotations

EXECUTION_VALIDITY = ("PASS", "FAIL", "PARTIAL")
IMPLEMENTATION_FIDELITY = ("AS_SPECIFIED", "DEVIATED", "NOT_IMPLEMENTED")
STATISTICAL_STATUSES = ("NOT_EVALUABLE", "INCONCLUSIVE",
                        "NEGATIVE_WITHIN_SCOPE", "POSITIVE_WITHIN_SCOPE")


def statistical_status_allowed(execution_validity: str, implementation_fidelity: str,
                               proposed: str) -> tuple[bool, str]:
    """Return ``(allowed, reason)`` for one proposed statistical status."""
    if execution_validity not in EXECUTION_VALIDITY:
        raise ValueError(f"unknown execution_validity {execution_validity!r}")
    if implementation_fidelity not in IMPLEMENTATION_FIDELITY:
        raise ValueError(f"unknown implementation_fidelity {implementation_fidelity!r}")
    if proposed not in STATISTICAL_STATUSES:
        raise ValueError(f"unknown statistical_status {proposed!r}")
    if (execution_validity != "PASS" or implementation_fidelity != "AS_SPECIFIED") \
            and proposed != "NOT_EVALUABLE":
        return False, ("a contrast whose execution validity or implementation fidelity is not "
                       "PASS/AS_SPECIFIED may only be reported as NOT_EVALUABLE")
    return True, "allowed under the registered claim hierarchy"
