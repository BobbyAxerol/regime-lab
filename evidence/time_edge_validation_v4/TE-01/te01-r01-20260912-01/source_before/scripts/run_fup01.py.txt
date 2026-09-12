#!/usr/bin/env python
"""FUP-01 — native-event capability for A-VWAP and A-HASH and the 20-cell route matrix.

Registered follow-up study
``evidence/corrective_mode4_v3/followup-studies/followup_studies_registration.json``
entry FUP-01: unlock the native-event command projection for the two alphas the
RF-02 route matrix blocked (``AMEND_PROTECTION`` for A-VWAP, the partial TP
ladder for A-HASH), qualify both routes on synthetic fixtures and one bounded
real BTCUSDT window each, and update all 20 primary-cell route statuses.

The engine is the pinned ``quantbt==1.1.1``; the adapters are the lab's
``a_vwap.py`` / ``a_hash.py``; the provider is never reimplemented. What this
script emits:

* ``native_event_capability.json`` — per alpha, the supported command list, the
  engine events actually observed, the per-fill ledger, the projection-probe
  evidence (a scripted adapter that exercises amend/cancel/reduce/ladder on a
  synthetic frame) and the bounded real-BTCUSDT window evidence. Route status is
  ``QUALIFIED_EVENT`` only when every assertion holds; otherwise it is
  ``BLOCKED_CAPABILITY`` with the exact missing command and null metrics.
* ``route_matrix.json`` — one row per primary cell (4 alphas x 5 symbols), the
  updated A-VWAP/A-HASH status merged with the committed RF-04 event-route
  cells. A cell that has no discovery run carries ``metrics: null`` with a
  reason, never a zero.

Reads the lab's byte-copied parquet snapshots directly (``run_rf04_paired_pilot
.load_frame``); never calls ``data_loader.py``. Nothing outside LAB_ROOT is
written.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))
sys.path.insert(0, str(LAB_ROOT / "scripts"))

import run_rf04_paired_pilot as pilot_runner  # noqa: E402

from crypto_regime_lab.alphas.contracts import (  # noqa: E402
    BarDecision, ExecutionPhase, IntentKind, OrderIntent, QuantityBasis,
)
from crypto_regime_lab.evidence.manifest import EvidenceWriter  # noqa: E402
from crypto_regime_lab.integration import event_account as EA  # noqa: E402
from crypto_regime_lab.integration.continuous_account import VersionWindow  # noqa: E402
from crypto_regime_lab.quantbt_bridge.routes import ONE_WAY_TAKER_FEE  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy, sha256_file  # noqa: E402
from crypto_regime_lab.selector.alpha_schemas import SEED_POINTS  # noqa: E402

STUDY_ID = "corrective_mode4_v3"
RUN_ID = "FUP-01"
RUN_DIR = LAB_ROOT / "evidence" / STUDY_ID / RUN_ID
RF02_DIR = LAB_ROOT / "evidence" / STUDY_ID / "RF-02"
RF04_DIR = LAB_ROOT / "evidence" / STUDY_ID / "RF-04"
SNAPSHOT_ID = "server_core_v1"
PRODUCT = "crypto_binance_futures_1m"
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT")
ALPHAS = ("A-SC", "A-HMA", "A-VWAP", "A-HASH")
ONE_WAY_FEE = ONE_WAY_TAKER_FEE

# Bounded real windows: selected for COMMAND COVERAGE, never for performance.
# A-VWAP exercises the registered exit_at_vwap=True variant (the canonical seed
# keeps it off, SD-VWAP-04); A-HASH uses the registered seed unchanged.
VWAP_REAL_WINDOW = ("2021-01-01", "2021-04-01")
HASH_REAL_WINDOW = ("2021-01-01", "2021-01-15")

FILL_LEDGER_KEYS = ("bar_index", "side", "qty", "price", "fee", "tag", "order_id",
                    "intent_kind", "position_before", "position_after")


# ---------------------------------------------------------------------------
# synthetic fixtures
# ---------------------------------------------------------------------------

def _frame_from_close(close: np.ndarray, *, start: str = "2021-01-01",
                      freq: str = "15min", pad: float = 0.3,
                      volume: float = 1000.0) -> pd.DataFrame:
    open_ = np.r_[close[0], close[:-1]]
    index = pd.date_range(start, periods=len(close), freq=freq, tz="UTC")
    return pd.DataFrame({"open": open_, "high": np.maximum(open_, close) + pad,
                         "low": np.minimum(open_, close) - pad, "close": close,
                         "volume": np.full(len(close), volume)}, index=index)


def vwap_synthetic_frame(seed: int = 2, n: int = 6000) -> pd.DataFrame:
    """Mean-reverting noise plus periodic oversold shocks (no market claim)."""
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 0.1, n))
    for start in range(2500, n - 600, 400):
        close[start:start + 8] -= np.linspace(0, 6.0, 8)
        close[start + 8:start + 80] += np.linspace(0, 6.0, 72)
    return _frame_from_close(np.maximum(close, 5.0))


def hash_synthetic_frame(n: int = 640, up: int = 64, down: int = 16,
                         up_pct: float = 0.14, down_pct: float = 0.04) -> pd.DataFrame:
    """Deterministic momentum cycles so the projected ladder rungs fill in order."""
    close = [100.0]
    while len(close) < n:
        for _ in range(up):
            if len(close) >= n:
                break
            close.append(close[-1] * (1.0 + up_pct / up))
        for _ in range(down):
            if len(close) >= n:
                break
            close.append(close[-1] * (1.0 - down_pct / down))
    return _frame_from_close(np.asarray(close[:n]), pad=0.02)


def probe_frame(*, rungs: bool) -> pd.DataFrame:
    """Deterministic prices for the scripted projection probe.

    Entry fills near 100; the stop at 95 and TP at 115 are never touched; the
    reduce half fills at the market; with ``rungs`` the three ladder limits at
    101/102/103 fill on separate bars and close the position exactly.
    """
    n = 30
    close = np.full(n, 100.0)
    if rungs:
        close[5] = 100.5
        close[7] = 101.4
        close[8] = 100.9
        close[10] = 102.4
        close[11] = 101.6
        close[13] = 103.4
        close[14:] = 103.6
    else:
        close[5:12] = 100.6
        close[12:16] = 100.2
        close[16:] = 100.4
    return _frame_from_close(close, start="2024-01-01", freq="1h", pad=0.05)


class ScriptedProbe:
    """A stub adapter that exercises every projected command on the event route."""

    def __init__(self, script: dict[int, list[OrderIntent]], *, ladder: bool,
                 on_entry=None) -> None:
        self.script = script
        self.ladder = ladder
        self.position = 0.0
        self.fills: list[dict] = []
        self.on_entry = on_entry or (lambda fill: [self._protection(fill)])

    def warmup_bars(self) -> int:
        return 0

    def _protection(self, fill) -> OrderIntent:
        side = 1 if fill.quantity > 0 else -1
        stop = fill.price * (0.95 if side > 0 else 1.05)
        if self.ladder:
            rungs = ((fill.price * (1 + side * 0.01), 0.4),
                     (fill.price * (1 + side * 0.02), 0.5),
                     (fill.price * (1 + side * 0.03), 1.0))
            return OrderIntent(kind=IntentKind.SET_PROTECTION, decision_index=fill.index,
                               earliest_phase=ExecutionPhase.RESTING_INTRABAR,
                               reason="probe_ladder", stop_price=stop, ladder=rungs,
                               quantity_basis=QuantityBasis.FRACTION_OF_REMAINING)
        return OrderIntent(kind=IntentKind.SET_PROTECTION, decision_index=fill.index,
                           earliest_phase=ExecutionPhase.RESTING_INTRABAR,
                           reason="probe_protection", stop_price=stop,
                           take_profit_price=fill.price * (1 + side * 0.15))

    def on_bar_close(self, t: int) -> BarDecision:
        return BarDecision(index=t, position_entering_bar=self.position,
                           target_after_close=self.position,
                           intents=list(self.script.get(t, [])))

    def on_fill(self, fill) -> list[OrderIntent]:
        self.position += fill.quantity
        self.fills.append({"intent_kind": fill.intent_kind.value, "quantity": fill.quantity,
                           "price": fill.price})
        if fill.intent_kind in (IntentKind.ENTER_LONG, IntentKind.ENTER_SHORT):
            return self.on_entry(fill)
        return []


def probe_amend_cancel_reduce() -> ScriptedProbe:
    return ScriptedProbe({
        1: [OrderIntent(kind=IntentKind.ENTER_LONG, decision_index=1,
                        earliest_phase=ExecutionPhase.NEXT_OPEN, reason="probe_entry")],
        3: [OrderIntent(kind=IntentKind.AMEND_PROTECTION, decision_index=3,
                        earliest_phase=ExecutionPhase.RESTING_INTRABAR,
                        reason="probe_amend", stop_price=96.0,
                        metadata={"effective_from_bar": 4})],
        5: [OrderIntent(kind=IntentKind.CANCEL_PROTECTION, decision_index=5,
                        earliest_phase=ExecutionPhase.RESTING_INTRABAR,
                        reason="probe_cancel", metadata={"protection_target": "stop"})],
        8: [OrderIntent(kind=IntentKind.REDUCE, decision_index=8,
                        earliest_phase=ExecutionPhase.NEXT_OPEN, reason="probe_reduce",
                        quantity_basis=QuantityBasis.FRACTION_OF_REMAINING,
                        quantity_value=0.5)],
        11: [OrderIntent(kind=IntentKind.EXIT_ALL, decision_index=11,
                         earliest_phase=ExecutionPhase.NEXT_OPEN, reason="probe_exit")],
    }, ladder=False)


def probe_ladder() -> ScriptedProbe:
    return ScriptedProbe({
        1: [OrderIntent(kind=IntentKind.ENTER_LONG, decision_index=1,
                        earliest_phase=ExecutionPhase.NEXT_OPEN, reason="probe_entry")],
        16: [OrderIntent(kind=IntentKind.EXIT_ALL, decision_index=16,
                         earliest_phase=ExecutionPhase.NEXT_OPEN, reason="probe_exit")],
    }, ladder=True)


def run_scripted_probe(probe: ScriptedProbe, frame: pd.DataFrame) -> EA.EventAccountRun:
    original = EA.build_adapter
    EA.build_adapter = lambda *args, **kwargs: probe
    try:
        return EA.run_event_account("A-VWAP", frame,
                                    initial=VersionWindow("PROBE", {}, 0, "probe"), schedule=[])
    finally:
        EA.build_adapter = original


# ---------------------------------------------------------------------------
# payload helpers
# ---------------------------------------------------------------------------

RF05_FREEZE_COMPONENT = "src/crypto_regime_lab/integration/event_account.py"
RF05_TEST_PATH = "tests/mode4_corrective/test_rf05_claims.py"


def _sha_in_manifest(manifest: dict, relpath: str, container: str) -> str | None:
    if container == "components":
        for rows in manifest.get("components", {}).values():
            for row in rows:
                if row["path"] == relpath:
                    return row["sha256"]
    elif container == "canonical_runners":
        for row in manifest.get("canonical_runners", []):
            if row["path"] == relpath:
                return row["sha256"]
    return None


def frozen_component_supersessions() -> list[dict]:
    """Declare the RF-05-pinned files this registered follow-up repairs.

    RF-05 froze the event account and pinned the RF-05 test as a canonical
    runner. FUP-01 adds the native command projection and extends the freeze
    guard with a declared-supersession clause, so both hashes move. The prior
    hashes stay in the RF-05 artifacts; these declarations let the RF-05 guards
    distinguish a registered repair from an undeclared drift. RF-05 results are
    never recomputed or restated.
    """
    rf05_dir = LAB_ROOT / "evidence" / STUDY_ID / "RF-05"
    entries = (
        (RF05_FREEZE_COMPONENT, rf05_dir / "freeze_manifest.json", "components",
         "FUP-01 adds the AMEND/CANCEL/REDUCE/ladder command projection to the event "
         "account; the frozen RF-05 results are not recomputed or restated"),
        (RF05_TEST_PATH, rf05_dir / "reproducibility_manifest.json", "canonical_runners",
         "FUP-01 extends the RF-05 freeze/reproducibility guards with a declared-"
         "supersession clause so post-freeze repairs must be explicitly registered"),
    )
    out = []
    for relpath, manifest_path, container, reason in entries:
        path = LAB_ROOT / relpath
        if not manifest_path.is_file() or not path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        prior = _sha_in_manifest(manifest, relpath, container)
        if prior is None:
            continue
        out.append({
            "path": relpath,
            "frozen_by": f"evidence/corrective_mode4_v3/RF-05/{manifest_path.name}",
            "frozen_sha256": prior,
            "current_sha256": sha256_file(path),
            "registered_study": "FUP-01",
            "registration_ref": ("evidence/corrective_mode4_v3/followup-studies/"
                                 "followup_studies_registration.json#/studies/0"),
            "reason": reason,
            "rf05_results_recomputed": False,
        })
    return out


def _ledger_non_null(fills: list[dict]) -> bool:
    return bool(fills) and all(all(fill.get(key) is not None for key in FILL_LEDGER_KEYS)
                               for fill in fills)


def _fee_accounting(run: EA.EventAccountRun) -> dict:
    errors = []
    for fill in run.fills:
        expected = fill["qty"] * fill["price"] * ONE_WAY_FEE
        errors.append(abs(fill["fee"] - expected) / max(expected, 1e-12))
    return {
        "one_way_fee": ONE_WAY_FEE,
        "fills_checked": len(run.fills),
        "max_abs_relative_error": (max(errors) if errors else None),
        "pass": bool(errors) and max(errors) <= 1e-9,
    }


def _episode_ladder_summary(run: EA.EventAccountRun) -> dict:
    """Walking fills: episodes that close their whole campaign via ladder rungs."""
    episodes: list[list[dict]] = []
    current: list[dict] = []
    position = 0.0
    for fill in run.fills:
        position += fill["side"] * fill["qty"]
        current.append(fill)
        if abs(position) <= 1e-9:
            episodes.append(current)
            current = []
            position = 0.0
    if current:
        episodes.append(current)
    ladder_episodes = []
    for index, episode in enumerate(episodes):
        rungs = [fill for fill in episode if fill["tag"] == "ladder"]
        entry = next((fill for fill in episode if fill["tag"] == "entry"), None)
        if len(rungs) >= 2 and entry is not None:
            closed = abs(sum(fill["qty"] for fill in rungs) - entry["qty"]) \
                <= 1e-9 * max(entry["qty"], 1.0)
            ladder_episodes.append({
                "episode": index,
                "entry_order_id": entry["order_id"],
                "entry_bar": entry["bar_index"],
                "final_bar": episode[-1]["bar_index"],
                "entry_qty": entry["qty"],
                "ladder_fills": len(rungs),
                "ladder_qty_total": float(sum(fill["qty"] for fill in rungs)),
                "remaining_qty_after_last": float(
                    episode[-1]["position_after"]),
                "closes_exactly": bool(closed),
                "tags": [fill["tag"] for fill in episode],
            })
    return {
        "episodes": len(episodes),
        "ladder_episodes_with_two_or_more_rungs": len(ladder_episodes),
        "details": ladder_episodes[:12],
    }


def run_payload(run: EA.EventAccountRun, *, extra: dict | None = None) -> dict:
    events = Counter(event["event_name"] for event in run.order_events)
    actions = Counter(command["engine_action"] for command in run.commands)
    payload = {
        "status": run.status,
        "engine_backend_resolved": run.diagnostics.get("engine_backend_resolved"),
        "entries": run.entries,
        "engine_fill_count": run.engine_fill_count,
        "unmapped_intents": run.unmapped_intents,
        "rejections": run.rejections,
        "command_actions": dict(actions),
        "engine_events_observed": dict(events),
        "per_fill_ledger_non_null": _ledger_non_null(run.fills),
        "fee_accounting": _fee_accounting(run),
        "ladder_summary": _episode_ladder_summary(run),
        "per_fill_ledger": [
            {key: fill.get(key) for key in FILL_LEDGER_KEYS} for fill in run.fills],
        "commands": run.commands,
        "order_events": run.order_events,
        "order_ids_by_version": run.order_ids_by_version,
    }
    if extra:
        payload.update(extra)
    return payload


def assertion_block(checks: dict[str, bool]) -> dict:
    return {"checks": checks, "pass": bool(checks) and all(checks.values()),
            "failed": sorted(name for name, ok in checks.items() if not ok)}


# ---------------------------------------------------------------------------
# qualification
# ---------------------------------------------------------------------------

def qualify_vwap(snapshot_root: Path) -> tuple[dict, dict]:
    """Synthetic real-adapter run (amend) + scripted probe + real BTCUSDT window."""
    frame = vwap_synthetic_frame()
    params = {**SEED_POINTS["A-VWAP"], "exit_at_vwap": True}
    synthetic = EA.run_event_account(
        "A-VWAP", frame, initial=VersionWindow("V1", params, 0, "v1"), schedule=[])
    synthetic_events = Counter(event["event_name"] for event in synthetic.order_events)
    synthetic_checks = {
        "status_evaluated": synthetic.status == "EVALUATED",
        "per_fill_ledger_non_null": _ledger_non_null(synthetic.fills),
        "entry_fill_observed": any(fill["tag"] == "entry" for fill in synthetic.fills),
        "amend_command_projected": any(c["engine_action"] == "amend" for c in synthetic.commands),
        "amend_event_observed": synthetic_events.get("amend", 0) >= 1,
    }

    probe_run = run_scripted_probe(probe_amend_cancel_reduce(), probe_frame(rungs=False))
    probe_events = Counter(event["event_name"] for event in probe_run.order_events)
    probe_actions = Counter(command["engine_action"] for command in probe_run.commands)
    probe_checks = {
        "status_evaluated": probe_run.status == "EVALUATED",
        "amend_command_projected": probe_actions.get("amend", 0) >= 1,
        "amend_event_observed": probe_events.get("amend", 0) >= 1,
        "cancel_command_projected": probe_actions.get("cancel", 0) >= 1,
        "cancel_event_observed": probe_events.get("cancel", 0) >= 1,
        "reduce_fill_observed": any(fill["tag"] == "reduce" for fill in probe_run.fills),
        "position_flat_at_end": abs(float(probe_run.positions[-1])) <= 1e-9,
    }

    real_frame = pilot_runner.load_frame(snapshot_root, "BTCUSDT", "15min")
    real = real_frame.loc[VWAP_REAL_WINDOW[0]:VWAP_REAL_WINDOW[1]]
    real_run = EA.run_event_account(
        "A-VWAP", real, initial=VersionWindow("V1", params, 0, "v1"), schedule=[])
    real_events = Counter(event["event_name"] for event in real_run.order_events)
    real_checks = {
        "status_evaluated": real_run.status == "EVALUATED",
        "per_fill_ledger_non_null": _ledger_non_null(real_run.fills),
        "entry_fill_observed": any(fill["tag"] == "entry" for fill in real_run.fills),
        "amend_event_observed": real_events.get("amend", 0) >= 1,
        "protection_or_exit_fill_observed": any(
            fill["tag"] in ("stop", "tp") for fill in real_run.fills),
    }

    checks = {"synthetic": assertion_block(synthetic_checks),
              "projection_probe": assertion_block(probe_checks),
              "real_btcusdt_window": assertion_block(real_checks)}
    all_pass = all(block["pass"] for block in checks.values())
    alpha = {
        "status": "QUALIFIED_EVENT" if all_pass else "BLOCKED_CAPABILITY",
        "adapter_version": "canonical_v1",
        "intents_exercised": ["enter_long", "enter_short", "set_protection",
                              "amend_protection", "cancel_protection", "reduce", "exit_all"],
        "supported_commands": [
            "PLACE MARKET (entry, non-reduce-only)",
            "PLACE STOP_MARKET reduce_only (bracket stop)",
            "PLACE LIMIT reduce_only (bracket take profit)",
            "AMEND(target_order_id=tracked stop trigger)",
            "AMEND(target_order_id=tracked limit price)",
            "CANCEL(target_order_id=tracked protection)",
            "PLACE MARKET reduce_only (REDUCE from quantity_basis/quantity_value)",
        ],
        "synthetic": run_payload(synthetic, extra={
            "fixture": {"kind": "synthetic", "bars": int(len(frame)), "seed": 2,
                        "params_override": {"exit_at_vwap": True},
                        "reason": ("the canonical seed keeps exit_at_vwap off (SD-VWAP-04); "
                                   "the registered True variant must still be expressible")}}),
        "projection_probe": run_payload(probe_run, extra={
            "fixture": {"kind": "scripted_probe", "bars": int(len(probe_frame(rungs=False))),
                        "commands": ["amend_protection", "cancel_protection", "reduce",
                                     "exit_all"]}}),
        "real_btcusdt_window": run_payload(real_run, extra={
            "fixture": {"kind": "real_snapshot", "symbol": "BTCUSDT", "interval": "15min",
                        "window": list(VWAP_REAL_WINDOW),
                        "source": f"{SNAPSHOT_ID}/{PRODUCT}",
                        "bars": int(len(real)),
                        "selection_reason": "command coverage, not performance"}}),
        "assertions": checks,
        "reason": ("QUALIFIED_EVENT: AMEND_PROTECTION reaches the engine on the tracked "
                   "protection id at the next-bar effective phase, and CANCEL/REDUCE/reported "
                   "fills were observed as engine order events"
                   if all_pass else
                   "BLOCKED_CAPABILITY: " + ", ".join(
                       f"{name}:{','.join(block['failed'])}"
                       for name, block in checks.items() if not block["pass"])),
        "missing_command": None if all_pass else "OrderAction.AMEND(target_order_id=tracked)",
    }
    return alpha, checks


def qualify_hash(snapshot_root: Path) -> tuple[dict, dict]:
    """Scripted ladder probe + real BTCUSDT window with full ladder campaigns."""
    probe_run = run_scripted_probe(probe_ladder(), probe_frame(rungs=True))
    rungs = [fill for fill in probe_run.fills if fill["tag"] == "ladder"]
    probe_checks = {
        "status_evaluated": probe_run.status == "EVALUATED",
        "per_fill_ledger_non_null": _ledger_non_null(probe_run.fills),
        "multiple_ladder_partial_fills": len(rungs) >= 2,
        "remaining_reaches_zero": abs(float(probe_run.positions[-1])) <= 1e-9,
        "partial_fills_are_reduce": all(fill["intent_kind"] == "reduce" for fill in rungs),
        "no_amend_or_cancel_rejection": not probe_run.rejections,
    }
    probe_summary = _episode_ladder_summary(probe_run)
    probe_checks["single_campaign_closes_exactly"] = any(
        "closes_exactly" in detail and detail["closes_exactly"]
        for detail in probe_summary["details"])

    synthetic = EA.run_event_account(
        "A-HASH", hash_synthetic_frame(),
        initial=VersionWindow("V1", dict(SEED_POINTS["A-HASH"]), 0, "v1"), schedule=[])
    synthetic_summary = _episode_ladder_summary(synthetic)
    synthetic_ladder_fills = sum(1 for fill in synthetic.fills if fill["tag"] == "ladder")
    synthetic_checks = {
        "status_evaluated": synthetic.status == "EVALUATED",
        "per_fill_ledger_non_null": _ledger_non_null(synthetic.fills),
        "multiple_ladder_partial_fills": synthetic_ladder_fills >= 2,
        "campaign_closes_exactly": any(detail["closes_exactly"]
                                       for detail in synthetic_summary["details"]),
        "protection_fill_observed": any(
            fill["tag"] in ("stop", "ladder", "tp") for fill in synthetic.fills),
    }

    real_frame = pilot_runner.load_frame(snapshot_root, "BTCUSDT", "15min")
    real = real_frame.loc[HASH_REAL_WINDOW[0]:HASH_REAL_WINDOW[1]]
    real_run = EA.run_event_account(
        "A-HASH", real, initial=VersionWindow("V1", dict(SEED_POINTS["A-HASH"]), 0, "v1"),
        schedule=[])
    real_summary = _episode_ladder_summary(real_run)
    real_fee = _fee_accounting(real_run)
    real_ladder_fills = sum(1 for fill in real_run.fills if fill["tag"] == "ladder")
    real_checks = {
        "status_evaluated": real_run.status == "EVALUATED",
        "per_fill_ledger_non_null": _ledger_non_null(real_run.fills),
        "multiple_ladder_partial_fills": real_ladder_fills >= 2,
        "campaign_closes_exactly": any(detail["closes_exactly"]
                                       for detail in real_summary["details"]),
        "remaining_reaches_zero": any(abs(detail["remaining_qty_after_last"]) <= 1e-9
                                      for detail in real_summary["details"]),
        "fees_match_one_way_rate_per_partial": real_fee["pass"],
        "no_rejections": not real_run.rejections,
    }

    checks = {"projection_probe": assertion_block(probe_checks),
              "synthetic": assertion_block(synthetic_checks),
              "real_btcusdt_window": assertion_block(real_checks)}
    all_pass = all(block["pass"] for block in checks.values())
    alpha = {
        "status": "QUALIFIED_EVENT" if all_pass else "BLOCKED_CAPABILITY",
        "adapter_version": "canonical_v1",
        "intents_exercised": ["enter_long", "enter_short", "set_protection", "reduce", "exit_all"],
        "supported_commands": [
            "PLACE MARKET (entry, non-reduce-only)",
            "PLACE STOP_MARKET reduce_only (ladder stop)",
            "PLACE LIMIT reduce_only per ladder rung (fraction_of_remaining)",
            "PLACE MARKET reduce_only (REDUCE from quantity_basis/quantity_value)",
            "CANCEL(target_order_id=tracked protection) on flatten/version cleanup",
            "AMEND(target_order_id=tracked protection)",
        ],
        "synthetic": run_payload(synthetic, extra={
            "fixture": {"kind": "synthetic", "bars": int(len(hash_synthetic_frame())),
                        "params": "registered seed, unchanged",
                        "ladder_summary": synthetic_summary}}),
        "projection_probe": run_payload(probe_run, extra={
            "fixture": {"kind": "scripted_probe", "bars": int(len(probe_frame(rungs=True))),
                        "commands": ["set_protection ladder", "exit_all"],
                        "ladder_summary": probe_summary}}),
        "real_btcusdt_window": run_payload(real_run, extra={
            "fixture": {"kind": "real_snapshot", "symbol": "BTCUSDT", "interval": "15min",
                        "window": list(HASH_REAL_WINDOW),
                        "source": f"{SNAPSHOT_ID}/{PRODUCT}",
                        "bars": int(len(real)),
                        "selection_reason": "command coverage, not performance",
                        "ladder_summary": real_summary}}),
        "assertions": checks,
        "reason": ("QUALIFIED_EVENT: the ordered ladder emits one reduce-only LIMIT per rung, "
                   "partial fills reach the adapter as REDUCE, the remaining quantity reaches "
                   "zero on the final rung and each partial pays the one-way fee"
                   if all_pass else
                   "BLOCKED_CAPABILITY: " + ", ".join(
                       f"{name}:{','.join(block['failed'])}"
                       for name, block in checks.items() if not block["pass"])),
        "missing_command": None if all_pass else "OrderAction.PLACE(reduce_only LIMIT per rung)",
    }
    return alpha, checks


# ---------------------------------------------------------------------------
# route matrix
# ---------------------------------------------------------------------------

def build_route_matrix(capability: dict) -> dict:
    full = json.loads((RF04_DIR / "paired_discovery_full.json").read_text(encoding="utf-8"))
    full_index = {cell["cell"]: index for index, cell in enumerate(full["cells"])}
    coverage = json.loads((RF04_DIR / "cell_coverage.json").read_text(encoding="utf-8"))
    coverage_by_cell = {cell["cell"]: cell for cell in coverage["cells"]}
    rf02 = json.loads((RF02_DIR / "pilot_and_route_matrix.json").read_text(encoding="utf-8"))
    rf02_by_cell = {cell["cell"]: cell for cell in rf02["route_matrix"]["cells"]}
    new_status = {alpha: capability["alphas"][alpha]["status"] for alpha in ("A-VWAP", "A-HASH")}
    new_reason = {alpha: capability["alphas"][alpha]["reason"]
                  for alpha in ("A-VWAP", "A-HASH")}

    cells = []
    for alpha in ALPHAS:
        for symbol in SYMBOLS:
            name = f"{alpha}/{symbol}"
            if alpha in ("A-SC", "A-HMA"):
                row = full_index.get(name)
                entry = full["cells"][row] if row is not None else {}
                prior = coverage_by_cell.get(name, {})
                route_status = entry.get("route_status", rf02_by_cell[name]["route_status"])
                cells.append({
                    "cell": name, "alpha_id": alpha, "symbol": symbol, "route": "event",
                    "registered_route": entry.get("registered_route"),
                    "route_status": route_status,
                    "route_role": entry.get("route_role"),
                    "reason": entry.get("route_reason") or rf02_by_cell[name]["reason"],
                    "source": {
                        "kind": "committed_rf04_cell",
                        "artifact": "evidence/corrective_mode4_v3/RF-04/paired_discovery_full.json",
                        "pointer": f"#/cells/{row}",
                        "run_status": prior.get("coverage_status"),
                    },
                    "metrics": None,
                    "metrics_reason": ("route artifact only; the executed RF-04 account metrics "
                                       "live in paired_discovery_full.json and are not restated "
                                       "or zero-filled here"),
                    "discovery_run": prior.get("coverage_status"),
                })
            else:
                cap = capability["alphas"][alpha]
                cells.append({
                    "cell": name, "alpha_id": alpha, "symbol": symbol, "route": "event",
                    "registered_route": "event",
                    "route_status": new_status[alpha],
                    "route_role": "QUALIFIED_BY_FUP01",
                    "reason": new_reason[alpha],
                    "source": {
                        "kind": "fup01_native_event_capability",
                        "artifact": "evidence/corrective_mode4_v3/FUP-01/"
                                    "native_event_capability.json",
                        "pointer": f"#/alphas/{alpha}",
                        "run_status": cap["real_btcusdt_window"]["status"],
                    },
                    "metrics": None,
                    "metrics_reason": ("no paired discovery run exists on this cell in any "
                                       "committed artifact; metrics are null and are never "
                                       "replaced with a zero or an estimate"),
                    "discovery_run": "NOT_RUN",
                })
    counts = Counter(cell["route_status"] for cell in cells)
    return {
        "schema": "regime_lab.fup01_route_matrix.v1",
        "phase": "FUP-01",
        "study_id": STUDY_ID,
        "rule": ("route decisions come from capability and schema before any outcome; a cell "
                 "that cannot preserve alpha semantics is BLOCKED_CAPABILITY with the exact "
                 "missing command, never silently rerouted; a cell with no discovery run "
                 "carries null metrics and a reason, never a zero"),
        "status_vocabulary": ["QUALIFIED_FAST", "QUALIFIED_EVENT", "BLOCKED_CAPABILITY",
                              "INSUFFICIENT_DATA"],
        "sources": [
            {"artifact": "evidence/corrective_mode4_v3/RF-04/paired_discovery_full.json",
             "sha256": sha256_file(RF04_DIR / "paired_discovery_full.json")},
            {"artifact": "evidence/corrective_mode4_v3/RF-04/cell_coverage.json",
             "sha256": sha256_file(RF04_DIR / "cell_coverage.json")},
            {"artifact": "evidence/corrective_mode4_v3/RF-02/pilot_and_route_matrix.json",
             "sha256": sha256_file(RF02_DIR / "pilot_and_route_matrix.json")},
        ],
        "counts": {status: int(counts.get(status, 0)) for status in
                   ("QUALIFIED_FAST", "QUALIFIED_EVENT", "BLOCKED_CAPABILITY",
                    "INSUFFICIENT_DATA")},
        "cells": cells,
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                        help="overwrite an existing capability artifact explicitly")
    args = parser.parse_args()
    policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID, lab_run_id=RUN_ID)
    capability_path = RUN_DIR / "native_event_capability.json"
    if capability_path.exists() and not args.force:
        raise SystemExit(f"{capability_path} exists; pass --force to supersede explicitly")

    snapshot_root = policy.lab_root / "snapshots" / SNAPSHOT_ID
    started = time.perf_counter()
    vwap_alpha, vwap_checks = qualify_vwap(snapshot_root)
    hash_alpha, hash_checks = qualify_hash(snapshot_root)
    capability = {
        "schema": "regime_lab.fup01_native_event_capability.v1",
        "phase": "FUP-01",
        "study_id": STUDY_ID,
        "engine": {
            "package": "quantbt",
            "pinned_version": "1.1.1",
            "backend_requested": "native_event",
            "backend_resolved": vwap_alpha["real_btcusdt_window"]["engine_backend_resolved"],
            "supported_order_actions": ["place", "amend", "cancel", "replace"],
            "oco_group_id_supported": True,
            "evidence": ("order events observed in the runs below; the scripted probe shows "
                         "amend/cancel/reduce/ladder commands actually executed by the engine"),
        },
        "projection_contract": {
            "amend_target": "tracked protection order id per parameter version",
            "cancel_target": "tracked protection order id per parameter version",
            "reduce_sizing": "quantity_basis/quantity_value, capped at the open position",
            "ladder_sizing": "fraction_of_remaining applied sequentially per rung",
            "effective_phase": "next_bar (the engine applies commands at the next bar close)",
            "unsupported_rule": "unknown/unprojectable intents force NOT_EVALUATED",
        },
        "alphas": {"A-VWAP": vwap_alpha, "A-HASH": hash_alpha},
        "frozen_component_supersessions": frozen_component_supersessions(),
        "blocked_capabilities": [
            {"alpha_id": alpha, "missing_command": capability_alpha["missing_command"],
             "reason": capability_alpha["reason"]}
            for alpha, capability_alpha in (("A-VWAP", vwap_alpha), ("A-HASH", hash_alpha))
            if capability_alpha["status"] != "QUALIFIED_EVENT"],
        "runtime_seconds": round(time.perf_counter() - started, 3),
    }
    capability_record = writer.write_json(
        "native_event_capability.json", capability, schema=capability["schema"])

    matrix = build_route_matrix(capability)
    matrix_record = writer.write_json("route_matrix.json", matrix, schema=matrix["schema"])
    summary = {
        "native_event_capability": {"sha256": capability_record["sha256"],
                                    "A-VWAP": vwap_alpha["status"],
                                    "A-HASH": hash_alpha["status"]},
        "route_matrix": {"sha256": matrix_record["sha256"], "counts": matrix["counts"]},
        "checks": {"A-VWAP": {name: block["pass"] for name, block in vwap_checks.items()},
                   "A-HASH": {name: block["pass"] for name, block in hash_checks.items()}},
    }
    print(json.dumps(summary, indent=2))
    blocked = capability["blocked_capabilities"]
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
