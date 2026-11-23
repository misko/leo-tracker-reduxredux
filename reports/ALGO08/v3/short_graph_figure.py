"""Plot saved solver timings and position error under each graph configuration."""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from short_graph_budget import DATA, read


def main():
    dense = read("dense-quadratic-proxy-summary.json")
    geo = read("dense-quadratic-fused.json")
    old_geo = read("dense-geographic-kernel.json")["physical"]
    native, quadratic = "#29496d", "#00836e"
    fig, axes = plt.subplots(1, 3, figsize=(12.6, 4.1), layout="constrained")
    time = axes[0]
    for values, offset, color, name in (
        ([dense["original_live"]["solve"]["cpu_s"], old_geo["native"]["cpu_s"]], -.17, native, "Installed graph"),
        ([geo["records"][k]["solve"]["cpu_s"] for k in ("control", "fused")], .17, quadratic, "Quadratic graph")
    ):
        bars = time.bar([n + offset for n in range(2)], values, width=.32, color=color, label=name)
        time.bar_label(bars, fmt="%.1f", padding=2, fontsize=9)
    time.set(xticks=[0,1], xticklabels=["Original\nprojection", "Native\nprojection"],
             ylabel="Saved solve CPU (s)", title="Dense DS30-0008", ylim=(0, 50))
    time.legend(fontsize=8, frameon=False)
    samples = read("full-short-graph-transfer.json")
    for arm, axis, title in zip(("c0", "fitted_c"), axes[1:], ("Fixed c = 0", "Fitted c"), strict=True):
        ordinary = [dense["original_live"]["arms"][arm]["horizontal_error_km"]]
        limited = [dense["quadratic_live"]["arms"][arm]["horizontal_error_km"]]
        for case in ("physical", "south-inside"):
            ordinary.append(samples[case]["score"]["arms"][arm]["error_km"])
            limited.append(samples[case]["control"]["score"]["arms"][arm]["error_km"])
        for n in range(3):
            axis.plot([ordinary[n], limited[n]], [n,n], color="#b8c0c5", lw=2)
        axis.scatter(ordinary, range(3), color=native, marker="o", s=45)
        axis.scatter(limited, range(3), color=quadratic, marker="D", s=38)
        axis.set(yticks=range(3), yticklabels=["Dense · v3 input","Physical · short","South · short"],
                 xlabel="Horizontal error (km)", xlim=(0, 2.85), ylim=(2.5,-.5),title=title)
        axis.grid(axis="x", alpha=.2)
    for axis in axes:
        axis.set_axisbelow(True)
        axis.spines[["right","top"]].set_visible(False)
    fig.savefig(DATA.parent / "development/short-graph-transfer.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
