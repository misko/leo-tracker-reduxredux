"""Plot unchanged measured CFO marks left by the complete high-coverage policy."""

import csv
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.lines import Line2D
import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
DATA = REPORTS / "2026_10_16_dsx01_fast_association_losses"
BIAS = REPORTS / "2026_10_17_dsx01_iteration4/frequency_bias"
ALIAS = 1 / 4.4e-6
RED = "#d44732"
GRAY = "#aeb6be"


def sha(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def verified_path(folder, relative):
    manifest = json.loads((folder / "manifest.json").read_text())["files"]
    hashes = manifest if isinstance(manifest, dict) else {r["path"]: r["sha256"] for r in manifest}
    path = folder / relative
    if sha(path) != hashes[relative]:
        raise ValueError("Changed frozen evidence: " + str(path))
    return path


def align(metadata, state):
    if len(metadata) != len(state["associated"]) or state["associated"].dtype != bool:
        raise ValueError("Complete boolean association flags required")
    np.testing.assert_array_equal(state["times_s"], [r["time_s"] for r in metadata])
    for name, field, transform in [
        ("observation_id", "observation_id", str),
        ("receiver", "receiver", lambda x: int(x) - 1),
        ("channel", "channel", int),
    ]:
        if name in state:
            np.testing.assert_array_equal(state[name], [transform(r[field]) for r in metadata])
    return np.asarray(state["associated"]).copy()


def members_mask(metadata, members):
    ids = np.array([r["observation_id"] for r in metadata])
    if len(set(ids)) != len(ids) or len(set(members)) != len(members):
        raise ValueError("Unique observation IDs required")
    if not set(members).issubset(ids):
        raise ValueError("Missing frozen window members")
    return np.isin(ids, members)


def cfo(values, folded):
    values = np.asarray(values)
    return ((values + ALIAS / 2) % ALIAS - ALIAS / 2 if folded else values) / 1000


def scatter(ax, arrays, mask, folded=False, size=10):
    t, y, associated = arrays["time"], cfo(arrays["cfo"], folded), arrays["associated"]
    gray, red = mask & associated, mask & ~associated
    ax.scatter(t[gray], y[gray], s=size * .7, color=GRAY, alpha=.65, linewidths=0)
    ax.scatter(t[red], y[red], s=size, color=RED, alpha=.9, linewidths=0)
    ax.grid(alpha=.18)
    ax.set_axisbelow(True)


def legend(fig, y):
    handles = [Line2D([], [], marker="o", linestyle="", color=RED, label="Unassociated"),
               Line2D([], [], marker="o", linestyle="", color=GRAY, label="Associated context")]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.5, y), ncol=2,
               frameon=False, markerscale=.8, fontsize=11)


def zoom_figure(regions, sources, window_counts, folded):
    fig, axes = plt.subplots(5, 3, figsize=(16, 15))
    fig.subplots_adjust(left=.065, right=.985, bottom=.07, top=.90, hspace=.58, wspace=.25)
    kind = "CFO modulo 227.273 kHz" if folded else "Original measured CFO"
    fig.suptitle("High-coverage experiment: the 231 remaining points in all 15 windows", fontsize=19, y=.985)
    fig.text(.5, .958, kind + " · fitted c · one unchanged 462/693 policy · no trajectory lines inferred",
             ha="center", fontsize=11)
    legend(fig, .947)
    for region, ax, count in zip(regions, axes.flat, window_counts, strict=True):
        source = sources[region["source_id"]]
        start, end = float(region["start_s"]), float(region["end_s"])
        rx, ch = int(region["receiver"]), int(region["channel"])
        use = (source["receiver"] == rx) & (source["channel"] == ch)
        use &= (source["time"] >= max(0., start - 3)) & (source["time"] <= end + 3)
        ax.axvspan(start, end, color="#e9f2fa", alpha=.7)
        scatter(ax, source, use, folded=folded, size=15)
        ax.set_xlim(max(0., start - 3), end + 3)
        ax.set_title(f"{region['region_id']} · {region['source_id']} RX{rx}/CH{ch}\n"
                     f"{start:g}–{end:g} s · {count['unassociated']}/{count['observations']} left", fontsize=10.5)
        ax.set_xlabel("Time from scan start (s)", fontsize=9)
        ax.set_ylabel("CFO (kHz)", fontsize=9)
        ax.tick_params(labelsize=9)
    fig.text(.065, .018, "Dots are saved GLRT observations, without a new satellite fit. "
             "Shading marks the exact requested span; 3 s of context is shown on each side.\n"
             "Frequency wrapping can split a continuous trajectory; neither panel groups nor smooth appearance establish emitter identity.",
             fontsize=10, linespacing=1.5)
    return fig


