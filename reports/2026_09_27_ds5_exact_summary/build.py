#!/usr/bin/env python3
"""Summarize sealed DS5 exact aggregates, then score reference post-seal."""
from __future__ import annotations
import argparse, hashlib, json, math, tempfile
from pathlib import Path
from typing import Any
import matplotlib.pyplot as plt
import numpy as np

REFERENCE=(37.84903264307456,-122.4856541910174)
METHODS={"cell":{"schema":"ds4-cell-batched-stage-aggregate/v1","objective":"weighted_mse_hz2"},"crossfit":{"schema":"ds4-cell-batched-crossfit-exact-stage-aggregate/v1","objective":"heldout_equal_session_mse_hz2"}}
def canonical(v):return json.dumps(v,indent=2,sort_keys=True,allow_nan=False)+"\n"
def digest(p):return "sha256:"+hashlib.sha256(p.read_bytes()).hexdigest()
def verify(p):
    if not p.is_file():raise FileNotFoundError(p)
    s=p.with_suffix(p.suffix+".sha256");actual=digest(p).removeprefix("sha256:")
    if not s.is_file() or s.read_text().strip().split()[0].removeprefix("sha256:")!=actual:raise ValueError(f"unsealed input: {p}")
def load(p):verify(p);return json.loads(p.read_text())
def write(p,v):
    if p.exists():raise FileExistsError(p)
    p.parent.mkdir(parents=True,exist_ok=True);body=canonical(v)
    with tempfile.NamedTemporaryFile("w",dir=p.parent,delete=False) as h:h.write(body);q=Path(h.name)
    q.replace(p);p.with_suffix(p.suffix+".sha256").write_text(hashlib.sha256(body.encode()).hexdigest()+"\n")
def distance(a,b):
    p1,p2=map(math.radians,(a[0],b[0]));dp=math.radians(b[0]-a[0]);dl=math.radians(b[1]-a[1]);x=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2;return 6371.0088*2*math.atan2(math.sqrt(x),math.sqrt(1-x))
def inference(paths):
    results=[]
    for method,path in paths.items():
        value=load(path);contract=METHODS[method]
        if value.get("schema")!=contract["schema"] or value.get("complete") is not True:raise ValueError("incomplete or wrong aggregate")
        truth=value.get("truth_and_reference",{})
        if truth.get("reference_used_for_inference") is not False or truth.get("truth_accessed") is not False:raise ValueError("truth-blind boundary violated")
        winner=value["winner"]
        results.append({"method":method,"aggregate":{"path":str(path.resolve()),"sha256":digest(path)},"objective_name":contract["objective"],"objective_value":float(winner[contract["objective"]]),"winner":winner,"winner_on_edge":bool(value["winner_on_edge"]),"point_scores":value["point_scores"],"accounting":value["accounting"]})
    return {"schema":"ds5-exact-full42-inference-summary/v1","complete":True,"dataset":"DS5","scope":"full42","reference_coordinate_present":False,"reference_used_for_inference":False,"truth_accessed":False,"results":results}
def postseal(source):
    value=load(source);rows=[]
    for r in value["results"]:
        w=r["winner"];rows.append({"method":r["method"],"latitude_deg":w["latitude_deg"],"longitude_deg":w["longitude_deg"],"east_km":w["east_km"],"north_km":w["north_km"],"horizontal_error_km":distance(REFERENCE,(w["latitude_deg"],w["longitude_deg"])),"winner_on_edge":r["winner_on_edge"],"objective_name":r["objective_name"],"objective_value":r["objective_value"]})
    return {"schema":"ds5-exact-full42-postseal/v1","complete":True,"inference":{"path":str(source.resolve()),"sha256":digest(source)},"reference":{"latitude_deg":REFERENCE[0],"longitude_deg":REFERENCE[1]},"reference_used_postseal_only":True,"results":rows,"limitations":["Both winners lie on the 2 km grid boundary, so the reported errors are truncated coarse-grid results.","DS5 is development data, not an independent final test set.","Cell and crossfit objectives use different weighting and selection rules and their numeric losses are not directly comparable."]}
def render(inference_value,scored,png):
    fig,axes=plt.subplots(1,3,figsize=(14,4));colors={"cell":"tab:blue","crossfit":"tab:orange"}
    for axis,r in zip(axes[:2],inference_value["results"],strict=True):
        pts=r["point_scores"];x=np.array([p["east_km"] for p in pts]);y=np.array([p["north_km"] for p in pts]);z=np.array([p[r["objective_name"]] for p in pts]);w=r["winner"]
        sc=axis.scatter(x,y,c=z,s=90,cmap="viridis");axis.scatter(w["east_km"],w["north_km"],marker="x",s=120,color=colors[r["method"]]);axis.set(xlabel="east (km)",ylabel="north (km)",title=f"{r['method']} 2 km surface");fig.colorbar(sc,ax=axis,label=r["objective_name"])
    rows=scored["results"];axes[2].bar([r["method"] for r in rows],[r["horizontal_error_km"] for r in rows],color=[colors[r["method"]] for r in rows]);axes[2].set(ylabel="horizontal error (km)",title="Post-seal reference error");fig.tight_layout();fig.savefig(png,dpi=180);plt.close(fig);png.with_suffix(png.suffix+".sha256").write_text(hashlib.sha256(png.read_bytes()).hexdigest()+"\n")
def main():
    p=argparse.ArgumentParser();s=p.add_subparsers(dest="command",required=True);i=s.add_parser("inference");i.add_argument("--cell",type=Path,required=True);i.add_argument("--crossfit",type=Path,required=True);i.add_argument("--output",type=Path,required=True);q=s.add_parser("postseal");q.add_argument("--inference",type=Path,required=True);q.add_argument("--output",type=Path,required=True);q.add_argument("--png",type=Path,required=True);a=p.parse_args()
    if a.command=="inference":v=inference({"cell":a.cell,"crossfit":a.crossfit});write(a.output,v)
    else:v=postseal(a.inference);write(a.output,v);render(load(a.inference),v,a.png)
    print(canonical(v),end="")
if __name__=="__main__":main()
