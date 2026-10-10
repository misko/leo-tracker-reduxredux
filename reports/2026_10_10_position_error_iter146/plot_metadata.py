"""Reproduce the metadata membership figure; no localization input."""

import datetime
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def main():
    manifest = json.loads((HERE / "local/manifest.json").read_text())
    counts = [
        sum(c["sample_rate_hz"] == rate for c in manifest["captures"])
        for rate in (2500000, 10000000)
    ]
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.4), layout="constrained")
    axes[0].bar(["2.5 MS/s", "10 MS/s"], counts, color=["#357a99", "#d39a42"])
    axes[0].set_ylabel("Whole sealed recordings")
    axes[0].set_ylim(0, max(counts) + 2)
    for index, count in enumerate(counts):
        axes[0].text(index, count + 0.3, str(count), ha="center")
    times = [
        datetime.datetime.fromtimestamp(c["capture_start_utc_ns"] / 1e9, datetime.UTC)
        for c in manifest["captures"]
    ]
    axes[1].scatter(times, [c["sample_rate_hz"] / 1e6 for c in manifest["captures"]], s=30)
    axes[1].set_ylabel("Sample rate (MS/s)")
    axes[1].set_xlabel("Capture start UTC")
    fig.autofmt_xdate()
    fig.suptitle("POST18-LATER-20261010: metadata only, all 22 outcomes closed")
    fig.savefig(HERE / "membership.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
