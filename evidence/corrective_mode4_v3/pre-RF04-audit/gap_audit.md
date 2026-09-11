# Pre-RF04 gap audit

Generated before RF-04. Method: compare every RF phase against the merged plan's
tasks/outputs/exit, inspect the committed artifacts, and re-run the full suite.
No new market run.

## Regression check

| | |
|---|---|
| full suite before | **3 failed / 810 passed** |
| causes | 2 historical tests asserting the RF-03-superseded raising contract; 1 unreachable public helper (`execution_slice_after`) |
| fix | tests updated to the repaired contract (fewer cutoffs, no padding); helper deleted |
| after | 30 passed across the affected tests + `tests/mode4_corrective` (27) |

## Gaps

| id | phase | severity | requirement | status | action |
|---|---|---|---|---|---|
| G1 | RF-01.4 | medium | positive-control plan | PARTIAL | write the plan in RF-04.0 |
| G2 | RF-01/A15 | **high** | corrected MDE units frozen before RF-04 | OPEN | measure actual turnover/account units, freeze before results |
| G3 | RF-01 | medium | spec revisions for schema/sizing | OPEN | append revisions (A05 3→4 choices; A08 signal_notional, alloc 0.1) |
| G4 | RF-02.2 | **high** | `_exit_oracle` out of the active evaluator | PARTIAL | explicit quarantine/raise outside historical tests |
| G5 | RF-02.2 | **high** | every command executed/rejected/unsupported | OPEN | consume `order_events_this_bar` rejections; invalidate on rejection |
| G6 | RF-02.3 | medium | timing pinned for the scored/final account | OPEN | apply A06 to the WFO final execution or register the close-target cohort |
| G7 | RF-02.6 | medium | A-SC + one order-sensitive alpha on real snapshot | PARTIAL | rerun pilot with A-HMA on the real BTCUSDT slice |
| G8 | RF-02 | low | parity, thin diff, failed-intent ledger, full profile | MISSING | produce if still required |
| G9 | RF-02.1 | low | route registry consistent with the pilot | OPEN | update statuses from PENDING_QUALIFICATION |
| G10 | RF-03.1/2 | **high** | model ladder, inner-only scaler, common-coordinate mapping, fixed-target ablation | DISPOSITIONED_NOT_IMPLEMENTED | implement or formally scope out before any model claim |
| G11 | RF-03.4 | **high** | QuantBT-simulated positive control changing params/trades | MISSING | run one synthetic positive-control engine session |
| G12 | RF-03.3 | medium | trigger→search→ready→activation log | PARTIAL | wire the lifecycle log |
| G13 | RF-03 | medium | prefix/streaming parity after the emission change | OPEN | record a parity artifact |
| G14 | RF-03.5 | medium | A12/A13 response runner wiring | PARTIAL | wire or mark NOT_IMPLEMENTED |

Counts: **5 high / 8 medium / 2 low**.

## Verdict

- RF-01 `TECHNICAL_ONLY` — accepted, with G1–G3 to clear.
- RF-02 `PARTIAL_TECHNICAL_CLOSURE` — accepted for the proven paths; G4–G9 remain.
- RF-03 `TECHNICAL_PASS` at controller level; G10/G11 are real implementation gaps
  (model/ablation + engine positive control), not documentation gaps.
- RF-04 must start with a clearing step for **G2/G4/G5** (validity), then G3, G6, G7.
  G10–G14 may be scoped to RF-05 if the primary timing contrast does not depend on
  the model/response layer, but that scope decision must be registered.
