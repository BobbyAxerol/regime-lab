# Regime-lab — Trích đoạn nguồn đã đối chiếu

Nguồn duy nhất: ZIP người dùng cung cấp. Không phải live GitHub HEAD. Số dòng bên trái là số dòng trong file được trích. Các hash là SHA-256 của **toàn file**, không phải riêng excerpt.

## SRC01 — `src/crypto_regime_lab/experiments/factorial.py:170–203`

SHA-256: `9b22545e5f0f6fce59b07cab2d54379ba550890a9e38a3a996f0e243a2846ddf`

```text
  170 | def _schedule_from_selections(selections: list[dict], bars: pd.DataFrame, alpha_id: str,
  171 |                               *, seed_params: dict | None = None
  172 |                               ) -> tuple[VersionWindow, list[VersionWindow], bool]:
  173 |     """Turn a list of (cutoff, params) into an initial version plus a schedule.
  174 | 
  175 |     A selector that returns nothing admissible at every cutoff is a RESULT, not
  176 |     an error: the retention rule keeps the incumbent, and the honest deployment
  177 |     of "never selected" is the seed point held for the whole window. An earlier
  178 |     version raised here and took a nine-cell run down with it, which turned a
  179 |     reportable finding into a crash.
  180 |     """
  181 |     windows: list[VersionWindow] = []
  182 |     for index, record in enumerate(selections):
  183 |         params = record["params"]
  184 |         if params is None:
  185 |             continue                            # retention: the incumbent stays
  186 |         cutoff = pd.Timestamp(record["cutoff"])
  187 |         if cutoff.tzinfo is None:
  188 |             cutoff = cutoff.tz_localize("UTC")
  189 |         position = int(bars.index.searchsorted(cutoff))
  190 |         if position >= len(bars):
  191 |             continue
  192 |         windows.append(VersionWindow(
  193 |             parameter_version=parameter_digest(params), params=params,
  194 |             requested_at_bar=position, activation_id=f"act-{index}"))
  195 |     if windows:
  196 |         return windows[0], windows[1:], False
  197 |     if seed_params is None:
  198 |         raise FactorialError(
  199 |             f"{alpha_id}: the selector chose nothing at any cutoff and no incumbent seed was "
  200 |             "supplied, so there is nothing to deploy")
  201 |     return (VersionWindow(parameter_version=parameter_digest(seed_params),
  202 |                           params=dict(seed_params), requested_at_bar=0,
  203 |                           activation_id="act-incumbent-retained"), [], True)
```

## SRC02 — `src/crypto_regime_lab/integration/continuous_account.py:165–222`

SHA-256: `1c27da4459b009ce6ca4d5630ce173eafc72c035ff153ddda81dba0da6f81f67`

```text
  165 |        bars, and never carried over from the old version's state.
  166 |     """
  167 |     n = len(frame)
  168 |     if n < 10:
  169 |         raise ContinuousAccountError(f"window of {n} bars is too short")
  170 |     arrays = [frame[c].to_numpy(float) for c in ("open", "high", "low", "close", "volume")]
  171 |     engine_frame = frame[["open", "high", "low", "close", "volume"]]
  172 |     market = MarketSlice(*arrays, index=frame.index)
  173 | 
  174 |     ordered_schedule = sorted(schedule, key=lambda w: w.requested_at_bar)
  175 | 
  176 |     def sweep(forced_exits: dict[int, float] | None):
  177 |         return _one_sweep(alpha_id, frame, arrays, engine_frame, market, n,
  178 |                           initial=initial, schedule=ordered_schedule, backend=backend,
  179 |                           forced_exits=forced_exits)
  180 | 
  181 |     # The same fixed point run_candidate uses. A single forward pass schedules
  182 |     # protective exits from the per-trade oracle; the whole-window engine run may
  183 |     # disagree once several positions interact, and an unverified disagreement
  184 |     # means the adapter was driven by exits the account did not actually get.
  185 |     # A-SC never fires a protective order, so this loop converges on the first
  186 |     # pass here -- but A-HMA, A-VWAP and A-HASH all rest stops, and LAB-08 runs
  187 |     # those on this same function.
  188 |     forced: dict[int, float] | None = None
  189 |     result = None
  190 |     for attempt in range(max_sweeps):
  191 |         result = sweep(forced)
  192 |         observed = {int(f["bar_index"]): float(f["price"]) for f in result.fills
  193 |                     if f["reason"] in PROTECTIVE}
  194 |         result.diagnostics["sweeps"] = attempt + 1
  195 |         result.diagnostics["protective_exits"] = len(observed)
  196 |         if set(observed) == set(result.diagnostics["applied_exits"]):
  197 |             result.diagnostics["exit_fixed_point_converged"] = True
  198 |             return result
  199 |         forced = observed
  200 |     result.diagnostics["exit_fixed_point_converged"] = False
  201 |     result.diagnostics["unconverged_exit_symmetric_difference"] = len(
  202 |         set(result.diagnostics["applied_exits"]).symmetric_difference(
  203 |             {int(f["bar_index"]) for f in result.fills if f["reason"] in PROTECTIVE}))
  204 |     return result
  205 | 
  206 | 
  207 | def _one_sweep(alpha_id: str, frame: pd.DataFrame, arrays, engine_frame, market,
  208 |                n: int, *, initial: VersionWindow, schedule: list[VersionWindow],
  209 |                backend: str, forced_exits: dict[int, float] | None) -> ContinuousAccountRun:
  210 |     """One chronological pass. Exits come from the oracle, or from a previously
  211 |     observed whole-window run when ``forced_exits`` is supplied."""
  212 |     open_ = arrays[0]
  213 |     pending = list(schedule)
  214 |     active = initial
  215 |     adapter = build_adapter(alpha_id, active.params, market)
  216 |     # Every version's adapter is fed EVERY bar from the moment it is requested,
  217 |     # so its indicators warm on real history rather than being reinitialised at
  218 |     # the switch. Only the active one may emit intents.
  219 |     shadow: dict[str, tuple[Any, VersionWindow, int]] = {}
  220 | 
  221 |     switches: list[SwitchRecord] = []
  222 |     version_by_bar: list[str] = []
```

## SRC03 — `src/crypto_regime_lab/integration/continuous_account.py:275–335`

SHA-256: `1c27da4459b009ce6ca4d5630ce173eafc72c035ff153ddda81dba0da6f81f67`

```text
  275 |                 record.wait("WAITING_FOR_WARM_INDICATORS")
  276 |                 continue
  277 |             adapter = candidate_adapter          # the warmed adapter, not a fresh one
  278 |             active = window
  279 |             record.effective_at_bar = t
  280 |             record.blocked_reason = None
  281 |             record.warm_bars_at_activation = warm_bars
  282 |             del shadow[activation_id]
  283 | 
  284 |         # -- every shadow adapter observes the bar so its indicators stay causal
  285 |         for candidate_adapter, _, _ in shadow.values():
  286 |             if candidate_adapter is not adapter:
  287 |                 candidate_adapter.on_bar_close(t)
  288 | 
  289 |         version_by_bar.append(active.parameter_version)
  290 |         decision = adapter.on_bar_close(t)
  291 |         tape_decisions.append(decision)
  292 |         for intent in decision.intents:
  293 |             if intent.kind in (IntentKind.ENTER_LONG, IntentKind.ENTER_SHORT) and t + 1 < n:
  294 |                 side = 1 if intent.kind is IntentKind.ENTER_LONG else -1
  295 |                 qty = ACCOUNT["entry_notional_usdt"] / max(float(open_[t + 1]), 1e-12)
  296 |                 follow_ups = adapter.on_fill(Fill(index=t + 1, side=side,
  297 |                                                  quantity=float(side) * qty,
  298 |                                                  price=float(open_[t + 1]),
  299 |                                                  intent_kind=intent.kind))
  300 |                 entries += 1
  301 |                 stop = take_profit = float("nan")
  302 |                 for follow in follow_ups:
  303 |                     if follow.stop_price is not None:
  304 |                         stop = float(follow.stop_price)
  305 |                         tp = follow.take_profit_price
  306 |                         if tp is None and follow.ladder:
  307 |                             tp = follow.ladder[-1][0]
  308 |                         take_profit = float(tp) if tp is not None else float("nan")
  309 |                 if np.isfinite(stop) or np.isfinite(take_profit):
  310 |                     pending_levels[t] = (stop, take_profit)
  311 |                     if forced_exits is None:
  312 |                         bar, price, _ = _exit_oracle(engine_frame, t, side, stop, take_profit,
  313 |                                                      backend=backend)
  314 |                         next_exit_bar, next_exit_price = bar, price
  315 |             elif intent.kind is IntentKind.EXIT_ALL and adapter.state.position != 0.0 \
  316 |                     and t + 1 < n:
  317 |                 adapter.on_fill(Fill(index=t + 1, side=-int(np.sign(adapter.state.position)),
  318 |                                      quantity=-adapter.state.position,
  319 |                                      price=float(open_[t + 1]),
  320 |                                      intent_kind=IntentKind.EXIT_ALL))
  321 |                 next_exit_bar, next_exit_price = None, None
  322 | 
  323 |         # a switch requested while flat, on a bar with no new entry, may land next loop
  324 |         if adapter.state.position == 0.0 and shadow:
  325 |             for activation_id in list(shadow):
  326 |                 record = next(s for s in switches if s.activation_id == activation_id)
  327 |                 if record.blocked_reason == "TRANSITION_BLOCKED_OPEN_CAMPAIGN":
  328 |                     record.blocked_reason = "WAITING_FOR_WARM_INDICATORS"
  329 | 
  330 |     if len(tape_decisions) != n:
  331 |         raise ContinuousAccountError(
  332 |             f"the decision tape has {len(tape_decisions)} rows for {n} bars; every bar must "
  333 |             "contribute exactly one decision from whichever version was active on it")
  334 |     build = build_intent_tape(tape_decisions, n, unit_size=1.0, pending_levels=pending_levels)
  335 |     out = _engine(engine_frame, build, backend)
```

## SRC04 — `src/crypto_regime_lab/experiments/regime_schedule.py:78–156`

SHA-256: `c8f50b326cfcff56913d855ea5f3bb40c7877d8afe48d74187a6a3d1bf066b15`

```text
   78 | def transition_cutoffs(emissions: list[dict], *, count: int, earliest: str,
   79 |                        latest: str, min_gap_days: float = 30.0) -> RegimeSchedule:
   80 |     """Pick ``count`` refresh times from state changes already emitted.
   81 | 
   82 |     One trigger per period, not the first ``count`` transitions. Taking them
   83 |     greedily from the front puts every refresh in the opening months and leaves
   84 |     the arm holding its initial parameters for years -- which is a coverage
   85 |     artefact wearing a timing result's clothes. Splitting the window into as many
   86 |     periods as the calendar has folds and taking the first transition INSIDE each
   87 |     period gives the same cadence with the timing chosen by the model, which is
   88 |     the only difference the contrast is meant to measure.
   89 | 
   90 |     Two properties make it causal rather than merely plausible.
   91 | 
   92 |     A trigger sits at an emission's ``available_at``, not at the bar it
   93 |     describes: the state for a bar that has not closed is not knowable, and
   94 |     LAB-07 found a version of this published fifteen times too early.
   95 | 
   96 |     And no transition is ranked by how large or how profitable it turned out to
   97 |     be. "The biggest transitions" is a quantity only the future knows; within a
   98 |     period the FIRST one is taken.
   99 |     """
  100 |     earliest_ts = pd.Timestamp(earliest)
  101 |     latest_ts = pd.Timestamp(latest)
  102 |     if earliest_ts.tzinfo is None:
  103 |         earliest_ts = earliest_ts.tz_localize("UTC")
  104 |     if latest_ts.tzinfo is None:
  105 |         latest_ts = latest_ts.tz_localize("UTC")
  106 | 
  107 |     changes: list[pd.Timestamp] = []
  108 |     previous = None
  109 |     for record in emissions:
  110 |         state = (record.get("state_namespace"), record.get("state_id"))
  111 |         moment = pd.Timestamp(record["available_at"])
  112 |         if moment.tzinfo is None:
  113 |             moment = moment.tz_localize("UTC")
  114 |         if previous is not None and state != previous and earliest_ts <= moment <= latest_ts:
  115 |             changes.append(moment)
  116 |         previous = state
  117 | 
  118 |     period = (latest_ts - earliest_ts) / count
  119 |     chosen: list[pd.Timestamp] = []
  120 |     gap = pd.Timedelta(days=min_gap_days)
  121 |     for index in range(count):
  122 |         window_start = earliest_ts + period * index
  123 |         window_end = earliest_ts + period * (index + 1)
  124 |         candidates = [m for m in changes if window_start <= m < window_end
  125 |                       and (not chosen or m - chosen[-1] >= gap)]
  126 |         if candidates:
  127 |             chosen.append(candidates[0])            # first in the period, never "biggest"
  128 |         else:
  129 |             raise ScheduleError(
  130 |                 f"no state change between {window_start.date()} and {window_end.date()} that "
  131 |                 f"respects the {min_gap_days:g}-day gap. A dynamic arm cannot be given a refresh "
  132 |                 "the states did not ask for, and one padded to the count is just the calendar")
  133 | 
  134 |     if len(chosen) != count:
  135 |         raise ScheduleError(
  136 |             f"placed {len(chosen)} of {count} refresh times; a dynamic arm with fewer refreshes "
  137 |             "is not compute-matched")
  138 |     return RegimeSchedule(
  139 |         cutoffs=tuple(t.isoformat() for t in chosen),
  140 |         source=(f"{len(changes)} emitted state changes; the first inside each of {count} equal "
  141 |                 f"periods, with a {min_gap_days:g}-day minimum gap"))
  142 | 
  143 | 
  144 | def assert_compute_matched(calendar: CalendarSpec, schedule: RegimeSchedule) -> dict:
  145 |     """The dynamic arm may not buy its advantage with extra searches."""
  146 |     matched = calendar.folds == schedule.folds and calendar.train_days == schedule.train_days
  147 |     return {
  148 |         "schema": "crypto_regime_lab.compute_match_check.v1",
  149 |         "calendar_refreshes": calendar.folds,
  150 |         "dynamic_refreshes": schedule.folds,
  151 |         "calendar_train_days": calendar.train_days,
  152 |         "dynamic_train_days": schedule.train_days,
  153 |         "matched": bool(matched),
  154 |         "rule": ("same refresh count and same training memory. Only the timing differs, which is "
  155 |                  "the contribution being measured (guide 10.1 arm C: 'training memory giữ như A')"),
  156 |     }
```

## SRC05 — `scripts/run_lab08_factorial.py:260–303`

SHA-256: `e260ffc4f542b56ceb3f78b6523d77d84a116a7f6ab48c6b382600be87eab49b`

