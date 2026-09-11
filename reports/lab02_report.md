# LAB-02 — Four-alpha canonical adaptation and domain certification

**Status: PASS.** 44/45 guide requirements DONE after a second audit, 1 recorded as a measured blocker.
`pytest tests -q` → **210 passed** (LAB-01 97 → LAB-02 first pass 178 → second audit 210). `scripts/run_lab02.py` → **STATUS = PASS**.
**Date:** 2026-09-09 · **Study:** `crypto_regime_timeedge_v2`

## 1. Exit gate — per alpha

| Alpha | Status | Adapter | Synthetic suite |
|---|---|---|---|
| A-SC | **READY_FOR_RESEARCH** | `SignalCombineAdapterV1` | 260 bars, 1 entry, engine round trip |
| A-HMA | **READY_FOR_RESEARCH** | `AdaptiveHmaEventAdapterV1` | 160 bars, 2 entries, 1 technical exit |
| A-VWAP | **READY_FOR_RESEARCH** | `VwapMeanReversionEventAdapterV1` | 1200 bars, 6 entries, 6 time-stop exits |
| A-HASH | **NOT_READY_SPECIFIC_BLOCKER** | `HashMomentumEventAdapterV1` (built and tested) | 400 bars, 1 entry, engine round trip |

A-HASH keeps all five of its cells in the 20-cell matrix with null metrics. It is **not** swapped for another alpha and **not** removed from any denominator.

## 2. The A-HASH blocker — measured, not assumed

The canonical alpha needs three things on one route: a next-open entry, a protective stop, and partial reduce-only exits. Neither route on this install provides all three:

| Capability | `intrabar_bracket_v1` | `orders` route |
|---|---|---|
| next-open entry fill | **yes** | no — a market order fills at the close of the stamped bar |
| protective stop | **yes** | no — `NotImplementedError: unsupported order_type=stop_market` |
| single take profit | yes | yes |
| partial reduce-only ladder | **no** — the tape has one `take_profit_value` | **yes** — 10 → 5 → 2.5 → 0 verified |
| same-bar stop+TP conservative | yes | — |
| funding at event | yes | — |
| forced-flat / mark-open | yes / yes | — |

Recorded as `BLOCKED_CAPABILITY` per guide §4.4, with a **declared reduced-fidelity variant** (`A-HASH-single-tp-v1`, the final rung only) that may never be reported as the canonical alpha. Owner: LAB-07.

## 3. What was built

| Task | Delivered |
|---|---|
| L02.1 | `alphas/catalog.py`, `findings.py`, `probes.py` → `alpha_registry.json`, `preset_catalog.json`, `unmapped_presets.json`, `semantic_delta.json` |
| L02.2 | `alphas/reference/indicators.py` + `parity.py` — scalar oracle, fastmath-free |
| L02.3–L02.6 | four adapters on a shared typed contract (`contracts.py`, `base.py`) |
| L02.7 | `alphas/fixtures.py` — 13 fixtures run by the **installed** engine |
| L02.8 | `quantbt_bridge/{intent_tape,parity,capability_probe}.py` |
| exit | `alpha_certification/{A-SC,A-HMA,A-VWAP,A-HASH}.json`, `golden_traces/*.json` |

## 3b. Second audit — 8 further gaps found and closed

The first LAB-02 pass was declared against the exit gate, not against every sentence of L02.1–L02.8. Re-reading the spec line by line found eight requirements that had not been delivered.

