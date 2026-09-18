"""Generate the phase/finding acceptance inventory from committed test evidence."""
from pathlib import Path

from ..experiments.time_edge_contracts import ContractError
from .planning import ref
from .reporting import collect, require_committed
from .runtime import local, source_identity
from .storage import digest, read, save, utcnow


def build_delivery(root, *, acceptance, preflight, coverage, output, lab_run_id):
    root=Path(root)
    refs=[ref(root,p) for p in (acceptance,preflight,coverage)]
    tests,environment,data_coverage=collect(root,refs)
    if tests["status"] != "TECHNICAL_TESTS_PASS" or tests["source_identity"] != digest(source_identity(root)):
        raise ContractError("delivery requires passing tests on unchanged current source identity")
    scope_path=root/"configs/time_edge_validation_v4/delivery_scope_r05.json"
    require_committed(root,[scope_path]); scope=read(scope_path)
    by_name={}
    for case in tests["cases"]:
        by_name.setdefault(case["name"].split("::")[-1].split("[")[0],[]).append(case["status"])
    findings=[]
    for finding in scope["findings"]:
        passed=[name for name in finding["required_tests"] if by_name.get(name) and all(s == "PASS" for s in by_name[name])]
        if len(passed) != len(finding["required_tests"]): raise ContractError("unverified finding test mapping: "+finding["finding_id"])
        source=local(root,finding["source"]); require_committed(root,[source])
        findings.append({**finding,"source_ref":ref(root,source),"passed_tests":passed,"runtime_status":"NOT_QUALIFIED"})
    result={"lab_run_id":lab_run_id,"created_at":utcnow(),"status":"TECHNICAL_DELIVERY_RUNTIME_BLOCKED",
        "input_refs":refs+[ref(root,scope_path)],"source_identity":tests["source_identity"],
        "technical_tests":tests["technical_tests"],"technical_wall_seconds":tests["wall_seconds"],
        "engine_runs":tests["engine_runs"],"runtime_status":environment["runtime_status"],
        "protected_source_count":tests["protected_source_count"],"protected_changed":tests["protected_changed"],
        "quantbt_git_status":tests["quantbt_git_status"],"phase_acceptance":scope["phases"],"finding_acceptance":findings,
        "data_coverage":data_coverage,"model_evaluation":tests["model_evaluation"],"next_actions":tests["next_actions"],
        "blockers":[
            "Sandbox preflight: "+environment["runtime_status"]+"; no engine run was substituted outside isolation.",
            f"R01 initial history: {data_coverage['boundary_eligible_cells']}/{data_coverage['planned_cells']} boundary-eligible; {', '.join(data_coverage['blocked_cells'])} blocked. A boundary PASS still needs full row/gap verification.",
            "Public next-open fill callback has no certified true pre-fill equity; decision equity and pre-bar diagnostics cannot silently replace the registered sizing/turnover/economic-threshold contract.",
            "All-alpha native lifecycle qualification, actual optimizer/account parity and measured latency are pending host evidence.",
            "Learned structural controls and statistical-only simulation do not establish full-path power at known net effect=2delta; no economic claim can pass that gate.",
            "Placebo/delay/risk acceptance matrix remains partial. Historical FUP outputs cannot substitute for the missing controls."
        ],"economic_conclusion":"NOT_EVALUABLE","claim":"No proof of time edge; no declaration that all 20 findings or full TE phases are closed."}
    save(local(root,output),result)
    return {"lab_run_id":lab_run_id,"output":output,"status":result["status"],"findings":len(findings),"technical_tests":result["technical_tests"]}