```text
  260 |     else:
  261 |         try:
  262 |             schedule = transition_cutoffs(
  263 |                 emissions, count=CB.CALENDAR.folds,
  264 |                 earliest=f"{window_start} 00:00:00+00:00",
  265 |                 latest=f"{window_end} 00:00:00+00:00")
  266 |         except ScheduleError as exc:
  267 |             # no padding: a dynamic arm the states cannot support is absent, not
  268 |             # quietly replaced by an evenly spaced calendar
  269 |             for arm in ("C", "D", "E"):
  270 |                 results[arm] = ArmResult(arm, alpha_id, symbol, "TOO_FEW_TRANSITIONS",
  271 |                                          detail={"reason": str(exc)})
  272 |             notes["state_provider"] = "TOO_FEW_TRANSITIONS"
  273 |         else:
  274 |             notes["regime_schedule"] = schedule.as_record()
  275 |             notes["compute_match"] = assert_compute_matched(CB.CALENDAR, schedule)
  276 |             if progress:
  277 |                 progress(f"  {alpha_id}/{symbol}: {schedule.folds} regime cutoffs "
  278 |                          f"{[c[:10] for c in schedule.cutoffs]}")
  279 |             dynamic = selections_at_cutoffs(alpha_id, symbol, training_bars,
  280 |                                             list(schedule.cutoffs), progress=progress)
  281 |             notes["regime_cutoff_evidence"] = dynamic["evidence"]
  282 |             for arm, which in (("C", "A"), ("D", "B")):
  283 |                 results[arm] = run_arm(arm, alpha_id, symbol, bars, dynamic["per_arm"][which])
  284 |                 notes["deployed_selections"][arm] = dynamic["per_arm"][which]
  285 |             notes["deployed_selections"]["E"] = dynamic["per_arm"]["B"]
  286 |             # arm E extends D with the bank/response policy; without a switch the
  287 |             # policy deploys D's schedule, which is reported rather than hidden
  288 |             results["E"] = run_arm("E", alpha_id, symbol, bars, dynamic["per_arm"]["B"])
  289 |             results["E"].detail["policy_note"] = (
  290 |                 "LAB-06 measured ZERO switches for this policy on the registered thresholds, so E "
  291 |                 "deploys D's schedule and its own contribution is null by construction here. "
  292 |                 "That is reported, not hidden: E is an extension and never a substitute for C "
  293 |                 "or D")
  294 | 
  295 |     record = {
  296 |         "alpha_id": alpha_id, "symbol": symbol, "status": "RUN",
  297 |         "window": [window_start, window_end],
  298 |         "bars": int(len(bars)),
  299 |         "decision_bars": protocol["timeframes"][alpha_id]["decision_bars"],
  300 |         "arms": {arm: results[arm].as_record() for arm in ARMS},
  301 |         "contrasts": {},
  302 |         "notes": notes,
  303 |         "wall_seconds": time.perf_counter() - started,
```

## SRC06 — `scripts/run_response_policy.py:46–147`

SHA-256: `b4f24e71fa8eac168342c323f547d85305aa9eda07db2f2f4f80b6762b0d4a83`

```text
   46 | STUDY_ID = "crypto_regime_timeedge_v2"
   47 | SNAPSHOT_ID = "server_core_v1"
   48 | ALPHA, SYMBOL = "A-SC", "BTCUSDT"
   49 | HORIZON_DAYS = EP.PILOT_HORIZON_DAYS
   50 | BANK_WARMUP_BARS = 120
   51 | DEVELOPMENT_END = "2023-12-31"
   52 | 
   53 | #: The policy is the same policy in both roles. LAB-06 ran it on development;
   54 | #: L09.5 runs it on the confirmation interval to see how it behaves where the
   55 | #: design was not built -- new episodes, ambiguous states, a bank that goes stale.
   56 | #: The thresholds, the horizon, the warmup and the cost model are NOT touched
   57 | #: between the two: a policy retuned for the confirmation is not a confirmation.
   58 | ROLES = {
   59 |     "development": {
   60 |         "cells_dir": LAB_ROOT / ".cache" / "lab04_cells",
   61 |         "tape": "lab05_emission_tape.json",
   62 |         "window": (None, DEVELOPMENT_END),
   63 |         "prefix": "lab06",
   64 |         "panel": "response_panel.parquet",
   65 |     },
   66 |     "confirmation": {
   67 |         "cells_dir": LAB_ROOT / ".cache" / "lab09_cells",
   68 |         "tape": "lab09_btcusdt_emission_tape.json",
   69 |         "window": ("2024-01-01", "2026-08-31"),
   70 |         "prefix": "lab09_policy",
   71 |         "panel": "lab09_policy_response_panel.parquet",
   72 |     },
   73 | }
   74 | ROLE = "development"
   75 | CELLS_DIR = ROLES["development"]["cells_dir"]
   76 | 
   77 | 
   78 | def load_contexts(tape_name: str) -> dict:
   79 |     """Emissions keyed by the time they became AVAILABLE, not observed."""
   80 |     tape = json.loads((LAB_ROOT / "configs" / tape_name).read_text())
   81 |     def _utc(value):
   82 |         """The panel stores naive UTC; the bar index is tz-aware. Normalise once here
   83 |         rather than comparing them and hoping."""
   84 |         stamp = pd.Timestamp(value)
   85 |         return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
   86 | 
   87 |     rows = []
   88 |     for namespace, record in tape["namespaces"].items():
   89 |         for emission in record["emissions"]:
   90 |             rows.append({
   91 |                 "available_at": _utc(emission["available_at"]),
   92 |                 "observed_at": _utc(emission["observed_at"]),
   93 |                 "namespace": namespace, "state_id": emission["state_id"],
   94 |                 "features": emission["feature_contributions"],
   95 |                 "quality_status": emission["quality_status"],
   96 |                 "decision_eligible": emission["decision_eligible"],
   97 |                 "second_best_gap": emission["second_best_gap"],
   98 |             })
   99 |     rows.sort(key=lambda r: r["available_at"])
  100 |     return {"rows": rows, "namespaces": sorted(tape["namespaces"])}
  101 | 
  102 | 
  103 | def context_at(rows: list, when: pd.Timestamp) -> dict | None:
  104 |     """The most recent emission ALREADY AVAILABLE at ``when``. Never a later one."""
  105 |     best = None
  106 |     for row in rows:
  107 |         if row["available_at"] <= when:
  108 |             best = row
  109 |         else:
  110 |             break
  111 |     return best
  112 | 
  113 | 
  114 | def cutoff_records(cell: dict) -> list[dict]:
  115 |     """The (cutoff, evidence) pairs this cell produced, in either runner's shape.
  116 | 
  117 |     LAB-04 wrote them as `folds`; the LAB-09 confirmation runner writes them under
  118 |     `notes.calendar_cutoff_evidence` because it also carries a regime schedule.
  119 |     Same records, two containers -- read both rather than duplicating the policy.
  120 |     """
  121 |     if cell.get("folds"):
  122 |         return cell["folds"]
  123 |     return (cell.get("notes") or {}).get("calendar_cutoff_evidence") or []
  124 | 
  125 | 
  126 | def load_discoveries() -> list:
  127 |     """Candidates from the selector's search, each tagged with its discovery cutoff."""
  128 |     cell = json.loads((CELLS_DIR / f"{ALPHA}_{SYMBOL}.json").read_text())
  129 |     out = []
  130 |     for fold in cutoff_records(cell):
  131 |         evidence = fold.get("cutoff_evidence")
  132 |         if not evidence:
  133 |             continue
  134 |         cutoff = pd.Timestamp(fold["cutoff"])
  135 |         if cutoff.tzinfo is None:
  136 |             cutoff = cutoff.tz_localize("UTC")
  137 |         for point_id, score in evidence["robust_scores"].items():
  138 |             out.append({
  139 |                 "candidate_id": f"{point_id}",
  140 |                 "params": score["params"],
  141 |                 "discovered_at": cutoff,
  142 |                 "score": score.get("r") if score.get("r") is not None else -1e9,
  143 |                 "validation_panel": {k: score.get(k) for k in
  144 |                                      ("g", "f", "r", "p_survive", "episodes_used",
  145 |                                       "neighbours_used", "status")},
  146 |                 "reason": f"discovered by the LAB-04 search at cutoff {fold['cutoff'][:10]}",
  147 |             })
```

## SRC07 — `src/crypto_regime_lab/regime/emissions.py:190–240`

SHA-256: `1ece10418d865eb1010d2cfbb66125caded2034c8fbf09bbb2c4ca02a2239a1f`

```text
  190 |             shift = float(costs.min())
  191 |             costs = costs - shift
  192 |             self._offset += shift
  193 |         self._previous = costs
  194 |         return int(np.argmin(costs)), costs, raw
  195 | 
  196 | 
  197 | def build_emission(state_id: int, costs: np.ndarray, *, namespace: str, z_t: np.ndarray,
  198 |                    centroids: np.ndarray, weights: np.ndarray, groups: dict,
  199 |                    observed_at: str, available_at: str, inferred_at: str,
  200 |                    model_fit_cutoff: str, ready_at: str, version: str,
  201 |                    quality_status: str = QUALITY_OK,
  202 |                    input_refs: tuple[str, ...] = (),
  203 |                    novelty_score: float = 0.0,
  204 |                    decision_eligible: bool = True) -> Emission:
  205 |     """Assemble one emission with the fields guide 8.5 requires."""
  206 |     if quality_status not in QUALITY_STATUSES:
  207 |         raise JumpModelError(f"unknown quality status {quality_status!r}")
  208 |     z_t = np.asarray(z_t, dtype=np.float64)
  209 |     weights = np.asarray(weights, dtype=np.float64)
  210 |     residual = z_t - np.asarray(centroids, dtype=np.float64)[state_id]
  211 |     per_feature = 0.5 * weights * residual * residual
  212 |     group_contributions: dict[str, float] = {}
  213 |     for name, indices in groups.items():
  214 |         group_contributions[name] = float(per_feature[list(indices)].sum())
  215 |     gap = float(second_best_gap(np.asarray(costs).reshape(1, -1))[0])
  216 |     return Emission(
  217 |         state_id=int(state_id), state_namespace=namespace,
  218 |         state_costs=tuple(float(c) for c in costs), second_best_gap=gap,
  219 |         fit_residual=float(per_feature.sum()), novelty_score=float(novelty_score),
  220 |         feature_contributions=tuple(float(c) for c in per_feature),
  221 |         group_contributions=group_contributions,
  222 |         observed_at=observed_at, available_at=available_at, inferred_at=inferred_at,
  223 |         model_fit_cutoff=model_fit_cutoff, ready_at=ready_at, version=version,
  224 |         quality_status=quality_status, input_refs=tuple(input_refs),
  225 |         membership_score=tuple(float(m) for m in membership_scores(np.asarray(costs))),
  226 |         membership_is_calibrated=False, decision_eligible=decision_eligible)
  227 | 
  228 | 
  229 | def batch_stream_parity(z: np.ndarray, centroids: np.ndarray, weights: np.ndarray,
  230 |                         lambda_jump: float, *, namespace: str = "parity") -> dict:
  231 |     """T38 — streaming one observation at a time must equal the batch filter at EVERY prefix."""
  232 |     from .jump_model import forward_filter
  233 | 
  234 |     z = np.asarray(z, dtype=np.float64)
  235 |     batch = forward_filter(loss_matrix(z, centroids, weights), lambda_jump, normalise=True)
  236 | 
  237 |     streamer = OnlineStateFilter(centroids, weights, lambda_jump, namespace=namespace)
  238 |     stream_states, stream_costs = [], []
  239 |     for t in range(z.shape[0]):
  240 |         state, costs, _ = streamer.step(z[t])
```

## SRC08 — `scripts/run_response_policy.py:195–270`

SHA-256: `b4f24e71fa8eac168342c323f547d85305aa9eda07db2f2f4f80b6762b0d4a83`

```text
  195 |     # ---- L06.1 horizon from holding diagnostics -----------------------
  196 |     probe = run_candidate(ALPHA, dict(SEED_POINTS[ALPHA]),
  197 |                           bars[(bars.index >= cutoffs[0]) & (bars.index < cutoffs[1])])
  198 |     holding = window_metrics(probe)
  199 |     bar_hours = pd.Timedelta(DECISION_INTERVAL[ALPHA]).total_seconds() / 3600.0
  200 |     horizon_note = EP.horizon_from_holding_diagnostics(
  201 |         holding["mean_holding_bars"] or 0.0, bar_hours)
  202 | 
  203 |     # ---- L06.2 bank at each cutoff, lineage enforced ------------------
  204 |     banks = {}
  205 |     with writer.attempt("L06.2.bank") as att:
  206 |         for cutoff in cutoffs:
  207 |             banks[cutoff] = BK.build_bank(
  208 |                 cutoff, discoveries, adapter_hash=BK.parameter_digest({"alpha": ALPHA}),
  209 |                 warmup_bars=BANK_WARMUP_BARS, schema=schema)
  210 |         att.detail = {"cutoffs": len(banks),
  211 |                       "sizes": [len(b.admissible()) for b in banks.values()]}
  212 | 
  213 |     # ---- L06.1 episodes for every bank candidate ----------------------
  214 |     windows = EP.build_grid(bars.index, horizon_days=HORIZON_DAYS)
  215 |     window_index = {start: i for i, (start, _end) in enumerate(windows)}
  216 |     all_candidates: dict[str, dict] = {}
  217 |     for bank_obj in banks.values():
  218 |         for entry in bank_obj.admissible():
  219 |             all_candidates.setdefault(entry.candidate_id, entry.params)
  220 |     incumbent_id = "incumbent_seed"
  221 |     all_candidates[incumbent_id] = dict(SEED_POINTS[ALPHA])
  222 | 
  223 |     def outcome_for(params):
  224 |         def _fn(start, end):
  225 |             window = bars[(bars.index >= start) & (bars.index < end)]
  226 |             if len(window) < 20:
  227 |                 return None
  228 |             try:
  229 |                 run = run_candidate(ALPHA, params, window)
  230 |             except Exception:
  231 |                 return None
  232 |             metrics = window_metrics(run)
  233 |             return {"net_return": metrics["net_return"],
  234 |                     "max_drawdown": metrics["max_drawdown"],
  235 |                     "turnover": float(metrics["entries"]) * ACCOUNT["entry_notional_usdt"]
  236 |                     / ACCOUNT["initial_capital_usdt"],
  237 |                     "cost": float(metrics["fills"]) * ACCOUNT["taker_fee_rate"],
  238 |                     "trades": metrics["fills"], "exposure": metrics["exposure"],
  239 |                     "terminal_position": 0.0 if run.positions[-1] == 0 else float(
  240 |                         run.positions[-1])}
  241 |         return _fn
  242 | 
  243 |     context_lookup = {}
  244 |     for start, _end in windows:
  245 |         row = context_at(contexts["rows"], start)
  246 |         if row is not None and row["decision_eligible"]:
  247 |             context_lookup[start] = {"features": row["features"], "state_id": row["state_id"],
  248 |                                      "namespace": row["namespace"]}
  249 | 
  250 |     grids = {}
  251 |     with writer.attempt("L06.1.episodes") as att:
  252 |         for candidate_id, params in all_candidates.items():
  253 |             grids[candidate_id] = EP.build_episodes(
  254 |                 decision_times=[s for s, _ in windows], contexts=context_lookup,
  255 |                 candidate_id=candidate_id, parameter_version=BK.parameter_digest(params),
  256 |                 outcome_fn=outcome_for(params), horizon_days=HORIZON_DAYS)
  257 |         att.detail = {"candidates": len(grids),
  258 |                       "episodes": sum(len(g.episodes) for g in grids.values())}
  259 | 
  260 |     # ---- L06.3 + L06.4 decisions at every episode boundary ------------
  261 |     scheduler = CL.Scheduler()
  262 |     book = CP.CampaignBook()
  263 |     for candidate_id in all_candidates:
  264 |         book.warmups[candidate_id] = CP.IndicatorWarmup(candidate_id, BANK_WARMUP_BARS,
  265 |                                                         bars_seen=BANK_WARMUP_BARS)
  266 |     ledger, responses = [], []
  267 |     response_status_counts: dict[str, int] = {}
  268 |     current_incumbent = incumbent_id
  269 |     last_switch_at = None
  270 | 
```

