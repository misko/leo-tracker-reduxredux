"""Render the known-epoch acquisition ceiling and measured native costs."""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from statistics import median

import matplotlib

from ..__main__ import save_json
from .full_v5_check import _sha

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

METHODS = ("stock", "oracle", "half_frame")
NAMES = {"stock": "Stock", "oracle": "Known epoch", "half_frame": "Half-frame sham"}


def csv_file(name, rows):
    keys = list(dict.fromkeys(k for item in rows for k in item))
    with name.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def data(folder):
    proof = json.loads((folder / "worker-lock.json").read_bytes())
    if any(_sha(folder / name) != sha for name, sha in proof["files"].items()):
        raise ValueError("pre-score data differ from the immutable worker lock")
    source = json.loads((folder / "summary.json").read_bytes())
    metadata = json.loads((folder / "input-lock.json").read_bytes())["cases"]
    edges = {
        (ident, row["visit"]): row["archive_probe"]["edge"]
        for ident, case in metadata.items()
        for row in case["selected"]
    }
    fields = ("visit", "receiver", "kind", "stratum", "channel", "known_center", "status")
    endpoints, stages, groups = [], [], {}
    for ident, rows in source.items():
        for row in rows:
            common = dict(
                case=ident, edge=edges[ident, row["visit"]], **{k: row[k] for k in fields}
            )
            target = row["target"]
            if not row["methods"]:
                endpoints.append(dict(common, method=None, reason=row["reason"]))
            for method, details in row["methods"].items():
                measures = {
                    k: v for k, v in details.items() if k not in ("ordinary", "selected", "timing")
                }
                measures["endpoint_status"] = measures.pop("status")
                endpoints.append(
                    dict(
                        common,
                        method=method,
                        archive_margin=target["fractional_margin"],
                        archive_rank=target["candidate_rank"],
                        **measures,
                    )
                )
                for repeat, run in enumerate(details["timing"], 1):
                    for rx, lane in enumerate(run["rows"]):
                        stages.append(
                            dict(
                                common,
                                method=method,
                                repeat=repeat,
                                timed_lane=rx,
                                full_detector_cpu_ms=run["detector_ms"],
                                adapter_process_cpu_ms=run["cpu_ns"] / 1e6,
                                adapter_wall_ms=run["wall_ns"] / 1e6,
                                **{f"lane_{k}_ms": v for k, v in lane.items()},
                            )
                        )
        misses = [row for row in rows if row["kind"] == "miss"]
        fits = [row["methods"]["oracle"] for row in misses if row["methods"]]
        groups[ident] = dict(
            misses=len(misses),
            matched_controls=len(rows) - len(misses),
            processed=sum(bool(row["methods"]) for row in rows),
            status_counts=Counter(r["status"] for r in fits),
            gated=sum(r["passes"] for r in fits),
            winner=sum(r["winner"] for r in fits),
            unaliased_gated=sum(r["physical_passes"] for r in fits),
            unaliased_winner=sum(r["physical_winner"] for r in fits),
            other_displaced=sum(r["stock_other_lost"] for r in fits),
            detector_cpu_median_ms={
                m: median(
                    item["detector_ms"]
                    for row in rows
                    for item in row["methods"].get(m, {}).get("timing", [])
                )
                for m in METHODS
            },
            adapter_wall_median_ms={
                m: median(
                    item["wall_ns"] / 1e6
                    for row in rows
                    for item in row["methods"].get(m, {}).get("timing", [])
                )
                for m in METHODS
            },
        )
    return proof, endpoints, stages, groups


def render(folder):
    worker, endpoints, stages, groups = data(folder)
    csv_file(folder / "oracle-start.csv", endpoints)
    csv_file(folder / "oracle-start-stages.csv", stages)
    save_json(folder / "counts.json", groups)
    fig, (recover, clock) = plt.subplots(1, 2, figsize=(11.1, 4.5))
    labels = list(groups)
    x = list(range(len(labels)))
    wins = [r["winner"] for r in groups.values()]
    hits = [r["gated"] for r in groups.values()]
    full = [r["misses"] for r in groups.values()]
    recover.bar(x, wins, color="#17796f", label="Becomes wide winner")
    recover.bar(
        x,
        [g - w for g, w in zip(hits, wins, strict=True)],
        bottom=wins,
        color="#80b9a9",
        label="Gated, another winner",
    )
    recover.bar(
        x,
        [n - g for n, g in zip(full, hits, strict=True)],
        bottom=hits,
        color="#e7a776",
        label="Target not recovered",
    )
    recover.set_title("Archived winner absent from stock", loc="left", fontweight="bold")
    recover.set_yticks(range(5))
    recover.set_ylim(0, 4.33)
    recover.set_ylabel("Missed targets tested")
    recover.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=1)

    color = {"stock": "#34495b", "oracle": "#17796f", "half_frame": "#ad642a"}
    stage_map = {"stock": "o", "oracle": "s", "half_frame": "^"}
    for i, method in enumerate(METHODS):
        coords = [j + (i - 1) * 0.18 for j in x]
        values = [row["detector_cpu_median_ms"][method] for row in groups.values()]
        clock.scatter(
            coords, values, color=color[method], marker=stage_map[method], s=42, label=NAMES[method]
        )
    clock.set_title("Complete dual-RX detector cost", loc="left", fontweight="bold")
    clock.set_ylabel("Median native CPU (ms)")
    clock.set_ylim(0, 22)
    clock.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=1)
    for ax in (recover, clock):
        ax.set_xticks(x, labels, fontsize=9)
        ax.grid(axis="y", alpha=0.18)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle(
        f"A known start recovers {sum(hits)} of {sum(full)} missed wide-GLRT targets",
        x=0.08,
        y=0.985,
        ha="left",
        fontweight="bold",
        fontsize=15,
    )
    others = sum(
        row.get("passes", False)
        for row in endpoints
        if row["kind"] == "miss" and row["method"] == "half_frame"
    )
    message = (
        f"Saved-IQ diagnostic. The half-frame sham recovered {others}/{sum(full)}. "
        "The input uses privileged timing."
    )
    fig.text(0.08, 0.891, message, fontsize=10)
    fig.subplots_adjust(left=0.085, bottom=0.25, right=0.98, top=0.806, wspace=0.30)
    fig.savefig(folder / "oracle-start.png", dpi=170)
    fig.savefig(folder / "oracle-start.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)

    names = (
        *worker["files"],
        "worker-lock.json",
        "summary.json",
        "counts.json",
        "oracle-start.csv",
        "oracle-start-stages.csv",
        "oracle-start.png",
        "oracle-start.pdf",
    )
    save_json(
        folder / "result-lock.json",
        dict(
            files={name: _sha(folder / name) for name in names},
            figure_source_sha256=_sha(Path(__file__)),
            boundary="label-assisted raw wide detector, one epoch and unchanged four-center limit",
        ),
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("folder", type=Path)
    render(cli.parse_args().folder)
