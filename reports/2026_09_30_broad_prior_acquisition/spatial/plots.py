"""Static figures from the sealed corrected max512 conditional pilot."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from matplotlib.patches import Wedge
import numpy as np

HERE = Path(__file__).resolve().parent
RECEIPT = Path.home() / ".cache/leo/research/broad_prior_acquisition/spatial/DS9-F001-fixed_zero-development512-tracks8.json"


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_sealed(path: Path) -> dict:
    seal = json.loads(path.with_suffix(".seal.json").read_text())
    if seal.get("prediction_sha256") != digest(path):
        raise ValueError("corrected512 receipt seal mismatch")
    document = json.loads(path.read_text())
    if document.get("profile") != "development512" or document.get("status") != "spatial_convergence_unresolved":
        raise ValueError("unexpected spatial pilot identity or status")
    return document


def generate(document: dict, output: Path = HERE) -> list[Path]:
    cells = document["cells"]
    density = np.array([
        sum(cell["joint_mass"]) /
        (0.5 * (cell["radius_squared_max"] - cell["radius_squared_min"])
         * (cell["angle_max_rad"] - cell["angle_min_rad"]))
        for cell in cells
    ])
    log_relative = np.log10(np.maximum(density / density.max(), 1e-8))
    normalization = Normalize(-8, 0)
    cmap = plt.get_cmap("viridis")
    fig, axis = plt.subplots(figsize=(7.5, 6.5), constrained_layout=True)
    for cell, value in zip(cells, log_relative, strict=True):
        inner = np.sqrt(cell["radius_squared_min"])
        outer = np.sqrt(cell["radius_squared_max"])
        # Wedge angles are counterclockwise from east; map angle is clockwise from north.
        theta1 = 90 - np.degrees(cell["angle_max_rad"])
        theta2 = 90 - np.degrees(cell["angle_min_rad"])
        axis.add_patch(Wedge((0, 0), outer, theta1, theta2, width=outer-inner,
                             facecolor=cmap(normalization(value)), edgecolor="none"))
    axis.add_patch(plt.Circle((0, 0), 250, fill=False, color="white", linewidth=1.2))
    axis.scatter(0, 0, marker="+", color="white", s=80, label="Sacramento prior center")
    axis.set(xlim=(-255,255),ylim=(-255,255),aspect="equal",xlabel="east from Sacramento (km)",
             ylabel="north from Sacramento (km)",
             title="DS9-F001 posterior mass density\nfixed-nuisance conditional diagnostic; spatially unresolved")
    axis.legend(loc="lower left",fontsize="small")
    scalar=plt.cm.ScalarMappable(norm=normalization,cmap=cmap)
    fig.colorbar(scalar,ax=axis,label="log10 mass density / peak")
    map_path=output/"corrected512-conditional-spatial-mass.png"
    fig.savefig(map_path,dpi=180); plt.close(fig)

    tracks=document["tracks"]
    x=np.arange(1,len(tracks)+1)
    errors=np.array([row["quadrature_log_evidence_error"] for row in tracks])
    ranges=np.array([row["max_log_likelihood_range"] for row in tracks])
    cell_counts=np.array([row["cells"] for row in tracks])
    fig,(audit,variation)=plt.subplots(2,1,figsize=(9,7),sharex=True,constrained_layout=True)
    audit.plot(x,errors,marker="o",label="same-leaf |q2 − q3| log evidence")
    audit.axhline(document["quadrature_log_evidence_tolerance"],color="tab:red",linestyle="--",
                  label="frozen 0.5 tolerance")
    audit.set(ylabel="absolute log-evidence difference",title="Corrected max512 convergence diagnostics")
    audit.legend(fontsize="small")
    variation.plot(x,ranges,marker="o",color="tab:purple",label="maximum within-cell log-likelihood range")
    cell_axis=variation.twinx()
    cell_axis.plot(x,cell_counts,color="0.35",linestyle=":",marker="s",label="leaf cells")
    variation.set(xlabel="whole-track update",ylabel="max within-cell log range")
    cell_axis.set(ylabel="leaf-cell count",ylim=(0,560))
    handles1,labels1=variation.get_legend_handles_labels(); handles2,labels2=cell_axis.get_legend_handles_labels()
    variation.legend(handles1+handles2,labels1+labels2,fontsize="small",loc="upper left")
    fig.suptitle("Fixed-nuisance conditional diagnostic; spatial convergence unresolved")
    convergence_path=output/"corrected512-convergence.png"
    fig.savefig(convergence_path,dpi=180); plt.close(fig)
    return [map_path,convergence_path]


if __name__ == "__main__":
    for path in generate(load_sealed(RECEIPT)):
        print(path)
