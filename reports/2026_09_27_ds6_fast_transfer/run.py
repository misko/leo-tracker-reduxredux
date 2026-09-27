#!/usr/bin/env python3
"""Transfer the two preselected DS5 point aggregators to blind DS6 products."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, math, tempfile
from pathlib import Path
from typing import Any
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
DS6=Path("/home/mouse9911/gits/leo-ds6/reports/2026_09_27_ds6_roof")
MANIFEST=DS6/"manifest.json";UNITS=DS6/"evaluation-units.json";POSE=DS6/"pose-authority.json"
SOURCE=Path("/srv/bulk/leo/scanner-adaptive-tle-position-v2")
METHODS=("inverse_rf_rms2_mean","rf_trimmed_mean")
spec=importlib.util.spec_from_file_location("ds6_point_oracle",ROOT/"reports/2026_09_25_ds3_ds4_position_iteration1/run.py");assert spec and spec.loader
POINT=importlib.util.module_from_spec(spec);spec.loader.exec_module(POINT)
def canonical(v):return json.dumps(v,indent=2,sort_keys=True,allow_nan=False)+"\n"
def digest(p):return "sha256:"+hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def write(p,v):
    if p.exists():raise FileExistsError(p)
    p.parent.mkdir(parents=True,exist_ok=True);body=canonical(v)
    with tempfile.NamedTemporaryFile("w",dir=p.parent,delete=False) as h:h.write(body);q=Path(h.name)
    q.replace(p);p.with_suffix(p.suffix+".sha256").write_text(hashlib.sha256(body.encode()).hexdigest()+"\n")
def compact(v):return json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def source_document(session):
    m=load(SOURCE/session/"manifest.json");outer=m.get("document")
    if not isinstance(outer,dict) or m.get("sha256")!="sha256:"+hashlib.sha256(compact(outer)).hexdigest():raise ValueError("invalid storage envelope")
    d=outer.get("document");
    if d!=load(SOURCE/session/"document.json"):raise ValueError("document mismatch")
    return d
def audit_one(session):
    d=source_document(session);cfg=d.get("diagnostics",{}).get("configuration",{})
    if d.get("analysis_id")!="scanner-adaptive-tle-position-v2" or d.get("known_position_used_for_inference") is not False or cfg.get("known_position_used_for_inference") is not False:raise ValueError("non-blind position product")
    sacramento=cfg.get("priors",{}).get("sacramento",{})
    if sacramento!={"latitude_deg":38.5816,"longitude_deg":-121.4944,"radius_km":250.0}:raise ValueError("not Sacramento-250 blind configuration")
    prior=next((p for p in d.get("priors",[]) if p.get("name")=="sacramento"),None)
    if prior is None:raise ValueError("Sacramento result absent")
    selected=prior["selected"];points=d.get("diagnostics",{}).get("evaluated_points",{}).get("sacramento",[])
    if len(points)!=400:raise ValueError("incomplete Sacramento surface")
    matches=[p for p in points if float(p["east_km"])==float(selected["east_km"]) and float(p["north_km"])==float(selected["north_km"]) and float(p["capped_weighted_rmse_hz"])==float(selected["capped_weighted_rmse_hz"])]
    if len(matches)!=1:raise ValueError("selected point does not replay from objective surface")
    return {"session_id":session,"configuration_sha256":d["configuration_sha256"],"latitude_deg":float(selected["latitude_deg"]),"longitude_deg":float(selected["longitude_deg"]),"rf_rms_hz":float(selected["capped_weighted_rmse_hz"]),"matched_track_count":int(selected["matched_track_count"]),"source_search_complete":bool(prior["search_complete"]),"source_stop_reason":str(prior["stop_reason"]),"source":{"manifest_sha256":digest(SOURCE/session/"manifest.json"),"document_sha256":digest(SOURCE/session/"document.json")},"leakage_exclusion":{"source_evaluation_metrics_ignored":True,"only_signal_selected_fields_copied":True}}
def unit_rows(e):
    rows=[{"unit_id":f"single-{i+1:03d}","scope":"single","session_ids":list(ids)} for i,ids in enumerate(e["single_scans"])]
    rows += [{"unit_id":f"group8-{i+1:03d}","scope":"group8","session_ids":list(ids)} for i,ids in enumerate(e["groups_of_8"])]
    rows.append({"unit_id":"full43","scope":"full","session_ids":list(e["full_dataset"])});return rows
def infer(output):
    manifest,e=load(MANIFEST),load(UNITS);ids=[r["session_id"] for r in manifest["captures"]]
    if ids!=list(e["full_dataset"]):raise ValueError("DS6 membership/order mismatch")
    sessions={sid:audit_one(sid) for sid in ids};configs={r["configuration_sha256"] for r in sessions.values()}
    if len(configs)!=1:raise ValueError("mixed V2 configurations")
    results=[]
    for u in unit_rows(e):
        source=[sessions[s] for s in u["session_ids"]]
        for method in METHODS:
            lat,lon=POINT.estimate(method,source);results.append({**u,"method":method,"latitude_deg":lat,"longitude_deg":lon,"source_session_count":len(source),"matched_track_count_sum":sum(r["matched_track_count"] for r in source),"all_source_searches_complete":all(r["source_search_complete"] for r in source),"source_stop_reason_counts":dict(sorted({reason:sum(r["source_stop_reason"]==reason for r in source) for reason in {r["source_stop_reason"] for r in source}}.items()))})
    value={"schema":"ds6-fast-winner-transfer-inference/v1","complete":True,"dataset":"DS6","reference_coordinate_present":False,"known_position_used_for_inference":False,"truth_accessed":False,"transfer":{"selected_on":"DS5","methods":list(METHODS),"retuned_on_ds6":False},"bindings":{"manifest":{"path":str(MANIFEST),"sha256":digest(MANIFEST)},"evaluation_units":{"path":str(UNITS),"sha256":digest(UNITS)},"source_root":str(SOURCE),"source_configuration_sha256":next(iter(configs))},"coverage":{"single":43,"group8":5,"full":1,"result_count":len(results)},"sessions":sessions,"results":results,"radio_geometry_caveat":"Roof fixture receiver mapping is provisional; RF phase centers, baseline, elevation, altitude, and survey uncertainty are unmeasured.","source_coordinate_leakage_excluded":True}
    lowered=canonical(value).lower().replace('"reference_coordinate_present": false',"")
    if "horizontal_error" in lowered or '"reference"' in lowered:raise ValueError("reference leakage in inference")
    write(output,value);return value
def haversine(a,b):
    p1,p2=map(math.radians,(a[0],b[0]));dp=math.radians(b[0]-a[0]);dl=math.radians(b[1]-a[1]);x=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2;return 6371.0088*2*math.atan2(math.sqrt(x),math.sqrt(1-x))
def postseal(source,output,png):
    seal=source.with_suffix(source.suffix+".sha256");
    if not seal.is_file() or seal.read_text().strip().split()[0]!=digest(source).removeprefix("sha256:"):raise ValueError("unsealed inference")
    inf=load(source);pose=load(POSE);ref=(float(pose["latitude_deg"]),float(pose["longitude_deg"]));rows=[{**r,"horizontal_error_km":haversine(ref,(r["latitude_deg"],r["longitude_deg"]))} for r in inf["results"]]
    summaries=[]
    for method in METHODS:
        for scope in ("single","group8","full"):
            x=np.array([r["horizontal_error_km"] for r in rows if r["method"]==method and r["scope"]==scope]);summaries.append({"method":method,"scope":scope,"count":len(x),"median_error_km":float(np.median(x)),"p90_error_km":float(np.quantile(x,.9)),"maximum_error_km":float(x.max())})
    value={"schema":"ds6-fast-winner-transfer-postseal/v1","complete":True,"inference":{"path":str(source.resolve()),"sha256":digest(source)},"reference":{"latitude_deg":ref[0],"longitude_deg":ref[1],"pose_authority_sha256":digest(POSE)},"reference_used_postseal_only":True,"results":rows,"summaries":summaries,"radio_geometry_caveat":inf["radio_geometry_caveat"]};write(output,value)
    fig,ax=plt.subplots(figsize=(7,4));x=np.arange(3);width=.35
    for i,m in enumerate(METHODS):ax.bar(x+(i-.5)*width,[next(s["median_error_km"] for s in summaries if s["method"]==m and s["scope"]==q) for q in ("single","group8","full")],width,label=m)
    ax.set_xticks(x,["43 singles","5 groups of 8","full43"]);ax.set_ylabel("median horizontal error (km)");ax.set_title("DS6 preselected DS5 fast aggregators");ax.legend(fontsize=8);fig.tight_layout();fig.savefig(png,dpi=180);plt.close(fig);png.with_suffix(png.suffix+".sha256").write_text(hashlib.sha256(png.read_bytes()).hexdigest()+"\n");return value
def main():
    p=argparse.ArgumentParser();s=p.add_subparsers(dest="cmd",required=True);a=s.add_parser("infer");a.add_argument("--output",type=Path,required=True);b=s.add_parser("postseal");b.add_argument("--inference",type=Path,required=True);b.add_argument("--output",type=Path,required=True);b.add_argument("--png",type=Path,required=True);x=p.parse_args();v=infer(x.output) if x.cmd=="infer" else postseal(x.inference,x.output,x.png);print(canonical({"schema":v["schema"],"complete":v["complete"]}),end="")
if __name__=="__main__":main()
