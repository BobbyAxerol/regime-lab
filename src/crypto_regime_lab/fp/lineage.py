"""FP-02 item 7: lineage from a selection to actual activation/orders/fills.

Built by scanning ``version_by_bar`` itself (``EventAccountStrategy``'s own
per-bar record of which version was active) into contiguous runs, rather
than reconstructing boundaries from ``diagnostics["switches"]`` metadata --
the engine's own ground truth showed why on the first real run: even the
INITIAL version is not active from bar 0. ``version_by_bar`` carries two
sentinels before real trading starts (``event_account.py``):

* ``FLAT_UNTIL_READY`` -- before ``bar >= initial.requested_at_bar``, no
  adapter exists yet.
* ``WARMING`` -- an adapter exists (initial or just-switched) but has not
  yet seen ``warmup_bars()`` live bars, so it makes no decisions -- guide
  9.5's activation delay, which also applies to the INITIAL version, not
  only to switches.

Fills CAN occur during a ``WARMING`` run (a resting protective exit on a
position opened by the version being warmed away FROM): this module does
not guess which prior version such a fill belongs to. It reports the
sentinel run's own fill count honestly rather than attributing it
backward, which the guide (10.5, "không lấy full-history... thay exposure")
treats as the correct default over a convenient smoothing.

This module relies on one property of how ``evaluator.py`` builds each
``VersionWindow``: ``parameter_version == activation_id`` always, so a
non-sentinel ``version_by_bar`` entry directly names the activation it
belongs to -- no separate id<->version lookup is built or trusted.
"""
from __future__ import annotations

LINEAGE_SCHEMA = "regime_lab.fp02_lineage.v1"
SENTINELS = ("FLAT_UNTIL_READY", "WARMING")


class LineageError(ValueError):
    """A lineage input was internally inconsistent -- never silently patched."""


def _runs(version_by_bar: list[str]) -> list[tuple[int, int, str]]:
    """Contiguous [start, end) runs of one repeated value, in bar order."""
    runs: list[tuple[int, int, str]] = []
    start = 0
    for i in range(1, len(version_by_bar) + 1):
        if i == len(version_by_bar) or version_by_bar[i] != version_by_bar[start]:
            runs.append((start, i, version_by_bar[start]))
            start = i
    return runs


def build_lineage(*, switches: list[dict], version_by_bar: list[str],
                  fills: list[dict], initial_version: str) -> dict:
    if not version_by_bar:
        raise LineageError("version_by_bar is empty: nothing to attribute")
    requested_at_bar = {initial_version: 0}
    for s in switches:
        requested_at_bar[s["activation_id"]] = s["requested_at_bar"]
    effective_at_bar = {s["activation_id"]: s["effective_at_bar"] for s in switches}

    rows: list[dict] = []
    for start, end, value in _runs(version_by_bar):
        row_fills = [f for f in fills if start <= int(f["bar_index"]) < end]
        if value in SENTINELS:
            rows.append({
                "activation_id": None, "parameter_version": None, "sentinel": value,
                "requested_at_bar": None, "effective_at_bar": None,
                "bar_range": [start, end], "fill_count": len(row_fills), "fills": row_fills,
                "note": ("no adapter yet (flat)" if value == "FLAT_UNTIL_READY"
                         else "adapter warming, no decisions; fills here (if any) are a "
                              "resting exit from the version being left, not attributed "
                              "to any activation by this module"),
            })
            continue
        rows.append({
            "activation_id": value, "parameter_version": value,
            "requested_at_bar": requested_at_bar.get(value),
            "effective_at_bar": effective_at_bar.get(value, start if value == initial_version else None),
            "bar_range": [start, end], "fill_count": len(row_fills), "fills": row_fills,
        })

    requested_ids = {initial_version} | {s["activation_id"] for s in switches}
    activated_ids = {r["activation_id"] for r in rows if r["activation_id"] is not None}
    pending_ids = requested_ids - activated_ids
    for activation_id in pending_ids:
        rows.append({
            "activation_id": activation_id, "parameter_version": None,
            "requested_at_bar": requested_at_bar.get(activation_id),
            "effective_at_bar": None, "bar_range": None, "fill_count": 0, "fills": [],
            "note": "requested but never activated within this run's window",
        })

    attributed = sum(r["fill_count"] for r in rows)
    if attributed != len(fills):
        raise LineageError(
            f"{len(fills)} fills but only {attributed} attributed across all runs "
            "-- every fill must land in exactly one bar range")
    return {
        "schema": LINEAGE_SCHEMA,
        "total_bars": len(version_by_bar),
        "activations": rows,
        "activations_effected": len(activated_ids),
        "activations_pending": len(pending_ids),
        "fills_total": len(fills),
        "fills_attributed": attributed,
        "fills_during_sentinel": sum(r["fill_count"] for r in rows if r["activation_id"] is None
                                     and r.get("sentinel")),
    }
