#!/usr/bin/env python3
"""Overlay bounded continuations on immutable T4 primary attempts."""
from __future__ import annotations
import argparse,importlib.util,json,sys
from collections import Counter
from pathlib import Path

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]


def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);assert spec and spec.loader
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module);return module


def load_resumes(root:Path,primary_records):
    helper=load_module("continuation_dev_eval",HERE/"evaluate.py")
    index=helper.snapshot_index(HERE/"development")
    index.update(helper.snapshot_index(HERE/"continuation-source"));records={}
    for launch_path in sorted(root.glob("*-resume.launch.json")):
        launch=json.loads(launch_path.read_text());unit=launch.get("unit_id",launch_path.name.removesuffix("-resume.launch.json"))
        if unit in records:raise ValueError(f"duplicate continuation: {unit}")
        if unit not in primary_records:raise ValueError(f"continuation lacks primary attempt: {unit}")
        parent=primary_records[unit]
        if parent.get("receipt",{}).get("status")=="converged_local_mode":raise ValueError(f"continuation parent already converged: {unit}")
        receipt_path=launch_path.with_name(launch_path.name.replace(".launch.json",".json"));seal_path=launch_path.with_name(launch_path.name.replace(".launch.json",".seal.json"))
        row={"unit_id":unit,"launch":launch,"launch_path":str(launch_path),"sealed":False}
        if receipt_path.exists() or seal_path.exists():
            if not receipt_path.exists() or not seal_path.exists():raise ValueError(f"partial continuation receipt: {unit}")
            seal=json.loads(seal_path.read_text())
            if seal.get("prediction_sha256")!=helper.sha256(receipt_path):raise ValueError(f"continuation seal mismatch: {unit}")
            receipt=json.loads(receipt_path.read_text());binding=receipt.get("parent_binding",{})
            parent_path=Path(binding.get("path",""));parent_path=parent_path if parent_path.is_absolute() else ROOT/parent_path
            if (Path(parent["receipt_path"]).resolve()!=parent_path.resolve() or
                    binding.get("sha256")!=parent.get("receipt_sha256") or helper.sha256(parent_path)!=binding.get("sha256")):
                raise ValueError(f"continuation parent binding mismatch: {unit}")
            receipt["_verified_sources"]=helper.verify_source_bindings(receipt.get("source_sha256",{}),index)
            height=receipt.get("height_input_bindings",{});grid=Path(height.get("grid_path",""))
            if not grid.is_file() or helper.sha256(grid)!=height.get("grid_sha256"):raise ValueError(f"continuation geoid binding mismatch: {unit}")
            row.update(receipt=receipt,sealed=True,receipt_path=str(receipt_path),receipt_sha256=seal["prediction_sha256"])
        records[unit]=row
    return records


def overlay(primary_document,resumes):
    helper=load_module("continuation_dev_eval_rows",HERE/"evaluate.py");rows=[]
    for original in primary_document["rows"]:
        row={"unit_id":original["unit_id"],"dataset":original.get("dataset"),"primary":original,
             "continuation_attempted":original["unit_id"] in resumes,"effective_status":original["status"],
             "effective_native_numerically_converged":original.get("native_numerically_converged",original.get("numerically_converged")),
             "effective_numerically_converged":original.get("native_numerically_converged",original.get("numerically_converged")),
             "effective_error_m":original.get("error_m"),"effective_failed_point_error_m_diagnostic":original.get("failed_point_error_m_diagnostic"),
             "effective_east_km":original.get("east_km"),"effective_north_km":original.get("north_km"),
             "effective_num_factors_fit":original.get("num_factors_fit"),"total_runtime_s":original.get("runtime_s"),
             "effective_accepted":original.get("error_m") is not None}
        resume=resumes.get(original["unit_id"])
        if resume:
            receipt=resume.get("receipt");launch=resume["launch"]
            processing=launch.get("status")=="complete" and launch.get("returncode")==0
            row["continuation"]={"status":(receipt or launch).get("status"),"sealed":resume["sealed"],
                "launch_path":resume["launch_path"],"receipt_path":resume.get("receipt_path"),"receipt_sha256":resume.get("receipt_sha256"),
                "runtime_s":launch.get("wall_seconds"),"processing_complete":processing}
            row["total_runtime_s"]=(original.get("runtime_s") or 0)+(launch.get("wall_seconds") or 0)
            if receipt:
                best=receipt.get("best") or {};mean=best.get("mean");point=helper.latlon_from_enu(*mean[:2]) if mean else None
                error=helper.distance_m(point,helper.REFERENCE) if point else None;converged=bool(best.get("converged"))
                accepted=bool(resume["sealed"] and converged and processing and row["total_runtime_s"]<=180)
                row["continuation"].update(native_numerically_converged=converged,numerically_converged=converged,
                    accepted=accepted,iterations=best.get("iterations"),
                    num_factors_fit=len(best.get("associations",[])),resumed_fits_attempted=len(receipt.get("resumed_fits",[])),
                    resumed_fits_converged=sum(bool(x.get("converged")) for x in receipt.get("resumed_fits",[])))
                row.update(effective_status=receipt["status"],effective_native_numerically_converged=converged,
                    effective_numerically_converged=converged,
                    effective_accepted=accepted,effective_error_m=error if accepted else None,
                    effective_failed_point_error_m_diagnostic=None if accepted else error,
                    effective_east_km=None if mean is None else mean[0],effective_north_km=None if mean is None else mean[1],
                    effective_num_factors_fit=len(best.get("associations",[])))
            else:
                row.update(effective_status=launch.get("status","unknown"),effective_native_numerically_converged=False,
                    effective_numerically_converged=False,effective_accepted=False,effective_error_m=None)
        row["two_stage_budget_s"]=180;row["within_two_stage_budget"]=row["total_runtime_s"] is not None and row["total_runtime_s"]<=180
        rows.append(row)
    ready=bool(primary_document.get("publication_ready") and primary_document.get("attempted_count")==64 and len(rows)==64)
    return {"schema":"fixed-height-t4-continuation-evaluation/v1","planned_units":64,"primary_attempted_count":primary_document.get("attempted_count"),
        "publication_ready":ready,"continuation_attempted_count":len(resumes),
        "effective_status_counts":dict(sorted(Counter(r["effective_status"] for r in rows).items())),
        "qualification":"two-stage method, maximum 180 seconds; primary outcomes preserved verbatim; roof diagnostic after seals", "rows":rows}


def main():
    p=argparse.ArgumentParser();p.add_argument("--primary-root",type=Path,default=HERE/"runs/t4-primary");p.add_argument("--continuation-root",type=Path,default=HERE/"runs/t4-continuation");p.add_argument("--output",type=Path,default=HERE/"continuation-evaluation.json");p.add_argument("--inspect-incomplete",action="store_true");a=p.parse_args()
    primary=load_module("continuation_primary_eval",HERE/"evaluate_primary.py");records=primary.load_attempts(a.primary_root)
    if not a.inspect_incomplete:primary.require_complete_panel(records)
    primary_document=primary.evaluate(records);resumes=load_resumes(a.continuation_root,records);result=overlay(primary_document,resumes)
    if not a.inspect_incomplete and not result["publication_ready"]:raise ValueError("continuation publication requires complete 64-attempt primary panel")
    a.output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n");print(json.dumps({"output":str(a.output),"publication_ready":result["publication_ready"],"resumes":len(resumes)}))


if __name__=="__main__":main()
