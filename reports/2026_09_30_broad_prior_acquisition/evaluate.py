#!/usr/bin/env python3
"""Seal-verified comparison of frozen v3 and merge-128-to-32 receipts."""
from __future__ import annotations
import argparse, csv, hashlib, importlib.util, json
from collections import Counter
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
OLD=ROOT/"reports/2026_09_30_gaussian_sum_64_scan"
REFERENCE=(37.849056280893684,-122.48575489722863)
CENTER=(38.5816,-121.4944)


def sha256(path): return "sha256:"+hashlib.sha256(Path(path).read_bytes()).hexdigest()


def old_evaluator():
    spec=importlib.util.spec_from_file_location("frozen_old_evaluator",OLD/"evaluate.py")
    assert spec and spec.loader
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


def load_records(run_root: Path, expected_arm: str | None=None):
    records={}
    for seal_path in sorted(run_root.glob("batch-*/*.seal.json")):
        receipt_path=seal_path.with_name(seal_path.name.replace(".seal.json",".json"))
        seal=json.loads(seal_path.read_text())
        if not receipt_path.exists() or seal.get("prediction_sha256") != sha256(receipt_path):
            raise ValueError(f"seal mismatch for {receipt_path}")
        receipt=json.loads(receipt_path.read_text()); arm=receipt["arm"]
        if expected_arm and arm != expected_arm: raise ValueError(f"unexpected arm {arm}")
        for source,expected in receipt.get("source_sha256",{}).items():
            if sha256(source) != expected: raise ValueError(f"source binding mismatch: {source}")
        key=(receipt["unit_id"],arm)
        if key in records: raise ValueError(f"duplicate sealed receipt {key}")
        receipt.update(_sealed=True,_receipt_path=str(receipt_path),_receipt_sha256=seal["prediction_sha256"])
        records[key]=receipt
    for path in sorted(run_root.glob("batch-*/*.launch.json")):
        launch=json.loads(path.read_text()); key=(launch["unit_id"],launch["arm"])
        if expected_arm and key[1] != expected_arm: raise ValueError(f"unexpected arm {key[1]}")
        if key in records:
            records[key]["_launch"]=launch; records[key]["_launch_path"]=str(path)
        else:
            records[key]={"unit_id":key[0],"arm":key[1],"status":launch.get("status","unknown"),
                          "_launch_only":True,"_launch":launch,"_launch_path":str(path)}
    return records


def publication_gate(units, merging):
    expected={(u["unit_id"],"merge128_to32") for u in units}
    missing=sorted(expected-set(merging)); extra=sorted(set(merging)-expected)
    if missing or extra:
        raise ValueError(f"publication requires 64 merge attempts; missing={len(missing)}, extra={len(extra)}")


def top_point(receipt):
    components=receipt.get("components",[])
    if not components: return None,None
    _,top=min(enumerate(components),key=lambda x:(-float(x[1]["weight"]),x[0]))
    point=old_evaluator().latlon_from_enu(CENTER,float(top["mean"][0]),float(top["mean"][1]))
    return [float(point[0]),float(point[1])],old_evaluator().great_circle_km(point,REFERENCE)


def merging_row(unit, receipt):
    base={**unit,"arm":"merge128_to32","attempted":receipt is not None}
    if receipt is None: return {**base,"status":"missing","completed":False,"error_km":None}
    launch=receipt.get("_launch",{}); completed=receipt.get("status")=="complete" and receipt.get("_sealed")
    point,diagnostic_error=top_point(receipt)
    cps=receipt.get("checkpoints",[]); first=cps[0] if cps else {}
    return {**base,"status":receipt.get("status"),"completed":completed,
        "error_km":diagnostic_error if completed else None,
        "highest_weight_component_error_km_diagnostic":diagnostic_error,
        "highest_weight_component_latlon_diagnostic":point,
        "runtime_s":launch.get("wall_seconds",receipt.get("wall_seconds")),
        "consumed_factors":len(cps),"planned_factors":receipt.get("planned_factors"),
        "gate_failures":receipt.get("gate_failures",[]),
        "first_retained_mass_before_merging":first.get("retained_mass_before_merging"),
        "first_projected_merge_score":first.get("projected_merge_score"),
        "first_density_weighted_mean_absolute_log_error":first.get("projected_density_distortion",{}).get("weighted_mean_absolute_log_error"),
        "first_density_maximum_absolute_log_error":first.get("projected_density_distortion",{}).get("maximum_absolute_log_error"),
        "materialized_component_cap":128,"retained_component_cap":32,
        "receipt_path":receipt.get("_receipt_path"),"receipt_sha256":receipt.get("_receipt_sha256"),
        "launch_path":receipt.get("_launch_path"),"source_sha256":receipt.get("source_sha256",{}),
        "input_sha256":receipt.get("inputs",{}),"diagnostic_only":True}


