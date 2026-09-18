"""Recompute from immutable artifacts; reports never invoke optimizer/engine."""
from pathlib import Path
import subprocess
import json

import pandas as pd

from ..experiments.time_edge_contracts import ContractError, paired_difference, economic_claim
from .decay import matched_decay
from .inference import fixed_cohort, family, HYPOTHESES
from .metrics import describe
from .runtime import local, verify_ref, source_identity
from .storage import digest, file_digest, read, save, utcnow

CELLS=tuple(f"{a}/{s}" for a in ("A-SC","A-HMA","A-VWAP","A-HASH") for s in ("BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","DOGEUSDT"))


def require_committed(root, paths):
    subprocess.run(["git","status","--porcelain"],cwd=root,check=True,capture_output=True)
    for path in paths:
        relative=str(Path(path).resolve().relative_to(Path(root).resolve()))
        result=subprocess.run(["git","show",f"HEAD:{relative}"],cwd=root,capture_output=True)
        if result.returncode or result.stdout != Path(path).read_bytes():
            raise ContractError("report input must be committed and unchanged: "+relative)


def collect(root, refs, *, committed=True):
    paths=[verify_ref(root,r) for r in refs]
    if committed: require_committed(root,paths)
    return [read(p) for p in paths]


def analyse_accounts(accounts, *, delta=None, decay_accounts=(), information_rows=(), model_table=(), emissions=()):
    keyed={}
    for account in accounts:
        key=(account["cell_id"],account["arm"])
        if key in keyed: raise ContractError("duplicate account in fixed cohort")
        if key[0] not in CELLS or key[1] not in ("M4_CAL","M4_REGIME","M4_CAL_MATCHED"):
            raise ContractError("unregistered primary arm/cell; historical E/NEIGH cannot enter")
        keyed[key]=account
    contrasts={"H-TIMING":{},"H-BUDGET":{}}; table=[]
    for cell in CELLS:
        row={"cell_id":cell,"arms":{}}
        for arm in ("M4_CAL","M4_REGIME","M4_CAL_MATCHED"):
            account=keyed.get((cell,arm))
            row["arms"][arm]={"status":account["status"] if account else "NOT_RUN", "metrics":None if account is None or account["status"] != "EVALUATED" else describe(account["daily_returns"]),
                              "reason":None if account and account["status"] == "EVALUATED" else "no qualified completed account"}
        for h,base in (("H-TIMING","M4_CAL"),("H-BUDGET","M4_CAL_MATCHED")):
            a,b=keyed.get((cell,"M4_REGIME")),keyed.get((cell,base))
            if a and b and a["status"] == b["status"] == "EVALUATED":
                if a["score_start"] != b["score_start"] or a["score_end_exclusive"] != b["score_end_exclusive"]:
                    raise ContractError("paired account score windows differ")
                paired=paired_difference(a["daily_returns"],b["daily_returns"])
                contrasts[h][cell]=list(zip(paired["dates"],paired["values"]))
        table.append(row)
    aggregate={h:fixed_cohort(cells,CELLS) if cells else None for h,cells in contrasts.items()}
    series={h:aggregate[h]["values"] if aggregate[h] else None for h in aggregate}
    decay=matched_decay(list(decay_accounts)) if decay_accounts else {"status":"NOT_EVALUABLE","effect":None,"reason":"fixed-theta age accounts not supplied"}
    series["H-DECAY"]=[v for _,v in decay.get("calendar_influence",[])] or None
    series["H-MODEL-INFO"]=None
    if information_rows:
        evaluable=[r for r in information_rows if r["effect"] is not None]
        if evaluable:
            dates=pd.to_datetime([r["origin"] for r in evaluable],utc=True).floor("D")
            grouped=pd.DataFrame({"date":dates,"value":[r["effect"] for r in evaluable]}).groupby("date")["value"].agg(["sum","count"])
            calendar=pd.date_range(grouped.index[0],grouped.index[-1],freq="D")
            grouped=grouped.reindex(calendar,fill_value=0.)
            series["H-MODEL-INFO"]={"numerator":grouped["sum"].tolist(),"weight":grouped["count"].tolist()}
    thresholds={h:(0. if h == "H-MODEL-INFO" else delta) for h in HYPOTHESES}
    statistics=family(series,thresholds)
    from .model_evaluation import operational_folds
    lookup={m["model_id"]:m for m in model_table}
    folds=[r for a in accounts if a["status"] == "EVALUATED" for r in operational_folds(a,emissions,lookup)]
    return {"cell_table":table,"paired_aggregates":aggregate,"decay":decay,"inference":statistics,"fold_table":folds,"model_table":list(model_table),
            "primary_full_cohort_status":"ESTIMATED" if all(aggregate[h] and aggregate[h]["full_cohort"] for h in aggregate) else "NOT_EVALUABLE",
            "full_cohort_reason":"complete planned 20-cell cohort required; partial cohorts are named explicitly",
            "data_role":"NESTED_RETROSPECTIVE","deployment_eligibility":"NOT_ASSESSED"}