def full_figure(source_id, arrays, regions, recording_id):
    fig, axes = plt.subplots(4, 4, figsize=(17, 11))
    fig.subplots_adjust(left=.055, right=.985, bottom=.115, top=.88, hspace=.45, wspace=.23)
    n, missing = len(arrays["time"]), int((~arrays["associated"]).sum())
    fig.suptitle(f"{source_id}: all channels · {missing}/{n} GLRT points remain unassociated", fontsize=17, y=.985)
    fig.text(.5, .954, recording_id, ha="center", fontsize=11)
    legend(fig, .944)
    for rx in (1, 2):
        for ch in range(1, 9):
            ax = axes.flat[(rx - 1) * 8 + ch - 1]
            use = (arrays["receiver"] == rx) & (arrays["channel"] == ch)
            for region in regions:
                if region["source_id"] == source_id and int(region["receiver"]) == rx and int(region["channel"]) == ch:
                    ax.axvspan(float(region["start_s"]), float(region["end_s"]), color="#e9f2fa", alpha=.8)
            scatter(ax, arrays, use, size=8)
            ax.set_title(f"RX{rx} CH{ch} · {int((use & ~arrays['associated']).sum())}/{int(use.sum())} left", fontsize=10)
            ax.set_xlim(0, 300)
            ax.set_xlabel("Time (s)", fontsize=8)
            ax.set_ylabel("Measured CFO (kHz)", fontsize=8)
            ax.tick_params(labelsize=8)
    fig.text(.055, .019, "All saved original GLRT marks retained; original measured CFO is shown. "
             "Blue shading identifies the requested DSX01 windows.\n"
             "Saved fitted-c satellite-bias experiment; no refit, changed gate, selected satellite overlay or inferred connecting line.",
             fontsize=10, linespacing=1.4)
    return fig


def example_figure(regions, sources, counts):
    """Presentation examples; these do not select or change any model result."""
    fig, axes = plt.subplots(2, 2, figsize=(13, 8))
    fig.subplots_adjust(left=.075, right=.98, bottom=.13, top=.83, hspace=.55, wspace=.24)
    fig.suptitle("Clear trajectories remain unassociated", fontsize=19, y=.98)
    fig.text(.5, .928, "High-coverage experiment · original measured CFO · selected examples", ha="center")
    legend(fig, .91)
    selected = [(r, c) for r, c in zip(regions, counts, strict=True)
                if r["region_id"].endswith(("003", "004", "012", "014"))]
    if len(selected) != 4:
        raise ValueError("Expected four presentation windows")
    for ax, (region, count) in zip(axes.flat, selected, strict=True):
        source = sources[region["source_id"]]
        start, end = float(region["start_s"]), float(region["end_s"])
        rx, ch = int(region["receiver"]), int(region["channel"])
        use = ((source["receiver"] == rx) & (source["channel"] == ch)
               & (source["time"] >= start) & (source["time"] <= end))
        scatter(ax, source, use, size=25)
        ax.set_xlim(start, end)
        ax.set_title(f"{region['region_id']} · {region['source_id']} RX{rx}/CH{ch} · "
                     f"{count['unassociated']}/{count['observations']} unassociated", fontsize=11)
        ax.set_xlabel("Time from scan start (s)")
        ax.set_ylabel("Measured CFO (kHz)")
    fig.text(.075, .025, "Red points remain unassociated; gray points are associated context.\n"
             "Smooth carrier trajectories do not establish satellite identity. All 15 windows are included in the companion plots.",
             fontsize=10, linespacing=1.5)
    return fig


