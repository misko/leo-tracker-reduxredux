#!/usr/bin/env python3
"""Strict 64-unit evaluator for the frozen T4 primary panel."""
from __future__ import annotations
import argparse,importlib.util,json,sys
from collections import Counter
from pathlib import Path

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.append(str(HERE.parent/"2026_09_30_broad_prior_acquisition"))
from common import selected_units  # noqa:E402


def helpers():
    spec=importlib.util.spec_from_file_location("fixed_dev_evaluate",HERE/"evaluate.py")
    assert spec and spec.loader
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module);return module


def load_attempts(run_root:Path):
    helper=helpers();index=helper.snapshot_index(HERE/"development")
    index.update(helper.snapshot_index(HERE/"primary-source"));records={}
    for launch_path in sorted(run_root.glob("batch-*/*.launch.json")):
        launch=json.loads(launch_path.read_text());unit=launch["unit_id"]
        if unit in records:raise ValueError(f"duplicate primary attempt: {unit}")
        receipt_path=launch_path.with_name(launch_path.name.replace(".launch.json",".json"));seal_path=launch_path.with_name(launch_path.name.replace(".launch.json",".seal.json"))
        row={"unit_id":unit,"launch":launch,"launch_path":str(launch_path),"sealed":False}
        if receipt_path.exists() or seal_path.exists():
            if not receipt_path.exists() or not seal_path.exists():raise ValueError(f"partial native receipt: {unit}")
            seal=json.loads(seal_path.read_text())
            if seal.get("prediction_sha256")!=helper.sha256(receipt_path):raise ValueError(f"seal mismatch: {unit}")
            receipt=json.loads(receipt_path.read_text());receipt["_verified_sources"]=helper.verify_source_bindings(receipt.get("source_sha256",{}),index)
            row.update(receipt=receipt,sealed=True,receipt_path=str(receipt_path),receipt_sha256=seal["prediction_sha256"])
        records[unit]=row
    return records


def require_complete_panel(records):
    expected=set(selected_units());missing=sorted(expected-set(records));extra=sorted(set(records)-expected)
    if missing or extra:raise ValueError(f"publication requires exactly 64 attempts; missing={len(missing)}, extra={len(extra)}")


def evaluate(records):
    helper=helpers();rows=[]
    old_path=ROOT/"reports/2026_09_30_gaussian_sum_64_scan/evaluation.json"
    old=json.loads(old_path.read_text()) if old_path.exists() else {"rows":[]}
    baseline={r["unit_id"]:r for r in old["rows"] if r.get("arm")=="greedy"}
    for unit in selected_units():
        attempt=records.get(unit)
        if attempt is None:
            rows.append({"unit_id":unit,"dataset":unit.split("-")[0],"attempted":False,"status":"missing","processing_complete":False,
                         "native_numerically_converged":None,"numerically_converged":None,"accepted":False,
                         "acceptance_failures":["missing_attempt"],"within_primary_budget":False,
                         "error_m":None,"east_km":None,"north_km":None});continue
        launch=attempt["launch"];receipt=attempt.get("receipt");status=(receipt or launch).get("status","unknown")
        point=error=None;converged=None;iterations=None;num_factors=None;fits=[]
        if receipt:
            mean=(receipt.get("best") or {}).get("mean");point=helper.latlon_from_enu(*mean[:2]) if mean else None
            error=helper.distance_m(point,helper.REFERENCE) if point else None
            converged=bool((receipt.get("best") or {}).get("converged"));iterations=(receipt.get("best") or {}).get("iterations")
            num_factors=len((receipt.get("best") or {}).get("associations",[]));fits=receipt.get("fits",[])
        launcher_success=launch.get("status")=="complete" and launch.get("returncode")==0
        within_budget=launch.get("wall_seconds") is not None and launch["wall_seconds"]<=90
        accepted=bool(receipt and attempt["sealed"] and status=="converged_local_mode" and
                      converged and launcher_success and within_budget)
        acceptance_failures=[]
        if not attempt["sealed"]:acceptance_failures.append("unsealed")
        if not converged:acceptance_failures.append("native_winner_not_converged")
        if not launcher_success:acceptance_failures.append("launcher_not_successful")
        if not within_budget:acceptance_failures.append("runtime_above_90s_or_missing")
        base=baseline.get(unit,{})
        rows.append({"unit_id":unit,"dataset":unit.split("-")[0],"attempted":True,"sealed":attempt["sealed"],"status":status,
            "processing_complete":launcher_success,"within_primary_budget":within_budget,
            "native_numerically_converged":converged,"numerically_converged":converged,
            "accepted":accepted,"acceptance_failures":acceptance_failures,
            "error_m":error if accepted else None,
            "failed_point_error_m_diagnostic":None if accepted else error,"point_latlon":None if point is None else list(point),
            "east_km":None if not receipt or not (receipt.get("best") or {}).get("mean") else float(receipt["best"]["mean"][0]),
            "north_km":None if not receipt or not (receipt.get("best") or {}).get("mean") else float(receipt["best"]["mean"][1]),
            "iterations":iterations,"num_factors_fit":num_factors,"planned_factors":None if not receipt else receipt.get("planned_factors"),
            "seed_fits_attempted":len(fits),"seed_fits_converged":sum(bool(f.get("converged")) for f in fits),
            "runtime_s":launch.get("wall_seconds"),"old_greedy_status":base.get("status"),
            "old_greedy_error_m":None if base.get("error_km") is None else base["error_km"]*1000,
            "launch_path":attempt["launch_path"],"receipt_path":attempt.get("receipt_path"),
            "receipt_sha256":attempt.get("receipt_sha256"),"diagnostic_only":True})
    return {"schema":"fixed-height-t4-primary-evaluation/v1","planned_units":64,
        "attempted_count":sum(r["attempted"] for r in rows),"sealed_count":sum(bool(r.get("sealed")) for r in rows),
        "publication_ready":len(records)==64,"status_counts":dict(sorted(Counter(r["status"] for r in rows).items())),
        "qualification":"roof-reference diagnostic after sealed predictions; failures excluded from accepted error", "rows":rows}


def main():
    p=argparse.ArgumentParser();p.add_argument("--run-root",type=Path,default=HERE/"runs/t4-primary");p.add_argument("--output",type=Path,default=HERE/"primary-evaluation.json");p.add_argument("--inspect-incomplete",action="store_true");a=p.parse_args()
    records=load_attempts(a.run_root)
    if not a.inspect_incomplete:require_complete_panel(records)
    result=evaluate(records)
    if not a.inspect_incomplete and not result["publication_ready"]:raise ValueError("incomplete primary panel")
    a.output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n");print(json.dumps({"output":str(a.output),"publication_ready":result["publication_ready"]}))


if __name__=="__main__":main()
