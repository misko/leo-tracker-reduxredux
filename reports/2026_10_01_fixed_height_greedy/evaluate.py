#!/usr/bin/env python3
"""Seal-gated diagnostic evaluator for fixed-height development fits."""
from __future__ import annotations
import csv,hashlib,json,math
from collections import Counter
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
CENTER=(38.5816,-121.4944)
REFERENCE=(37.849056280893684,-122.48575489722863)
EARTH_RADIUS_KM=6371.0088


def sha256(path): return "sha256:"+hashlib.sha256(Path(path).read_bytes()).hexdigest()


def latlon_from_enu(east,north):
    lat1,lon1=map(math.radians,CENTER); distance=math.hypot(east,north)
    if distance==0:return CENTER
    bearing=math.atan2(east,north); angle=distance/EARTH_RADIUS_KM
    lat2=math.asin(math.sin(lat1)*math.cos(angle)+math.cos(lat1)*math.sin(angle)*math.cos(bearing))
    lon2=lon1+math.atan2(math.sin(bearing)*math.sin(angle)*math.cos(lat1),math.cos(angle)-math.sin(lat1)*math.sin(lat2))
    return math.degrees(lat2),((math.degrees(lon2)+180)%360)-180


def distance_m(a,b):
    lat1,lon1,lat2,lon2=map(math.radians,(*a,*b));dlat=lat2-lat1;dlon=lon2-lon1
    h=math.sin(dlat/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 2*EARTH_RADIUS_KM*1000*math.asin(min(1,math.sqrt(h)))


def snapshot_index(development: Path):
    result={}
    direct=development/"bindings.json"
    paths=([direct] if direct.is_file() else [])+sorted(development.glob("*source*/bindings.json"))
    for path in paths:
        bindings=json.loads(path.read_text())
        for source,entry in bindings.items():
            snapshot=Path(entry["snapshot"])
            if not snapshot.is_absolute(): snapshot=ROOT/snapshot
            result[(source,entry["sha256"])]=snapshot
    return result


def verify_source_bindings(bindings,index):
    verified=[]
    for source,expected in bindings.items():
        live=Path(source)
        if live.is_file() and sha256(live)==expected:
            verified.append({"source":source,"sha256":expected,"verified_via":"live"});continue
        snapshot=index.get((source,expected))
        if snapshot is None or not snapshot.is_file() or sha256(snapshot)!=expected:
            raise ValueError(f"no valid live or archived source binding for {source}")
        verified.append({"source":source,"sha256":expected,"verified_via":"archived_snapshot","snapshot":str(snapshot)})
    return verified


def load_sealed(development: Path):
    index=snapshot_index(development); records=[]
    for seal_path in sorted(development.glob("*/*.seal.json")):
        receipt_path=seal_path.with_name(seal_path.name.replace(".seal.json",".json"))
        seal=json.loads(seal_path.read_text())
        if not receipt_path.is_file() or seal.get("prediction_sha256")!=sha256(receipt_path):
            raise ValueError(f"seal mismatch: {receipt_path}")
        receipt=json.loads(receipt_path.read_text())
        if receipt.get("schema") not in {"fixed-msl-greedy-replay/v1","fixed-height-joint-greedy/v1"}: continue
        receipt["_path"]=str(receipt_path);receipt["_sha256"]=seal["prediction_sha256"];receipt["_sealed"]=True
        receipt["_verified_sources"]=verify_source_bindings(receipt.get("source_sha256",{}),index)
        launch_path=receipt_path.with_name(receipt_path.stem+".launch.json")
        receipt["_launch"]=json.loads(launch_path.read_text()) if launch_path.is_file() else {}
        receipt["_variant"]=receipt_path.parent.name
        records.append(receipt)
    return records


def point_and_iterations(receipt):
    if receipt["schema"]=="fixed-height-joint-greedy/v1":
        best=receipt.get("best") or {};mean=best.get("mean")
        return (None if not mean else mean[:2]),best.get("iterations"),"joint_best_mean"
    components=receipt.get("components") or []
    if not components:return None,len(receipt.get("checkpoints",[])),"sequential_highest_weight_component_mean"
    _,component=min(enumerate(components),key=lambda x:(-float(x[1]["weight"]),x[0]))
    return component["mean"][:2],len(receipt.get("checkpoints",[])),"sequential_highest_weight_component_mean"


def evaluate(records,old_evaluation=None):
    baseline={}
    if old_evaluation:
        for row in old_evaluation.get("rows",[]):
            if row.get("arm")=="greedy":baseline[row["unit_id"]]=row
    rows=[]
    for receipt in records:
        en,iterations,rule=point_and_iterations(receipt)
        point=latlon_from_enu(*en) if en is not None else None
        error=distance_m(point,REFERENCE) if point else None
        accepted=receipt["status"] in {"complete","converged_local_mode"}
        joint=receipt["schema"]=="fixed-height-joint-greedy/v1"
        native_converged=(bool((receipt.get("best") or {}).get("converged")) if joint else None)
        processing_complete=(receipt.get("_launch",{}).get("status")=="complete" and
                             receipt.get("_launch",{}).get("returncode")==0 and receipt.get("_sealed",False))
        fits=receipt.get("fits",[]) if joint else []
        consumed=(len((receipt.get("best") or {}).get("associations",[])) if joint
                  else len(receipt.get("checkpoints",[])))
        old=baseline.get(receipt["unit_id"],{})
        rows.append({"unit_id":receipt["unit_id"],"arm":receipt.get("arm","joint"),"variant":receipt["_variant"],
            "status":receipt["status"],"processing_complete":processing_complete,
            "numerically_converged":native_converged,"accepted":accepted,
            "error_m":error if accepted else None,"failed_point_error_m_diagnostic":None if accepted else error,
            "point_latlon":None if point is None else list(point),"point_rule":rule,"iterations":iterations,
            "runtime_s":receipt["_launch"].get("wall_seconds",receipt.get("wall_seconds")),
            "planned_factors":receipt.get("planned_factors"),"consumed_factors":consumed,
            "num_factors_fit":consumed,"seed_fits_attempted":len(fits) if joint else None,
            "seed_fits_converged":sum(bool(fit.get("converged")) for fit in fits) if joint else None,
            "old_greedy_status":old.get("status"),"old_greedy_error_m":None if old.get("error_km") is None else old["error_km"]*1000,
            "receipt_path":receipt["_path"],"receipt_sha256":receipt["_sha256"],
            "source_binding_verification":receipt["_verified_sources"],"diagnostic_only":True})
    return {"schema":"fixed-height-greedy-development-evaluation/v1","planned_future_panel_units":64,
        "development_receipt_count":len(rows),"publication_claim":False,
        "qualification":"development diagnostics; roof reference accessed only after sealed predictions",
        "status_counts":dict(sorted(Counter(r["status"] for r in rows).items())),"rows":rows}


def format_table(rows):
    header="| unit | arm / variant | status | error m | iterations | runtime s |\n|---|---|---:|---:|---:|---:|"
    lines=[header]
    for r in rows:
        error=r["error_m"] if r["error_m"] is not None else r["failed_point_error_m_diagnostic"]
        suffix=" (failed diagnostic)" if r["error_m"] is None and error is not None else ""
        lines.append(f"| {r['unit_id']} | {r['arm']} / {r['variant']} | {r['status']} | {'' if error is None else f'{error:.1f}{suffix}'} | {r['iterations']} | {r['runtime_s']:.3f} |")
    return "\n".join(lines)+"\n"


def main():
    records=load_sealed(HERE/"development")
    old_path=ROOT/"reports/2026_09_30_gaussian_sum_64_scan/evaluation.json"
    result=evaluate(records,json.loads(old_path.read_text()) if old_path.is_file() else None)
    (HERE/"development-evaluation.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    fields=sorted({k for row in result["rows"] for k in row})
    with (HERE/"development-evaluation.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for row in result["rows"]:writer.writerow({k:json.dumps(v) if isinstance(v,(list,dict)) else v for k,v in row.items()})
    table=format_table(result["rows"]);(HERE/"DEVELOPMENT_RESULTS.md").write_text("# Sealed development results\n\n"+table+"\nNumerical convergence and roof-reference error are separate fields. Failed point errors are diagnostic only. The future panel denominator is 64; this table is not a publication claim.\n")
    print(table,end="")


if __name__=="__main__":main()