| Task | Gap found on re-audit | Closed by |
|---|---|---|
| L02.1 | "AST inventory **input names**" — only parameters and functions were inventoried, never the market data each alpha reads | `data_inputs` + `index_uses` per alpha. A-VWAP needs open/high/low/close/volume **and a DatetimeIndex**; A-HASH needs close/high/low and never touches the index; A-SC and A-HMA need volume and the index. These are LAB-03's concrete data requirements |
| L02.2 | **Numba parity never measured** — `@njit` was stripped and the compiled kernels were never run | `reference/numba_parity.py` compiles the real kernels (keeping `fastmath=True`) and compares them to the interpreted oracle: **14 kernels**, non-fastmath bit-exact, fastmath within 7.1e-14, and both decision-bearing comparisons (RSI band membership, rounded slope angle) **identical**. fastmath does not change a decision — measured |
| guide §2.1 | The **`legacy_reproduction` tier was declared but never built** | `alphas/legacy.py` runs all four originals end to end with the minimum fix each needs (numpy for A-HASH, the `ta` classes for A-SC, **nothing** for A-HMA/A-VWAP), tagged diagnostic/in-sample only and never eligible for an arm |
| L02.8 | "the original alpha and the corrected adapter may differ **by documented repairs**" — the two were never compared | `divergence_report` drives the adapter to a **fixed point** against the engine's own protective fills, then attributes every difference |
| L02.3 | "preserve **bars-since** state" — tested only against my own vectorised path | K1/K2/O1/O2 and the buy/sell/long signals compared element-wise against the raw `generate_signals`, NaN prefix included |
| L02.6 / T12 | **Lot rounding and dust** deferred to LAB-03 | `quantize_ladder` uses QuantBT's own `quantize_signed_quantity`: `fraction_of_remaining` preserved exactly, a rung below the minimum notional **rejected** rather than resized, leftover **dust reported**, never over-closed |
| L02.6 | The legacy equity helper did not faithfully reproduce the source's shape | Now flat while a position is open and realising only at the closing fill (finding AH-03), still diagnostic-only |
| L02.8 | "one corrected alpha version shared by A/B/C/D/E" was described, not enforced | Asserted: every canonical delta applies to all five arms, every non-canonical delta to none |

### Legacy vs canonical — every difference attributed

| Alpha | Result | Attribution |
|---|---|---|
| A-SC | **IDENTICAL** — same entry bar | repairs change timing and accounting, not the signal |
| A-VWAP | **IDENTICAL** — all 6 entry bars | same |
| A-HMA | **CONSTANT OFFSET of exactly +1 bar** on every entry (legacy 82/116/125 vs canonical 81/115/124) | `SD-HMA-02`: legacy `pos_weight[t]` is the position *entering* bar t; canonical records the decision bar (finding HM-02) |
| A-HASH | first **6 entries identical**, then separates; the replay does not reach a fixed point | `BLOCK-HASH-LADDER`: only the final rung is expressible, so the position closes at a different bar and the cooldown then admits different entries |

An unattributed difference would be an adapter defect, not a result. There are none.

## 4. Findings and semantic deltas

**29 findings**: all 7 A-HASH (AH-01…07), all 7 A-VWAP (AV-01…07), all 9 A-HMA (HM-01…09) and all 6 A-SC (SC-01…06) from guide §3, **plus SC-07 found by the lab** — `trend` is seeded at 0.0, so the first condition-true bar ratchets it from 0 to a real price level and always manufactures a `buy_signal`. Repaired by `SD-SC-06`: no decision until 3 bars after the trend leaves its seed.

**25 semantic deltas**: 10 `packaging_fix`, 10 `execution_repair`, 4 `indicator_repair`, 1 `thesis_change`. Two carry an **empty** `applies_to_experiment_arms` and can never run inside a canonical arm: `SD-HASH-05` (true-range ATR revision) and `SD-SC-05` (conventional crossover).

## 5. Appendix B — all 21 probes re-run, inside containment

21/21 CONFIRMED, executed in the bubblewrap sandbox (network unreachable, protected roots read-only). Every observation matches guide appendix E exactly: parse line counts 249/166/349/145; `HASH_EQUITY_NO_MTM` terminal 10100 vs reported 10000; `HASH_ONE_TP_BRANCH_PER_BAR` units [0, 10, 5]; unordered presets `huhu, bubu, haft, kuku`; `HMA_FLAT_RSI` 50 → 100; inverted lengths `hfhf, hjhj, hoho, hbhb`; `sl_mult` in 13 presets and read by nothing; `SIGCOMBINE_LONG_FLAT_ONLY` [0, 2, 0, 0, 2]; crossover actual `[F,F,F,F]` vs conventional `[F,F,F,T]`.

One honest difference: `JM_FORWARD_DP_ORACLE` reproduces the property (DP equals brute force to float epsilon, 2.2e-16) but its `prefix_endpoint_states` differ from the guide's, because the guide did not publish the seed of its random loss matrix.

## 6. Preset classification — schema-driven, matching the guide exactly

A dictionary is a preset for an alpha only when at least half its keys are parameter names that alpha's code actually reads. Result: A-HASH 6/0, A-HMA 13/1, A-SC 1/0, A-VWAP 5/10 — exactly guide appendix A.1 ("4 dictionaries carry VWAP keys, `base` has HTF, 10 are not the VWAP parameter schema"). The 11 unmapped dictionaries (9 `cetp_*`, `keke`, `sl_mode_map`) are retained for audit and are **not eligible for anything**. All 25 presets stay `provenance=user_full_sample_tpe`.