def compare(selection, old_records, merging_records):
    old=old_evaluator(); units=old.selected_units(selection)
    baseline=old.evaluate(selection,old_records); by_old={(x["unit_id"],x["arm"]):x for x in baseline["rows"]}
    rows=[]
    for unit in units:
        new=merging_row(unit,merging_records.get((unit["unit_id"],"merge128_to32")))
        old_gsf=by_old[(unit["unit_id"],"gaussian_sum")]; old_greedy=by_old[(unit["unit_id"],"greedy")]; prior=by_old[(unit["unit_id"],"prior_only")]
        receipt=merging_records.get((unit["unit_id"],"merge128_to32"),{})
        old_receipt=old_records.get((unit["unit_id"],"gaussian_sum"),{})
        old_first=(old_receipt.get("checkpoints") or [{}])[0]
        rows.append({**new,"old_gaussian_sum_status":old_gsf["status"],"old_greedy_status":old_greedy["status"],
            "old_prior_status":prior["status"],"old_gaussian_sum_error_km":old_gsf["error_km"],
            "old_greedy_error_km":old_greedy["error_km"],"old_prior_error_km":prior["error_km"],
            "old_first_retained_mass":old_first.get("retained_mass"),
            "first_retained_mass_delta":(None if not old_first.get("retained_mass") or not receipt.get("checkpoints") else
                receipt["checkpoints"][0].get("retained_mass_before_merging")-old_first["retained_mass"])})
    gates=Counter(g for row in rows for g in row.get("gate_failures",[]))
    def count_status(key): return dict(sorted(Counter(row[key] for row in rows).items()))
    return {"schema":"broad-prior-acquisition-comparison/v1","planned_units":64,
        "publication_ready":len(merging_records)==64,"diagnostic_only":True,
        "qualification":"roof-reference highest-weight-component point rule; failed errors excluded",
        "retention_comparison_qualification":"128-vs-32 child-bank capacity effect before reduction; not attributable solely to the reducer",
        "temporary_component_cap":128,"retained_component_cap":32,"rows":rows,
        "completion":{"merging":count_status("status"),"old_gaussian_sum":count_status("old_gaussian_sum_status"),
                      "old_greedy":count_status("old_greedy_status"),"old_prior":count_status("old_prior_status")},
        "merging_gate_categories":dict(sorted(gates.items()))}


def write_outputs(result, output: Path):
    output.mkdir(parents=True,exist_ok=True)
    (output/"comparison.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    fields=sorted({k for row in result["rows"] for k in row})
    with (output/"conditional-errors.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for row in result["rows"]: w.writerow({k:json.dumps(v) if isinstance(v,(list,dict)) else v for k,v in row.items()})
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(7,5.5)); pairs=[r for r in result["rows"] if r.get("old_first_retained_mass") is not None and r.get("first_retained_mass_before_merging") is not None]
    ax.scatter([r["old_first_retained_mass"] for r in pairs],[r["first_retained_mass_before_merging"] for r in pairs],s=22,alpha=.7)
    ax.plot([0,1],[0,1],color="black",lw=1); ax.set(
        xlabel="32-child truncation retained mass",
        ylabel="128-child bank retained mass (before merging)",
        title=f"First-factor probability retention • {len(pairs)} independent scans")
    fig.tight_layout(); fig.savefig(output/"retention-scatter.png",dpi=160); plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(13,5)); names=list(result["completion"]); complete=[result["completion"][n].get("complete",0) for n in names]
    axes[0].bar(names,complete); axes[0].set(ylim=(0,64),ylabel="complete / 64"); axes[0].tick_params(axis='x',rotation=25)
    gates=result["merging_gate_categories"]
    short={"position_support_boundary":"position support","height_support_boundary":"height support",
           "uniform_region_center_boundary":"center outside 250 km",
           "posterior_mass_pruned_above_1_percent":">1% pre-merge pruning",
           "projected_merge_score_above_0_1_nat":"merge score >0.1 nat",
           "merge_pair_budget_exhausted":"merge pair budget"}
    axes[1].barh([short.get(name,name.replace("_"," ")) for name in gates],list(gates.values()))
    axes[1].set(xlabel="scan count",title="Merge gate categories"); fig.tight_layout(); fig.savefig(output/"completion-and-gates.png",dpi=160); plt.close(fig)


def main():
    p=argparse.ArgumentParser(); p.add_argument("--output",type=Path,default=HERE/"comparison"); p.add_argument("--inspect-incomplete",action="store_true"); a=p.parse_args()
    selection=json.loads((OLD/"selection.json").read_text()); units=old_evaluator().selected_units(selection)
    old_records=load_records(OLD/"runs-v3"); merging=load_records(HERE/"runs/merging","merge128_to32")
    if not a.inspect_incomplete: publication_gate(units,merging)
    result=compare(selection,old_records,merging)
    if not result["publication_ready"] and not a.inspect_incomplete: raise ValueError("incomplete publication panel")
    write_outputs(result,a.output); print(json.dumps({"output":str(a.output),"publication_ready":result["publication_ready"]}))


if __name__=="__main__": main()
