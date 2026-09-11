"""L03.5 — external enrichment: inventory only, never acquisition.

The guide is explicit that enrichment is optional and must not become scope
creep, that the primary lab must run on server-core alone, and that nothing is
bought. This module therefore records what each source WOULD mean and the rule
for using it, and states plainly that none has been acquired.

Acquisition, if it ever happens, is a separate allow-listed stage that writes
into the lab. Nothing here opens a socket.
"""

from __future__ import annotations

SOURCES = {
    "defillama_stablecoin_supply": {
        "guide_ref": "S11",
        "correct_meaning": "slow supply / composition / liquidity context",
        "usage_rule": "snapshot endpoint availability and revisions; a rise in raw TVL is NOT an inflow",
        "cadence": "daily",
        "licence_check_required": True,
    },
    "whale_alert_published_alerts": {
        "guide_ref": "S12",
        "correct_meaning": "an archive of PUBLISHED large-transfer alerts",
        "usage_rule": "use the publication timestamp, deduplicate event ids, carry coverage masks; "
                      "this is not whale netflow and not the full transaction set",
        "cadence": "event",
        "licence_check_required": True,
    },
    "farside_btc_etf_flows": {
        "guide_ref": "S13",
        "correct_meaning": "daily ETF flow table over the period the product existed",
        "usage_rule": "respect the publication lag; never fill 0 before the product existed",
        "cadence": "daily",
        "licence_check_required": True,
    },
    "coin_metrics_community": {
        "guide_ref": "S14",
        "correct_meaning": "a subset of network and market metrics",
        "usage_rule": "review coverage and the non-commercial terms before any use; free does not "
                      "mean unrestricted commercial use",
        "cadence": "daily",
        "licence_check_required": True,
    },
}


def enrichment_inventory() -> dict:
    return {
        "schema": "crypto_regime_lab.enrichment_inventory.v1",
        "acquired": [],
        "sources": {
            name: {**spec, "status": "NOT_ACQUIRED",
                   "reason": "network is off in run/certify/report stages and no licence review has "
                             "been performed; acquisition would be a separate allow-listed stage"}
            for name, spec in SOURCES.items()
        },
        "primary_depends_on_enrichment": False,
        "primary_runs_without_it": True,
        "policy": (
            "the lab buys no data. An enrichment block enters the model only with demonstrated "
            "rights and coverage, and is always compared against the core cohort on the SAME "
            "interval so a short recent window cannot masquerade as an improvement (guide 6.5)."
        ),
        "cohort_label": "FREE_ENRICHED (empty on this run)",
    }