The scope-aware unused-argument pass independently rediscovered `open_p` (AV-02) and `time_ms`/`volume`/`double_up` (HM-05).

## 7. Numeric parity

**Oracle vs source**: 14 pairs. 13 are **bit-exact** (max abs error 0.0), including the dynamic Hull MA and its index clamping, the slope/angle formula, all three RSI conventions and all ATR conventions. `n_stdev` sits at an accumulation tolerance (6.8e-12) because the source uses running sums of x and x² while the oracle recomputes each window.

**Oracle vs `ta`**: SMA and MFI match; RSI and ATR are **documented divergences**, not failures — `ta` seeds Wilder differently. The requirement is that the seed error decays, and it does: RSI 1.99e-1 → 3.59e-7, ATR 5.10e-4 → 1.72e-9. Neither side was edited to make them agree.

## 8. Execution fixtures and engine parity

13/13 fixtures pass on the installed engine. Verified behaviour: entry at the **next open** (103.5, not the 103.0 decision close); a 30% gap fills at 130, not 100; a bar touching both stop and take profit resolves to the **stop**; OCO cancels the losing leg and total closed quantity never exceeds the position; a zero-size order produces nothing; funding is charged at exactly the two declared events; requesting funding without events is **refused** rather than defaulted to zero; forced-flat and mark-open are two declared modes.

Engine parity: 7 cases, Python reference vs Rust, **equity/positions/fees/funding bit-identical in every case**. The rust backend exposes no fill sequence at any report level, so fill-by-fill parity is recorded as `BLOCKED_CAPABILITY` — this is account-trace parity, and it is not described as more than that.

## 9. Honest limits

1. **A-HASH is not certified.** Its partial-exit thesis cannot be tested at full fidelity on this install.
2. **Engine parity is account-trace only** (blocker BLOCK-RUST-FILLS).
3. **Everything here is synthetic.** No market data was read; `market_test_evidence_refs` is empty in all four certification records by design. No statement about edge, PnL or regime value exists.
4. **Lot/step rounding and dust** are now implemented and tested against a declared synthetic instrument; binding them to each symbol's real tick/lot metadata is LAB-03.
5. **21 of 64 acceptance requirements** are implemented (21 COVERED, 2 PARTIAL, 41 NOT_YET_IMPLEMENTED), plus four extra gates (ISO, CAP, NUMBA, LEGACY); the rest belong to LAB-03…LAB-10.
7. **A-HASH's canonical replay does not converge** to a fixed point — a direct consequence of the ladder blocker, recorded rather than smoothed over.
6. The guide's `event_lifecycle_v3_next_open` exists in the registry, but the route that actually delivers next-open market fills plus brackets on this install is **`intrabar_bracket_v1`**. That substitution is recorded, not silent.

## 10. Protected trees

`../quantbt` untouched: `git status --porcelain` empty, `.git/index` digest unchanged by the check itself (`GIT_OPTIONAL_LOCKS=0`). The lab consumes the PyPI wheels only.

**Next:** LAB-03 — server-first snapshots and causal feature panels (T21–T28).

## Glossary — what each term means and where it applies

| term | meaning | where it applies in this lab |
|---|---|---|
| **version tier** | which of the four states an alpha is in: raw_supplied (original bytes), legacy_reproduction (diagnostic only), canonical_v1 (the only tier allowed to prove edge), research_revision_N (deliberate thesis change) | LAB-02 — all four are built for each of the four alphas |
| **semantic delta** | a recorded difference between two tiers, classified as packaging_fix, execution_repair, indicator_repair or thesis_change, with source lines and a reproducer | LAB-02 — `configs/semantic_delta.json`; e.g. SD-HASH-01 is the missing numpy import |
| **certification** | whether an alpha's economics can actually be expressed on an available engine route; it is NOT about profitability | LAB-02 — A-HASH is NOT_READY because no single route gives next-open entry + protective stop + partial reduce-only ladder together |
| **intent tape** | the array form the engine consumes: entry side/size, stop, take-profit and technical exit per bar. The adapter proposes; the engine decides | LAB-02 — `quantbt_bridge/intent_tape.py`, contract `intrabar_bracket_v1` |
| **numba parity** | checking a compiled kernel against the interpreted reference bit for bit before it is allowed to ship | LAB-02/04 — an accelerated kernel is admitted only while `exact` is true |
| **NOT_READY** | an alpha that cannot be certified keeps all its cells with NULL metrics; booking it as PnL = 0 would bias every aggregate | LAB-02/04 — A-HASH, 5 cells |
