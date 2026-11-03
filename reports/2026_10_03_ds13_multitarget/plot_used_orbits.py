"""Render archived physical Doppler curves and validated prototype-used peaks."""
from pathlib import Path
import argparse
import json
import math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from common import ROOT, SESSIONS, load_scan, digest
from review import read_records, validate_and_score

OUTPUT = ROOT / "orbit-overlays"
METHODS = ("Baseline", "Activity", "History", "Tracklet")
RX_COLORS = ("#0072B2", "#D55E00")
CHANNEL_MARKERS = ("o", "^", "s", "D")
FOOTNOTE = ("Assigned GLRT peaks only; nearest fitted alias, RX/RF calibration removed, normalized to 11.085 GHz.\n"
            "Identical frozen timing-adjusted orbit curves for every method. No extra state, linear or quadratic subtraction. In-sample diagnostic.")
ALL_FOOTNOTE = ("All stored GLRT rows, including unassigned rows and exact-alias copies; no additional gate or decimation.\n"
                "RX/RF calibrated, normalized to 11.085 GHz. Gray alias alternatives are NOT associations. Frozen fits; no extra detrending.")


def partition_rows(row_count, assigned_rows, assigned_columns, column):
    assigned = np.zeros(row_count, bool)
    assigned[assigned_rows] = True
    return (np.flatnonzero(~assigned), assigned_rows[assigned_columns != column],
            assigned_rows[assigned_columns == column])


def unassigned_alias_points(arrays, assigned_rows):
    """Show each unassigned row once per distinct candidate-nearest alias branch.

    No best-satellite choice is made for an unassigned peak. Many satellites
    imply the same branch, which is drawn only once for this source row.
    """
    mask = np.ones(len(arrays["times_s"]), bool)
    mask[assigned_rows] = False
    unused = np.flatnonzero(mask)
    count = len(arrays["catalog_numbers"])
    rr = np.repeat(unused, count)
    cc = np.tile(np.arange(count), len(unused))
    keys = np.column_stack([rr, arrays["alias_integer"][rr, cc]])
    _, indices = np.unique(keys, axis=0, return_index=True)
    return rr[indices], cc[indices]


def source_paths(label):
    session = SESSIONS[label]
    return {
        "Baseline": ROOT/"baseline"/f"{label}-assignments.csv",
        "Activity": ROOT/"activity/assignments.csv",
        "History": ROOT/"history/results/beam32-state"/f"{session}-assignments.csv",
        "Tracklet": ROOT/"tracklet/outputs/assignments.csv",
    }


def selected_pairs(data, records):
    validate_and_score(data, records)
    lookup = {int(n): i for i, n in enumerate(data["arrays"]["catalog_numbers"])}
    return np.asarray([r["row_index"] for r in records], int), np.asarray(
        [lookup[r["catalog_number"]] for r in records], int)


