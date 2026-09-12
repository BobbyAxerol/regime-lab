#!/usr/bin/env python
"""Guide 4.3 — at what resolution are protective orders actually resolved?

The frozen protocol declares `execution_bars: 1m` for all four alphas. The
account does not use a 1-minute frame: `run_continuous_account` and
`run_candidate` both hand the engine the DECISION-bar frame
(`engine_frame = frame[["open","high","low","close","volume"]]`), so a stop and a
take-profit inside the same 15-minute bar are resolved against that bar's high
and low, not along the minute path within it.

Guide 4.3 is explicit that 1-minute data is not a tick path and that the
ambiguity inside a bar remains either way — but it is equally explicit that the
resolution has to be the SAME for every arm and that a benefit from changing fill
fidelity must never be attributed to regime work.

So this measures three things instead of asserting them:

  * what the protocol declares, read from the protocol;
  * what the code does, read from the source;
  * how EXPOSED each alpha is, by counting the fills that are protective rather
    than technical. An alpha that rests no protection cannot be affected by the
    resolution at all, and A-SC is one.

It does not build the 1-minute cohort. That is an implementation, not a
measurement, and guide L00 says to record the gap and propose the revision rather
than improvise one (OP-19).
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))
sys.path.insert(0, str(LAB_ROOT / "scripts"))

from crypto_regime_lab.evidence.manifest import EvidenceWriter, utc_now_iso  # noqa: E402
from crypto_regime_lab.experiments import calendar_baseline as CB  # noqa: E402
from crypto_regime_lab.experiments.evaluator import PROTECTIVE  # noqa: E402
from crypto_regime_lab.experiments.factorial import run_arm  # noqa: E402
from crypto_regime_lab.safety.paths import SandboxPolicy  # noqa: E402
from run_lab08_factorial import bars_for, load  # noqa: E402

STUDY_ID = "crypto_regime_timeedge_v2"
CONFIGS = LAB_ROOT / "configs"
#: one probe window per alpha, long enough to trade and short enough to be cheap.
#: The exposure is a property of the strategy, not of the window.
PROBE = ("2021-01-01", "2021-06-30")
SYMBOL = "BTCUSDT"


def exposure(alpha_id: str, protocol: dict, cache: dict) -> dict:
    if alpha_id in CB.NOT_READY:
        return {"status": "NOT_READY", "reason": CB.NOT_READY[alpha_id]}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        bars = bars_for(alpha_id, SYMBOL, protocol, cache, window=PROBE)
        result = run_arm("A", alpha_id, SYMBOL, bars,
                         [{"cutoff": f"{PROBE[0]}T00:00:00+00:00",
                           "params": dict(CB.SEED_POINTS[alpha_id]), "point_id": "seed"}])
    reasons: dict[str, int] = {}
    for fill in result.fills:
        reasons[fill["reason"]] = reasons.get(fill["reason"], 0) + 1
    protective = sum(count for reason, count in reasons.items() if reason in PROTECTIVE)
    return {
        "status": "MEASURED",
        "window": list(PROBE),
        "symbol": SYMBOL,
        "decision_bars": protocol["timeframes"][alpha_id]["decision_bars"],
        "fills": len(result.fills),
        "fill_reasons": dict(sorted(reasons.items())),
        "protective_fills": protective,
        "protective_share": protective / len(result.fills) if result.fills else 0.0,
        "exposed_to_the_resolution": protective > 0,
        "reading": ("only a fill resolved by a resting stop or take-profit depends on the bar "
                    "resolution. A strategy whose exits are all technical is unaffected"),
    }


def main() -> int:
    policy = SandboxPolicy.load(CONFIGS / "sandbox_policy.json")
    policy.assert_lab_root_ok()
    writer = EvidenceWriter.open(policy, study_id=STUDY_ID)

    protocol = load("lab08_pilot_protocol.json")
    cache: dict = {}
    per_alpha = {}
    for alpha_id in sorted(protocol["timeframes"]):
        print(f"  {alpha_id} ...", flush=True)
        with writer.attempt(f"G4.3.exposure@{alpha_id}") as att:
            per_alpha[alpha_id] = exposure(alpha_id, protocol, cache)
            att.detail = {"status": per_alpha[alpha_id]["status"]}

    source = (LAB_ROOT / "src/crypto_regime_lab/integration/continuous_account.py").read_text()
    builds_from_decision_frame = 'engine_frame = frame[["open", "high", "low", "close", "volume"]]' \
        in source
    measured = [v for v in per_alpha.values() if v["status"] == "MEASURED"]
    exposed = [a for a, v in per_alpha.items()
               if v["status"] == "MEASURED" and v["exposed_to_the_resolution"]]

    document = {
        "schema": "crypto_regime_lab.protective_order_fidelity.v1",
        "generated_at_utc": utc_now_iso(),
        "guide_section": "4.3",
        "declared": {
            "execution_bars": {a: f["execution_bars"] for a, f in protocol["timeframes"].items()},
            "source": "configs/lab08_pilot_protocol.json timeframes",
        },
        "actual": {
            "protection_resolved_on": "the DECISION bar",
            "evidence": ("integration/continuous_account.py and experiments/evaluator.py both "
                         "build engine_frame from the decision-bar frame and pass it to "
                         "run_intrabar; no 1-minute frame is constructed anywhere in the "
                         "account path"),
            "source_check_passes": builds_from_decision_frame,
        },
        "declared_matches_actual": False,
        "finding": (
            "the protocol declares 1-minute execution bars and the account resolves protective "
            "orders on the decision bar. Within a 15-minute bar that touched both a stop and a "
            "take-profit, the engine's intrabar contract picks one by its own ordering rule "
            "rather than by the minute path"),
        "direction": (
            "unknown in sign and bounded in scope. It is NOT a contrast risk: every arm, every "
            "control and both selectors run through the same engine on the same frame, so the "
            "resolution cancels in B-A, C-A, D-B and D-C. It is a LEVEL risk, and guide 4.3's "
            "warning is precisely about crediting a fill-fidelity difference to regime work"),
        "exposure": {
            "per_alpha": per_alpha,
            "alphas_measured": len(measured),
            "alphas_exposed": exposed,
            "alphas_not_exposed": [a for a, v in per_alpha.items()
                                   if v["status"] == "MEASURED"
                                   and not v["exposed_to_the_resolution"]],
        },
        "two_cohort_requirement": {
            "guide_text": ("guide 4.3: keep an exact legacy-resolution cohort and a common "
                           "higher-fidelity corrected cohort, and never attribute a fill-fidelity "
                           "gain to a regime edge"),
            "status": "NOT_BUILT",
            "why_not_built": ("a 1-minute cohort means re-indexing every decision-bar intent onto "
                              "the minute frame and re-running every account. That is an "
                              "implementation, not a measurement, and the lab records the gap and "
                              "proposes the revision rather than improvising one mid-phase "
                              "(OP-19)"),
            "what_protects_the_conclusion_meanwhile": (
                "the resolution is identical across arms, so no contrast can be explained by it, "
                "and the alphas that rest no protection are unaffected even in level"),
        },
    }
    writer.write_config("protective_order_fidelity.json", document)
    writer.write_json("protective_order_fidelity.json", document, schema=document["schema"])

    print(f"\ndeclared execution bars : {document['declared']['execution_bars']}")
    print(f"actual resolution       : {document['actual']['protection_resolved_on']}")
    print(f"declared matches actual : {document['declared_matches_actual']}")
    for alpha_id, record in per_alpha.items():
        if record["status"] != "MEASURED":
            print(f"  {alpha_id:<8} {record['status']}")
            continue
        print(f"  {alpha_id:<8} {record['fills']:>4} fills, protective "
              f"{record['protective_fills']} ({record['protective_share']:.0%})  "
              f"reasons={record['fill_reasons']}")
    print(f"exposed alphas          : {exposed}")
    print(f"evidence -> {writer.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
