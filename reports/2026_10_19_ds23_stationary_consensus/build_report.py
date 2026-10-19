"""Regenerate evaluation-only stationary consensus visualizations."""

import csv
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parent


def run():
    evidence=json.loads((ROOT/"evidence/report_evidence.json").read_text());rows=evidence["rows"]
    figures=ROOT/"figures";figures.mkdir(exist_ok=True)
    fig,axes=plt.subplots(2,1,figsize=(14,8),sharex=True,constrained_layout=True)
    for arm,ax in zip(("c0","fitted_c"),axes,strict=True):
        good=[r for r in rows if r["RF_update"]];x=[r["index"] for r in good]
        ax.scatter(x,[r[arm]["independent_error_km"] for r in good],s=10,alpha=.4,label="Independent ALGO02 RF")
        ax.plot(x,[r[arm]["mean"]["error_km"] for r in good],color="#b43a29",lw=2,label="Causal mean · stationary assumption")
        ax.plot(x,[r[arm]["spatial_median"]["error_km"] for r in good],color="#487951",lw=1.2,label="Causal spatial median · control")
        ax.axhline(.5,color="black",ls="--",lw=1,label="0.5 km goal")
        ax.set(title=arm+" · same 404 fresh RF scans; no warm-up excluded",ylabel="Position error (km)",yscale="log",ylim=(.04,25))
        ax.grid(alpha=.2);ax.legend(fontsize=8,ncol=2)
    axes[-1].set_xlabel("DS23 chronological recording index")
    fig.suptitle("Conditional multi-scan improvement; no reference coordinate enters fusion")
    fig.savefig(figures/"causal_errors.png",dpi=155);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(13,6),constrained_layout=True)
    good=[r for r in rows if r["RF_update"]];arm="c0"
    original=np.array([r[arm]["independent_east_north_km"] for r in good]);path=np.array([r[arm]["mean"]["east_north_km"] for r in good])
    axes[0].scatter(original[:,0],original[:,1],s=12,alpha=.25,label="Independent RF fixes")
    axes[0].plot(path[:,0],path[:,1],color="#b43a29",lw=1.5,label="Causal mean path")
    axes[0].scatter(*path[-1],s=70,marker="x",color="#b43a29",label="Last causal mean")
    reference=np.array([(-122.48574968092912+122.545)*111.32*np.cos(np.deg2rad(37.906)),(37.849061591561885-37.906)*111.])
    axes[0].scatter(*reference,marker="*",s=130,color="black",label="Evaluation reference only")
    axes[0].set(xlabel="East from original regional center (km)",ylabel="North from original regional center (km)",title="c0 · position estimates in the original 25 km region",aspect="equal")
    axes[0].grid(alpha=.2);axes[0].legend(fontsize=8)
    axes[1].plot([r["index"] for r in rows],[r[arm]["mean"]["contributing_RF_scans"] for r in rows],color="#b43a29")
    axes[1].set(xlabel="DS23 chronological recording index",ylabel="Eligible RF positions used",title="History grows only from qualified earlier data")
    axes[1].grid(alpha=.2)
    fig.savefig(figures/"position_paths.png",dpi=155);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(13,5),constrained_layout=True)
    for arm,ax in zip(("c0","fitted_c"),axes,strict=True):
        groups=evidence["quartiles"]["results"][arm];x=np.arange(4)
        for offset,key,label,color in [(-.2,"independent_ALGO02_RF","Independent ALGO02","#629ec2"),(.2,"causal_over_block","Causal mean with history reset","#b43a29")]:
            ax.bar(x+offset,[groups["chronological_quartile_"+str(k)][key]["mean_km"] for k in range(4)],width=.38,label=label,color=color)
            ax.scatter(x+offset,[groups["chronological_quartile_"+str(k)][key]["median_km"] for k in range(4)],marker="_",s=180,color="black")
        ax.axhline(.5,color="black",ls="--",lw=1)
        ax.set(xticks=x,xticklabels=["Block 1","Block 2","Block 3","Block 4"],ylabel="Position error (km)",title=arm+" · bars: mean; black ticks: median")
        ax.grid(axis="y",alpha=.2);ax.legend(fontsize=8)
    fig.suptitle("Four separate cold-start histories · same-site temporal check")
    fig.savefig(figures/"reset_blocks.png",dpi=155);plt.close(fig)
    with (ROOT/"per_scan_errors.csv").open("w",newline="") as stream:
        writer=csv.writer(stream,lineterminator="\n");writer.writerow(["case","fresh_RF_update","arm","independent_error_km","causal_mean_error_km","causal_spatial_median_error_km","contributing_RF_scans"])
        for r in rows:
            for a in ("c0","fitted_c"):
                q=r[a];writer.writerow([r["case"],r["RF_update"],a,q["independent_error_km"],q["mean"]["error_km"],q["spatial_median"]["error_km"],q["mean"]["contributing_RF_scans"]])


if __name__=="__main__":run()
