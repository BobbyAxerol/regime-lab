"""VWFO-04 Policy Runtime & Operational Interface Module.

Implements the unified decision interface connecting:
- Model bundles (weights, imputer medians, temperature scaling, taxonomy quantiles, feature schema)
- Policy proposals with strict timing contracts (candidate window, target window, not_before, expiry)
- Runtime controller managing incumbent lifecycle, versioning, idempotency, same-param watermark refreshes,
  and SAFE_ENTRY_PAUSE boundaries.
- Strict causality: zero expected-fill feedback (actual engine fills/rejects only), no backdating.
"""
from __future__ import annotations

import copy
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import numpy as np
import pandas as pd


@dataclass
class ModelBundle:
    """Complete serialized model bundle. Weights-only shortcuts are rejected (V4-T07)."""
    recipe_id: str
    weights: Dict[str, Any]
    imputer_medians: Dict[str, float]
    temperature_t_v: float
    taxonomy_quantiles: Dict[str, float]
    feature_schema: List[str]

    def validate(self) -> Tuple[bool, str]:
        """Strict validation of bundle completeness."""
        if not self.recipe_id:
            return False, "MISSING_RECIPE_ID"
        if not self.weights:
            return False, "MISSING_MODEL_WEIGHTS"
        if not self.imputer_medians or len(self.imputer_medians) == 0:
            return False, "MISSING_IMPUTER_MEDIANS"
        if self.temperature_t_v is None or not (self.temperature_t_v > 0.0):
            return False, "MISSING_OR_INVALID_TEMPERATURE_SCALING"
        if not self.taxonomy_quantiles or "q33_3" not in self.taxonomy_quantiles or "q66_7" not in self.taxonomy_quantiles:
            return False, "MISSING_TAXONOMY_QUANTILES"
        if not self.feature_schema or len(self.feature_schema) != 38:
            return False, f"INVALID_FEATURE_SCHEMA_LENGTH (expected 38, got {len(self.feature_schema) if self.feature_schema else 0})"
        return True, "VALID"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ModelBundle:
        return cls(
            recipe_id=str(data["recipe_id"]),
            weights=dict(data.get("weights", {})),
            imputer_medians=dict(data.get("imputer_medians", {})),
            temperature_t_v=float(data.get("temperature_t_v", 1.0)),
            taxonomy_quantiles=dict(data.get("taxonomy_quantiles", {})),
            feature_schema=list(data.get("feature_schema", [])),
        )


@dataclass
class PolicyProposal:
    """Atomic parameter proposal published at cutoff for a 14-day target window."""
    proposal_id: str
    arm_id: str
    cutoff_time: pd.Timestamp
    target_window_start: pd.Timestamp
    target_window_end: pd.Timestamp
    not_before: pd.Timestamp
    expires_at: pd.Timestamp
    expected_incumbent_version: int
    sequence_number: int
    candidate_params: Dict[str, Any]
    model_bundle: ModelBundle
    selection_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "arm_id": self.arm_id,
            "cutoff_time": self.cutoff_time.isoformat(),
            "target_window_start": self.target_window_start.isoformat(),
            "target_window_end": self.target_window_end.isoformat(),
            "not_before": self.not_before.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "expected_incumbent_version": self.expected_incumbent_version,
            "sequence_number": self.sequence_number,
            "candidate_params": self.candidate_params,
            "model_bundle": self.model_bundle.to_dict(),
            "selection_metadata": self.selection_metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PolicyProposal:
        return cls(
            proposal_id=str(data["proposal_id"]),
            arm_id=str(data["arm_id"]),
            cutoff_time=pd.Timestamp(data["cutoff_time"]),
            target_window_start=pd.Timestamp(data["target_window_start"]),
            target_window_end=pd.Timestamp(data["target_window_end"]),
            not_before=pd.Timestamp(data["not_before"]),
            expires_at=pd.Timestamp(data["expires_at"]),
            expected_incumbent_version=int(data["expected_incumbent_version"]),
            sequence_number=int(data["sequence_number"]),
            candidate_params=dict(data["candidate_params"]),
            model_bundle=ModelBundle.from_dict(data["model_bundle"]),
            selection_metadata=dict(data.get("selection_metadata", {})),
        )


@dataclass
class OrderIntent:
    """Order intent emitted by strategy."""
    order_id: str
    symbol: str
    side: str  # "BUY" or "SELL"
    order_type: str  # "MARKET" or "LIMIT"
    quantity: float
    reference_price: float
    is_protective_exit: bool
    version: int
    emitted_at: pd.Timestamp


