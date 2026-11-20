"""Plot search-origin sensitivity and geographic error distributions."""

import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parent
COLORS={"geometry12":"#b24420","full":"#2c4057","coordinate_network":"#837133",
        "shape_grid":"#067f87","refined_shape":"#3156a5","prior_center":"#606870"}
LABELS={"geometry12":"12 tracks by geometry","full":"Full track set","coordinate_network":"Coordinate network",
        "shape_grid":"Coarse shape grid","refined_shape":"Refined shape grid","prior_center":"Prior center"}


def main():
    report=json.loads((ROOT/"summary.json").read_bytes())
    with (ROOT/"geographic-scores.csv").open() as f:
        scores=[r for r in csv.DictReader(f) if r["scenario"]=="new_regions_and_offsets"
                and r["orbit"]=="later" and r["arm"]=="fitted_c"]
    fig,(left,right)=plt.subplots(1,2,figsize=(11.5,5.1))
    fig.subplots_adjust(left=.086,right=.98,bottom=.25,top=.76,wspace=.30)
    for m,offset,symbol in (("geometry12",-.16,"o"),("full",0,"s"),("coordinate_network",.16,"^")):
        values=report["real"]["methods"][m]["fitted_c"]["per_case_near_spread"]
        left.scatter(np.arange(len(values))+offset,[d["km"] for d in values],
                     color=COLORS[m],label=LABELS[m],marker=symbol,s=37,zorder=3)
    left.set_xticks(np.arange(len(values)),[d["case"][-4:] for d in values],fontsize=8.5)
    left.set(ylabel="Maximum separation of fixes (km)",xlabel="DS26 scan",
             ylim=(-.6,17),yticks=[0,4,8,12,16])
    left.set_title("Same recording, five overlapping priors",loc="left",weight="bold",fontsize=12)
    for m,style in (("shape_grid","--"),("refined_shape","-"),("coordinate_network","-."),("geometry12","-"),("prior_center",":")):
        mask=[r for r in scores if r["method"]==m]
        values=sorted(float(r["error_km"]) for r in mask if r["error_km"])
        right.step([0]+values+[16],[0]+list(100*np.arange(1,len(values)+1)/len(mask))+[100*len(values)/len(mask)],
                   where="post",color=COLORS[m],linestyle=style,linewidth=1.8,label=LABELS[m])
    right.set(xlim=(0,15.5),ylim=(-2,102),xlabel="Allowed position error (km)",ylabel="Positions within error (%)",
              xticks=[0,3,6,9,12,15],yticks=[0,25,50,75,100])
    right.set_title("32 virtual positions in four new regions",loc="left",weight="bold",fontsize=12)
    for ax in (left,right):
        ax.spines[["top","right"]].set_visible(False)
        ax.grid(axis="y",alpha=.18)
        ax.legend(loc="upper left",bbox_to_anchor=(-.04,-.21),ncol=2,fontsize=8,frameon=False)
    fig.text(.055,.94,"How much does the location prior decide?",fontsize=19,weight="bold",color="#142c37")
    fig.text(.055,.87,"Recorded signals on the left. Simulated signals from updated orbit elements on the right. Both use a 25 km search box.",
             fontsize=10,color="#354850")
    fig.savefig(ROOT/"location-transfer.png",dpi=160,facecolor="white")
    plt.close(fig)


if __name__=="__main__":
    main()