def gate_claims(analysis, evidence):
    """Only measured prerequisite records can open an economic claim."""
    required=("execution_valid","data_valid","treatment_valid","support_sufficient","calibration_passed","family_complete","threshold_materialized")
    claims={}
    for h,result in analysis["inference"].items():
        checks={key:bool(evidence.get(key,{}).get("status") == "PASS" and evidence.get(key,{}).get("artifact_refs") and evidence.get(key,{}).get("denominator",0)>0) for key in required}
        if h in ("H-TIMING","H-BUDGET"):
            checks["data_valid"] &= analysis["primary_full_cohort_status"] == "ESTIMATED"
        checks["family_complete"] &= all("ci_simultaneous_basic" in r for r in analysis["inference"].values())
        interval=result.get("ci_simultaneous_basic",[None,None])
        sensitivity=result.get("sensitivity",[])
        risk_pass=evidence.get("risk",{}).get("status") == "PASS"
        if interval[0] is not None:
            risk_pass &= len(sensitivity) == 3 and all(r.get("ci_simultaneous_basic",[float("-inf")])[0] > result["threshold"] for r in sensitivity)
        claims[h]=economic_claim(lower=interval[0],upper=interval[1],delta=result.get("threshold",0.),adjusted_p=result["adjusted_p"],checks=checks,risk_pass=risk_pass)
    return claims


def freeze(root, refs, output, *, lab_run_id):
    paths=[verify_ref(root,r) for r in refs]
    if not paths: raise ContractError("empty freeze cannot pass")
    require_committed(root,paths)
    payload={"lab_run_id":lab_run_id,"created_at":utcnow(),"artifacts":refs,
        "source_identity":source_identity(root),"data_role":"NESTED_RETROSPECTIVE",
        "untouched_holdout":False,"prospective":"SPECIFIED_NOT_EXECUTED","deployment_eligibility":"NOT_ASSESSED"}
    save(local(root,output),payload)
    return payload


def verify_freeze(root, manifest):
    if not manifest["artifacts"]: raise ContractError("empty freeze cannot verify")
    paths=[verify_ref(root,r) for r in manifest["artifacts"]]
    require_committed(root,paths)
    changed=manifest["source_identity"] != source_identity(root)
    return {"lab_run_id":manifest["lab_run_id"],"status":"FAILED_SOURCE_DRIFT" if changed else "VERIFIED",
            "artifact_count":len(paths),"source_file_count":len(manifest["source_identity"]),"economic_proof":False}