## SRC09 — `scripts/run_response_policy.py:319–415`

SHA-256: `b4f24e71fa8eac168342c323f547d85305aa9eda07db2f2f4f80b6762b0d4a83`

```text
  319 |             estimates, costs = [], {}
  320 |             pooled = {}
  321 |             for entry in active:
  322 |                 if entry.candidate_id == current_incumbent:
  323 |                     continue
  324 |                 data = prepared.get(entry.candidate_id)
  325 |                 if data is None:
  326 |                     continue
  327 |                 n = usable_prefix(entry.candidate_id, decision_time)
  328 |                 keep = [k for k in range(n) if data["decision_time"][k] in inc_by_time]
  329 |                 if not keep:
  330 |                     continue
  331 |                 cand_u = data["net_return"][keep]
  332 |                 inc_u = np.asarray([inc_by_time[data["decision_time"][k]] for k in keep])
  333 |                 ctx = data["context"][keep]
  334 |                 ages = np.asarray([(decision_time - data["decision_time"][k]).total_seconds()
  335 |                                    / 86400.0 for k in keep])
  336 |                 elig = np.ones(len(keep))
  337 |                 ids = [data["episode_id"][k] for k in keep]
  338 |                 order = data["order"][keep]
  339 |                 # the pooled prior: an UNWEIGHTED mean over every eligible episode, so it
  340 |                 # carries no information about the current context and is a genuine prior
  341 |                 # rather than a second copy of the local estimate
  342 |                 pooled.update(RS.pooled_delta_from({entry.candidate_id: cand_u - inc_u}))
  343 |                 estimate = RS.estimate_response(
  344 |                     response_id=f"resp-{i}-{entry.candidate_id}",
  345 |                     candidate_id=entry.candidate_id, incumbent_id=current_incumbent,
  346 |                     x_t=np.asarray(row["features"], dtype=float),
  347 |                     contexts=ctx, ages_days=ages, eligibility=elig,
  348 |                     feature_weights=np.full(len(row["features"]),
  349 |                                             1.0 / len(row["features"])),
  350 |                     candidate_utility=cand_u, incumbent_utility=inc_u,
  351 |                     episode_ids=ids, order=order,
  352 |                     pooled_delta=pooled[entry.candidate_id])
  353 |                 estimates.append(estimate)
  354 |                 if len(responses) < 4000:
  355 |                     responses.append(estimate.as_record())
  356 |                 response_status_counts[estimate.status] = response_status_counts.get(
  357 |                     estimate.status, 0) + 1
  358 |                 costs[entry.candidate_id] = DC.transition_cost(
  359 |                     projected_turnover=1.0, fee_rate=ACCOUNT["taker_fee_rate"],
  360 |                     slippage_rate=ACCOUNT["slippage_bps"] / 1e4)
  361 | 
  362 |             outcome = DC.decide(
  363 |                 selection_id=f"sel-{i}", decision_time=decision_time,
  364 |                 incumbent_id=current_incumbent, estimates=estimates, costs=costs,
  365 |                 quality_status=row["quality_status"],
  366 |                 campaign_open=bool(book.open_campaigns()),
  367 |                 last_switch_at=last_switch_at,
  368 |                 bank_adequate=bool(active),
  369 |                 warm_candidates={c for c, w in book.warmups.items()
  370 |                                  if w.status == CP.WARMUP_READY},
  371 |                 data_cutoff=str(decision_time), bank_cutoff=str(bank_cutoff),
  372 |                 model_version=row["namespace"],
  373 |                 # guide 13.4: typed params on both sides, and the campaign version
  374 |                 # the decision would replace
  375 |                 incumbent_params=all_candidates.get(current_incumbent),
  376 |                 candidate_params={entry.candidate_id: all_candidates.get(entry.candidate_id)
  377 |                                   for entry in active},
  378 |                 campaign_version=BK.parameter_digest(
  379 |                     all_candidates.get(current_incumbent) or {}))
  380 |             ledger.append(outcome)
  381 |             if outcome.decision == DC.SWITCH_READY:
  382 |                 book.request_activation(outcome.selection_id, outcome.challenger_id,
  383 |                                         decision_time, outcome.reason)
  384 |                 current_incumbent = outcome.challenger_id
  385 |                 last_switch_at = decision_time
  386 |                 scheduler.counters.switches_executed += 1
  387 |         att.detail = {"decisions": len(ledger), "responses": len(responses)}
  388 | 
  389 |     # ---- L06.5 scheduling behaviour on the real cadence ---------------
  390 |     with writer.attempt("L06.5.clocks") as att:
  391 |         for k, cutoff in enumerate(cutoffs):
  392 |             job = scheduler.trigger(f"bank-{k}", CL.BANK_REFRESH, cutoff,
  393 |                                     "frozen baseline calendar")
  394 |             if job.status == CL.JOB_PENDING:
  395 |                 scheduler.complete(job.job_id, cutoff + pd.Timedelta(hours=6))
  396 |                 scheduler.activate(job.job_id, cutoff + pd.Timedelta(hours=6))
  397 |         att.detail = scheduler.counters.as_record()
  398 | 
  399 |     # ---- outputs ------------------------------------------------------
  400 |     panel = pd.concat([EP.to_frame(g) for g in grids.values()], ignore_index=True)
  401 |     panel_path = policy.resolve_write_target(
  402 |         LAB_ROOT / "evidence" / STUDY_ID / role["panel"])
  403 |     panel.to_parquet(panel_path, index=False)
  404 | 
  405 |     ledger_record = DC.summarize_ledger(ledger)
  406 |     informative = EP.informativeness(panel, incumbent_id)
  407 |     response_model = {
  408 |         "schema": "crypto_regime_lab.response_model.v1",
  409 |         "episode_informativeness": informative,
  410 |         "alpha_id": ALPHA, "symbol": SYMBOL,
  411 |         "horizon": horizon_note,
  412 |         "hyperparameters": RS.hyperparameters(),
  413 |         "responses": responses[:400],
  414 |         "response_count": int(sum(response_status_counts.values())),
  415 |         "status_counts": dict(sorted(response_status_counts.items())),
```

## SRC10 — `src/crypto_regime_lab/policy/response.py:100–200`

SHA-256: `4e372653a18e6257597aacf9d35244750224f74a84119e05403654edcc626057`

```text
  100 |             "diagnostics": self.diagnostics.as_record(),
  101 |             "supporting_episodes": self.supporting_episodes,
  102 |             "estimator_note": ("a policy estimator, not a calibrated posterior. The shrinkage is a "
  103 |                                "declared heuristic and the interval it implies is not a coverage "
  104 |                                "guarantee (guide 9.2)"),
  105 |         }
  106 | 
  107 | 
  108 | def context_distance(x_t: np.ndarray, x_e: np.ndarray, weights: np.ndarray) -> float:
  109 |     """Weighted distance in context space. Weights are TRAIN-ONLY (L06.3.4)."""
  110 |     x_t = np.asarray(x_t, dtype=np.float64)
  111 |     x_e = np.asarray(x_e, dtype=np.float64)
  112 |     weights = np.asarray(weights, dtype=np.float64)
  113 |     if x_t.shape != x_e.shape or weights.shape != x_t.shape:
  114 |         raise ValueError("context vectors and weights must have the same shape")
  115 |     diff = x_t - x_e
  116 |     return float(np.sqrt(np.sum(weights * diff * diff)))
  117 | 
  118 | 
  119 | def similarity_weights(x_t: np.ndarray, contexts: np.ndarray, ages_days: np.ndarray,
  120 |                        eligibility: np.ndarray, feature_weights: np.ndarray, *,
  121 |                        bandwidth: float = BANDWIDTH_H,
  122 |                        tau_days: float = RECENCY_TAU_DAYS) -> np.ndarray:
  123 |     """Guide 9.2: ``w = exp(-d^2/2h^2) * exp(-(t-e)/tau) * q_e``.
  124 | 
  125 |     ``eligibility`` may only be 0 or 1. A continuous "quality" that happened to
  126 |     correlate with outcome would smuggle the answer into the weights, so the
  127 |     function refuses anything else.
  128 |     """
  129 |     contexts = np.asarray(contexts, dtype=np.float64)
  130 |     ages = np.asarray(ages_days, dtype=np.float64)
  131 |     eligibility = np.asarray(eligibility, dtype=np.float64)
  132 |     if not np.all(np.isin(eligibility, (0.0, 1.0))):
  133 |         raise ValueError(
  134 |             "eligibility q_e must be 0 or 1. A graded quality score would let outcome-correlated "
  135 |             "information into the weights, which guide 9.2 forbids")
  136 |     if bandwidth <= 0 or tau_days <= 0:
  137 |         raise ValueError("bandwidth and tau must be positive")
  138 |     distances = np.asarray([context_distance(x_t, c, feature_weights) for c in contexts])
  139 |     kernel = np.exp(-(distances ** 2) / (2.0 * bandwidth ** 2))
  140 |     recency = np.exp(-np.maximum(ages, 0.0) / tau_days)
  141 |     return kernel * recency * eligibility
  142 | 
  143 | 
  144 | def effective_sample(weights: np.ndarray) -> float:
  145 |     weights = np.asarray(weights, dtype=np.float64)
  146 |     total = float(weights.sum())
  147 |     if total <= 0:
  148 |         return 0.0
  149 |     return float(total ** 2 / float(np.sum(weights ** 2)))
  150 | 
  151 | 
  152 | #: The support set is the smallest group of episodes carrying this share of the
  153 | #: weight. Counting blocks over EVERY episode with a non-zero weight would always
  154 | #: give one block, because a Gaussian kernel never reaches zero.
  155 | SUPPORT_COVERAGE = 0.90
  156 | 
  157 | 
  158 | def support_set(weights: np.ndarray, coverage: float = SUPPORT_COVERAGE) -> np.ndarray:
  159 |     """Indices of the smallest set of episodes carrying ``coverage`` of the weight."""
  160 |     weights = np.asarray(weights, dtype=np.float64)
  161 |     total = float(weights.sum())
  162 |     if total <= 0:
  163 |         return np.asarray([], dtype=int)
  164 |     order = np.argsort(-weights)
  165 |     cumulative = np.cumsum(weights[order]) / total
  166 |     keep = int(np.searchsorted(cumulative, coverage) + 1)
  167 |     return np.sort(order[:min(keep, weights.size)])
  168 | 
  169 | 
  170 | def contiguous_blocks(order: np.ndarray, weights: np.ndarray, *,
  171 |                       coverage: float = SUPPORT_COVERAGE) -> int:
  172 |     """How many separate stretches of time the real evidence comes from.
  173 | 
  174 |     Counted over the SUPPORT SET, not over every episode with a non-zero weight.
  175 |     The kernel gives some weight to everything, so a threshold near zero would
  176 |     always report one block and the check would be dead. What matters is whether
  177 |     the episodes actually carrying the estimate sit in one stretch of history or
  178 |     several: twelve consecutive weeks inside one market regime are one piece of
  179 |     evidence wearing twelve hats.
  180 |     """
  181 |     order = np.asarray(order)
  182 |     weights = np.asarray(weights, dtype=np.float64)
  183 |     active = support_set(weights, coverage)
  184 |     if active.size == 0:
  185 |         return 0
  186 |     positions = np.sort(order[active])
  187 |     return 1 + int(np.count_nonzero(np.diff(positions) > 1))
  188 | 
  189 | 
  190 | def lag1_autocorrelation(values: np.ndarray) -> float | None:
  191 |     values = np.asarray(values, dtype=np.float64)
  192 |     if values.size < 3:
  193 |         return None
  194 |     centred = values - values.mean()
  195 |     denominator = float(np.sum(centred ** 2))
  196 |     if denominator <= 0:
  197 |         return None
  198 |     return float(np.sum(centred[1:] * centred[:-1]) / denominator)
  199 | 
  200 | 
```

## SRC11 — `src/crypto_regime_lab/policy/bank.py:155–214`

SHA-256: `c3ef5c2bee708bac0464e603f882ce4d5f844c119719cd25ba9e3e4f125a1a55`

