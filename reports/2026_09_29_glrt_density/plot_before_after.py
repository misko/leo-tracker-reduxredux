"""Render the requested before/after GLRT view from the frozen pilot products."""
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from evaluate import products
from run import ROOT, sha, write


def main():
    plt.rcParams.update({"font.size":11,"axes.spines.top":False,"axes.spines.right":False})
    fig, axes = plt.subplots(1, 2, figsize=(17, 5.8), sharex=True, sharey=True)
    counts = {}
    for ax, stride, label in zip(axes, (120, 10), ("BEFORE · Current analysis", "AFTER · Dense replay")):
        values = products(stride)
        count = 0
        for rx, color, marker in ((0, "#3583a0", "o"), (1, "#c78131", "x")):
            winners = [max(p["candidates"], key=lambda c: c["fractional_margin"])
                       for visit in values for p in visit["probes"]
                       if p["receiver_id"] == rx and p["candidates"]]
            count += len(winners)
            ax.scatter([c["fractional_time_s"] for c in winners],
                       [c["fractional_margin"] for c in winners],
                       s=13, alpha=.7, color=color, marker=marker, label=f"RX{rx}")
        counts[str(stride)] = count
        ax.axhline(.025, color="#555555", ls="--", lw=1, label="Margin gate: 0.025")
        ax.set(xlim=(0,30), ylim=(-.025,.9), xlabel="Device time since capture start (s)",
               title=f"{label}\n20 ms windows / {stride} ms stride · {count:,} receiver-probes")
        ax.grid(alpha=.16)
        ax.legend(loc="upper right", fontsize=9)
    axes[0].set_ylabel("Fractional GLRT64 exact − control margin")
    fig.suptitle("Time vs GLRT response — same 30 seconds of saved IQ", fontsize=17, y=.98)
    fig.text(.5,.025,"One winning candidate per probe/RX at its fractional epoch; identical axes and threshold; no interpolation.",
             ha="center", fontsize=10, color="#444444")
    fig.tight_layout(rect=(0,.06,1,.93))
    artifacts=[]
    for extension in ("png", "svg"):
        path=ROOT/f"glrt-before-after.{extension}"
        fig.savefig(path,dpi=170,bbox_inches="tight")
        artifacts.append(dict(name=path.name,bytes=path.stat().st_size,sha256=sha(path.read_bytes())))
    plt.close(fig)
    write(ROOT/"glrt-before-after-manifest.json",dict(artifacts=artifacts,receiver_probe_counts=counts,
        source_specification_sha256=sha((ROOT/"spec.json").read_bytes()),
        scope_amendment_sha256=sha((ROOT/"protocol-amendment.md").read_bytes())))
    print(json.dumps(dict(artifacts=artifacts,receiver_probe_counts=counts)))


if __name__ == "__main__":
    main()