def render(root, evidence_ref, output):
    path=verify_ref(root,evidence_ref); require_committed(root,[path]); data=read(path)
    lines=["# TE — báo cáo nghiệm thu từ evidence", "",f"- lab_run_id: `{data['lab_run_id']}`",
           f"- Evidence: `{evidence_ref['path']}`; SHA-256 `{evidence_ref['sha256']}`.",
           "- Scope: retrospective; chưa có xác nhận prospective/live time edge.",""]
    if "technical_tests" in data:
        tests=data["technical_tests"]
        lines += [f"Kiểm thử kỹ thuật: {tests['passed']} PASS, {tests['failed']} FAIL, {tests['errors']} ERROR, {tests['skipped']} SKIP.",
                  f"Runtime: **{data['runtime_status']}**. Engine runs: {data['engine_runs']}.", ""]
    if "cell_table" in data:
        lines += ["| Cell | CAL | REGIME | CAL_MATCHED |","|---|---|---|---|"]
        for row in data["cell_table"]:
            lines.append("| "+" | ".join([row["cell_id"]]+[row["arms"][a]["status"] for a in ("M4_CAL","M4_REGIME","M4_CAL_MATCHED")])+" |")
        lines += ["",f"Full cohort: **{data['primary_full_cohort_status']}**.",""]
        for h,result in data["inference"].items():
            lines.append(f"- {h}: {result['status']}; effect={result.get('estimate')}; adjusted p={result['adjusted_p']}.")
        lines += ["", "## Từng fold và model thực dùng", "", "| Cell / arm / fold | Ready / activation | Model lúc chọn | Ngày / SR / daily PF / DD | Unknown / emissions |", "|---|---|---|---|---|"]
        for row in data.get("fold_table",[]):
            m=row["metrics"] or {}; sr=m.get("daily_sharpe",{}).get("value")
            activation=row.get("activation") or {}
            lines.append(f"| {row['cell_id']} / {row['arm']} / {row['fold_id']} | {row['ready_at']} / {activation.get('at')} | {row['model_at_selection']} | {m.get('days')} / {sr} / {m.get('profit_factor_daily')} / {m.get('max_drawdown')} | {row['unknown_count']} / {row['emission_count']} |")
        lines += ["", "Fold vận hành có thể mang campaign của incumbent. Chỉ D2 giữ một theta cố định để đo decay theo tuổi.", ""]
        for model in data.get("model_table",[]):
            lines += [f"### Model `{model['model_id']}`", "",f"Cutoff `{model['cutoff']}`; ready `{model['ready_at']}`; design `{json.dumps(model['design'],ensure_ascii=False)}`; decision `{model['decision']}`.",
                f"Outer information: effect={model['mean_outer_information_effect']}; evaluable/planned={model['evaluable_outer_targets']}/{model['planned_outer_targets']}. CI: {model['ci_reason']}.", "",
                "| State | Train count | Mean raw features | Std (ddof=1) |", "|---|---|---|---|"]
            for state in model["dossier"]["state_profiles"]:
                lines.append(f"| {state['state_id']} | {state['train_count']} | `{json.dumps(state['raw_feature_means'])}` | `{json.dumps(state.get('raw_feature_std_ddof1'))}` |")
    if "phase_acceptance" in data:
        lines += ["", "## Nghiệm thu coding theo phase", "", "| Phase | Kết quả kỹ thuật | Runtime / bước tiếp | Guide |", "|---|---|---|---|"]
        for row in data["phase_acceptance"]:
            lines.append(f"| {row['phase']} | {row['technical_scope']} | {row['next_action']} | {row['guide']} |")
        lines += ["", "## 20 findings và phạm vi đã kiểm", "", "| Finding | Implementation | Tests đã PASS | Điều kiện còn thiếu |", "|---|---|---|---|"]
        for row in data["finding_acceptance"]:
            lines.append(f"| {row['finding_id']} | {row['implementation_status']} | {', '.join(row['passed_tests'])} | {row['remaining']} |")
        lines += ["", "## Blockers đo được", ""]+[f"- {s}" for s in data["blockers"]]
    lines += ["", "## Regime model used and evaluated", "", data.get("model_evaluation","NOT_EVALUATED_IN_THIS_PHASE: xem dossier của task fit_model/emissions; không suy từ lợi nhuận tổng."),
              "", "## Việc tiếp theo và điều kiện nghiệm thu", ""]
    actions=data.get("next_actions",[{"action":"Chạy preflight rồi qualify trên host có OS isolation.","reason":"kiểm chứng clock/fills/account thực trước pilot.","gate":"giữ tất cả lỗi/partial; chưa chạy full discovery khi gates thiếu."}])
    for action in actions: lines.append(f"- {action['action']} Lý do: {action['reason']} Gate: {action['gate']}")
    lines += ["", "## Thuật ngữ", "", "PASS kỹ thuật = đúng phép kiểm đã chạy. Runtime qualified = engine/model được kiểm chứng trong worker cô lập. Time edge = hiệu ứng paired vượt ngưỡng kinh tế và các gate thống kê. NOT_EVALUABLE = thiếu điều kiện đánh giá; không phải lợi nhuận bằng 0.", ""]
    out=local(root,output)
    if out.exists(): raise ContractError("report is append-only; choose a new path")
    out.parent.mkdir(parents=True,exist_ok=True); out.write_text("\n".join(lines))
    return {"report_path":str(out.relative_to(root)),"sha256":file_digest(out),"input_hash":digest(data)}
