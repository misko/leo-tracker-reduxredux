"""Attribute frozen seeded-tracker misses and report search-only latency."""

import argparse
from collections import Counter
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json
from ..scoring import distribution
from ..variants import seeded_acquisition as seeded
from . import scout_stage_figures as plot
from . import seeded_acquisition_results as results
from . import seeded_acquisition_trial as trial
from .full_v5_check import _sha
from .prefix_figures import csv_file


def diagnose(lock, rows, mode):
    counts, anchors = Counter(), {}
    cpu, wall, anchor_cpu, anchor_wall = [], [], [], []
    for row in rows:
        if row["status"] != "processed":
            continue
        ref = lock["reference"][str(row["visit"])]["probes"]
        sample = row["sample"]
        keys = [(row["generation"], row["rf"], rx) for rx in (0, 1)]
        if "anchor" in row:
            anchor_cpu.append(row["anchor"]["clocks"]["cpu_ns"] / 1e6)
            anchor_wall.append(row["anchor"]["clocks"]["wall_ns"] / 1e6)
            for key, p in zip(keys, row["anchor"]["probes"], strict=True):
                if results.positive(p):
                    anchors[key] = sample
                else:
                    anchors.pop(key, None)
            continue
        actual = row["follow"].get(mode)
        if actual is None:
            continue
        lanes = actual.get("lanes")
        if lanes is None or any(lane["status"] == "searched" for lane in lanes):
            cpu.append(actual["clocks"]["cpu_ns"] / 1e6)
            wall.append(actual["clocks"]["wall_ns"] / 1e6)
        if lanes is None:
            continue
        for key, lane, p in zip(keys, lanes, ref, strict=True):
            positive = results.positive(p)
            if lane["status"] == "no_seed":
                category = "expired" if key in anchors else "no_anchor"
                counts[category] += 1
                counts[category + "_reference_positive"] += bool(positive)
                continue
            counts["searched"] += 1
            counts["searched_reference_positive"] += bool(positive)
            epoch = [
                c
                for c in positive
                if abs(
                    seeded.wrapped(
                        c["integer_epoch_sample"]
                        + c["fractional_epoch_offset_samples"]
                        - lane["epoch"]
                    )
                )
                <= lane["radius"] + 0.5
            ]
            counts["epoch_window_reference_positive"] += bool(epoch)
            counts["signed_window_reference_positive"] += any(
                abs(c["fractional_tracking_cfo_hz"] - lane["cfo"]) <= seeded.MAX_CFO_INNOVATION
                for c in epoch
            )
            counts["shortlist_reference_positive"] += any(
                abs(
                    seeded.wrapped(
                        k - c["integer_epoch_sample"] - c["fractional_epoch_offset_samples"]
                    )
                )
                <= results.MATCH_EPOCH
                for k in lane["ranked_epochs"]
                for c in epoch
            )
            if lane["updated"]:
                anchors[key] = sample
    return dict(
        counts=dict(counts),
        active_cpu_ms=distribution(cpu),
        active_wall_ms=distribution(wall),
        active_within_20ms=sum(v <= 20 for v in wall),
        anchor_cpu_ms=distribution(anchor_cpu),
        anchor_wall_ms=distribution(anchor_wall),
    )


def publish(work):
    out = trial.REPORT
    raw = out / "stage-lock.json"
    statement = whole_iq.read(raw)
    for f, digest in statement["files"].items():
        whole_iq.checked(out / f, digest)
    lock, receipt = results.loaded(work, trial.HELD)
    scores = {m: diagnose(lock, receipt["rows"], m) for m in ("seeded", "shifted", "native")}
    dev_lock, dev = results.loaded(work, trial.DEVELOPMENT)
    development = {str(rate): diagnose(dev_lock, dev["rows"], str(rate)) for rate in trial.DEVRATES}
    save_json(
        out / "active-search.json",
        dict(held=scores, development=development, publisher_sha256=_sha(Path(__file__))),
    )
    csv_file(
        out / "active-search.csv",
        [
            dict(
                policy=m,
                active_visits=d["active_cpu_ms"]["n"],
                within_20ms=d["active_within_20ms"],
                cpu_p50_ms=d["active_cpu_ms"]["p50"],
                cpu_p95_ms=d["active_cpu_ms"]["p95"],
                wall_p50_ms=d["active_wall_ms"]["p50"],
                wall_p95_ms=d["active_wall_ms"]["p95"],
            )
            for m, d in scores.items()
        ],
    )
    fig, axes = plot.canvas(
        "Active pilot search latency on held saved IQ",
        "DS29-0082 upper edge · follow visits that ran an actual detector",
        "Seedless polls are outside this chart. All policies share the same original anchor "
        "scans. Search-only sample sizes differ and are shown per row.",
    )
    labels = [
        f"{tag} ({value['active_cpu_ms']['n']})"
        for tag, value in zip(("Seeded", "Shifted", "Native control"), scores.values(), strict=True)
    ]
    for ax, metric, title in zip(
        axes, ("active_cpu_ms", "active_wall_ms"), ("Detector CPU", "Detector wall"), strict=True
    ):
        plot.paired(
            ax,
            labels,
            [(v[metric]["p50"], v[metric]["p95"]) for v in scores.values()],
            title=title,
            xlabel="Milliseconds",
        )
    plot.key(fig, "Median", "95th percentile")
    fig.savefig(out / "active-search.png", dpi=165, facecolor="white")
    fig.savefig(out / "active-search.pdf", facecolor="white", metadata={"CreationDate": None})
    plot.plt.close(fig)
    names = (
        "stage-lock.json",
        "active-search.json",
        "active-search.csv",
        "active-search.png",
        "active-search.pdf",
    )
    save_json(out / "active-lock.json", {"files": {name: _sha(out / name) for name in names}})
    save_json(
        out / "stage-figure.json",
        dict(
            version=1,
            id="seeded-pilot-acquisition",
            title="Causal seeded pilot acquisition",
            sample="128 held slots, 72 valid follow visits and separately logged anchors",
            boundary="Resident CI16 through actual follow search and fractional factor projection",
            note="Timing is restricted to visits that ran a search. Physical exclusions, unseeded "
            "polls, and original anchor costs are retained in the study audit.",
            seal="active-lock.json",
            image="active-search.png",
            pdf="active-search.pdf",
            csv="active-search.csv",
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output, nargs="?", default=trial.WORK)
    args = parser.parse_args()
    publish(args.work)