```text
  155 |     with a reason rather than dropped quietly, so the lineage is auditable.
  156 |     """
  157 |     bank = CandidateBank(cutoff=pd.Timestamp(cutoff))
  158 |     bank.trial_rows_retained = len(discoveries)
  159 | 
  160 |     eligible = []
  161 |     for row in discoveries:
  162 |         # normalise once and KEEP IT ON THE ROW. Reading a loop variable from the
  163 |         # filtering pass inside the building pass gave every entry the discovery
  164 |         # time of whichever row happened to be last, which is precisely the
  165 |         # lineage field T46 exists to protect.
  166 |         row = {**row, "discovered_at": pd.Timestamp(row["discovered_at"])}
  167 |         discovered = row["discovered_at"]
  168 |         if discovered > bank.cutoff:
  169 |             bank.rejected.append({
  170 |                 "candidate_id": row["candidate_id"], "discovered_at": str(discovered),
  171 |                 "reason": "discovered after the cutoff; a bank at T may not contain it (T46)"})
  172 |             continue
  173 |         eligible.append(row)
  174 | 
  175 |     # merge effective duplicates for COVERAGE, keeping the trial rows
  176 |     kept: list[BankEntry] = []
  177 |     for row in sorted(eligible, key=lambda r: (-float(r.get("score", 0.0)),
  178 |                                                str(r["candidate_id"]))):
  179 |         duplicate_of = None
  180 |         if schema is not None:
  181 |             for entry in kept:
  182 |                 if schema.distance(entry.params, row["params"]) <= duplicate_distance:
  183 |                     duplicate_of = entry
  184 |                     break
  185 |         if duplicate_of is not None:
  186 |             duplicate_of.merged_duplicates.append(row["candidate_id"])
  187 |             continue
  188 |         if len(kept) >= max_size:
  189 |             bank.rejected.append({
  190 |                 "candidate_id": row["candidate_id"],
  191 |                 "reason": f"bank already holds the proposed maximum of {max_size}"})
  192 |             continue
  193 |         kept.append(BankEntry(
  194 |             candidate_id=row["candidate_id"], params=row["params"],
  195 |             discovered_at=row["discovered_at"], entry_date=bank.cutoff,
  196 |             strategy_adapter_hash=adapter_hash,
  197 |             validation_panel=row.get("validation_panel", {}),
  198 |             warmup_bars_required=warmup_bars,
  199 |             status=STATUS_ACTIVE,
  200 |             reason=row.get("reason", "admitted from a pre-cutoff discovery")))
  201 |     bank.entries = kept
  202 |     return bank
  203 | 
  204 | 
  205 | def specialist_note() -> dict:
  206 |     """Guide 7.4 — a specialist is not dropped just because the pooled mean is lower."""
  207 |     return {
  208 |         "rule": ("a candidate whose pooled mean is below the global best may still belong in the "
  209 |                  "bank if it has conditional evidence with enough support. It is dropped for lack "
  210 |                  "of support or for failing cost/risk constraints, never for a low pooled mean "
  211 |                  "alone (guide 7.4)"),
  212 |         "counted_against_search_budget": True,
  213 |         "inactive_params_do_not_add_diversity": True,
  214 |     }
```

## SRC12 — `src/crypto_regime_lab/experiments/evaluator.py:84–119`

SHA-256: `b70fcaa6a53f428648050dbdfc06d222f58c7cc06533abc12d416a393f48d5a5`

```text
   84 | 
   85 | 
   86 | def _engine(frame: pd.DataFrame, tape, backend: str) -> dict:
   87 |     with warnings.catch_warnings():
   88 |         warnings.simplefilter("ignore")
   89 |         return run_intrabar(frame, tape, backend=backend,
   90 |                             initial_capital=ACCOUNT["initial_capital_usdt"],
   91 |                             fee=ACCOUNT["taker_fee_rate"],
   92 |                             slippage_bps=ACCOUNT["slippage_bps"],
   93 |                             use_funding=ACCOUNT["use_funding"], close_on_last_bar=True,
   94 |                             sizing_mode="fixed_notional",
   95 |                             unit_notional=ACCOUNT["entry_notional_usdt"])
   96 | 
   97 | 
   98 | PROTECTIVE = ("stop_loss", "take_profit", "liquidation")
   99 | 
  100 | 
  101 | def _exit_oracle(engine_frame: pd.DataFrame, decision_bar: int, side: int,
  102 |                  stop: float, take_profit: float, *, backend: str,
  103 |                  horizon: int = ORACLE_HORIZON) -> tuple[int | None, float | None, str | None]:
  104 |     """Ask the ENGINE when this one position's resting protection fires.
  105 | 
  106 |     A single forward pass cannot know this, and iterating the whole window to a
  107 |     fixed point converges only about one trade per pass -- measured at roughly
  108 |     17 s per pass for A-HMA, which is hopeless at a 96-candidate budget. Asking
  109 |     the engine about one trade at a time costs about 10 ms and is exact for the
  110 |     quantity that matters: absolute price levels against that bar's own OHLC.
  111 |     The whole-window run afterwards re-derives these exits and any disagreement
  112 |     is reported rather than absorbed.
  113 |     """
  114 |     n = len(engine_frame)
  115 |     hi = min(n, decision_bar + 1 + horizon)
  116 |     segment = engine_frame.iloc[decision_bar:hi]
  117 |     m = len(segment)
  118 |     if m < 2:
  119 |         return None, None, None
```

## SRC13 — `src/crypto_regime_lab/quantbt_bridge/intent_tape.py:55–150`

SHA-256: `b690b50fa08aba7a42fca1b4474654c61f031d7d708a1ee3dbe1e2a295496a0d`

```text
   55 | def build_intent_tape(decisions: list[BarDecision], n_bars: int, *,
   56 |                       unit_size: float = 1.0,
   57 |                       pending_levels: dict[int, tuple[float, float]] | None = None) -> TapeBuild:
   58 |     """Fold a decision tape into the engine's array form.
   59 | 
   60 |     ``pending_levels`` supplies (stop, take_profit) for an entry bar when the
   61 |     adapter derives them from the fill. The engine prices the entry at the next
   62 |     open, so an absolute level chosen at the decision close is an INTENT the
   63 |     engine may reject or clamp; that is the whole point of feeding it through the
   64 |     engine rather than booking it in the adapter.
   65 |     """
   66 |     entry_side = np.zeros(n_bars)
   67 |     entry_size = np.zeros(n_bars)
   68 |     stop_value = np.full(n_bars, np.nan)
   69 |     take_profit_value = np.full(n_bars, np.nan)
   70 |     technical_exit = np.zeros(n_bars, dtype=bool)
   71 |     decision_map: dict[int, dict] = {}
   72 |     unmapped: list[dict] = []
   73 |     levels = pending_levels or {}
   74 | 
   75 |     for decision in decisions:
   76 |         for intent in decision.intents:
   77 |             t = intent.decision_index
   78 |             if intent.kind is IntentKind.ENTER_LONG:
   79 |                 entry_side[t] = 1.0
   80 |                 entry_size[t] = unit_size
   81 |             elif intent.kind is IntentKind.ENTER_SHORT:
   82 |                 entry_side[t] = -1.0
   83 |                 entry_size[t] = unit_size
   84 |             elif intent.kind is IntentKind.EXIT_ALL:
   85 |                 technical_exit[t] = True
   86 |             elif intent.kind is IntentKind.SET_PROTECTION:
   87 |                 if intent.stop_price is not None:
   88 |                     stop_value[t] = intent.stop_price
   89 |                 if intent.take_profit_price is not None:
   90 |                     take_profit_value[t] = intent.take_profit_price
   91 |                 if intent.ladder:
   92 |                     # A multi-rung ladder is not expressible in this tape; the
   93 |                     # final rung is used and the omission is recorded, never hidden.
   94 |                     take_profit_value[t] = intent.ladder[-1][0]
   95 |                     unmapped.append({
   96 |                         "index": t, "kind": intent.kind.value,
   97 |                         "reason": "ladder_rungs_beyond_final_not_expressible_in_intent_tape",
   98 |                         "rungs": [list(x) for x in intent.ladder],
   99 |                         "handling": "BLOCKED_CAPABILITY for partial ladders on this route",
  100 |                     })
  101 |             elif intent.kind in (IntentKind.AMEND_PROTECTION, IntentKind.CANCEL_PROTECTION,
  102 |                                  IntentKind.REDUCE):
  103 |                 unmapped.append({"index": t, "kind": intent.kind.value,
  104 |                                  "reason": "not expressible in IntrabarIntentTape",
  105 |                                  "handling": "BLOCKED_CAPABILITY"})
  106 |             decision_map.setdefault(t, {"intents": []})["intents"].append(intent.kind.value)
  107 | 
  108 |     for t, (stop, tp) in levels.items():
  109 |         if 0 <= t < n_bars:
  110 |             stop_value[t] = stop
  111 |             take_profit_value[t] = tp
  112 | 
  113 |     return TapeBuild(entry_side, entry_size, stop_value, take_profit_value,
  114 |                      technical_exit, decision_map, unmapped)
  115 | 
  116 | 
  117 | def run_intrabar(frame, tape_build: TapeBuild, *, backend: str = "reference",
  118 |                  initial_capital: float = 20000.0, fee: float = 0.0004,
  119 |                  slippage_bps: float = 1.0, use_funding: bool = False,
  120 |                  funding_timestamps=None, funding_rates=None,
  121 |                  close_on_last_bar: bool = True, symbol: str = "S",
  122 |                  sizing_mode: str = "units", unit_notional: float | None = None) -> dict:
  123 |     """Execute a tape on the installed engine and return the account trace."""
  124 |     import quantbt as q
  125 | 
  126 |     factory = {
  127 |         "reference": q.QuantBTEndpoint.intrabar_bracket_reference,
  128 |         "rust": q.QuantBTEndpoint.intrabar_bracket_rust,
  129 |         "auto": q.QuantBTEndpoint.intrabar_bracket,
  130 |     }[backend]
  131 |     sizing = {"units": q.IntrabarSizingMode.UNITS,
  132 |               "fixed_notional": q.IntrabarSizingMode.FIXED_NOTIONAL}[sizing_mode]
  133 |     kwargs: dict[str, Any] = dict(
  134 |         level_mode=q.IntrabarLevelMode.ABSOLUTE_PRICE,
  135 |         intrabar_sizing_mode=sizing,
  136 |         close_on_last_bar=close_on_last_bar,
  137 |         account=q.AccountConfig(initial_capital=initial_capital),
  138 |         fee=fee, slippage_bps=slippage_bps, symbols=[symbol],
  139 |         use_funding=use_funding,
  140 |     )
  141 |     if sizing is q.IntrabarSizingMode.FIXED_NOTIONAL:
  142 |         if unit_notional is None:
  143 |             raise ValueError("fixed_notional sizing requires unit_notional")
  144 |         # The engine reads the per-entry notional from alloc_per_trade (endpoint.py:3087);
  145 |         # passing it any other way silently sizes every entry at zero.
  146 |         kwargs["alloc_per_trade"] = float(unit_notional)
  147 |     elif unit_notional is not None:
  148 |         raise ValueError("unit_notional only applies to sizing_mode='fixed_notional'")
  149 |     endpoint = factory(**kwargs)
  150 |     backtest_kwargs: dict[str, Any] = {"data": frame, "intent": tape_build.as_tape()}
```

## SRC14 — `src/crypto_regime_lab/experiments/evaluator.py:126–239`

SHA-256: `b70fcaa6a53f428648050dbdfc06d222f58c7cc06533abc12d416a393f48d5a5`

```text
  126 |     tape.take_profit_value[0] = take_profit
  127 |     out = _engine(segment, tape, backend)
  128 |     for fill in out["fills"]:
  129 |         if fill["reason"] in PROTECTIVE:
  130 |             return decision_bar + int(fill["bar_index"]), float(fill["price"]), fill["reason"]
  131 |     return None, None, None
  132 | 
  133 | 
  134 | def _sweep(alpha_id: str, params: dict, frame: pd.DataFrame, arrays: list[np.ndarray],
  135 |            engine_frame: pd.DataFrame, *, backend: str,
  136 |            forced_exits: dict[int, float] | None = None):
  137 |     """One chronological pass. Protective exits come from the oracle, or from a
  138 |     previously observed whole-window run when ``forced_exits`` is supplied."""
  139 |     n = len(frame)
  140 |     open_ = arrays[0]
  141 |     market = MarketSlice(*arrays, index=frame.index)
  142 |     adapter = build_adapter(alpha_id, params, market)
  143 |     pending_levels: dict[int, tuple[float, float]] = {}
  144 |     applied_exits: dict[int, float] = {}
  145 |     next_exit_bar: int | None = None
  146 |     next_exit_price: float | None = None
  147 | 
  148 |     for t in range(n):
  149 |         if forced_exits is not None and t in forced_exits and adapter.state.position != 0.0:
  150 |             adapter.on_fill(Fill(index=t, side=-int(np.sign(adapter.state.position)),
  151 |                                  quantity=-adapter.state.position,
  152 |                                  price=float(forced_exits[t]), intent_kind=IntentKind.EXIT_ALL))
  153 |             applied_exits[t] = float(forced_exits[t])
  154 |         elif next_exit_bar == t and adapter.state.position != 0.0:
  155 |             adapter.on_fill(Fill(index=t, side=-int(np.sign(adapter.state.position)),
  156 |                                  quantity=-adapter.state.position,
  157 |                                  price=float(next_exit_price), intent_kind=IntentKind.EXIT_ALL))
  158 |             applied_exits[t] = float(next_exit_price)
  159 |             next_exit_bar, next_exit_price = None, None
  160 | 
  161 |         decision = adapter.on_bar_close(t)
  162 |         for intent in decision.intents:
  163 |             if intent.kind in (IntentKind.ENTER_LONG, IntentKind.ENTER_SHORT) and t + 1 < n:
  164 |                 side = 1 if intent.kind is IntentKind.ENTER_LONG else -1
  165 |                 qty = ACCOUNT["entry_notional_usdt"] / max(float(open_[t + 1]), 1e-12)
  166 |                 follow_ups = adapter.on_fill(Fill(index=t + 1, side=side,
  167 |                                                   quantity=float(side) * qty,
  168 |                                                   price=float(open_[t + 1]),
  169 |                                                   intent_kind=intent.kind))
  170 |                 stop = take_profit = float("nan")
  171 |                 for follow in follow_ups:
  172 |                     if follow.stop_price is not None:
  173 |                         stop = float(follow.stop_price)
  174 |                         tp = follow.take_profit_price
  175 |                         if tp is None and follow.ladder:
  176 |                             tp = follow.ladder[-1][0]
  177 |                         take_profit = float(tp) if tp is not None else float("nan")
  178 |                 if np.isfinite(stop) or np.isfinite(take_profit):
  179 |                     pending_levels[t] = (stop, take_profit)
  180 |                     if forced_exits is None:
  181 |                         bar, price, _ = _exit_oracle(engine_frame, t, side, stop, take_profit,
  182 |                                                      backend=backend)
  183 |                         next_exit_bar, next_exit_price = bar, price
  184 |             elif intent.kind is IntentKind.EXIT_ALL and adapter.state.position != 0.0 \
  185 |                     and t + 1 < n:
  186 |                 adapter.on_fill(Fill(index=t + 1,
  187 |                                      side=-int(np.sign(adapter.state.position)),
  188 |                                      quantity=-adapter.state.position,
  189 |                                      price=float(open_[t + 1]),
  190 |                                      intent_kind=IntentKind.EXIT_ALL))
  191 |                 next_exit_bar, next_exit_price = None, None
  192 |     return adapter, pending_levels, applied_exits
  193 | 
  194 | 
  195 | def run_candidate(alpha_id: str, params: dict, frame: pd.DataFrame, *,
  196 |                   backend: str = "reference", max_sweeps: int = MAX_SWEEPS) -> CandidateRun:
  197 |     """Evaluate one parameter point over one contiguous window.
  198 | 
  199 |     Sweep chronologically with an exit oracle, run the resulting tape over the
  200 |     whole window, and require the whole-window protective exits to agree with the
  201 |     exits the adapter was actually driven with. Disagreement triggers a bounded
  202 |     repair and, if it persists, ``converged=False`` on the record.
  203 |     """
  204 |     n = len(frame)
  205 |     if n < 10:
  206 |         raise EvaluationError(f"window of {n} bars is too short to evaluate")
  207 |     arrays = [frame[c].to_numpy(float) for c in ("open", "high", "low", "close", "volume")]
  208 |     engine_frame = frame[["open", "high", "low", "close", "volume"]]
  209 | 
  210 |     forced: dict[int, float] | None = None
  211 |     out = build = None
  212 |     applied: dict[int, float] = {}
  213 |     sweeps = 0
  214 |     for attempt in range(max_sweeps):
  215 |         sweeps = attempt + 1
  216 |         adapter, pending, applied = _sweep(alpha_id, params, frame, arrays, engine_frame,
  217 |                                            backend=backend, forced_exits=forced)
  218 |         build = build_intent_tape(adapter.decisions, n, unit_size=1.0, pending_levels=pending)
  219 |         out = _engine(engine_frame, build, backend)
  220 |         observed = {int(f["bar_index"]): float(f["price"]) for f in out["fills"]
  221 |                     if f["reason"] in PROTECTIVE}
  222 |         if set(observed) == set(applied):
  223 |             return CandidateRun(np.asarray(out["equity"], float).reshape(-1),
  224 |                                 np.asarray(out["positions"], float).reshape(-1),
  225 |                                 out["fills"], frame.index, True, sweeps,
  226 |                                 int(np.count_nonzero(build.entry_side)),
  227 |                                 len(build.unmapped_intents),
  228 |                                 {"protective_exits": len(observed)})
  229 |         forced = observed
  230 | 
  231 |     return CandidateRun(np.asarray(out["equity"], float).reshape(-1),
  232 |                         np.asarray(out["positions"], float).reshape(-1),
  233 |                         out["fills"], frame.index, False, sweeps,
  234 |                         int(np.count_nonzero(build.entry_side)),
  235 |                         len(build.unmapped_intents),
  236 |                         {"unconverged_exit_symmetric_difference":
  237 |                              len(set(applied).symmetric_difference(
  238 |                                  {int(f["bar_index"]) for f in out["fills"]
  239 |                                   if f["reason"] in PROTECTIVE}))})
```

