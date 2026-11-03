"""Figures for the frozen 64-scan evaluation; no receipt mutation."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from evaluate import (ARMS, REFERENCE_LATLON, SACRAMENTO_CENTER_LATLON,
                      ecdf_with_failures, enu_from_latlon)


COLORS = {"gaussian_sum":"tab:blue", "greedy":"tab:orange", "prior_only":"0.35"}
LABELS = {"gaussian_sum":"Gaussian sum", "greedy":"Greedy", "prior_only":"Prior center"}


def spatial_mixture_relative_density(components: list[dict], east: np.ndarray, north: np.ndarray) -> np.ndarray:
    """Evaluate a sealed receipt's weighted 2-D location marginal, scaled to its peak."""
    density=np.zeros_like(east,dtype=float)
    for component in components:
        mean=np.asarray(component["mean_en_km"],dtype=float)
        covariance=np.asarray(component["covariance_en_km2"],dtype=float)
        delta=np.stack((east-mean[0],north-mean[1]),axis=-1)
        precision=np.linalg.inv(covariance)
        exponent=np.einsum("...i,ij,...j->...",delta,precision,delta)
        density += float(component["weight"])*np.exp(-.5*exponent)/(2*np.pi*np.sqrt(np.linalg.det(covariance)))
    maximum=float(density.max())
    return density/maximum if maximum > 0 else density