@dataclass
class AccountState:
    """State of an arm account in the policy runtime."""
    cash: float = 20000.0
    position: float = 0.0
    equity: float = 20000.0
    entry_price: float = 0.0
    active_version: int = 0
    active_params: Dict[str, Any] = field(default_factory=dict)
    last_param_change: Optional[pd.Timestamp] = None
    last_revalidation: Optional[pd.Timestamp] = None
    revalidation_count: int = 0
    operational_status: str = "ACTIVE"  # "ACTIVE", "SAFE_ENTRY_PAUSE", "WAIT_FLAT"
    processed_proposal_ids: Set[str] = field(default_factory=set)
    fills_count: int = 0
    rejections_count: int = 0
    active_orders: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cash": float(self.cash),
            "position": float(self.position),
            "equity": float(self.equity),
            "entry_price": float(self.entry_price),
            "active_version": int(self.active_version),
            "active_params": dict(self.active_params),
            "last_param_change": self.last_param_change.isoformat() if self.last_param_change else None,
            "last_revalidation": self.last_revalidation.isoformat() if self.last_revalidation else None,
            "revalidation_count": int(self.revalidation_count),
            "operational_status": str(self.operational_status),
            "processed_proposal_ids": sorted(list(self.processed_proposal_ids)),
            "fills_count": int(self.fills_count),
            "rejections_count": int(self.rejections_count),
            "active_orders": dict(self.active_orders),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AccountState:
        return cls(
            cash=float(data["cash"]),
            position=float(data["position"]),
            equity=float(data["equity"]),
            entry_price=float(data["entry_price"]),
            active_version=int(data["active_version"]),
            active_params=dict(data.get("active_params", {})),
            last_param_change=pd.Timestamp(data["last_param_change"]) if data.get("last_param_change") else None,
            last_revalidation=pd.Timestamp(data["last_revalidation"]) if data.get("last_revalidation") else None,
            revalidation_count=int(data.get("revalidation_count", 0)),
            operational_status=str(data.get("operational_status", "ACTIVE")),
            processed_proposal_ids=set(data.get("processed_proposal_ids", [])),
            fills_count=int(data.get("fills_count", 0)),
            rejections_count=int(data.get("rejections_count", 0)),
            active_orders=dict(data.get("active_orders", {})),
        )