## SRC15 — `src/crypto_regime_lab/experiments/evaluator.py:246–326`

SHA-256: `b70fcaa6a53f428648050dbdfc06d222f58c7cc06533abc12d416a393f48d5a5`

```text
  246 | def episode_bounds(index: pd.DatetimeIndex, episodes: int) -> list[tuple[str, int, int]]:
  247 |     """Contiguous inner episodes of EQUAL bar length (guide 7.3).
  248 | 
  249 |     Equal length is the point: the score may not mix long and short blocks, so a
  250 |     remainder is dropped from the front rather than making one block longer.
  251 |     """
  252 |     n = len(index)
  253 |     if episodes <= 0 or n < episodes * 2:
  254 |         raise EvaluationError(f"window of {n} bars cannot carry {episodes} inner episodes")
  255 |     size = n // episodes
  256 |     start0 = n - size * episodes
  257 |     return [(f"e{i}", start0 + i * size, start0 + (i + 1) * size) for i in range(episodes)]
  258 | 
  259 | 
  260 | def _drawdown(equity: np.ndarray) -> float:
  261 |     peak = np.maximum.accumulate(equity)
  262 |     with np.errstate(divide="ignore", invalid="ignore"):
  263 |         dd = np.where(peak > 0, (peak - equity) / peak, 0.0)
  264 |     return float(np.max(dd)) if dd.size else 0.0
  265 | 
  266 | 
  267 | def episode_metrics(run: CandidateRun, bounds: list[tuple[str, int, int]]) -> dict:
  268 |     """Utility and gate outcome per inner episode.
  269 | 
  270 |     U = (net return - lambda_dd * max drawdown) / risk unit, with net return taken
  271 |     against the frozen initial capital so every episode is measured against the
  272 |     same fixed risk allocation rather than a drifting equity base.
  273 |     """
  274 |     capital = ACCOUNT["initial_capital_usdt"]
  275 |     out: dict[str, dict] = {}
  276 |     for name, lo, hi in bounds:
  277 |         segment = run.equity[lo:hi]
  278 |         if segment.size < 2 or not np.isfinite(segment).all():
  279 |             raise EvaluationError(f"episode {name}: account trace is not finite")
  280 |         net_return = float(segment[-1] - segment[0]) / capital
  281 |         mdd = _drawdown(segment)
  282 |         utility = (net_return - UTILITY["drawdown_penalty"] * mdd) / UTILITY["risk_unit_fraction"]
  283 |         trades = sum(1 for f in run.fills if lo <= f["bar_index"] < hi)
  284 |         exposure = float(np.mean(np.abs(run.positions[lo:hi]) > 0.0))
  285 |         out[name] = {
  286 |             "utility": float(utility), "net_return": net_return, "max_drawdown": mdd,
  287 |             "trades": int(trades), "exposure": exposure,
  288 |             "gate_pass": bool(net_return > UTILITY["gate_min_return"]
  289 |                               and mdd <= UTILITY["gate_max_drawdown"]),
  290 |         }
  291 |     return out
  292 | 
  293 | 
  294 | def window_metrics(run: CandidateRun) -> dict:
  295 |     """Whole-window summary, used for deployment reporting rather than selection."""
  296 |     capital = ACCOUNT["initial_capital_usdt"]
  297 |     equity = run.equity
  298 |     net_return = float(equity[-1] - equity[0]) / capital
  299 |     steps = np.diff(equity) / capital
  300 |     sharpe = None
  301 |     if steps.size > 2 and float(np.std(steps)) > 0:
  302 |         sharpe = float(np.mean(steps) / np.std(steps) * np.sqrt(len(steps)))
  303 |     holding = []
  304 |     open_at = None
  305 |     for i, pos in enumerate(run.positions):
  306 |         if pos != 0.0 and open_at is None:
  307 |             open_at = i
  308 |         elif pos == 0.0 and open_at is not None:
  309 |             holding.append(i - open_at)
  310 |             open_at = None
  311 |     return {
  312 |         "net_return": net_return,
  313 |         "max_drawdown": _drawdown(equity),
  314 |         "sharpe_per_window": sharpe,
  315 |         "fills": len(run.fills),
  316 |         "entries": run.entries,
  317 |         "exposure": float(np.mean(np.abs(run.positions) > 0.0)),
  318 |         "mean_holding_bars": float(np.mean(holding)) if holding else None,
  319 |         "bars": int(equity.size),
  320 |         "converged": run.converged,
  321 |         "passes": run.passes,
  322 |         "unmapped_intents": run.unmapped_intents,
  323 |     }
  324 | 
  325 | 
  326 | def run_candidate_fixed_point_reference(alpha_id: str, params: dict, frame: pd.DataFrame, *,
```

## SRC16 — `src/crypto_regime_lab/experiments/calendar_baseline.py:142–210`

SHA-256: `f468f00abf37afe692f0f7650dff411d4a38e1f72e71c4e632b79e8c8ee8642d`

```text
  142 | # ---------------------------------------------------------------------------
  143 | 
  144 | @dataclass
  145 | class Evaluation:
  146 |     point_id: str
  147 |     params: dict
  148 |     origin: str
  149 |     status: str
  150 |     episodes: dict = field(default_factory=dict)
  151 |     window: dict = field(default_factory=dict)
  152 |     error: str | None = None
  153 | 
  154 |     @property
  155 |     def objective(self) -> float:
  156 |         """The in-sample aggregate arm A ranks on: the mean episode utility."""
  157 |         values = [e["utility"] for e in self.episodes.values()]
  158 |         return float(np.mean(values)) if values else float("-inf")
  159 | 
  160 | 
  161 | def _evaluate(alpha_id: str, params: dict, frame: pd.DataFrame, bounds, origin: str,
  162 |               schema: ParamSchema, backend: str) -> Evaluation:
  163 |     point_id = _point_id(params)
  164 |     feasible, reason = schema.is_feasible(params)
  165 |     if not feasible:
  166 |         return Evaluation(point_id, params, origin, ProbeStatus.STRUCTURALLY_INVALID,
  167 |                           error=reason)
  168 |     try:
  169 |         run = run_candidate(alpha_id, params, frame, backend=backend)
  170 |         episodes = episode_metrics(run, bounds)
  171 |         window = window_metrics(run)
  172 |     except EvaluationError as exc:
  173 |         return Evaluation(point_id, params, origin, ProbeStatus.RUNTIME_ERROR, error=str(exc))
  174 |     except Exception as exc:                      # a real failure, never a loss of 0
  175 |         return Evaluation(point_id, params, origin, ProbeStatus.RUNTIME_ERROR,
  176 |                           error=f"{type(exc).__name__}: {exc}")
  177 |     return Evaluation(point_id, params, origin, ProbeStatus.EVALUATED, episodes, window)
  178 | 
  179 | 
  180 | def _discover(alpha_id: str, schema: ParamSchema, frame: pd.DataFrame, bounds,
  181 |               budget: SearchBudget, seed: int, backend: str) -> list[Evaluation]:
  182 |     """TPE search on the training window only. It never sees the test window."""
  183 |     import logging
  184 | 
  185 |     import optuna
  186 | 
  187 |     optuna.logging.set_verbosity(optuna.logging.WARNING)
  188 |     logging.getLogger("optuna").setLevel(logging.WARNING)
  189 |     found: list[Evaluation] = []
  190 |     seen: set[str] = set()
  191 | 
  192 |     def objective(trial):
  193 |         point = suggest_point(trial, schema)
  194 |         pid = _point_id(point)
  195 |         if pid in seen:
  196 |             # A repeat costs no execution; it is reported, not counted as new evidence.
  197 |             prior = next(e for e in found if e.point_id == pid)
  198 |             return prior.objective if prior.status == ProbeStatus.EVALUATED else -1e9
  199 |         seen.add(pid)
  200 |         record = _evaluate(alpha_id, point, frame, bounds, "discovery", schema, backend)
  201 |         found.append(record)
  202 |         return record.objective if record.status == ProbeStatus.EVALUATED else -1e9
  203 | 
  204 |     study = optuna.create_study(direction="maximize",
  205 |                                 sampler=optuna.samplers.TPESampler(seed=seed))
  206 |     study.optimize(objective, n_trials=budget.discovery_trials, catch=(Exception,))
  207 |     return found
  208 | 
  209 | 
  210 | def run_cutoff(alpha_id: str, symbol: str, train: pd.DataFrame, fold: int,
```

## SRC17 — `src/crypto_regime_lab/experiments/calendar_baseline.py:351–409`

SHA-256: `f468f00abf37afe692f0f7650dff411d4a38e1f72e71c4e632b79e8c8ee8642d`

```text
  351 |         "local_coverage": _coverage(neighbourhoods, ok, calendar.inner_episodes),
  352 |         "evaluations": [
  353 |             {"point_id": pid, "origin": e.origin, "status": e.status,
  354 |              "objective": _finite(e.objective) if e.status == ProbeStatus.EVALUATED else None,
  355 |              "error": e.error}
  356 |             for pid, e in evaluated.items()
  357 |         ],
  358 |         "robust_scores": {pid: s for pid, s in scored["scores"].items()},
  359 |     }
  360 | 
  361 | 
  362 | def _select_with_installed(ok: dict[str, Evaluation]) -> dict:
  363 |     """Arm A. The decision is made by the installed function, not reimplemented."""
  364 |     from quantbt.walkforward import WalkForwardConfig, WalkForwardTrialRecord
  365 |     from quantbt.walkforward import _select_oos_candidate_record
  366 | 
  367 |     if not ok:
  368 |         return {"status": "NO_EVALUATION", "params": None,
  369 |                 "reason": "no candidate produced a valid evaluation"}
  370 |     order = sorted(ok)
  371 |     records = []
  372 |     for i, pid in enumerate(order):
  373 |         e = ok[pid]
  374 |         records.append(WalkForwardTrialRecord(
  375 |             trial_id=i, params=dict(e.params), objective=e.objective,
  376 |             mean_is_sharpe=e.objective, mean_oos_sharpe=0.0, mean_decay=0.0, std_decay=0.0,
  377 |             fold_metrics=[], pruned=False,
  378 |             selection_metadata={"stage": "is_search", "lab_point_id": pid,
  379 |                                 "oos_seen_by_optuna": False}))
  380 |     config = WalkForwardConfig()
  381 |     chosen = _select_oos_candidate_record(records, config)
  382 |     return {
  383 |         "status": "SELECTED",
  384 |         "selector": "quantbt.walkforward._select_oos_candidate_record",
  385 |         "candidate_selection_metric": config.candidate_selection_metric,
  386 |         "optimization_mode": config.optimization_mode,
  387 |         "rule": "max(records, key=objective) -- the public route's default",
  388 |         "point_id": chosen.selection_metadata.get("lab_point_id"),
  389 |         "params": dict(chosen.params),
  390 |         "objective": _finite(chosen.objective),
  391 |         "candidates_considered": len(records),
  392 |         "selection_metadata": {k: v for k, v in chosen.selection_metadata.items()
  393 |                                if isinstance(v, (str, int, float, bool, type(None)))},
  394 |     }
  395 | 
  396 | 
  397 | def _select_with_neighborhood(schema: ParamSchema, scored: dict, eligible: dict,
  398 |                               ok: dict[str, Evaluation]) -> dict:
  399 |     """Arm B. R = G - lambda_F*F over an independently designed local panel."""
  400 |     if not eligible:
  401 |         cause = _dominant_cause(scored["status_counts"])
  402 |         return {"status": f"NO_ADMISSIBLE_CANDIDATE:{cause}", "params": None,
  403 |                 "selector": "lab robust neighborhood",
  404 |                 "binding_constraint": cause,
  405 |                 "reason": "no candidate passed quality, survival and local-evidence gates; "
  406 |                           "the incumbent is retained rather than fabricating a plateau",
  407 |                 "status_counts": scored["status_counts"]}
  408 |     best_r = max(eligible, key=lambda pid: (scored["scores"][pid]["r"], -int(pid, 16)))
  409 |     rep = choose_representative(schema, eligible,
```

## SRC18 — `src/crypto_regime_lab/selector/alpha_schemas.py:35–85`

SHA-256: `933268e7b8d727016c74bec73811effc3a5f09fb4af3a816cd04cba83ff10b0b`

