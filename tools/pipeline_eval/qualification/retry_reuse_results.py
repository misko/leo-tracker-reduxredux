"""Package exact reused coarse scores and their measured full-detector cost."""

import argparse
import csv
import gzip
import json
from pathlib import Path
from statistics import median

from ..__main__ import save_json, write
from .full_v5_check import _sha
from .retry_reuse_eval import ROSTER

MODES = ("prepared", "reuse")
LABELS = ("Prepared 512", "Cache shared anchors")


def receipts(work):
    return [json.loads(gzip.decompress((work / f"{case}.json.gz").read_bytes())) for case in ROSTER]


def shared_keys(primary, retry, cfo_field):
    keys = [
        {(a["refined_epoch"], a[cfo_field]) for a in stage["acquired"]}
        for stage in (primary, retry)
    ]
    return len(keys[0] & keys[1])


def flatten(data):
    timing, grids, decisions = [], [], []
    for observation in data:
        case = observation["case"]
        for row in observation["runs"]:
            kind = "radio" if "visit" in row else "synthetic"
            visit = str(row["visit"]) if kind == "radio" else row["control"]
            retry = any(g["anchor_count"] == 22 for g in row["maps"])
            fine_key_overlap, acquired_key_overlap = None, None
            if retry:
                attempts = row["public"]["prepared"]["attempts"]
                wider = attempts[-1]
                primary = next(a for a in attempts[:-1] if a["receiver_id"] == wider["receiver_id"])

                fine_key_overlap = shared_keys(primary, wider, "coarse_cfo_hz")
                acquired_key_overlap = shared_keys(primary, wider, "cfo_hz")
            decisions.append(
                dict(
                    case=case,
                    visit=visit,
                    kind=kind,
                    retry=retry,
                    public_equal=row["public_equal"],
                    attempts_equal=row["attempts_equal"],
                    installed_equal=row["installed_equal"],
                    records=sum(
                        len(r["candidates"]) for r in row["public"]["reuse"]["public"]["receivers"]
                    ),
                    gate_positive=sum(
                        c["passed_fractional_margin_gate"]
                        for r in row["public"]["reuse"]["probes"]
                        for c in r["candidates"]
                    ),
                    dense_cells=sum(g["cells"] for g in row["maps"]),
                    dense_maps_equal=all(g["scores_identical"] for g in row["maps"]),
                    matched_reuses=sum(g["mode"] == 2 for g in row["maps"]),
                    fine_entry_key_overlap=fine_key_overlap,
                    acquired_key_overlap=acquired_key_overlap,
                    inverse_ffts_saved=sum(
                        g["prepared_inverse_calls"] - g["reuse_inverse_calls"] for g in row["maps"]
                    ),
                )
            )
            for repetition, pair in enumerate(row["timing"]):
                for mode in pair["order"]:
                    metric = pair["measurements"][mode]
                    timing.append(
                        dict(
                            case=case,
                            visit=visit,
                            kind=kind,
                            retry=retry,
                            repetition=repetition,
                            mode=mode,
                            full_cpu_ms=metric["cpu_ns"] / 1e6,
                            full_wall_ms=metric["wall_ns"] / 1e6,
                            coarse_cpu_ms=metric["stages_cpu_ns"]["coarse_inclusive"] / 1e6,
                            rss_after_kib=metric["rss_after"]["rss_kib"],
                            rss_high_water_kib=metric["rss_after"]["hwm_kib"],
                        )
                    )
                    for idx, g in enumerate(metric["grid_receipts"]):
                        grids.append(
                            dict(
                                case=case,
                                visit=visit,
                                kind=kind,
                                retry=retry,
                                repetition=repetition,
                                mode=mode,
                                invocation=idx,
                                anchors=g["anchors"],
                                native_cpu_ms=g["native_cpu_ns"] / 1e6,
                                lookup_cpu_ms=g.get("lookup_cpu_ns", 0) / 1e6,
                                cache_mode=g.get("cache_mode"),
                                inverse_ffts=g["inverse_ffts"],
                                reserved_cache_bytes=g.get("storage_bytes", 0),
                            )
                        )
    return timing, grids, decisions


def bars(timing, decisions):
    rows = []
    for item in decisions:
        if item["kind"] != "radio":
            continue
        case, visit = item["case"], item["visit"]
        for mode, label in zip(MODES, LABELS, strict=True):
            runs = [r for r in timing if (r["case"], r["visit"], r["mode"]) == (case, visit, mode)]
            rows.append(
                dict(
                    case=case,
                    visit=visit,
                    retry=item["retry"],
                    method=label,
                    pairs=len(runs),
                    full_cpu_ms=median(x["full_cpu_ms"] for x in runs),
                    full_wall_ms=median(x["full_wall_ms"] for x in runs),
                    coarse_cpu_ms=median(x["coarse_cpu_ms"] for x in runs),
                    inverse_ffts_saved=item["inverse_ffts_saved"] if mode == "reuse" else 0,
                )
            )
    return rows