def overview(label, data, methods, include_unassigned=False):
    a = data["arrays"]
    colors = plt.get_cmap("tab20")(np.arange(len(a["catalog_numbers"])))
    fig, axes = plt.subplots(2, 2, figsize=(16, 11), sharex=True, sharey=True)
    for ax, (name, records) in zip(axes.flat, methods.items()):
        rows, cols = selected_pairs(data, records)
        if include_unassigned:
            rr, cc = unassigned_alias_points(a, rows)
            ax.scatter(a["times_s"][rr], a["doppler_hz"][rr, cc]/1000,
                       s=3, color=".55", linewidths=0, alpha=.23, zorder=0, rasterized=True)
        for col, number in enumerate(a["catalog_numbers"]):
            if not np.any(cols == col):
                continue
            visible = np.where(a["dense_visible"][:, col], a["dense_doppler_hz"][:, col]/1000, np.nan)
            ax.plot(a["dense_times_s"], visible, color=colors[col], lw=1., alpha=.6, zorder=1)
            for rx, marker in ((0, "o"), (1, "^")):
                used = rows[(cols == col) & (a["receiver"][rows] == rx)]
                ax.scatter(a["times_s"][used], a["doppler_hz"][used, col]/1000,
                           c=[colors[col]], marker=marker, s=10, linewidths=0, alpha=.9, zorder=2)
        title = f"{name} · {len(rows):,} assigned"
        if include_unassigned: title += f" / {len(a['times_s'])-len(rows):,} unassigned"
        ax.set_title(title)
        ax.set_xlim(0, 300)
        ax.grid(alpha=.15)
        ax.set_xlabel("Receive time since capture start (s)")
        ax.set_ylabel("Calibrated Doppler (kHz)")
    handles = [Line2D([], [], color=colors[i], label=str(int(n)), lw=2)
               for i, n in enumerate(a["catalog_numbers"])]
    handles += [Line2D([], [], marker=m, color=".2", linestyle="none", label=f"RX{rx}")
                for rx, m in ((0, "o"), (1, "^"))]
    if include_unassigned:
        handles += [Line2D([], [], marker=".", color=".55", linestyle="none", label="Unassigned (alias alternatives)")]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(.5, .045), ncol=7, fontsize=10)
    fig.suptitle(f"DS13 scan {label} · satellite trajectories with {'all stored' if include_unassigned else 'used'} GLRT peaks\n"
                 "Line = orbit Doppler · colored points = assigned · gray = unassigned alias alternatives"
                 if include_unassigned else f"DS13 scan {label} · used satellite trajectories with GLRT peaks\n"
                 "Line = satellite orbit Doppler · dots/triangles = assigned GLRT measurements", fontsize=16)
    fig.text(.5, .013, ALL_FOOTNOTE if include_unassigned else FOOTNOTE, ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .115, 1, .93))
    path = OUTPUT/f"scan-{label.lower()}-all-methods.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def details(label, name, data, records, residual_limit, include_unassigned=False):
    a = data["arrays"]
    rows, cols = selected_pairs(data, records)
    used_columns = sorted(set(cols))
    fig = plt.figure(figsize=(15, 3.6*math.ceil(len(used_columns)/2)+1.4))
    grid = fig.add_gridspec(math.ceil(len(used_columns)/2), 2, left=.07, right=.98,
                           bottom=.065, top=.93, hspace=.48, wspace=.20)
    for k, col in enumerate(used_columns):
        sub = grid[k//2, k%2].subgridspec(2, 1, height_ratios=(2.2, 1), hspace=.07)
        ax = fig.add_subplot(sub[0])
        res = fig.add_subplot(sub[1], sharex=ax)
        curve = np.where(a["dense_visible"][:, col], a["dense_doppler_hz"][:, col]/1000, np.nan)
        ax.plot(a["dense_times_s"], curve, color=".1", lw=1.25, zorder=1)
        used = rows[cols == col]
        if include_unassigned:
            unassigned, elsewhere, _ = partition_rows(len(a["times_s"]), rows, cols, col)
            for rr, color, alpha in ((unassigned, ".55", .23), (elsewhere, "#a7bbc9", .28)):
                options = dict(s=3, color=color, alpha=alpha, linewidths=0, zorder=0, rasterized=True)
                ax.scatter(a["times_s"][rr], a["doppler_hz"][rr, col]/1000, **options)
                res.scatter(a["times_s"][rr], a["residual_hz"][rr, col], **options)
        for rx in (0, 1):
            for channel in range(1, 5):
                rr = used[(a["receiver"][used] == rx) & (a["channel"][used] == channel)]
                options = dict(color=RX_COLORS[rx], marker=CHANNEL_MARKERS[channel-1], s=9,
                               linewidths=0, alpha=.8, zorder=2)
                ax.scatter(a["times_s"][rr], a["doppler_hz"][rr, col]/1000, **options)
                res.scatter(a["times_s"][rr], a["residual_hz"][rr, col], **options)
        ax.set_title(f"NORAD {a['catalog_numbers'][col]} · {len(used)} used peaks", fontsize=11)
        ax.set_ylabel("Doppler (kHz)")
        ax.tick_params(labelbottom=False)
        res.axhline(0, color=".3", lw=.65)
        for y in (-100, 100): res.axhline(y, color=".6", linestyle=":", lw=.7)
        if include_unassigned:
            res.set_yscale("symlog", linthresh=250, linscale=1.0)
            res.set_yticks([-100000, -1000, -100, 0, 100, 1000, 100000])
            res.set_yticklabels(["−100k", "−1k", "−100", "0", "100", "1k", "100k"], fontsize=7)
        res.set_ylim(-residual_limit, residual_limit)
        res.set_ylabel("O − M (Hz)")
        res.set_xlabel("Receive time (s)")
        for pane in (ax, res):
            pane.set_xlim(0, 300)
            pane.grid(alpha=.15)
    subtitle = ("All GLRT rows against each satellite's nearest alias · residual axis symlog"
                if include_unassigned else "Used GLRT peaks against frozen satellite trajectories")
    fig.suptitle(f"DS13 scan {label} · {name}\n{subtitle}", fontsize=16, y=.987)
    handles = [Line2D([], [], color=".1", label="Timing-adjusted orbit")]
    handles += [Line2D([], [], color=RX_COLORS[rx], marker="o", linestyle="none", label=f"RX{rx}") for rx in (0,1)]
    handles += [Line2D([], [], color=".4", marker=m, linestyle="none", label=f"CH{i+1}") for i,m in enumerate(CHANNEL_MARKERS)]
    if include_unassigned:
        handles += [Line2D([], [], color=c, marker=".", linestyle="none", label=label)
                    for c,label in ((".55", "Unassigned"), ("#a7bbc9", "Assigned elsewhere"))]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.5, .958), ncol=5 if include_unassigned else 7, fontsize=9)
    fig.text(.5, .017, ALL_FOOTNOTE if include_unassigned else FOOTNOTE, ha="center", fontsize=9)
    path = OUTPUT/f"scan-{label.lower()}-{name.lower()}-satellites.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def main():
    global OUTPUT
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-unassigned", action="store_true")
    args = parser.parse_args()
    if args.include_unassigned: OUTPUT = ROOT / "orbit-overlays-all-glrt"
    OUTPUT.mkdir(exist_ok=True)
    receipt = dict(scope=__doc__, include_unassigned=args.include_unassigned,
                   display=ALL_FOOTNOTE if args.include_unassigned else FOOTNOTE,
                   overview_alias_policy="All distinct candidate-nearest branches per unassigned source row; no best-satellite assignment",
                   scans=[], source_hashes={str(Path(__file__)):digest(__file__)})
    artifacts = []
    for label in SESSIONS:
        data = load_scan(label, rf_variant="sealed")
        paths = source_paths(label)
        methods = {name:[r for r in read_records([p]) if r["scan"] == label] for name,p in paths.items()}
        if any(not rows for rows in methods.values()): raise ValueError("Missing method assignments")
        receipt["source_hashes"].update({str(p):digest(p) for p in paths.values()})
        receipt["source_hashes"].update(data["provenance"])
        maximum = max(abs(r["residual_hz"]) for records in methods.values() for r in records)
        if args.include_unassigned: maximum = np.max(np.abs(data["arrays"]["residual_hz"]))
        residual_limit = max(250., 50*np.ceil(1.05*maximum/50))
        artifacts.append(overview(label, data, methods, args.include_unassigned))
        for name, records in methods.items():
            artifacts.append(details(label, name, data, records, residual_limit, args.include_unassigned))
        receipt["scans"].append(dict(scan=label, session=SESSIONS[label],
                                    total_stored_rows=len(data["arrays"]["times_s"]),
                                    unassigned_counts={n:len(data["arrays"]["times_s"])-len(r) for n,r in methods.items()},
                                    counts={n:len(r) for n,r in methods.items()}, residual_limit_hz=residual_limit))
        print(label, receipt["scans"][-1]["counts"], flush=True)
    receipt["artifact_sha256"] = {str(p):digest(p) for p in artifacts}
    (OUTPUT/"receipt.json").write_text(json.dumps(receipt, indent=2)+"\n")


if __name__ == "__main__": main()