```text
   35 |         ParamSpec("AP", "int", 5, 60, 1),
   36 |         ParamSpec("alpha.condition_threshold", "int", 30, 80, 5),
   37 |         ParamSpec("novolumedata", "fixed", fixed_value=False),
   38 |         ParamSpec("src_col", "fixed", fixed_value="close"),
   39 |     ],
   40 |     name="A-SC",
   41 | )
   42 | 
   43 | A_HMA = ParamSchema.from_specs(
   44 |     [
   45 |         ParamSpec("min_length", "int", 40, 360, 10),
   46 |         ParamSpec("max_length", "int", 60, 420, 10),
   47 |         ParamSpec("minor_min", "int", 10, 120, 2),
   48 |         ParamSpec("minor_max", "int", 30, 220, 5),
   49 |         ParamSpec("flat", "float", 4.0, 50.0, 1.0),
   50 |         ParamSpec("atr_fast", "int", 4, 60, 2),
   51 |         ParamSpec("atr_slow", "int", 10, 140, 5),
   52 |         ParamSpec("mult", "float", 0.5, 6.0, 0.25),
   53 |         ParamSpec("max_sl", "float", 1.0, 9.0, 0.25),
   54 |         ParamSpec("take_profit", "float", 1.0, 8.0, 0.5),
   55 |         ParamSpec("min_profit", "float", 0.1, 4.0, 0.1),
   56 |         ParamSpec("sl_input", "categorical",
   57 |                   choices=("Half Distance Zone", "Zone Distance", "ATR")),
   58 |         ParamSpec("tick_size", "fixed", fixed_value=0.01),
   59 |     ],
   60 |     dependencies=(("min_length", "max_length"), ("minor_min", "minor_max"),
   61 |                   ("atr_fast", "atr_slow")),
   62 |     name="A-HMA",
   63 | )
   64 | 
   65 | A_VWAP = ParamSchema.from_specs(
   66 |     [
   67 |         ParamSpec("rsi_len", "int", 5, 80, 1),
   68 |         ParamSpec("rsi_os", "int", 10, 50, 1),
   69 |         ParamSpec("rsi_ob", "int", 55, 90, 1),
   70 |         ParamSpec("dev_mult", "float", 0.5, 5.0, 0.1),
   71 |         ParamSpec("atr_len", "int", 5, 90, 1),
   72 |         ParamSpec("stop_atr", "float", 1.0, 10.0, 0.1),
   73 |         ParamSpec("target_r", "float", 1.0, 10.0, 0.1),
   74 |         ParamSpec("htf_ema_len", "int", 20, 700, 10),
   75 |         ParamSpec("exit_at_vwap", "bool", choices=(False, True)),
   76 |         ParamSpec("time_stop_on", "bool", choices=(False, True)),
   77 |         # only meaningful when the time stop is on -> declared conditional
   78 |         ParamSpec("time_stop_bars", "int", 5, 120, 5, active_when=("time_stop_on", True)),
   79 |         ParamSpec("htf_tf", "fixed", fixed_value="1h"),
   80 |     ],
   81 |     dependencies=(("rsi_os", "rsi_ob"),),
   82 |     name="A-VWAP",
   83 | )
   84 | 
   85 | A_HASH = ParamSchema.from_specs(
```

## SRC19 — `src/crypto_regime_lab/alphas/a_hma.py:26–40`

SHA-256: `dbd05eb744b85ec5e50d592f68912cc9526667bbb57ef8b1f54ff4d5b8d682ca`

```text
   26 | from .contracts import (
   27 |     BarDecision, ExecutionPhase, Fill, IntentKind, OrderIntent, QuantityBasis,
   28 | )
   29 | from .reference import indicators as ref
   30 | 
   31 | ADAPT_PCT = 0.03141
   32 | SL_MODES = {"One Distance Zone": 0, "Half Distance Zone": 1, "Last High/Low": 2, "ATR Only": 3}
   33 | IGNORED_KNOBS = ("sl_mult", "double_up", "time_ms", "volume")
   34 | 
   35 | 
   36 | class InfeasibleConfiguration(ValueError):
   37 |     """Raised for a configuration the adapter refuses to run (SD-HMA-05)."""
   38 | 
   39 | 
   40 | @dataclass
```

## SRC20 — `src/crypto_regime_lab/alphas/a_hma.py:248–272`

SHA-256: `dbd05eb744b85ec5e50d592f68912cc9526667bbb57ef8b1f54ff4d5b8d682ca`

```text
  248 |                                target_after_close=target, diagnostics=diagnostics)
  249 | 
  250 |         tick = float(self.params["tick_size"])
  251 |         pip_size = tick * 10.0                                  # SD-HMA-04
  252 |         sl_low_max = m.low[t] - float(self.params["max_sl"]) * f.atr_base[t]
  253 |         sl_high_max = m.high[t] + float(self.params["max_sl"]) * f.atr_base[t]
  254 |         lo = t - 47 if t >= 47 else 0
  255 |         hh48 = float(np.max(m.high[lo:t + 1]))
  256 |         ll48 = float(np.min(m.low[lo:t + 1]))
  257 |         last_high = hh48 + 5.0 * pip_size
  258 |         last_low = ll48 - 5.0 * pip_size
  259 | 
  260 |         mode = SL_MODES.get(self.params.get("sl_input", "Half Distance Zone"), 1)
  261 |         sl_buy_raw, sl_sell_raw = {
  262 |             0: (bot_tl, top_tl),
  263 |             1: (lower_tl, upper_tl),
  264 |             2: (last_low, last_high),
  265 |         }.get(mode, (sl_low_max, sl_high_max))
  266 | 
  267 |         buy = (up_sig and not up_prev and m.close[t] > f.dynamic_hma[t]
  268 |                and m.low[t] <= upper_tl and 51.0 < f.rsi[t] <= 70.0)
  269 |         sell = (dn_sig and not dn_prev and m.close[t] < f.dynamic_hma[t]
  270 |                 and m.high[t] >= lower_tl and 30.0 <= f.rsi[t] < 49.0)
  271 |         mid = (m.high[t] + m.low[t]) / 2.0
  272 |         over_buy = (up_sig and not up_prev and f.rsi[t] > 70.0 and m.close[t] > f.dynamic_hma[t]
```

## SRC21 — `src/crypto_regime_lab/alphas/a_hma.py:315–352`

SHA-256: `dbd05eb744b85ec5e50d592f68912cc9526667bbb57ef8b1f54ff4d5b8d682ca`

```text
  315 |         return BarDecision(index=t, position_entering_bar=entering, target_after_close=target,
  316 |                            intents=intents, diagnostics=diagnostics)
  317 | 
  318 |     # -- fills ------------------------------------------------------------
  319 | 
  320 |     def _levels_from_fill(self, fill: Fill) -> list[OrderIntent]:
  321 |         """Validate the staged bracket against the ACTUAL fill (finding HM-03)."""
  322 |         staged = getattr(self, "_staged", None)
  323 |         if staged is None:
  324 |             return []
  325 |         stop_level = staged["stop_level"]
  326 |         tp_level = staged["tp_level"]
  327 |         side = staged["side"]
  328 |         wrong_side = (side > 0 and (stop_level >= fill.price or tp_level <= fill.price)) or \
  329 |                      (side < 0 and (stop_level <= fill.price or tp_level >= fill.price))
  330 |         if wrong_side:
  331 |             if self.gap_policy == "reject":
  332 |                 self.state.pending_exit = True
  333 |                 return [OrderIntent(
  334 |                     kind=IntentKind.EXIT_ALL, decision_index=fill.index,
  335 |                     earliest_phase=ExecutionPhase.NEXT_OPEN,
  336 |                     reason="bracket_invalid_after_gap",
  337 |                     metadata={"policy": "reject", "fill_price": fill.price,
  338 |                               "stop_level": stop_level, "tp_level": tp_level,
  339 |                               "note": "a gap put a protective level on the wrong side of the fill; "
  340 |                                       "the position is closed rather than booked as instant profit"})]
  341 |             distance_stop = abs(staged["stop_level"] - self.market.close[staged["decision_index"]])
  342 |             distance_tp = abs(staged["tp_level"] - self.market.close[staged["decision_index"]])
  343 |             stop_level = fill.price - side * distance_stop
  344 |             tp_level = fill.price + side * distance_tp
  345 |         self.state.stop_price = stop_level
  346 |         self.state.take_profit_price = tp_level
  347 |         return [OrderIntent(
  348 |             kind=IntentKind.SET_PROTECTION, decision_index=fill.index,
  349 |             earliest_phase=ExecutionPhase.RESTING_INTRABAR, reason="bracket_from_actual_fill",
  350 |             stop_price=stop_level, take_profit_price=tp_level,
  351 |             metadata={"fill_price": fill.price, "gap_policy": self.gap_policy,
  352 |                       "normalized": bool(wrong_side and self.gap_policy == "normalize")})]
```

## SRC22 — `src/crypto_regime_lab/alphas/a_vwap.py:201–233`

SHA-256: `242facf154f4505ab862ac6815ee497d0e9c6e3ee70bbdb8b6cb1895a2900b77`

```text
  201 | 
  202 |         # ---- open position: only the TIME stop is a close decision ----
  203 |         # The stop and the take profit are resting orders working in the engine;
  204 |         # the adapter never books them itself (finding AV-02).
  205 |         if entering != 0.0:
  206 |             bars_held = t - (self.state.entry_index if self.state.entry_index is not None else t)
  207 |             time_stop_due = bool(self.params["time_stop_on"]) and \
  208 |                 bars_held >= int(self.params["time_stop_bars"])
  209 |             diagnostics["bars_held"] = bars_held
  210 |             diagnostics["time_stop_due"] = time_stop_due
  211 |             if time_stop_due and not self.state.pending_exit:
  212 |                 self.state.pending_exit = True
  213 |                 target = 0.0
  214 |                 intents.append(OrderIntent(
  215 |                     kind=IntentKind.EXIT_ALL, decision_index=t,
  216 |                     earliest_phase=ExecutionPhase.NEXT_OPEN, reason="time_stop",
  217 |                     metadata={"exit_reason": "time_stop", "bars_held": bars_held,
  218 |                               "precedence": list(EXIT_PRECEDENCE),
  219 |                               "note": "submitted at the close; a resting stop or take profit that "
  220 |                                       "triggered intrabar takes precedence"}))
  221 |             if bool(self.params["exit_at_vwap"]) and not self.state.pending_exit:
  222 |                 # SD-VWAP-04: rest at the PREVIOUS bar's observed VWAP, never this bar's.
  223 |                 intents.append(OrderIntent(
  224 |                     kind=IntentKind.AMEND_PROTECTION, decision_index=t,
  225 |                     earliest_phase=ExecutionPhase.RESTING_INTRABAR,
  226 |                     reason="dynamic_vwap_resting_previous_observed",
  227 |                     price=float(f.vwap[t]),
  228 |                     metadata={"effective_from_bar": t + 1,
  229 |                               "variant": "resting_previous_observed_vwap"}))
  230 |             return BarDecision(index=t, position_entering_bar=entering, target_after_close=target,
  231 |                                intents=intents, diagnostics=diagnostics)
  232 | 
  233 |         if self.state.pending_entry_side:
```

## SRC23 — `scripts/close_lab01_blockers.py:52–94`

SHA-256: `45f98643f03b22cb0c3d2247c0b27785d7d3f36d6c3683509cbc808b7c06199d`

```text
   52 |     qualification = json.loads((configs / "market_qualification.json").read_text())
   53 |     per_alpha_turnover = {}
   54 |     for record in qualification["results"]:
   55 |         if record["status"] != "QUALIFIED":
   56 |             continue
   57 |         interval = DECISION_INTERVAL[record["alpha_id"]]
   58 |         bars_per_day = {"15min": 96, "1h": 24, "4h": 6}[interval]
   59 |         days = record["bars"] / bars_per_day
   60 |         entries = record["checks"]["entries"]
   61 |         per_alpha_turnover.setdefault(record["alpha_id"], []).append(entries / days if days else 0.0)
   62 | 
   63 |     round_trips_per_day = {a: sum(v) / len(v) for a, v in per_alpha_turnover.items()}
   64 |     busiest = max(round_trips_per_day.values()) if round_trips_per_day else 0.0
   65 |     round_trip_cost = 2.0 * (TAKER_FEE + SLIPPAGE)
   66 |     stress_span = round_trip_cost * (max(COST_STRESS) - min(COST_STRESS))
   67 |     minimum_daily_effect = stress_span * busiest
   68 | 
   69 |     effect = {
   70 |         "schema": "crypto_regime_lab.minimum_economic_effect.v1",
   71 |         "registered_at_utc": utc_now_iso(),
   72 |         "registered_before_any_arm_comparison": True,
   73 |         "definition": "the smallest mean daily net-return difference the lab will call economically "
   74 |                       "meaningful for the primary endpoint",
   75 |         "derivation": {
   76 |             "taker_fee": TAKER_FEE,
   77 |             "slippage": SLIPPAGE,
   78 |             "round_trip_cost": round_trip_cost,
   79 |             "cost_stress_multipliers": list(COST_STRESS),
   80 |             "cost_uncertainty_per_round_trip": stress_span,
   81 |             "round_trips_per_day_by_alpha": round_trips_per_day,
   82 |             "busiest_alpha_round_trips_per_day": busiest,
   83 |             "formula": "cost_uncertainty_per_round_trip * busiest_round_trips_per_day",
   84 |         },
   85 |         "minimum_daily_net_return_difference": minimum_daily_effect,
   86 |         "minimum_daily_net_return_bps": minimum_daily_effect * 1e4,
   87 |         "rule": (
   88 |             "an improvement smaller than this sits inside the registered cost-stress band and is "
   89 |             "reported as inconclusive, not as an edge. The threshold is fixed now, before any arm "
   90 |             "has been compared, so it can never be chosen to fit an observed delta (guide 11.2)."
   91 |         ),
   92 |         "turnover_source": "market qualification on development slices; a smoke measurement, not a "
   93 |                            "performance claim",
   94 |     }
```

## SRC24 — `scripts/fit_regime_model.py:140–220`

SHA-256: `3057737f342d9f11cf237d4a3a300c2ef69b43b84cf68d468f331077759339ae`