def chart(out, rows):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(11.1, 4.05), layout="constrained")
    axis_labels = ("Full detector", "Coarse stage")
    visits = [(r["case"], r["visit"], r["retry"]) for r in rows if r["method"] == LABELS[0]]
    names = [
        f"{case}\n{visit} · {'retry' if retry else 'primary'}" for case, visit, retry in visits
    ]
    for axis, label, metric in zip(
        axes, axis_labels, ("full_cpu_ms", "coarse_cpu_ms"), strict=True
    ):
        for name, delta, color in zip(LABELS, (-0.16, 0.16), ("#2f607b", "#b6593f"), strict=True):
            values = [r[metric] for r in rows if r["method"] == name]
            axis.bar([j + delta for j in range(len(visits))], values, 0.29, label=name, color=color)
        axis.set_xticks(range(len(visits)), names, rotation=25, ha="right")
        axis.set_title(label, loc="left")
        axis.set_ylabel("Median dual-receiver CPU (ms)")
        axis.set_ylim(0, 1.27 * max(r[metric] for r in rows))
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="y", alpha=0.20)
        axis.set_axisbelow(True)
    axes[0].legend(frameon=False, ncols=2, loc="upper center")
    fig.savefig(out / "stage.png", dpi=170)
    fig.savefig(out / "stage.pdf", metadata={"CreationDate": None})
    plt.close(fig)


def write_table(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def paired_deltas(rows):
    trials = {}
    for row in rows:
        if row["kind"] != "radio":
            continue
        key = row["case"], row["visit"], row["retry"], row["repetition"]
        trials.setdefault(key, {})[row["mode"]] = row
    return {
        ("retry" if had_retry else "primary"): {
            metric: median(
                pair["reuse"][metric] - pair["prepared"][metric]
                for key, pair in trials.items()
                if key[2] == had_retry
            )
            for metric in ("full_cpu_ms", "full_wall_ms", "coarse_cpu_ms")
        }
        for had_retry in (True, False)
    }


def assemble(work, out):
    timing, grids, decisions = flatten(receipts(work))
    plotted = bars(timing, decisions)
    out.mkdir(parents=True, exist_ok=True)
    for name in ("source-lock.json", *(f"{case}.json.gz" for case in ROSTER)):
        write(out / name, (work / name).read_bytes())
    for name, rows in (("timing", timing), ("grids", grids), ("stage", plotted)):
        write_table(out / f"{name}.csv", rows)
    save_json(out / "decisions.json", decisions)
    chart(out, plotted)
    radio = [d for d in decisions if d["kind"] == "radio"]
    summary = {}
    for had_retry in (True, False):
        pairs = [p for p in plotted if p["retry"] == had_retry]
        summary["retry" if had_retry else "primary"] = {
            mode: {
                key: median(p[key] for p in pairs if p["method"] == label)
                for key in ("full_cpu_ms", "full_wall_ms", "coarse_cpu_ms")
            }
            for mode, label in zip(MODES, LABELS, strict=True)
        }
    save_json(
        out / "qualification.json",
        dict(
            real_visits=len(radio),
            ordered_public_matches=sum(d["public_equal"] for d in radio),
            archived_matches=sum(d["installed_equal"] for d in radio),
            exact_dense_cells=sum(d["dense_cells"] for d in radio if d["dense_maps_equal"]),
            original_positive_candidates=sum(d["gate_positive"] for d in radio),
            reuse_count=sum(d["matched_reuses"] for d in radio),
            inverse_ffts_saved=sum(d["inverse_ffts_saved"] for d in radio),
            medians_ms=summary,
            paired_reuse_minus_prepared_ms=paired_deltas(timing),
            fine_entry_key_overlap=sum(d["fine_entry_key_overlap"] or 0 for d in radio),
            acquired_key_overlap=sum(d["acquired_key_overlap"] or 0 for d in radio),
        ),
    )
    save_json(
        out / "stage-figure.json",
        dict(
            version=1,
            id="retry-reuse",
            title="Reuse shared anchors for the original 22-anchor retry",
            sample="Six authenticated dual-receiver IQ visits from three producer releases",
            boundary="Saved physical IQ through prepared GLRT and its conditional same-visit retry",
            note="Both shared anchors have identical support. Full detector and coarse CPU "
            "include the cache fill on visits that end after the primary pass.",
            seal="stage-figure-lock.json",
            image="stage.png",
            pdf="stage.pdf",
            csv="stage.csv",
        ),
    )
    stage_names = ("stage-figure.json", "stage.png", "stage.pdf", "stage.csv")
    save_json(out / "stage-figure-lock.json", dict(files={n: _sha(out / n) for n in stage_names}))
    save_json(
        out / "evidence-lock.json",
        dict(
            files={
                p.name: _sha(p)
                for p in sorted(out.iterdir())
                if p.is_file() and p.name != "evidence-lock.json"
            }
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("out", type=Path)
    cli = parser.parse_args()
    assemble(cli.work, cli.out)