def generate_summary_figures(evaluation: dict, output: Path) -> list[Path]:
    output.mkdir(parents=True, exist_ok=True)
    rows = evaluation["rows"]
    paths=[]

    fig, axes = plt.subplots(1, 3, figsize=(13, 4), constrained_layout=True, sharey=True)
    for axis,dataset in zip(axes,("DS9","DS10","DS11"),strict=True):
        denominator={"DS9":22,"DS10":21,"DS11":21}[dataset]
        for arm in ARMS:
            subset=[r for r in rows if r["dataset"]==dataset and r["arm"]==arm]
            x,y=ecdf_with_failures(subset,denominator)
            label=f"{LABELS[arm]} ({x.size}/{denominator})"
            if x.size:
                axis.step(x,y,where="post",label=label,color=COLORS[arm],marker="o",markersize=3)
            else:
                axis.plot([],[],label=label,color=COLORS[arm])
        axis.axvline(1.,color="tab:red",linestyle="--",linewidth=1)
        axis.set(title=dataset,xlabel="roof-reference error (km)",xscale="log",ylim=(0,1.02))
        axis.legend(fontsize="x-small")
    axes[0].set_ylabel("fraction of all planned scans")
    fig.suptitle("Failure-aware error ECDF; curves stop below 1 when scans fail")
    path=output/"error-ecdf-all-planned.png"; fig.savefig(path,dpi=160); plt.close(fig); paths.append(path)

    complete=[r for r in rows if r["completed"] and r["arm"] in ("gaussian_sum","greedy")]
    fig,axis=plt.subplots(figsize=(8,5),constrained_layout=True)
    positions={"DS9":0,"DS10":1,"DS11":2}
    for arm,offset in (("gaussian_sum",-.12),("greedy",.12)):
        subset=[r for r in complete if r["arm"]==arm]
        x=np.array([positions[r["dataset"]]+offset for r in subset])
        axis.scatter(x,[r["error_km"] for r in subset],alpha=.7,s=24,label=LABELS[arm],color=COLORS[arm])
    if evaluation["prior_center_error_km"] is not None:
        axis.axhline(evaluation["prior_center_error_km"],color=COLORS["prior_only"],linestyle="--",
                     label=f"prior center {evaluation['prior_center_error_km']:.1f} km")
    axis.axhline(1.,color="tab:red",linestyle=":",label="1 km")
    axis.set(xticks=[0,1,2],xticklabels=["DS9","DS10","DS11"],ylabel="roof-reference error (km)",yscale="log",
             title="Completed fits only; failures remain in ECDF denominator")
    axis.legend()
    path=output/"completed-errors-vs-prior.png"; fig.savefig(path,dpi=160); plt.close(fig); paths.append(path)

    dynamic=[r for r in rows if r["arm"] in ("gaussian_sum","greedy") and r["attempted"]]
    fig,(mass,runtime)=plt.subplots(1,2,figsize=(11,4.5),constrained_layout=True)
    for arm in ("gaussian_sum","greedy"):
        subset=[r for r in dynamic if r["arm"]==arm]
        mass.scatter([r["consumed_fraction"] for r in subset],
                     [max(r["max_discarded_mass"] or 1e-16,1e-16) for r in subset],
                     alpha=.65,label=LABELS[arm],color=COLORS[arm])
        runtime.scatter([r["consumed_fraction"] for r in subset],[r["runtime_s"] for r in subset],
                        alpha=.65,label=LABELS[arm],color=COLORS[arm])
    mass.axhline(.01,color="tab:red",linestyle="--",label="1% Gaussian-sum-only gate")
    mass.set(xlabel="consumed fraction of planned factors",ylabel="maximum discarded mass",yscale="log")
    runtime.set(xlabel="consumed fraction of planned factors",ylabel="end-to-end launcher runtime (s)")
    mass.legend(); runtime.legend(); fig.suptitle("Bounded-work outcomes for every attempted dynamic arm")
    path=output/"mass-gate-and-runtime.png"; fig.savefig(path,dpi=160); plt.close(fig); paths.append(path)

    fig,axes=plt.subplots(1,3,figsize=(12,4),constrained_layout=True,sharey=True)
    for axis,dataset in zip(axes,("DS9","DS10","DS11"),strict=True):
        subset=[r for r in rows if r["dataset"]==dataset]
        complete=[sum(r["arm"]==arm and r["completed"] for r in subset) for arm in ARMS]
        attempted_failure=[sum(r["arm"]==arm and r["attempted"] and not r["completed"] for r in subset) for arm in ARMS]
        missing=[sum(r["arm"]==arm and not r["attempted"] for r in subset) for arm in ARMS]
        x=np.arange(3)
        axis.bar(x,complete,color="tab:green",label="complete")
        axis.bar(x,attempted_failure,bottom=complete,color="tab:red",label="attempted, not accepted")
        axis.bar(x,missing,bottom=np.add(complete,attempted_failure),color="0.8",label="not attempted")
        axis.set(title=dataset,xticks=x,xticklabels=["GSF","greedy","prior"],ylim=(0,max(22,len(subset)//3)+.5))
        for i,value in enumerate(complete):
            axis.text(i,.3 if value == 0 else value-.7,str(value),ha="center",va="bottom",
                      fontsize="small",color="black" if value == 0 else "white")
    axes[0].set_ylabel("planned scans")
    handles,legend_labels=axes[-1].get_legend_handles_labels()
    fig.legend(handles,legend_labels,fontsize="x-small",loc="upper center",ncol=3,bbox_to_anchor=(.5,1.01))
    fig.suptitle("Completion status for every arm and dataset",y=1.08)
    path=output/"completion-status-by-dataset.png"; fig.savefig(path,dpi=160,bbox_inches="tight"); plt.close(fig); paths.append(path)

    context=evaluation.get("historical_pipeline_context")
    if context:
        historical=context["rows"]
        fig,(counts,errors)=plt.subplots(1,2,figsize=(11,4.5),constrained_layout=True)
        gsf=[r for r in rows if r["arm"]=="gaussian_sum"]
        counts.bar([0,1],[sum(r["completed"] for r in gsf),sum(r["status"]=="complete" for r in historical)],
                   color=[COLORS["gaussian_sum"],"tab:green"],label="complete / accepted")
        counts.bar([0,1],[64-sum(r["completed"] for r in gsf),64-sum(r["status"]=="complete" for r in historical)],
                   bottom=[sum(r["completed"] for r in gsf),sum(r["status"]=="complete" for r in historical)],
                   color="0.75",label="failed or incomplete")
        counts.set(xticks=[0,1],xticklabels=["Gaussian sum\n(new panel)","Published Sacramento\n(historical)"],
                   ylabel="scans (of 64)",title="Completion accounting")
        counts.legend(fontsize="small")
        gsf_errors=[r["error_km"] for r in gsf if r["completed"] and r["error_km"] is not None]
        historical_errors=[r["error_km"] for r in historical if r.get("error_km") is not None]
        values=[v for v in (gsf_errors,historical_errors) if v]
        labels=[label for label,v in zip(("Gaussian sum accepted","Historical selected\n(incomplete searches)"),
                                         (gsf_errors,historical_errors)) if v]
        if values:
            errors.boxplot(values,showfliers=True)
            errors.set_xticks(range(1,len(labels)+1),labels)
            errors.set_yscale("log")
        errors.axhline(1.,color="tab:red",linestyle=":")
        errors.set(ylabel="roof-reference error (km)",title="Point errors; unmatched diagnostic")
        fig.suptitle("Published pipeline context uses different tracks, objective, and 400-point budget")
        path=output/"historical-pipeline-context.png"; fig.savefig(path,dpi=160); plt.close(fig); paths.append(path)

    # The first selected scan in each dataset is fixed by selection order, never by result quality.
    examples=[]
    for dataset in ("DS9","DS10","DS11"):
        candidates=[r for r in rows if r["dataset"]==dataset and r["arm"]=="gaussian_sum"]
        if candidates and candidates[0].get("spatial_components"):
            examples.append(candidates[0])
    if examples:
        fig,axes=plt.subplots(1,len(examples),figsize=(4.5*len(examples),4.3),constrained_layout=True,
                              squeeze=False)
        coordinates=np.linspace(-300,300,181)
        east,north=np.meshgrid(coordinates,coordinates)
        reference_east,reference_north=enu_from_latlon(SACRAMENTO_CENTER_LATLON,REFERENCE_LATLON)
        filled=None
        for axis,row in zip(axes[0],examples,strict=True):
            relative=spatial_mixture_relative_density(row["spatial_components"],east,north)
            filled=axis.contourf(east,north,np.log10(np.maximum(relative,1e-6)),levels=np.linspace(-6,0,25),cmap="viridis")
            axis.add_patch(plt.Circle((0,0),250,fill=False,color="white",linewidth=1.2,label="intended 250 km disk"))
            axis.scatter(0,0,marker="+",s=80,color="white",label="Sacramento center")
            axis.scatter(reference_east,reference_north,marker="*",s=90,color="tab:red",label="roof reference")
            qualifier="accepted" if row["completed"] else "diagnostic only"
            axis.set(title=f"{row['unit_id']}\n{row['status']} ({qualifier})",xlabel="east from Sacramento (km)",
                     ylabel="north from Sacramento (km)",aspect="equal",xlim=(-300,300),ylim=(-300,300))
        handles,legend_labels=axes[0,0].get_legend_handles_labels()
        fig.legend(handles,legend_labels,fontsize="x-small",loc="lower center",ncol=3,
                   bbox_to_anchor=(.45,-.12),facecolor="0.25",labelcolor="white",framealpha=1.)
        fig.colorbar(filled,ax=axes[0].tolist(),label="log10 density / mixture peak",shrink=.82,pad=.02)
        fig.suptitle("Predeclared first scan: log10 density relative to each mixture peak")
        path=output/"chronological-first-scan-density.png"; fig.savefig(path,dpi=160,bbox_inches="tight"); plt.close(fig); paths.append(path)
    return paths


if __name__ == "__main__":
    here=Path(__file__).resolve().parent
    document=json.loads((here/"evaluation.json").read_text())
    for path in generate_summary_figures(document,here/"figures"):
        print(path)