```text
  140 |     ROLE = args.role
  141 |     ARTIFACT_PREFIX = args.artifact_prefix or (
  142 |         "lab05" if SYMBOL == "BTCUSDT" else f"lab08_{SYMBOL.lower()}")
  143 |     if ROLE != "development":
  144 |         unlock = LAB_ROOT / "configs" / "lab09_confirmation_spec.json"
  145 |         if not unlock.is_file():
  146 |             print(f"BLOCKED: role={ROLE} needs the L09.1 unlock "
  147 |                   "(scripts/unlock_lab09_confirmation.py) to exist first")
  148 |             return 1
  149 |     policy = SandboxPolicy.load(LAB_ROOT / "configs" / "sandbox_policy.json")
  150 |     policy.assert_lab_root_ok()
  151 |     policy.assert_lab_marker_ok(STUDY_ID)
  152 |     writer = EvidenceWriter.open(policy, study_id=STUDY_ID)
  153 | 
  154 |     frame, features, weights, schema = load_panel(policy)
  155 |     role = ROLES[ROLE]
  156 |     role_end = role["end"] or str(pd.Timestamp(frame["time"].max()).date())
  157 |     # `development` is the FITTING scope: every training window is cut from it. It
  158 |     # reaches back before the role starts because a trailing memory has to come from
  159 |     # somewhere; the emission loop below starts at the first cutoff, so nothing is
  160 |     # ever emitted before the role begins.
  161 |     development = frame[frame["time"] <= role_end].reset_index(drop=True)
  162 |     cutoffs = fit_cutoffs(DEVELOPMENT_START, role_end, TRAIN_MEMORY_DAYS,
  163 |                           FIT_CADENCE_DAYS, first_cutoff=role["first_cutoff"])
  164 |     groups: dict[str, list[int]] = {}
  165 |     for i, name in enumerate(features):
  166 |         groups.setdefault(name.split("_")[0].upper(), []).append(i)
  167 | 
  168 |     with writer.attempt("L05.4.choose_k") as att:
  169 |         # K is chosen on the FIRST cutoff's training window only, then frozen for
  170 |         # every later refit: re-choosing K at each refit would be selecting model
  171 |         # complexity repeatedly against overlapping data.
  172 |         first_cut = pd.Timestamp(cutoffs[0])
  173 |         first_train = development[(development["time"] < first_cut)
  174 |                                   & (development["time"] >= first_cut
  175 |                                      - pd.Timedelta(days=TRAIN_MEMORY_DAYS))]
  176 |         raw_first = first_train[features].to_numpy(float)
  177 |         scaler_first = C.fit_scaler(raw_first)
  178 |         z_first = C.apply_scaler(raw_first, scaler_first)
  179 |         k_choice = MS.choose_k(z_first, weights, lambda_jump=LAMBDA_JUMP, seeds=SEEDS,
  180 |                                candidates=(MS.PARSIMONIOUS_K, MS.STARTING_K))
  181 |         att.detail = {"best": k_choice["best_by_inner_criterion"]}
  182 |     # The registered starting K is 3. The inner criterion is REPORTED; it does not
  183 |     # silently override a registered choice (guide 8.1).
  184 |     n_states = MS.STARTING_K
  185 |     k_choice["registered_k_used"] = n_states
  186 |     k_choice["inner_criterion_agrees_with_registered"] = (
  187 |         k_choice["best_by_inner_criterion"] == n_states)
  188 |     k_choice["override_policy"] = (
  189 |         "the registered starting K=3 is used and the disagreement is reported rather than acted "
  190 |         "on. This is a JUDGEMENT CALL and the guide can be read both ways: 8.1 calls K=3 the "
  191 |         "'primary starting' K with K=2 a registered 'parsimonious alternative', while 8.3 says K "
  192 |         "is chosen in nested development -- which is exactly the criterion that preferred K=2 "
  193 |         "here. The lab keeps the registered starting point because switching after seeing a "
  194 |         "score, even a nested-development score, is still choosing the model on a result; but the "
  195 |         "margin is small and the decision belongs to the user, so it is recorded in "
  196 |         "reports/improvement_opinions.md rather than settled silently.")
  197 |     scores = {int(k): v["mean_per_observation_objective"] for k, v in k_choice["scores"].items()}
  198 |     if len(scores) > 1:
  199 |         best, second = sorted(scores.values())[:2]
  200 |         k_choice["margin_between_top_two"] = float(second - best)
  201 |         k_choice["relative_margin"] = float((second - best) / abs(second)) if second else None
  202 |     k_choice["direction_note"] = (
  203 |         "the usual worry is that a larger K fits better almost by construction. Here the SMALLER "
  204 |         "K scored better, which is the opposite direction and is why the standard warning does "
  205 |         "not settle this case.")
  206 |     writer.write_config(f"{ARTIFACT_PREFIX}_k_selection.json", k_choice)
  207 | 
  208 |     artifacts, mappings, transitions = [], [], []
  209 |     previous: R.ModelArtifact | None = None
  210 |     all_reports = {}
  211 | 
  212 |     for cutoff in cutoffs:
  213 |         cut = pd.Timestamp(cutoff)
  214 |         window = development[(development["time"] < cut)
  215 |                              & (development["time"] >= cut - pd.Timedelta(days=TRAIN_MEMORY_DAYS))]
  216 |         raw = window[features].to_numpy(float)
  217 |         with writer.attempt(f"L05.1.fit@{cutoff}") as att:
  218 |             scaler = C.fit_scaler(raw)
  219 |             z_train = C.apply_scaler(raw, scaler)
  220 |             fit = multi_start_fit(z_train, weights, n_states=n_states,
```

## SRC25 — `src/crypto_regime_lab/regime/registry.py:140–225`

SHA-256: `432a33230cba5fd271af9f0e06ba4141105893bdc5934cbf98863d07827a3ad6`

```text
  140 | # ---------------------------------------------------------------------------
  141 | # namespace mapping across a refit
  142 | # ---------------------------------------------------------------------------
  143 | 
  144 | def map_state_namespaces(old: ModelArtifact, new: ModelArtifact, *,
  145 |                          max_relative_distance: float = MAPPING_MAX_RELATIVE_DISTANCE) -> dict:
  146 |     """Map new-model states onto old-model states using TRAINING centroids only.
  147 | 
  148 |     No emission, no outcome and no market data after either cutoff enters this. A
  149 |     state that cannot be matched confidently is ``UNMAPPED_REFIT_STATE`` -- a model
  150 |     event, explicitly NOT a market transition and explicitly not a retrain trigger.
  151 |     """
  152 |     if tuple(old.feature_names) != tuple(new.feature_names):
  153 |         raise JumpModelError("cannot map namespaces across different feature schemas")
  154 |     old_c = np.asarray(old.centroids, dtype=np.float64)
  155 |     new_c = np.asarray(new.centroids, dtype=np.float64)
  156 |     weights = np.asarray(new.feature_weights, dtype=np.float64)
  157 | 
  158 |     def _distance(a, b):
  159 |         d = a - b
  160 |         return float(np.sqrt(np.sum(weights * d * d)))
  161 | 
  162 |     # scale by how far apart the OLD model's own states are: a "close" match must be
  163 |     # close relative to the structure the model itself resolves
  164 |     spread = [
  165 |         _distance(old_c[i], old_c[j])
  166 |         for i in range(old_c.shape[0]) for j in range(i + 1, old_c.shape[0])
  167 |     ]
  168 |     reference = float(np.median(spread)) if spread else 1.0
  169 |     if reference <= 0:
  170 |         reference = 1.0
  171 | 
  172 |     mapping = {}
  173 |     for k in range(new_c.shape[0]):
  174 |         distances = np.asarray([_distance(new_c[k], old_c[j]) for j in range(old_c.shape[0])])
  175 |         order = np.argsort(distances, kind="stable")
  176 |         best = int(order[0])
  177 |         best_d = float(distances[best])
  178 |         runner_up = float(distances[order[1]]) if distances.size > 1 else float("inf")
  179 |         relative = best_d / reference
  180 |         if relative > max_relative_distance:
  181 |             status = MAPPING_UNMAPPED
  182 |         elif runner_up < float("inf") and best_d > 0 and runner_up / max(best_d, 1e-12) < 1.25:
  183 |             status = MAPPING_AMBIGUOUS
  184 |         else:
  185 |             status = MAPPING_CONFIDENT
  186 |         mapping[str(k)] = {
  187 |             "new_state": k,
  188 |             "old_state": best if status == MAPPING_CONFIDENT else None,
  189 |             "status": status,
  190 |             "distance": best_d,
  191 |             "relative_distance": relative,
  192 |             "runner_up_distance": runner_up,
  193 |         }
  194 | 
  195 |     unmapped = [k for k, v in mapping.items() if v["status"] != MAPPING_CONFIDENT]
  196 |     return {
  197 |         "schema": "crypto_regime_lab.state_namespace_mapping.v1",
  198 |         "old_namespace": old.state_namespace, "new_namespace": new.state_namespace,
  199 |         "old_centroid_digest": old.centroid_digest(),
  200 |         "new_centroid_digest": new.centroid_digest(),
  201 |         "reference_spread": reference,
  202 |         "max_relative_distance": max_relative_distance,
  203 |         "mapping": mapping,
  204 |         "unmapped_states": unmapped,
  205 |         "all_states_mapped": not unmapped,
  206 |         "information_used": "training centroids and declared feature weights only",
  207 |         "is_market_transition": False,
  208 |         "triggers_parameter_search": False,
  209 |         "rule": ("a permuted or unmatched state ID after a refit is a MODEL event. It is emitted "
  210 |                  "as a model-transition/uncertainty record and never as a market regime change, "
  211 |                  "and it never triggers a parameter search or a market refit (guide 8.4)"),
  212 |     }
  213 | 
  214 | 
  215 | def relabel_states(states: np.ndarray, mapping: dict) -> np.ndarray:
  216 |     """Translate new-namespace states into old-namespace IDs; -1 where unmapped.
  217 | 
  218 |     -1 is deliberate: an unmapped state must be visibly absent rather than being
  219 |     folded into whichever old state happened to be nearest.
  220 |     """
  221 |     states = np.asarray(states, dtype=np.int64)
  222 |     lookup = {int(k): (v["old_state"] if v["status"] == MAPPING_CONFIDENT else -1)
  223 |               for k, v in mapping["mapping"].items()}
  224 |     return np.asarray([lookup.get(int(s), -1) for s in states], dtype=np.int64)
  225 | 
```

## SRC26 — `src/crypto_regime_lab/regime/ablation.py:1–199`

SHA-256: `5d7094c6be54a67b30f6056d9c15b2654cad4116e73b57730cbff2d5f9554e46`

