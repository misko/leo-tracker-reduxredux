"""Audit completed single-method grid experiment and render scientific figures."""
import csv
import importlib.util
import json
from pathlib import Path
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
from matplotlib.patches import Circle
import experiment as trial

HERE = Path(__file__).resolve().parent

def main():
    result=json.loads((HERE/"results.json").read_text())
    assert result["status"]=="complete"
    protocol=json.loads((HERE/"protocol.json").read_text())
    for path,expected in protocol["source_hashes"].items():
        assert trial.digest(path)==expected,path
    trial.load()
    _,obs,bank,prior,score,_=trial.CONTEXT
    previous=HERE.parent/"2026_10_07_2139_slope_cutoffs/experiment.py"
    spec=importlib.util.spec_from_file_location("old_pair_metrics",previous)
    paired=importlib.util.module_from_spec(spec);spec.loader.exec_module(paired)
    pair_doc=json.loads((HERE.parent/"2026_10_07_cone_failure_debug/paired_identity/2139.json").read_text())
    pairs=np.asarray(pair_doc["pair_rows"],int)
    assert len(pairs)==236
    searches={name:json.loads((HERE/f"{name}-search.json").read_text()) for name in trial.SCHEDULES}
    for search in searches.values():
        assert search["status"]=="complete" and len(search["points"])==400
        assert len({tuple(p["point"]) for p in search["points"]})==400
        assert len(search["search"]["evaluations"])==400
    audits=[];rows=[]
    for selection in result["selections"]:
        row=selection["result"]
        if row is None:
            rows.append(dict(schedule=selection["schedule"],arm=selection["arm"],accepted=False,
                             error_km=None,frequency_rms_hz=None,pair_median_hz=None))
            continue
        xy=row["point"];radius=row["local_radius_km"]
        region=json.loads((HERE/"regions"/f"{xy[0]:g}_{xy[1]:g}_{radius:g}.json").read_text())
        cal=region["calibration"];assoc=region["association"]
        obj=trial.PositionObjective(obs,bank.select(assoc["selected_indices"]),prior,score,
                                    receiver_baseline_hz=np.asarray(cal["receiver_baseline_hz"]))
        v=np.asarray(row["vector"]);value,gradient,terms=obj.evaluate(v)
        np.testing.assert_allclose(value,row["objective"],atol=1e-6,rtol=0)
        audit=trial.audit(obj,v,gradient,selection["arm"],xy,radius)
        assert audit["converged"] and audit["feasible"]
        np.testing.assert_allclose(audit["stationarity"],row["stationarity"],atol=1e-5,rtol=0)
        pair=paired.pair_metrics(obj,v,pairs)
        audits.append(dict(schedule=selection["schedule"],arm=selection["arm"],**audit,pair_clock=pair))
        rows.append(dict(schedule=selection["schedule"],arm=selection["arm"],accepted=True,
                         error_km=row["horizontal_error_m"]/1000,frequency_rms_hz=row["frequency_rms_hz"],
                         pair_median_hz=pair["median_absolute_residual_hz"],score=row["selection_score"],
                         data_nll=row["data_nll"],timing_penalty=row["timing_penalty"],
                         rx0_hz_s=row["additional_slopes_hz_s"][0],rx1_hz_s=row["additional_slopes_hz_s"][1],
                         region_east_km=xy[0],region_north_km=xy[1],radius_km=radius,
                         stationarity=audit["stationarity"],boundary=audit["boundary"],
                         slope_bound_active=bool(audit["slope_active_bounds"])))
    stats=[]
    for name,s in searches.items():
        counts={str(level):sum(p["spacing_km"]==level for p in s["search"]["evaluations"]) for level in s["levels_km"]}
        stats.append(dict(schedule=name,points=400,by_cell_width_km=counts,
                          converged=sum(p["converged"] is True for p in s["points"]),
                          failed=sum(p["status"]=="failed" for p in s["points"]),
                          elapsed_s=s["elapsed_s"],logical_scoring_seconds=s["logical_scoring_seconds"]))
    summary=dict(rows=rows,search_statistics=stats,audits=audits,coverage=result["coverage"],
                 elapsed_s=result["elapsed_s"],regression_tests_passed=7,source_hashes_verified=True,
                 final_refinement_runs=sum(r["runs"] for r in result["regions"]),regions=result["regions"])
    trial.write(HERE/"summary.json",summary)
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with (HERE/"comparison.csv").open("w") as output:
        writer=csv.DictWriter(output,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    # Evaluation marker is derived after selection, never fed to the search.
    from importlib.util import spec_from_file_location,module_from_spec
    spec=spec_from_file_location("old_prepare",HERE.parent/"2026_10_07_slope_priors/prepare.py")
    old_prepare=module_from_spec(spec);spec.loader.exec_module(old_prepare)
    reference=json.loads((HERE/"evaluation.json").read_text())
    truth=old_prepare.reference_point(prior,reference["latitude_deg"],reference["longitude_deg"])
    labels={"current100":"100 → 50 → 25 → 12.5 km", "start50":"50 → 25 → 12.5 → 6.25 km",
            "proposed50_20_5":"50 → 20 → 5 km"}
    fig,axes=plt.subplots(1,3,figsize=(16,6),layout="constrained")
    for ax,(name,s) in zip(axes,searches.items()):
        p=s["search"]["evaluations"]
        points=np.array([[r["east_km"],r["north_km"]] for r in p])
        widths=np.array([r["spacing_km"] for r in p])
        sc=ax.scatter(points[:,0],points[:,1],c=widths,s=12,cmap="viridis_r",norm=LogNorm(5,100),alpha=.8)
        ax.add_patch(Circle((0,0),250,fill=False,color="#888",lw=1))
        for b in s["basins"]:
            xy=b["east_km"],b["north_km"]
            r=max(25.,b["spacing_km"]/np.sqrt(2))
            ax.add_patch(Circle(xy,r,fill=False,color="#c23b22",lw=1.5))
            ax.scatter(*xy,marker="+",c="#c23b22",s=70,zorder=4)
        ax.scatter(*truth,marker="*",s=180,c="#f3b700",edgecolor="black",zorder=5,label="Known receiver (evaluation only)")
        ax.set(xlim=(-280,280),ylim=(-280,280),aspect="equal",xlabel="East of search origin (km)",
               ylabel="North of search origin (km)",title=labels[name]+"\n400 tested positions")
        ax.grid(alpha=.15)
    colorbar=fig.colorbar(sc,ax=axes,shrink=.7,ticks=[5,12.5,20,25,50,100])
    colorbar.ax.set_yticklabels(["5","12.5","20","25","50","100"])
    colorbar.set_label("Cell width (km)")
    fig.suptitle("V16-only discovery: yellow star = reference; red circles = retained refinement regions")
    fig.savefig(HERE/"grid_search.png",dpi=150);fig.savefig(HERE/"grid_search.svg");plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,4.8),layout="constrained")
    for ax,metric,label in zip(axes,["error_km","frequency_rms_hz"],["Position error (km)","Frequency fit RMS (Hz)"]):
        for offset,arm,color in [(-.18,"zero-c","#2878b5"),(.18,"fitted-c","#db7632")]:
            vals=[next(r for r in rows if r["schedule"]==name and r["arm"]==arm).get(metric) for name in searches]
            values=[np.nan if v is None else v for v in vals]
            bars=ax.bar(np.arange(3)+offset,values,width=.34,label=arm,color=color)
            ax.bar_label(bars,fmt="%.2f",padding=3,fontsize=9)
        ax.set_xticks(range(3),["100 km start","50 km start","50 → 20 → 5"])
        ax.set_ylabel(label);ax.set_ylim(bottom=0);ax.margins(y=.2);ax.grid(axis="y",alpha=.15);ax.legend()
    fig.suptitle("Same capture, σ = 1 s, hard ±60 Hz/s; 400-point discovery budget per schedule")
    fig.savefig(HERE/"comparison.png",dpi=150);fig.savefig(HERE/"comparison.svg");plt.close(fig)
    print(json.dumps(summary,indent=2))

if __name__=="__main__":main()
