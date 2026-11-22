"""Lock both prediction streams, score the entire DS30 cohort, and generate the report."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import zipfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
import numpy as np
from tools.pipeline_eval.scoring import distance_km
from panels import PANEL_SIZES, select_panel

HERE=Path(__file__).resolve().parent
BASE=HERE.parents[1]/"2026_11_21_ds30_full"
MODES=("deployed","optimized")
ARMS=("fitted_c","c0")
STAGES=("acquisition","solve","total")
COLORS=("#394f73","#008071")
LABELS=("Deployed ALGO08","Optimized two-scan")


def read(path):
    return json.loads(path.read_bytes())


def records(path):
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path,rows):
    with path.open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=rows[0],lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def lock_predictions(root,out,panel="smoke"):
    members={r["id"]:r for r in read(BASE/"cohort.json")["members"]}
    selected=select_panel(read(BASE/"prediction-lock.json")["predictions"],panel)
    binding={r["case"]:r for r in selected}
    cohort=[members[cid] for cid in binding]
    entries={}
    for case in cohort:
        cid=case["id"]
        pair=[]
        for m in MODES:
            payload=(root/cid/(m+".json")).read_bytes()
            r=json.loads(payload)
            assert (r["case"],r["mode"],r["windows"])==(cid,m,case["windows"])
            assert r["input_binding_sha256"]==binding[cid]["input_binding_sha256"] and r["raw_authority"]==binding[cid]["raw_authority"]
            assert set(r["arms"])==set(ARMS) and r["status"] in ("ok","withheld","unavailable")
            assert all((r["arms"][arm]["latlon"] is not None)==(r["status"]=="ok") for arm in ARMS)
            assert all(r[k+"_wall_s"]>=0 and r[k+"_cpu_s"]>=0 for k in STAGES)
            pair.append(r)
            entries[cid+"/"+m+".json"]=payload
        assert pair[0]["cpu"]==pair[1]["cpu"] and {r["order"] for r in pair}=={0,1}
        for k in ("region","release","eligible_visits","windows","raw_authority"):
            assert pair[0][k]==pair[1][k]
    assert len(entries)==2*PANEL_SIZES[panel]
    # The archive is deterministic. No scoring coordinates are read before this point.
    manifest={name:sha(payload) for name,payload in sorted(entries.items())}
    with zipfile.ZipFile(out/"predictions.zip","w") as z:
        for name,payload in sorted(entries.items()):
            z.writestr(zipfile.ZipInfo(name),payload,compress_type=zipfile.ZIP_DEFLATED)
    (out/"prediction-lock.json").write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n")
    (out/"panel.json").write_text(json.dumps(dict(panel=panel,cases=list(binding)),indent=2)+"\n")
    return cohort,{k:json.loads(v) for k,v in entries.items()}


def score(cohort,entries):
    refs={r["dataset_label"]:r["reference"] for r in read(BASE/"reference-audit.json")["cases"] if r["authority_eligible"]}
    prior={(r["case"],r["arm"]):r for r in records(HERE.parent/"regional-release/ds30-replay.csv")}
    times,positions=[],[]
    for case in cohort:
        cid=case["id"]
        p,q=(entries[cid+"/"+m+".json"] for m in MODES)
        ref=refs[cid]
        row=dict(case=cid,capture=case["recording_state"],cpu=p["cpu"],first=next(v["mode"] for v in (p,q) if not v["order"]),
                 windows=p["windows"],eligible_visits=p["eligible_visits"],same_factors=p["factor_digest"]==q["factor_digest"],
                 same_owners=p["owners"]==q["owners"],same_decision=p["status"]==q["status"],
                 deployed_status=p["status"],optimized_status=q["status"])
        for stage in STAGES:
            for unit in ("wall","cpu"):
                k=f"{stage}_{unit}_s"
                for m,v in zip(MODES,(p,q)):
                    row[m+"_"+k]=v[k]
                row[stage+"_"+unit+"_speedup"]=p[k]/q[k]
        times.append(row)
        for arm in ARMS:
            d=dict(case=cid,arm=arm,capture=case["recording_state"])
            for m,v in zip(MODES,(p,q)):
                a=v["arms"][arm]
                ll=a["latlon"]
                d.update({m+"_status":v["status"],m+"_lat":ll[0] if ll else None,m+"_lon":ll[1] if ll else None,
                          m+"_error_km":distance_km(ll,(ref["latitude_deg"],ref["longitude_deg"])),
                          m+"_rf_rms_hz":a.get("rf_rms_hz")})
            h=prior[cid,arm]
            d["deployed_matches_frozen"]=(p["status"]==h["state"] and
                d["deployed_lat"]==(float(h["latitude"]) if h["latitude"] else None) and
                d["deployed_lon"]==(float(h["longitude"]) if h["longitude"] else None) and
                d["deployed_rf_rms_hz"]==(float(h["rf_rms_hz"]) if h["rf_rms_hz"] else None))
            d["identical_position"]=p["arms"][arm]["latlon"]==q["arms"][arm]["latlon"]
            d["identical_rf_rms"]=d["deployed_rf_rms_hz"]==d["optimized_rf_rms_hz"]
            paired=p["status"]==q["status"]=="ok"
            d["optimized_minus_deployed_error_m"]=(1000*(d["optimized_error_km"]-d["deployed_error_km"])
                                                   if paired else None)
            d["endpoint_separation_m"]=(1000*distance_km(p["arms"][arm]["latlon"],q["arms"][arm]["latlon"])
                                        if paired else None)
            positions.append(d)
    return sorted(times,key=lambda x:x["case"]),sorted(positions,key=lambda x:(x["case"],x["arm"]))


def pct(values,n):
    return float(np.percentile(values,n)) if len(values) else float("nan")


def ecdf(ax,values,total,style,color,label):
    values=np.sort(values)
    if len(values):
        ax.step(np.r_[values[0],values],np.arange(len(values)+1)/total,where="post",
                color=color,linewidth=2,linestyle=style,label=label)


def plots(out,times,positions):
    fig,(a,b)=plt.subplots(1,2,figsize=(11,4.4),layout="constrained")
    for mode,color,label in zip(MODES,COLORS,LABELS):
        vals=[r[mode+"_total_wall_s"] for r in times]
        ecdf(a,vals,len(times),"-",color,label)
    a.set(xscale="log",title="Raw I/Q through position",xlabel="Elapsed seconds per recording",ylabel="Fraction of all recordings")
    stage_labels=("Read and detect","Fit and grid","End to end")
    for i,(stage,name) in enumerate(zip(STAGES,stage_labels)):
        ratios=[r[stage+"_wall_speedup"] for r in times]
        lo,median,hi=np.percentile(ratios,[10,50,90])
        b.plot([lo,hi],[i,i],color="#778a9a",linewidth=3)
        b.plot(median,i,"o",color=COLORS[1],markersize=9)
    b.axvline(1,color="#444",linestyle=":",zorder=0)
    b.set(yticks=np.arange(3),yticklabels=stage_labels,ylim=(2.6,-.6),xlabel="Deployed / optimized elapsed time",
          title="Paired speedup · median and 10th–90th percentiles")
    a.yaxis.set_major_formatter(PercentFormatter(1))
    a.legend(frameon=False)
    for ax in (a,b):
        ax.spines[["top","right"]].set_visible(False)
        ax.grid(alpha=.18)
    fig.savefig(out/"runtime.png",dpi=180)
    plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11,4.4),layout="constrained",sharey=True)
    for ax,arm,title in zip(axes,ARMS,("Fitted RF calibration","RF calibration fixed at zero")):
        rows=[r for r in positions if r["arm"]==arm]
        for mode,color,label,style in zip(MODES,COLORS,LABELS,("-","--")):
            x=sorted(r[mode+"_error_km"] for r in rows if r[mode+"_error_km"] is not None)
            ecdf(ax,x,len(rows),style,color,label)
        ax.yaxis.set_major_formatter(PercentFormatter(1))
        ax.set(xscale="log",ylim=(0,1.02),title=title,xlabel="Horizontal position error (km)")
        ax.spines[["top","right"]].set_visible(False)
        ax.grid(alpha=.18)
        ax.legend(frameon=False)
    axes[0].set_ylabel("Fraction of all assigned recordings")
    fig.savefig(out/"position-error.png",dpi=180)
    plt.close(fig)


def report(out,times,pos,panel):
    n=len(times)
    wall_ratio=pct([r["optimized_total_wall_s"]/r["deployed_total_wall_s"] for r in times],50)
    fitted=[r for r in pos if r["arm"]=="fitted_c"]
    fix_counts=[sum(r[m+"_status"]=="ok" for r in fitted) for m in MODES]
    same=sum(r["deployed_status"]==r["optimized_status"] and r["identical_position"] for r in fitted)
    visits=sum(r["eligible_visits"] for r in times)
    timing_change="shorter" if wall_ratio<=1 else "longer"
    md=[f"# Optimized two-scan versus deployed ALGO08 · DS30 {panel} panel ({n}/455)","",
        f"On Gauss the optimized pipeline took **{abs(1-wall_ratio):.1%} {timing_change} end to end** at the median of the {n} recording pairs. Deployed ALGO08 returned **{fix_counts[0]}/{n} fixes** and the optimized pipeline returned **{fix_counts[1]}/{n}**. Their fitted-calibration decisions and coordinates agreed on **{same}/{n}** recordings, counting a shared withholding or solver failure as a matching decision.","",
        f"The panel contains the first {n} recordings in the frozen DS30 prediction order. Panel membership is independent of completion order, timing and position error. See the [measurement protocol](PROTOCOL.md) for the worker count and timing conditions.","",
        f"Each pipeline independently read the sealed I/Q and processed {visits:,} eligible dual-antenna visits. Both used the installed regional compact v5 solver, the station profile and the same capture-era TLE archive. The only implementation change was the two-scan receiver library.","",
        "The optimized receiver reuses the list of eligible frequency bins, stores FFT coefficients in stage order, and returns the verified factors directly. It keeps both searches and the final exact-pilot versus control test.","",
        "## Runtime","",
        "| Stage | Deployed median / P90 elapsed | Optimized median / P90 elapsed | Paired median elapsed speedup | Paired median CPU speedup |",
        "|---|---:|---:|---:|---:|"]
    for stage,label in zip(STAGES,("Read, verify and detect","Position fit and diagnostic grid","Raw I/Q through position")):
        vals=lambda k:[r[k] for r in times]
        dep=vals("deployed_"+stage+"_wall_s")
        opt=vals("optimized_"+stage+"_wall_s")
        md.append(f"| {label} | {pct(dep,50):.1f} / {pct(dep,90):.1f} s | {pct(opt,50):.1f} / {pct(opt,90):.1f} s | {pct(vals(stage+'_wall_speedup'),50):.3f}× | {pct(vals(stage+'_cpu_speedup'),50):.3f}× |")
    fast=sum(r["total_wall_speedup"]>1 for r in times)
    md+=["",f"The optimized pipeline finished sooner on {fast}/{n} recordings. Speedups are calculated for each pair before taking the median. Each pair ran sequentially on one pinned core with one numerical thread. The two order groups and CPU times below help separate the receiver change from shared I/O and cache effects.","",
         "| First arm | Pairs | Median elapsed speedup | Median CPU speedup |","|---|---:|---:|---:|"]
    for first in MODES:
        x=[r for r in times if r["first"]==first]
        md.append(f"| {first.capitalize()} | {len(x)} | {pct([r['total_wall_speedup'] for r in x],50):.3f}× | {pct([r['total_cpu_speedup'] for r in x],50):.3f}× |")
    sums=[sum(r[m+"_total_cpu_s"] for r in times) for m in MODES]
    md+=["",f"Summed over the cohort, the replay workers recorded {sums[0]/3600:.2f} process CPU-hours for deployed ALGO08 and {sums[1]/3600:.2f} for the optimized build ({(sums[1]/sums[0]-1):+.1%})."]
    md+=["","![Measured runtime and paired stage speedups](runtime.png)","","## Fix rate and horizontal error","",
         "| Pipeline | Calibration | Fixes / assigned | Median error | P90 | P95 | Within 1 km / assigned | Median solver frequency RMS |",
         "|---|---|---:|---:|---:|---:|---:|---:|"]
    for m,label in zip(MODES,LABELS):
        for arm in ARMS:
            x=[r for r in pos if r["arm"]==arm and r[m+"_error_km"] is not None]
            err=[r[m+"_error_km"] for r in x]
            md.append(f"| {label} | {'Fitted' if arm=='fitted_c' else 'Zero'} | {len(x)}/{n} ({len(x)/n:.1%}) | {pct(err,50):.3f} km | {pct(err,90):.3f} km | {pct(err,95):.3f} km | {sum(e<=1 for e in err)}/{n} | {pct([r[m+'_rf_rms_hz'] for r in x],50):.2f} Hz |")
    paired_fitted=[r for r in pos if r["arm"]=="fitted_c" and r["endpoint_separation_m"] is not None]
    md+=["","Error percentiles and frequency RMS use returned fixes. For the curves, the height at 1 km is the fraction of all assigned recordings that returned a fix within 1 km. The final height is the fix rate. Where the errors coincide, the dashed optimized curve lies on the solid deployed curve.","",
         f"Among {len(paired_fitted)} common fitted fixes, the median change in error was {pct([r['optimized_minus_deployed_error_m'] for r in paired_fitted],50):+.3f} m, and the largest separation between the two published coordinates was {max((r['endpoint_separation_m'] for r in paired_fitted),default=float('nan')):.3f} m.","",
         "![Cumulative error over every assigned recording for both calibration arms](position-error.png)","","## Recording-level checks",""]
    for m,label in zip(MODES,LABELS):
        counts=Counter(r[m+"_status"] for r in times)
        md.append(f"- {label} returned {counts['ok']} fixes, withheld {counts['withheld']} and had {counts['unavailable']} solver failures.")
    fixed=[r for r in pos if r["deployed_status"]==r["optimized_status"]=="ok"]
    md+= [f"- The decisions matched on {sum(r['same_decision'] for r in times)}/{n} recordings. The complete post-history measurement streams matched on {sum(r['same_factors'] for r in times)}/{n}.",
          f"- On {len(fixed)} returned recording/calibration pairs, {sum(r['identical_position'] for r in fixed)} coordinates and {sum(r['identical_rf_rms'] for r in fixed)} solver RMS values were exactly equal. The final owner hashes agreed on {sum(r['same_owners'] for r in times if r['deployed_status']==r['optimized_status']=='ok')} common fixes.",
          f"- The freshly deployed baseline reproduced {sum(r['deployed_matches_frozen'] for r in pos)}/{len(pos)} previously published DS30 decision, coordinate and frequency-RMS rows.","",
          "DS30 measures repeated recordings at one physical station. These results do not estimate accuracy at a second location or runtime on an embedded processor. The clock covers recording read, decompression, digest checks, detection, causal selection, orbit preparation, position and its diagnostic grid. It stops before PNG encoding, web publication and scoring.","",
          "[Protocol and reproduction](PROTOCOL.md) · [Paired timings](runtime.csv) · [Positions and errors](positions.csv) · [Locked raw prediction receipts](predictions.zip) · [Receiver source](receiver-source.zip)"]
    (out/"README.md").write_text("\n".join(md)+"\n")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs",type=Path)
    parser.add_argument("output",type=Path)
    parser.add_argument("--panel",choices=PANEL_SIZES,default="smoke")
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    cohort,entries=lock_predictions(args.runs,args.output,args.panel)
    times,pos=score(cohort,entries)
    write_csv(args.output/"runtime.csv",times)
    write_csv(args.output/"positions.csv",pos)
    plots(args.output,times,pos)
    report(args.output,times,pos,args.panel)


if __name__=="__main__":
    main()
