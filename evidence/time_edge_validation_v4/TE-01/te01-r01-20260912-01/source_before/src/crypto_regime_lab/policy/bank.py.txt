"""L06.2 / guide 7.4 — the candidate bank and its lineage.

The bank is the set of parameter configurations a switch may choose between. Two
properties matter more than its contents:

**It is time-honest.** A bank at T contains only candidates discovered from
observations before T. That is the whole reason candidate creation time is a
recorded field rather than an implicit "whenever we ran the search" (T46).

**It never loses a row.** Duplicates are MERGED for coverage accounting -- two
near-identical parameter sets do not make a bank twice as diverse -- but the
underlying trial rows stay, because a merged duplicate is still a trial that was
paid for and counted against the search budget.

Retirement is not deletion. A retired parameter version keeps serving the
campaigns that entered under it, and it may not be removed while any order still
references it (guide 9.5).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

import pandas as pd

#: Guide 7.4: "tối đa khoảng 3-8 configurations". A proposal, not a hard law, and
#: the reason is stated: more candidates do not help when episodes are few.
BANK_MIN = 3
BANK_MAX = 8

STATUS_ACTIVE = "ACTIVE"
STATUS_RETIRED = "RETIRED"
STATUS_PENDING_WARMUP = "PENDING_WARMUP"


class BankError(ValueError):
    """A bank operation that would break lineage. Never silently repaired."""


def parameter_digest(params: dict) -> str:
    payload = json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class BankEntry:
    """One parameter version, with everything guide 7.4 requires it to carry."""

    candidate_id: str
    params: dict
    discovered_at: pd.Timestamp
    entry_date: pd.Timestamp
    strategy_adapter_hash: str
    validation_panel: dict
    warmup_bars_required: int
    status: str = STATUS_ACTIVE
    retire_date: pd.Timestamp | None = None
    reason: str = ""
    merged_duplicates: list[str] = field(default_factory=list)
    open_campaign_refs: list[str] = field(default_factory=list)

    @property
    def parameter_digest(self) -> str:
        return parameter_digest(self.params)

    def warm_at(self, now: pd.Timestamp, bar_hours: float) -> bool:
        """Indicator readiness by version and cutoff (L06.2.5)."""
        needed = pd.Timedelta(hours=self.warmup_bars_required * bar_hours)
        return pd.Timestamp(now) >= self.entry_date + needed

    def as_record(self) -> dict:
        return {
            "candidate_id": self.candidate_id, "params": self.params,
            "parameter_digest": self.parameter_digest,
            "discovered_at": str(self.discovered_at), "entry_date": str(self.entry_date),
            "retire_date": None if self.retire_date is None else str(self.retire_date),
            "strategy_adapter_hash": self.strategy_adapter_hash,
            "validation_panel": self.validation_panel,
            "warmup_bars_required": int(self.warmup_bars_required),
            "status": self.status, "reason": self.reason,
            "merged_duplicates": list(self.merged_duplicates),
            "open_campaign_refs": list(self.open_campaign_refs),
        }


@dataclass
class CandidateBank:
    """The bank at a declared cutoff."""

    cutoff: pd.Timestamp
    entries: list[BankEntry] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    trial_rows_retained: int = 0

    def admissible(self) -> list[BankEntry]:
        """Guide 7.4: the bank at T holds nothing discovered after T."""
        return [e for e in self.entries
                if e.discovered_at <= self.cutoff and e.status != STATUS_RETIRED]

    def serving_open_campaigns(self) -> list[BankEntry]:
        """Retired versions that must stay alive because a campaign still references them."""
        return [e for e in self.entries
                if e.status == STATUS_RETIRED and e.open_campaign_refs]

    def retire(self, candidate_id: str, when: pd.Timestamp, reason: str) -> None:
        entry = next((e for e in self.entries if e.candidate_id == candidate_id), None)
        if entry is None:
            raise BankError(f"unknown candidate {candidate_id}")
        entry.status = STATUS_RETIRED
        entry.retire_date = pd.Timestamp(when)
        entry.reason = reason

    def remove(self, candidate_id: str) -> None:
        """Deletion is refused while any order still references the version."""
        entry = next((e for e in self.entries if e.candidate_id == candidate_id), None)
        if entry is None:
            raise BankError(f"unknown candidate {candidate_id}")
        if entry.open_campaign_refs:
            raise BankError(
                f"{candidate_id} still serves open campaigns {entry.open_campaign_refs}; a "
                "parameter version may not be deleted while an order references it (guide 9.5)")
        self.entries.remove(entry)

    def as_record(self) -> dict:
        admissible = self.admissible()
        return {
            "schema": "crypto_regime_lab.candidate_bank.v1",
            "cutoff": str(self.cutoff),
            "entries": [e.as_record() for e in self.entries],
            "admissible_count": len(admissible),
            "within_proposed_size": BANK_MIN <= len(admissible) <= BANK_MAX,
            "proposed_size_range": [BANK_MIN, BANK_MAX],
            "size_rule": ("guide 7.4 proposes 3-8 configurations with DIFFERENT behaviour and "
                          "enough local evidence. 16 or 64 candidates are not better when the "
                          "episode count is small"),
            "retired_serving_open_campaigns": [
                e.candidate_id for e in self.serving_open_campaigns()],
            "rejected": self.rejected,
            "trial_rows_retained": self.trial_rows_retained,
            "lineage_rule": ("every candidate carries the time it was DISCOVERED, and the bank at "
                             "a cutoff admits only what was discovered before it. Duplicates are "
                             "merged for coverage but their trial rows are never deleted (T46)"),
        }


def build_bank(cutoff: pd.Timestamp, discoveries: list[dict], *,
               adapter_hash: str, warmup_bars: int, max_size: int = BANK_MAX,
               duplicate_distance: float = 0.02, schema=None) -> CandidateBank:
    """Assemble the bank from discoveries, newest evidence first.

    ``discoveries`` rows carry ``candidate_id``, ``params``, ``discovered_at`` and
    a ``validation_panel``. Anything discovered at or after the cutoff is REJECTED
    with a reason rather than dropped quietly, so the lineage is auditable.
    """
    bank = CandidateBank(cutoff=pd.Timestamp(cutoff))
    bank.trial_rows_retained = len(discoveries)

    eligible = []
    for row in discoveries:
        # normalise once and KEEP IT ON THE ROW. Reading a loop variable from the
        # filtering pass inside the building pass gave every entry the discovery
        # time of whichever row happened to be last, which is precisely the
        # lineage field T46 exists to protect.
        row = {**row, "discovered_at": pd.Timestamp(row["discovered_at"])}
        discovered = row["discovered_at"]
        if discovered > bank.cutoff:
            bank.rejected.append({
                "candidate_id": row["candidate_id"], "discovered_at": str(discovered),
                "reason": "discovered after the cutoff; a bank at T may not contain it (T46)"})
            continue
        eligible.append(row)

    # merge effective duplicates for COVERAGE, keeping the trial rows
    kept: list[BankEntry] = []
    for row in sorted(eligible, key=lambda r: (-float(r.get("score", 0.0)),
                                               str(r["candidate_id"]))):
        duplicate_of = None
        if schema is not None:
            for entry in kept:
                if schema.distance(entry.params, row["params"]) <= duplicate_distance:
                    duplicate_of = entry
                    break
        if duplicate_of is not None:
            duplicate_of.merged_duplicates.append(row["candidate_id"])
            continue
        if len(kept) >= max_size:
            bank.rejected.append({
                "candidate_id": row["candidate_id"],
                "reason": f"bank already holds the proposed maximum of {max_size}"})
            continue
        kept.append(BankEntry(
            candidate_id=row["candidate_id"], params=row["params"],
            discovered_at=row["discovered_at"], entry_date=bank.cutoff,
            strategy_adapter_hash=adapter_hash,
            validation_panel=row.get("validation_panel", {}),
            warmup_bars_required=warmup_bars,
            status=STATUS_ACTIVE,
            reason=row.get("reason", "admitted from a pre-cutoff discovery")))
    bank.entries = kept
    return bank


def specialist_note() -> dict:
    """Guide 7.4 — a specialist is not dropped just because the pooled mean is lower."""
    return {
        "rule": ("a candidate whose pooled mean is below the global best may still belong in the "
                 "bank if it has conditional evidence with enough support. It is dropped for lack "
                 "of support or for failing cost/risk constraints, never for a low pooled mean "
                 "alone (guide 7.4)"),
        "counted_against_search_budget": True,
        "inactive_params_do_not_add_diversity": True,
    }