def main():
    metadata_path = verified_path(DATA, "context-observations.jsonl")
    regions_path, members_path = verified_path(DATA, "regions.csv"), verified_path(DATA, "membership.csv")
    source_path = verified_path(DATA, "sources.json")
    metadata = {}
    for line in metadata_path.read_text().splitlines():
        row = json.loads(line)
        metadata.setdefault(row["source_id"], []).append(row)
    with regions_path.open() as stream:
        regions = list(csv.DictReader(stream))
    with members_path.open() as stream:
        members = list(csv.DictReader(stream))
    source_info = {r["source_id"]: r for r in json.loads(source_path.read_text())}
    arrays, inputs, full_counts = {}, {}, []
    for source_id, rows in metadata.items():
        path = verified_path(BIAS, f"results/{source_id}-fitted-c-b1000-profile.npz")
        with np.load(path, allow_pickle=False) as state:
            assigned = align(rows, state)
        inputs[str(path)] = sha(path)
        arrays[source_id] = dict(
            observation_id=np.array([r["observation_id"] for r in rows]),
            time=np.array([r["time_s"] for r in rows]),
            cfo=np.array([r["measured_cfo_hz"] for r in rows]),
            receiver=np.array([r["receiver"] for r in rows]),
            channel=np.array([r["channel"] for r in rows]), associated=assigned,
        )
        full_counts.append(dict(source_id=source_id, observations=len(rows), associated=int(assigned.sum()),
                                unassociated=int((~assigned).sum()), recording_id=source_info[source_id]["recording_id"]))
    counts, exported = [], []
    for region in regions:
        sid, rid = region["source_id"], region["region_id"]
        ix = members_mask(metadata[sid], [m["observation_id"] for m in members if m["region_id"] == rid])
        n = int(ix.sum())
        if n != int(region["observation_count"]):
            raise ValueError("Frozen window denominator differs")
        missing = ix & ~arrays[sid]["associated"]
        counts.append(dict(region_id=rid, source_id=sid, receiver=int(region["receiver"]),
                           channel=int(region["channel"]), start_s=float(region["start_s"]), end_s=float(region["end_s"]),
                           observations=n, associated=int(n - missing.sum()), unassociated=int(missing.sum())))
        for i in np.flatnonzero(missing):
            exported.append(dict(region_id=rid, **{k: metadata[sid][i][k] for k in
                ("source_id", "observation_id", "time_s", "receiver", "channel", "actual_rf_hz", "measured_cfo_hz")}))
    assert len(counts) == 15 and sum(r["observations"] for r in counts) == 693
    assert sum(r["associated"] for r in counts) == 462 and len(exported) == 231
    assert sum(r["observations"] for r in full_counts) == 20084
    assert sum(r["associated"] for r in full_counts) == 14372
    for filename, rows in [("window_counts.csv", counts), ("unassociated_window_points.csv", exported),
                           ("full_scan_counts.csv", full_counts)]:
        with (HERE / filename).open("w") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False})
    with PdfPages(HERE / "all_unassociated_cfos.pdf") as pdf:
        fig = example_figure(regions, arrays, counts)
        fig.savefig(HERE / "remaining_track_examples.png", dpi=150)
        pdf.savefig(fig)
        plt.close(fig)
        for folded in (False, True):
            fig = zoom_figure(regions, arrays, counts, folded)
            fig.savefig(HERE / ("windows_folded.png" if folded else "windows_raw_cfo.png"), dpi=150)
            pdf.savefig(fig)
            plt.close(fig)
        for record in full_counts:
            sid = record["source_id"]
            fig = full_figure(sid, arrays[sid], regions, record["recording_id"])
            fig.savefig(HERE / f"{sid}_all_channels.png", dpi=150)
            pdf.savefig(fig)
            plt.close(fig)
    inputs.update({str(p): sha(p) for p in [metadata_path, regions_path, members_path, source_path,
                                           DATA / "manifest.json", BIAS / "manifest.json"]})
    summary = dict(arm="fitted-c", method="b1000-profile", windows=counts, full_scans=full_counts,
        requested_observations=693, requested_unassociated=231, full_unassociated=5712,
        alias_hz=ALIAS, fits=0, localization_objectives=0,
        input_bindings=inputs, generator_sha256=sha(Path(__file__)),
        interpretation="Saved model flags and measured CFO scatter; smooth traces are not verified emitters.")
    with (HERE / "summary.json").open("w") as stream:
        json.dump(summary, stream, indent=2)
        stream.write("\n")
    print(json.dumps(dict(requested_unassociated=231, full_unassociated=5712, windows=counts)))


if __name__ == "__main__":
    main()
