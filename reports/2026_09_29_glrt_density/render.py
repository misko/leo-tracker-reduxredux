"""Standalone scientific figures and a local, digest-bound comparison page."""
import csv
import json
import math
import statistics
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from run import ROOT, sha, write
from evaluate import PERIOD, RF, canonical, panel, products, predict, match_tracks

ARMS=(120,10,20)
COLORS={120:"#355c9a",10:"#df7130",20:"#159580"}


def save(fig,name):
    fig.savefig(ROOT/name,dpi=150,bbox_inches="tight")
    plt.close(fig)


def main():
    plt.rcParams.update({"font.size":10,"axes.spines.top":False,"axes.spines.right":False})
    scores=json.loads((ROOT/"scores.json").read_text())
    refs=json.loads((ROOT/"references.json").read_text())
    origin=refs["origin_utc_ns"]
    allproducts={a:products(a) for a in ARMS}
    tracks={a:json.loads((ROOT/f"local/tracks-{a}-operational.json").read_text()) for a in ARMS}
    fig,axes=plt.subplots(3,1,figsize=(14,8),sharex=True,sharey=True)
    for ax,a in zip(axes,ARMS):
        for rx,color,marker in ((0,"#3583a0","o"),(1,"#c78131","x")):
            pts=[(max(q["candidates"],key=lambda c:c["fractional_margin"])["fractional_time_s"],
                  max(c["fractional_margin"] for c in q["candidates"]))
                 for p in allproducts[a] for q in p["probes"] if q["receiver_id"]==rx and q["candidates"]]
            if pts:
                x,y=zip(*pts)
                ax.scatter(x,y,s=7,alpha=.65,c=color,marker=marker,label=f"RX{rx}")
        ax.axhline(.025,color="gray",ls="--",lw=1)
        ax.set(xlim=(0,30),ylim=(-.03,1),ylabel="Winning GLRT margin",title=f"20 ms windows / {a} ms stride")
        ax.grid(alpha=.15)
        ax.legend(loc="upper right")
    axes[-1].set_xlabel("Device time since capture start (s); candidate epochs")
    fig.suptitle("Same saved IQ: denser GLRT sampling, fixed detector and thresholds",fontsize=15)
    fig.tight_layout()
    save(fig,"glrt-response.png")

    fig,axes=plt.subplots(4,3,figsize=(17,11),sharex=True,sharey=True)
    for col,a in enumerate(ARMS):
        for ch in range(1,5):
            ax=axes[ch-1,col]
            for rx,color,marker in ((0,"#9467bd","o"),(1,"#159580","x")):
                pts=[(c["fractional_time_s"],canonical(c["fractional_tracking_cfo_hz"])*RF/p["target"]["rf_center_hz"])
                    for p in allproducts[a] if p["target"]["channel"]==ch for q in p["probes"] if q["receiver_id"]==rx
                    for c in q["candidates"] if c["passed_fractional_margin_gate"]]
                if pts:
                    x,y=zip(*pts)
                    ax.scatter(x,np.asarray(y)/1000,s=3,alpha=.25,c=color,marker=marker,label=f"RX{rx}")
                for track in tracks[a]["result"]["tracklets"]:
                    if track["lane_key"][:3] != [ch,"upper",rx]:
                        continue
                    times=np.linspace(track["start_utc_ns"],track["end_utc_ns"],200)
                    period=PERIOD*RF/track["lane_key"][3]
                    values=np.array([(predict(track,t)+period/2)%period-period/2 for t in times])
                    values[np.r_[False,np.abs(np.diff(values))>period/2]]=np.nan
                    ax.plot((times-origin)/1e9,values/1000,color=color,lw=1.4)
            ax.set(xlim=(0,30),ylim=(-115,115))
            ax.grid(alpha=.15)
            if col==0:
                ax.set_ylabel(f"CH{ch}\nNormalized CFO (kHz)")
            if ch==1:
                ax.set_title(f"{a} ms stride; {len(tracks[a]['result']['tracklets'])} lane tracklets")
                ax.legend(loc="upper right")
            if ch==4:
                ax.set_xlabel("Device time (s)")
    fig.suptitle("All passing candidates and unchanged production tracklets\nCanonical alias interval, normalized to 11.2 GHz; lines are candidate associations, not satellite identities",fontsize=14)
    fig.tight_layout()
    save(fig,"cfo-tracks.png")

    common=[r for r in scores["ledger"] if all(r["predictions"].get(str(a),{}).get("reason")=="scored" for a in ARMS)]
    fig,axes=plt.subplots(1,2,figsize=(13,4.5))
    for a,marker in zip(ARMS,("o","x","+")):
        s=scores["summary"][str(a)]
        axes[0].scatter([r["time_s"] for r in common],
            [r["predictions"][str(a)]["error_hz"] for r in common],
            color=COLORS[a],marker=marker,label=f"{a} ms: {s['common_rms_hz']:.1f} Hz" if s["common_rms_hz"] is not None else f"{a} ms: no common support",s=35)
    axes[0].axhline(0,color="gray",lw=1)
    axes[0].set(xlabel="Held-out device time (s)",ylabel="Measured − predicted CFO (Hz)",title=f"Same {len(common)} references; no held-out refit")
    axes[0].legend()
    for x,a in enumerate(ARMS):
        s=scores["summary"][str(a)]
        axes[1].bar(x,s["available"],color=COLORS[a])
        axes[1].text(x,s["available"]+.5,f"{s['available']}/{s['eligible_references']}",ha="center")
    eligible=scores["summary"]["120"]["eligible_references"]
    axes[1].set(xticks=range(3),xticklabels=[f"{a} ms" for a in ARMS],ylim=(0,max(1,eligible)*1.15),
                ylabel="Eligible references with an unambiguous prediction",title="Availability uses the full frozen denominator")
    fig.suptitle("Training-only lane matches; alias-conditional prediction error, not absolute Doppler accuracy")
    fig.tight_layout()
    save(fig,"heldout-rms.png")

    rows=[]
    for a in ARMS:
        t=tracks[a]
        tt=t["result"]["tracklets"]
        rows.append(dict(stride_ms=a,scheduled_rx_probes=t["input_probes"],
            passed_candidates_before_overlap_filter=sum(c["passed_fractional_margin_gate"] for p in allproducts[a] for q in p["probes"] for c in q["candidates"]),
            projected_candidates=t["projected_candidates"],lane_tracklets=len(tt),
            physical_groups=len(t["result"]["physical_groups"]),
            median_span_s=statistics.median((x["end_utc_ns"]-x["start_utc_ns"])/1e9 for x in tt) if tt else None,
            median_operational_fit_rms_hz=statistics.median(x["residual_rms_hz"] for x in tt) if tt else None,
            **scores["summary"][str(a)]))
    write(ROOT/"summary.json",dict(arms=rows,scope="First 30 seconds, 221 actual 120 ms visits, one development scan",
        heldout_reference_reasons=dict(Counter(r["reason"] for r in refs["rows"])),
        scoring_ledger_reasons=dict(Counter(r["reason"] for r in scores["ledger"])),
        prediction_reasons={a:dict(Counter(r["predictions"].get(str(a),{}).get("reason","not-assigned") for r in scores["ledger"])) for a in ARMS}))
    correspondence=dict(training=scores["matches"],operational={a:match_tracks(tracks[120]["result"]["tracklets"],tracks[a]["result"]["tracklets"]) for a in (10,20)})
    write(ROOT/"track-correspondence.json",correspondence)
    equivalence={}
    for partition in ("operational","training"):
        left=json.loads((ROOT/f"local/tracks-10-{partition}.json").read_text())["result"]["tracklets"]
        right=json.loads((ROOT/f"local/tracks-20-{partition}.json").read_text())["result"]["tracklets"]
        def numeric(t):
            return tuple(t["lane_key"]),t["start_utc_ns"],t["end_utc_ns"],t["normalized_rate_hz_per_s"],t["normalized_intercept_hz"],t["residual_rms_hz"],len(t["points"])
        aa,bb=sorted(map(numeric,left)),sorted(map(numeric,right))
        equivalence[partition]=dict(track_counts=[len(aa),len(bb)],
            numeric_track_values_exactly_equal=aa==bb,
            note="Provenance identifiers intentionally differ by arm; no claim of identical serialized products.")
        if len(aa)==len(bb) and all(a[:3]==b[:3] and a[-1]==b[-1] for a,b in zip(aa,bb)):
            equivalence[partition]["max_rate_difference_hz_per_s"]=max(abs(a[3]-b[3]) for a,b in zip(aa,bb)) if aa else 0
            equivalence[partition]["max_intercept_difference_hz"]=max(abs(a[4]-b[4]) for a,b in zip(aa,bb)) if aa else 0
            equivalence[partition]["max_fit_rms_difference_hz"]=max(abs(a[5]-b[5]) for a,b in zip(aa,bb)) if aa else 0
    write(ROOT/"dense-control-equivalence.json",equivalence)
    with (ROOT/"per-track-rms.csv").open("w") as f:
        writer=csv.DictWriter(f,fieldnames=["stride_ms","baseline_track_index","count","rms_hz"])
        writer.writeheader()
        for a in ARMS:
            writer.writerows(dict(stride_ms=a,**r) for r in scores["summary"][str(a)]["per_track"])

    timings=[json.loads(p.read_text()) for p in (ROOT/"local/timing").glob("*.json")]
    wall=sum(t["wall_seconds"] for t in timings)
    cpu=sum(t["cpu_seconds"] for t in timings)
    fit_seconds=sum(json.loads(p.read_text())["fitting_seconds"] for p in (ROOT/"local").glob("tracks-*.json"))
    runtime=dict(dense_measured_wall_seconds=wall,dense_cpu_seconds=cpu,
        dense_max_rss_kib=max(t["max_rss_kib"] for t in timings),all_fit_seconds=fit_seconds,
        measured_dense_visits=len(list((ROOT/"local/dense").glob("*.json"))),
        projected_full_scan_dense_wall_minutes=wall/len(panel())*2216/60,
        projected_eight_similar_scans_dense_hours=wall/len(panel())*2216*8/3600,
        saved_iq_payload_bytes=len(panel())*600000*2*8,
        dense_output_bytes=sum(p.stat().st_size for p in (ROOT/"local/dense").glob("*.json")),
        note="Projected replay costs assume this excerpt's workload; storage cache and signal complexity can change them. Payload bytes are logical complex64 samples, not measured physical disk traffic. Control derived from verified dense subset.")
    write(ROOT/"runtime.json",runtime)
    artifacts=[]
    for name in ("glrt-response.png","cfo-tracks.png","heldout-rms.png"):
        payload=(ROOT/name).read_bytes()
        assert payload.startswith(b"\x89PNG\r\n\x1a\n")
        artifacts.append(dict(name=name,bytes=len(payload),sha256=sha(payload)))
    write(ROOT/"artifact-manifest.json",dict(artifacts=artifacts,
        specification_sha256=sha((ROOT/"spec.json").read_bytes()),
        amendment_sha256=sha((ROOT/"protocol-amendment.md").read_bytes()),
        reference_sha256=sha((ROOT/"references.json").read_bytes())))
    body="".join(f'<h2>{a["name"]}</h2><img src="{a["name"]}" style="max-width:100%">' for a in artifacts)
    (ROOT/"comparison.html").write_text('<!doctype html><meta charset="utf-8"><title>GLRT density pilot</title><main style="max-width:1600px;margin:40px auto;font:16px system-ui"><h1>GLRT density pilot — first 30 seconds</h1><p>Research comparison, not a production analysis product. All windows are 20 ms. Held-out errors are alias-conditional CFO prediction errors; no satellite identity or absolute Doppler accuracy is claimed.</p>'+body+'<p>See README.md, scores.json and runtime.json for exclusions, coverage, and cost.</p></main>')
    print(json.dumps(dict(rows=rows,runtime=runtime)),flush=True)


if __name__ == "__main__":
    main()