```text
    1 | """Guide 8.3 — group ablation and the position taken on the model ladder.
    2 | 
    3 | Two separate obligations live here.
    4 | 
    5 | **Group ablation.** Guide 8.3: "Group ablation cần chứng minh leverage/flow/market
    6 | features có contribution ngoài price/volatility." Adding feature blocks almost
    7 | always lowers a fit objective, so the question is not whether the objective drops
    8 | but whether it drops on data the fit did not see. The comparison therefore runs on
    9 | the same nested inner blocks that choose K, never on a holdout.
   10 | 
   11 | **The model ladder.** Guide 8.1 defines five rungs. LAB-05's task list asks for M0
   12 | and M1 only. Not building M1S, M2 and M3 is a defensible reading, but leaving that
   13 | undeclared is not -- a reader would have no way to tell a deliberate scope from an
   14 | oversight. The decision, and what would have to be true to revisit it, is recorded.
   15 | """
   16 | 
   17 | from __future__ import annotations
   18 | 
   19 | import numpy as np
   20 | 
   21 | from .model_selection import score_k
   22 | 
   23 | #: Guide 8.1. ``implemented`` is a fact about this repository, not an opinion.
   24 | MODEL_LADDER = {
   25 |     "M0": {
   26 |         "model": "rule-based volatility/path-direction/activity",
   27 |         "role": "explainable control, thresholds train-only",
   28 |         "implemented": True, "module": "regime/m0_rules.py",
   29 |     },
   30 |     "M1": {
   31 |         "model": "regularized discrete statistical jump model",
   32 |         "role": "primary state model",
   33 |         "implemented": True, "module": "regime/jump_model.py",
   34 |     },
   35 |     "M1S": {
   36 |         "model": "sparse JM or group-regularized features",
   37 |         "role": "extension when there are MANY blocks; ablation against M1",
   38 |         "implemented": False,
   39 |         "why_not": (
   40 |             "the primary core is 8 features in 3 blocks (G1 3, G2 2, G5 3). Guide 8.1 scopes M1S "
   41 |             "to 'khi nhiều blocks', and 3 is not that. Guide 8.3 also forbids writing a naive "
   42 |             "sparse objective and requires a pinned research implementation or a verified "
   43 |             "constrained one; none is pinned in this environment, so writing one would be exactly "
   44 |             "the move 8.3 warns against."),
   45 |         "what_would_change_it": (
   46 |             "G3 (leverage) and G4 (liquidity) becoming available for all five symbols would take "
   47 |             "the core past 3 blocks. Then M1S needs a pinned implementation with its weight "
   48 |             "normalisation and penalty conventions recorded, plus the nondegeneracy guard that "
   49 |             "already exists in quality.check_degeneracy."),
   50 |     },
   51 |     "M2": {
   52 |         "model": "small HMM or GMM",
   53 |         "role": "comparator; guide 8.1 says do NOT sweep every model family",
   54 |         "implemented": False,
   55 |         "why_not": ("LAB-05's task list (L05.2) asks for M0 and M1 references. M2 is a comparator "
   56 |                     "the guide explicitly declines to make mandatory, and adding it would widen "
   57 |                     "the model family sweep 8.1 warns against."),
   58 |         "what_would_change_it": ("a claim that the state structure is specific to a jump model "
   59 |                                  "rather than to the features would need M2 to be falsifiable."),
   60 |     },
   61 |     "M3": {
   62 |         "model": "online novelty/change detector",
   63 |         "role": "diagnostic/secondary trigger, explicitly not wired in by default",
   64 |         "implemented": False,
   65 |         "why_not": ("guide 8.1 marks it 'chưa ghép default'. The novelty AXIS it would feed is "
   66 |                     "already measured -- fit residual against the training-residual quantile in "
   67 |                     "quality.assess -- without introducing a second detector whose disagreements "
   68 |                     "with M1 would then need their own policy."),
   69 |         "what_would_change_it": "a decision to use novelty as a trigger rather than as a status.",
   70 |     },
   71 | }
   72 | 
   73 | 
   74 | def ladder_record() -> dict:
   75 |     implemented = [k for k, v in MODEL_LADDER.items() if v["implemented"]]
   76 |     return {
   77 |         "schema": "crypto_regime_lab.model_ladder.v1",
   78 |         "rungs": MODEL_LADDER,
   79 |         "implemented": implemented,
   80 |         "not_implemented": [k for k, v in MODEL_LADDER.items() if not v["implemented"]],
   81 |         "scope_rule": ("LAB-05 L05.2 asks for M0 and M1 references. The other rungs are declared "
   82 |                        "unbuilt with a reason and a condition that would reopen them, so an "
   83 |                        "omission cannot be mistaken for an oversight (guide 8.1)"),
   84 |         "k_policy": "primary K=3; K=2 parsimonious; K=4 only on an explicit discovery decision",
   85 |     }
   86 | 
   87 | 
   88 | def group_weights(all_features: tuple[str, ...], weights: np.ndarray,
   89 |                   keep_groups: tuple[str, ...]) -> np.ndarray:
   90 |     """Zero the excluded blocks and renormalise so total weight stays 1.
   91 | 
   92 |     Renormalising matters: without it a smaller feature set simply has less total
   93 |     weight and a lower loss, and the ablation would measure the normalisation
   94 |     rather than the information.
   95 |     """
   96 |     weights = np.asarray(weights, dtype=np.float64)
   97 |     mask = np.asarray([f.split("_")[0].upper() in keep_groups for f in all_features])
   98 |     restricted = np.where(mask, weights, 0.0)
   99 |     total = restricted.sum()
  100 |     if total <= 0:
  101 |         raise ValueError(f"keeping {keep_groups} leaves no weight at all")
  102 |     return restricted / total
  103 | 
  104 | 
  105 | def variance_resolved(z_block: np.ndarray, centroids: np.ndarray, states: np.ndarray,
  106 |                       weights: np.ndarray) -> float:
  107 |     """Share of weighted variance the state assignment removes, on a held-out block.
  108 | 
  109 |     This exists because the fit objective is NOT comparable across feature sets: a
  110 |     different feature set is a different objective function, and a larger number
  111 |     could mean "worse states" or simply "noisier features". This measure is
  112 |     scale-free -- within-state weighted variance over total weighted variance,
  113 |     subtracted from one -- so the same number means the same thing whether the
  114 |     model reads 3 features or 8.
  115 |     """
  116 |     z_block = np.asarray(z_block, dtype=np.float64)
  117 |     weights = np.asarray(weights, dtype=np.float64)
  118 |     grand = np.average(z_block, axis=0, weights=None)
  119 |     total = float(np.sum(weights * np.mean((z_block - grand) ** 2, axis=0)))
  120 |     if total <= 0:
  121 |         return 0.0
  122 |     residual = z_block - np.asarray(centroids, dtype=np.float64)[states]
  123 |     within = float(np.sum(weights * np.mean(residual ** 2, axis=0)))
  124 |     return 1.0 - within / total
  125 | 
  126 | 
  127 | def group_ablation(z: np.ndarray, all_features: tuple[str, ...], weights: np.ndarray, *,
  128 |                    n_states: int, lambda_jump: float, seeds: tuple[int, ...],
  129 |                    ladder: tuple[tuple[str, ...], ...] = (("G1",), ("G1", "G2"),
  130 |                                                           ("G1", "G2", "G5")),
  131 |                    n_folds: int = 3) -> dict:
  132 |     """Does each added block buy anything on data the fit did not see?
  133 | 
  134 |     Scored on the held-out inner blocks, so a block that only helps in-sample --
  135 |     which every block does -- shows no gain here.
  136 |     """
  137 |     from .jump_model import forward_filter, loss_matrix, multi_start_fit
  138 |     from .model_selection import inner_splits
  139 | 
  140 |     rows = []
  141 |     previous_objective = None
  142 |     previous_resolved = None
  143 |     for keep in ladder:
  144 |         restricted = group_weights(all_features, weights, keep)
  145 |         score = score_k(z, restricted, n_states=n_states, lambda_jump=lambda_jump,
  146 |                         seeds=seeds, n_folds=n_folds)
  147 | 
  148 |         # the scale-free measure, on the same held-out inner blocks
  149 |         resolved = []
  150 |         for train_end, valid_start, valid_end in inner_splits(z.shape[0], n_folds):
  151 |             fit = multi_start_fit(z[:train_end], restricted, n_states=n_states,
  152 |                                   lambda_jump=lambda_jump, seeds=seeds)
  153 |             block = z[valid_start:valid_end]
  154 |             states = forward_filter(loss_matrix(block, fit["centroids"], restricted),
  155 |                                     lambda_jump).online_states
  156 |             resolved.append(variance_resolved(block, fit["centroids"], states, restricted))
  157 |         mean_resolved = float(np.mean(resolved))
  158 | 
  159 |         gain = (None if previous_objective is None
  160 |                 else previous_objective - score["mean_per_observation_objective"])
  161 |         resolved_gain = (None if previous_resolved is None
  162 |                          else mean_resolved - previous_resolved)
  163 |         rows.append({
  164 |             "groups": list(keep),
  165 |             "features_active": int(np.count_nonzero(restricted)),
  166 |             "mean_per_observation_objective": score["mean_per_observation_objective"],
  167 |             "worst_fold": score["worst_fold"],
  168 |             "variance_resolved_out_of_fold": mean_resolved,
  169 |             "gain_over_previous": gain,
  170 |             "variance_resolved_gain": resolved_gain,
  171 |             "improved": None if resolved_gain is None else bool(resolved_gain > 0),
  172 |             "improved_on_objective": None if gain is None else bool(gain > 0),
  173 |         })
  174 |         previous_objective = score["mean_per_observation_objective"]
  175 |         previous_resolved = mean_resolved
  176 | 
  177 |     added = [r for r in rows if r["variance_resolved_gain"] is not None]
  178 |     return {
  179 |         "schema": "crypto_regime_lab.group_ablation.v1",
  180 |         "ladder": rows,
  181 |         "blocks_that_improved_out_of_fold": [r["groups"][-1] for r in added if r["improved"]],
  182 |         "blocks_that_did_not": [r["groups"][-1] for r in added if not r["improved"]],
  183 |         "scored_on": "held-out inner chronological blocks of the development window",
  184 |         "holdout_used": False,
  185 |         "weights_renormalised": True,
  186 |         "decided_on": "variance_resolved_out_of_fold",
  187 |         "why_not_the_objective": (
  188 |             "a different feature set is a DIFFERENT objective function, so its value is not "
  189 |             "comparable across rows -- a higher number can mean worse states or simply noisier "
  190 |             "features. variance_resolved is within-state over total weighted variance subtracted "
  191 |             "from one, which means the same thing at 3 features and at 8. The objective column is "
  192 |             "kept for reference and is not what the verdict rests on"),
  193 |         "requirement": ("guide 8.3: flow and market-coordination blocks must be shown to "
  194 |                         "contribute BEYOND price/volatility. A block that does not is reported as "
  195 |                         "not contributing, not quietly retained"),
  196 |         "interpretation_limit": ("this measures contribution to the FIT objective out of fold. It "
  197 |                                  "says nothing about whether the extra block improves a trading "
  198 |                                  "decision, which is a LAB-06+ question"),
  199 |     }
```

## SRC27 — `scripts/analyse_lab09_confirmation.py:860–991`

SHA-256: `949c322271bfd18290a60c01a6cb6bf14d8cb155b5e2f840fe8db73e5a7fbc51`

```text
  860 |           minimum_effect: float, vocabulary: list[str],
  861 |           accounting: dict | None = None) -> dict:
  862 |     def contrast(name: str) -> dict:
  863 |         return uncertainty["contrasts"].get(name, {})
  864 | 
  865 |     def verdict(name: str, question: str, reading: str) -> dict:
  866 |         record = contrast(name)
  867 |         if record.get("status") != "OK":
  868 |             # NOT_MEASURED needs a REASON, or it reads like a negative result.
  869 |             # Every contribution that cannot be judged says why it cannot be.
  870 |             return {"contrast": name, "question": question, "status": record.get("status"),
  871 |                     "verdict": "NOT_MEASURED",
  872 |                     "reason": record.get("reason")
  873 |                     or f"the {name} contrast produced no interval ({record.get('status')})",
  874 |                     "where": "configs/lab09_uncertainty.json contrasts"}
  875 |         # three outcomes, not two. An interval that straddles the minimum has not
  876 |         # ruled the effect out; calling that NOT_SUPPORTED reads as a negative
  877 |         # result when the honest answer is that the sample cannot tell.
  878 |         clears = record["ci_lower"] > minimum_effect
  879 |         ruled_out = record["ci_upper"] < minimum_effect
  880 |         return {
  881 |             "contrast": name, "question": question,
  882 |             "baseline_is_not_untouched": record.get("baseline_is_not_untouched", False),
  883 |             "baseline_caveat": record.get("baseline_caveat"),
  884 |             "point_estimate": record["point_estimate"],
  885 |             "ci": [record["ci_lower"], record["ci_upper"]],
  886 |             "holm_adjusted_p": record.get("holm_adjusted_p"),
  887 |             "minimum_economic_effect": minimum_effect,
  888 |             "clears_minimum_effect": bool(clears),
  889 |             "ruled_out_below_the_minimum": bool(ruled_out),
  890 |             "verdict": ("SUPPORTED" if clears
  891 |                         else "RULED_OUT" if ruled_out else "INCONCLUSIVE"),
  892 |             "reading": reading,
  893 |         }
  894 | 
  895 |     contributions = {
  896 |         "DESCRIPTIVE": descriptive_contribution(),
  897 |         "PREDICTIVE": predictive_contribution(support),
  898 |         "SELECTION": verdict("B-A", "does the neighbourhood selector beat the installed one on "
  899 |                                     "the same calendar?",
  900 |                              "this is the WHICH-parameters contribution, holding timing fixed"),
  901 |         "TIMING": verdict("C-A", "does regime-triggered refresh beat the frozen calendar with "
  902 |                                  "the same selector?",
  903 |                           "this is the WHEN contribution, holding the selector fixed. A "
  904 |                           "time-edge claim rests here and nowhere else"),
  905 |         "POLICY": {
  906 |             "question": "does the bank and response policy add anything beyond D?",
  907 |             "evidence": "arm E deployed arm D's schedule; its own contribution is null by "
  908 |                         "construction wherever LAB-06 measured zero switches",
  909 |             "verdict": "NULL_BY_CONSTRUCTION",
  910 |             "where": "configs/lab09_confirmation_results.json arms.E",
  911 |         },
  912 |     }
  913 | 
  914 |     blockers = []
  915 |     if reconciliation["financial_identity"].get("cost_binding_is_a_finding"):
  916 |         blockers.append(
  917 |             "ACCOUNTING: the lab charged half the registered one-way taker fee in every phase, "
  918 |             "because the registered ONE-WAY rate was passed into an engine parameter documented "
  919 |             "as ROUND-TRIP. Measured, not inferred (configs/cost_binding_verification.json)")
  920 |     if not reconciliation["financial_identity"]["all_hold"]:
  921 |         blockers.append("ACCOUNTING: the cash identity does not close on every arm")
  922 |     if confirmation["cells_not_ready"]:
  923 |         blockers.append(
  924 |             f"MATRIX: {confirmation['cells_not_ready']} of {confirmation['cells_planned']} cells "
  925 |             "are NOT_READY with null metrics, so the matrix is incomplete")
  926 |     if unlock["holdout_status"] != "CLEAN":
  927 |         blockers.append(
  928 |             "CONTAMINATION: the confirmation interval is NESTED RETROSPECTIVE. The supplied "
  929 |             "presets were tuned on the full sample with an unknown cutoff, so no interval of "
  930 |             "this dataset is an untouched holdout")
  931 |     if stress and not stress["cost_stress"]["harness_control"]["one_x_reproduces_every_arm"]:
  932 |         blockers.append("STRESS: the 1.0x cost level did not reproduce the confirmation run")
  933 |     supported = [name for name, entry in contributions.items()
  934 |                  if entry.get("verdict") == "SUPPORTED"]
  935 |     measured = [entry for entry in contributions.values() if entry.get("ci")]
  936 |     all_ruled_out = bool(measured) and all(e["verdict"] == "RULED_OUT" for e in measured)
  937 |     severity = (accounting or {}).get("severity")
  938 | 
  939 |     # The decision rule, in order, fixed before the numbers:
  940 |     #   1. a MAJOR accounting error invalidates the run regardless of what it says
  941 |     #   2. a contrast whose whole interval sits above the minimum is an edge
  942 |     #   3. every measured contrast ruled out below the minimum is no incremental value
  943 |     #   4. anything else is the sample failing to tell, which is not a negative result
  944 |     if severity == "MAJOR":
  945 |         level = "FAILED_VALIDITY"
  946 |     elif supported:
  947 |         level = {"SELECTION": "NET_PARAMETER_SELECTION_EDGE",
  948 |                  "TIMING": "NET_TIMING_EDGE",
  949 |                  "POLICY": "NET_POLICY_EDGE"}.get(supported[0], "DESCRIPTIVE_VALUE")
  950 |     elif all_ruled_out:
  951 |         level = "NO_INCREMENTAL_VALUE"
  952 |     else:
  953 |         level = "INCONCLUSIVE_SAMPLE"
  954 |     assert level in vocabulary, f"{level} is not in the registered vocabulary"
  955 | 
  956 |     return {
  957 |         "contributions": contributions,
  958 |         "contributions_judged_separately": True,
  959 |         "why_separately": ("a study that adds them up can call a risk-timing effect a "
  960 |                            "parameter-selection edge and never notice (guide 11.1)"),
  961 |         "net_gain_after_risk_and_cost": {
  962 |             "statistic": "mean daily net-return difference, paired on the same dates",
  963 |             "primary_contrast": "C-A for a timing claim, B-A for a selection claim",
  964 |             "interval_available": all(contrast(n).get("status") == "OK"
  965 |                                       for n in ("B-A", "C-A")),
  966 |             "B-A": contrast("B-A").get("ci_lower") is not None and [
  967 |                 contrast("B-A")["ci_lower"], contrast("B-A")["ci_upper"]],
  968 |             "C-A": contrast("C-A").get("ci_lower") is not None and [
  969 |                 contrast("C-A")["ci_lower"], contrast("C-A")["ci_upper"]],
  970 |             "minimum_economic_effect": minimum_effect,
  971 |         },
  972 |         "blockers": blockers,
  973 |         "accounting_severity": accounting,
  974 |         "decision_rule": [
  975 |             "1. a MAJOR accounting error yields FAILED_VALIDITY regardless of the contrasts",
  976 |             "2. a contrast whose whole 95% interval sits above the minimum economic effect is "
  977 |             "the corresponding edge",
  978 |             "3. every measured contrast ruled out BELOW the minimum is NO_INCREMENTAL_VALUE",
  979 |             "4. anything else is INCONCLUSIVE_SAMPLE -- the sample failing to distinguish is "
  980 |             "not a negative result, and reporting it as one would overstate the evidence",
  981 |         ],
  982 |         "decision_rule_fixed_before": "the confirmation intervals were computed",
  983 |         "conclusion_level": level,
  984 |         "conclusion_vocabulary": vocabulary,
  985 |         "vocabulary_source": "configs/hypothesis_registry.json",
  986 |         "development_outcome": (discovery or {}).get("design_selection", {}).get("outcome"),
  987 |         "confirms_the_development_outcome": None,
  988 |         "forbidden": {
  989 |             "fund_grade_alpha_proven": False,
  990 |             "statement": ("no claim of a proven fund-grade alpha is made or implied. This is a "
  991 |                           "lab backtest on one cohort with no funding product, a nested "
```
