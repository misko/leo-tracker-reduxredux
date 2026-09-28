"""Show actual recovered bit means before and after repetition combining."""

import json

import matplotlib
import numpy as np
from analyze import OUT

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    out = OUT / "best-upper"
    data = np.load(out / "tcode-soft-evidence.npz")
    result = json.loads((out / "tcodes.json").read_text())["results"][0]
    fig, axes = plt.subplots(1, 2, figsize=(11, 5))
    x = data["frame_0_raw_rx0"].ravel()
    axes[0].scatter(x.real, x.imag, s=4, alpha=0.25)
    axes[0].set(
        title="RX0 before repetition combining · 1,536 observations", xlim=(-4, 4), ylim=(-4, 4)
    )
    for receiver in [0, 1]:
        z = data[f"frame_0_rx{receiver}_means"]
        axes[1].scatter(
            z.real, z.imag, s=22, alpha=0.7, label=f"RX{receiver}: 60 recovered bit means"
        )
    axes[1].set(
        title="Independent receivers after repetition combining", xlim=(-1.6, 1.6), ylim=(-1.6, 1.6)
    )
    axes[1].legend(fontsize=8)
    for ax in axes:
        ax.axhline(0, color="grey", lw=0.5)
        ax.axvline(0, color="grey", lw=0.5)
        ax.set(xlabel="Template-removed I", ylabel="Template-removed Q")
        ax.set_aspect("equal")
    fig.suptitle("DS7: complete 60-bit T-code recovered from a 10 MS/s recording")
    fig.text(
        0.5,
        0.035,
        f"Visit 191, frame 0, symbols {result['first_symbol']}–{result['last_symbol']} · "
        f"both receivers: {result['combined_hex']} (60-bit display convention)\n"
        "Physical-layer repetition pattern; "
        "no satellite ID, timing, orbit, or user-traffic interpretation.",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.12, 1, 0.94))
    fig.savefig(out / "recovered-tcode-iq.png", dpi=170)


if __name__ == "__main__":
    main()