class PolicyRuntimeController:
    """Manages the operational lifecycle, timing contract, and boundaries for an arm.

    Guarantees:
    - Timing contract: Candidate/target window, not_before, and expiry per §5.2 and §9.
    - Idempotency: Duplicate proposal or restart after publish-before-ack does not double-activate (V4-T04).
    - Incumbent versioning: Rejects version mismatch or expired proposals (V4-T06).
    - Bundle completeness: Rejects missing medians, temp scaling, or taxonomy (V4-T07).
    - Watermark refresh: Same parameters refresh watermark without resetting indicators/equity/campaign (V4-T05).
    - SAFE_ENTRY_PAUSE: Max-revalidation pause blocks entries but preserves protective exits (V4-T08).
    - Actual feedback: Real engine fills/rejects drive state, zero expected-fill feedback (V4-T09).
    """

    def __init__(
        self,
        arm_id: str,
        initial_params: Dict[str, Any],
        *,
        initial_equity: float = 20000.0,
        allocation_fraction: float = 0.10,
        one_way_fee: float = 0.0004,
        slippage_bps: float = 1.0,
        common_ready_lag_days: int = 1,
        proposal_ttl_days: int = 2,
        max_revalidation_age_days: int = 28,
        wait_flat_required: bool = True,
    ):
        self.arm_id = arm_id
        self.allocation_fraction = allocation_fraction
        self.one_way_fee = one_way_fee
        self.slippage_bps = slippage_bps
        self.common_ready_lag_days = common_ready_lag_days
        self.proposal_ttl_days = proposal_ttl_days
        self.max_revalidation_age_days = max_revalidation_age_days
        self.wait_flat_required = wait_flat_required

        self.account_state = AccountState(
            cash=initial_equity,
            position=0.0,
            equity=initial_equity,
            entry_price=0.0,
            active_version=0,
            active_params=dict(initial_params),
            last_param_change=None,
            last_revalidation=None,
            revalidation_count=0,
            operational_status="ACTIVE",
        )
        self.pending_proposal: Optional[PolicyProposal] = None
        self.event_log: List[Dict[str, Any]] = []

    def receive_proposal(self, proposal: PolicyProposal, current_time: pd.Timestamp) -> Tuple[bool, str]:
        """Receives and validates a newly published policy proposal.

        Checks:
        1. Arm ID match.
        2. Idempotency (already processed proposal ID).
        3. Bundle completeness (medians, temp, taxonomy, schema).
        4. Expiry / clock checks (cannot be expired, cannot backdate past history).
        5. Incumbent version match.
        """
        if proposal.arm_id != self.arm_id:
            return False, f"ARM_MISMATCH (expected {self.arm_id}, got {proposal.arm_id})"

        # Idempotency check (V4-T04)
        if proposal.proposal_id in self.account_state.processed_proposal_ids:
            return True, "IDEMPOTENT_IGNORED_ALREADY_PROCESSED"

        # Model bundle validation (V4-T07)
        bundle_valid, bundle_err = proposal.model_bundle.validate()
        if not bundle_valid:
            return False, f"INVALID_BUNDLE: {bundle_err}"

        # Target window validity (V4-T02)
        if proposal.target_window_start >= proposal.target_window_end:
            return False, "INVALID_TARGET_WINDOW_BOUNDS"
        if proposal.not_before < proposal.cutoff_time:
            return False, "INVALID_NOT_BEFORE_PRECEDES_CUTOFF"

        # Expiry check (V4-T06)
        if current_time > proposal.expires_at:
            return False, "PROPOSAL_EXPIRED"

        # Incumbent version mismatch (V4-T06)
        if proposal.expected_incumbent_version != self.account_state.active_version:
            return False, f"INCUMBENT_VERSION_MISMATCH (expected {proposal.expected_incumbent_version}, active {self.account_state.active_version})"

        # Mark processed and buffer for activation at not_before
        self.account_state.processed_proposal_ids.add(proposal.proposal_id)
        self.pending_proposal = proposal

        self.event_log.append({
            "event": "PROPOSAL_ACCEPTED",
            "proposal_id": proposal.proposal_id,
            "timestamp": current_time.isoformat(),
            "target_window_start": proposal.target_window_start.isoformat(),
            "not_before": proposal.not_before.isoformat(),
        })
        return True, "PROPOSAL_ACCEPTED"

    def check_operational_safety(self, current_time: pd.Timestamp) -> None:
        """Evaluates max-revalidation age and transitions to SAFE_ENTRY_PAUSE if exceeded (V4-T08)."""
        if self.account_state.last_revalidation is not None:
            age_days = (current_time - self.account_state.last_revalidation).total_seconds() / 86400.0
            if age_days > float(self.max_revalidation_age_days):
                if self.account_state.operational_status != "SAFE_ENTRY_PAUSE":
                    self.account_state.operational_status = "SAFE_ENTRY_PAUSE"
                    self.event_log.append({
                        "event": "SAFE_ENTRY_PAUSE_TRIGGERED",
                        "timestamp": current_time.isoformat(),
                        "age_days": age_days,
                        "limit_days": self.max_revalidation_age_days,
                    })

    def process_pending_activation(self, current_time: pd.Timestamp) -> Tuple[bool, str]:
        """Attempts to activate pending proposal if legal timing reached."""
        if self.pending_proposal is None:
            return False, "NO_PENDING_PROPOSAL"

        prop = self.pending_proposal

        # Expiry check while pending
        if current_time > prop.expires_at:
            self.pending_proposal = None
            self.event_log.append({
                "event": "PROPOSAL_EXPIRED_UNACTIVATED",
                "proposal_id": prop.proposal_id,
                "timestamp": current_time.isoformat(),
            })
            return False, "PROPOSAL_EXPIRED"

        # Timing check: must be at or after not_before (V4-T03)
        if current_time < prop.not_before:
            return False, "WAITING_NOT_BEFORE"

        # Check if candidate params are identical to incumbent (V4-T05)
        same_params = (prop.candidate_params == self.account_state.active_params)

        # Wait-flat requirement if open position exists and switching to DIFFERENT parameters (V4-T03)
        if not same_params and self.wait_flat_required and abs(self.account_state.position) > 1e-6:
            return False, "WAITING_FLAT_POSITION"

        if same_params:
            # Same parameters refresh: update watermark without resetting indicators, equity, or version
            self.account_state.last_revalidation = current_time
            self.account_state.revalidation_count += 1
            if self.account_state.operational_status == "SAFE_ENTRY_PAUSE":
                self.account_state.operational_status = "ACTIVE"
            self.pending_proposal = None
            self.event_log.append({
                "event": "SAME_PARAMS_REVALIDATION_WATERMARK_REFRESHED",
                "proposal_id": prop.proposal_id,
                "timestamp": current_time.isoformat(),
                "active_version": self.account_state.active_version,
            })
            return True, "SAME_PARAMS_REFRESHED"
        else:
            # Different parameters: advance version and update active parameters
            self.account_state.active_params = dict(prop.candidate_params)
            self.account_state.active_version += 1
            self.account_state.last_param_change = current_time
            self.account_state.last_revalidation = current_time
            self.account_state.revalidation_count += 1
            if self.account_state.operational_status == "SAFE_ENTRY_PAUSE":
                self.account_state.operational_status = "ACTIVE"
            self.pending_proposal = None
            self.event_log.append({
                "event": "NEW_VERSION_ACTIVATED",
                "proposal_id": prop.proposal_id,
                "timestamp": current_time.isoformat(),
                "new_version": self.account_state.active_version,
                "params": self.account_state.active_params,
            })
            return True, "NEW_VERSION_ACTIVATED"

    def mark_to_market(self, current_price: float) -> float:
        """Mark-to-market equity valuation."""
        if current_price <= 0:
            raise ValueError(f"Invalid price: {current_price}")
        self.account_state.equity = self.account_state.cash + self.account_state.position * current_price
        return self.account_state.equity

    def on_fill(self, fill_event: Dict[str, Any]) -> None:
        """Updates internal account state strictly upon real engine fill (V4-T09)."""
        side = fill_event["side"]
        qty = float(fill_event["quantity"])
        price = float(fill_event["price"])
        fee = float(fill_event.get("fee", 0.0))

        if side == "BUY":
            cost = qty * price + fee
            self.account_state.cash -= cost
            self.account_state.position += qty
            self.account_state.entry_price = price
        elif side == "SELL":
            proceeds = qty * price - fee
            self.account_state.cash += proceeds
            self.account_state.position -= qty
            if abs(self.account_state.position) < 1e-6:
                self.account_state.position = 0.0
                self.account_state.entry_price = 0.0
        else:
            raise ValueError(f"Unknown side: {side}")

        self.account_state.fills_count += 1
        self.mark_to_market(price)

        self.event_log.append({
            "event": "ORDER_FILLED",
            "side": side,
            "quantity": qty,
            "price": price,
            "fee": fee,
            "timestamp": fill_event.get("timestamp"),
            "equity_after": self.account_state.equity,
            "position_after": self.account_state.position,
        })

    def on_reject(self, reject_event: Dict[str, Any]) -> None:
        """Records order rejection. Account cash and position are strictly untouched (V4-T09)."""
        self.account_state.rejections_count += 1
        self.event_log.append({
            "event": "ORDER_REJECTED",
            "order_id": reject_event.get("order_id"),
            "reason": reject_event.get("reason"),
            "timestamp": reject_event.get("timestamp"),
        })

    def save_state(self, path: Path) -> None:
        """Persists controller and account state for cold restart recovery."""
        state_dict = {
            "arm_id": self.arm_id,
            "account_state": self.account_state.to_dict(),
            "pending_proposal": self.pending_proposal.to_dict() if self.pending_proposal else None,
            "allocation_fraction": self.allocation_fraction,
            "one_way_fee": self.one_way_fee,
            "slippage_bps": self.slippage_bps,
            "common_ready_lag_days": self.common_ready_lag_days,
            "proposal_ttl_days": self.proposal_ttl_days,
            "max_revalidation_age_days": self.max_revalidation_age_days,
            "wait_flat_required": self.wait_flat_required,
            "event_log_count": len(self.event_log),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state_dict, f, indent=2, sort_keys=True)

    def load_state(self, path: Path) -> None:
        """Recovers controller and account state from persisted store (V4-T04, V4-T07)."""
        with open(path, "r", encoding="utf-8") as f:
            state_dict = json.load(f)

        if state_dict["arm_id"] != self.arm_id:
            raise ValueError(f"State store arm_id mismatch: {state_dict['arm_id']} vs {self.arm_id}")

        self.account_state = AccountState.from_dict(state_dict["account_state"])
        if state_dict.get("pending_proposal"):
            self.pending_proposal = PolicyProposal.from_dict(state_dict["pending_proposal"])
        else:
            self.pending_proposal = None
