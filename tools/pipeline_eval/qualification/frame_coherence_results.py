"""Publish an auditable detector-stage figure from locked frame-coherence replays."""

import argparse
import csv
import gzip
import io
import json
from pathlib import Path
from statistics import median, quantiles

from ..__main__ import ROOT, encoded, save_json, write
from . import factor_cross, oracle_start
from .frame_coherence_eval import CASES, REPORT, WORK, bind
from .full_v5_check import _from_native, _sha, compare_probes

BUCKETS = ((4, 2), (4, 20), (16, 2), (16, 20))
SOURCES = ("ordinary", "raw", "sham")
MODES = ("stock", "causal", "sham")


def capture(work, name):
    return json.loads(gzip.decompress((work / name).read_bytes()))


def timing_hits(epoch, lists):
    out = {}
    for name, centers in lists.items():
        for depth, tolerance in BUCKETS:
            if name == "ordinary" and depth != 4:
                continue
            out[f"{name}_{depth}_{tolerance}"] = (
                any(oracle_start.distance(c, epoch) <= tolerance for c in centers[:depth])
                if epoch is not None
                else None
            )
        out[f"{name}_nearest_samples"] = (
            min((oracle_start.distance(e, epoch) for e in centers), default=None)
            if epoch is not None
            else None
        )
    return out


def score_real(receipt):
    row = {k: receipt[k] for k in ("case", "visit", "receiver", "kind", "stratum", "status")}
    row["edge"] = receipt["archive_probe"]["edge"]
    row["iq_sha256"] = receipt["iq_sha256"]
    if row["status"] != "processed":
        return dict(row, reason=receipt["reason"])
    lane = row["receiver"]
    target = receipt["target"]
    measurement = receipt["measurement"]
    native = measurement["native"]
    ordinary = native["traces"]["off"][lane]["ordinary"]
    epoch = oracle_start.exact_epoch(target)
    row.update(
        timing_hits(
            epoch,
            dict(
                ordinary=ordinary,
                raw=measurement["centers"][lane],
                sham=measurement["sham_centers"][lane],
            ),
        )
    )
    row.update(
        target_epoch=epoch,
        target_cfo_hz=target[factor_cross.CFO],
        target_margin=target[factor_cross.MARGIN],
    )
    for mode in MODES:
        probes = receipt["probes"][mode]
        public = native["payloads"][mode]["rows"][lane]
        outcome = oracle_start.endpoints(target, probes[lane], public)
        # Compare other science changes even when the registered target is absent.
        other = [
            dict(
                p,
                candidates=[
                    c for c in p["candidates"] if not oracle_start.target_matches(c, target)
                ],
            )
            for p in (receipt["probes"]["stock"][lane], probes[lane])
        ]
        paired = compare_probes(*other, 10_000_000)
        row.update({f"{mode}_{k}": v for k, v in outcome.items()})
        row.update(
            {
                f"{mode}_other_added": paired["native_only"],
                f"{mode}_other_lost": paired["production_only"],
            }
        )
        row[f"{mode}_payload_changed"] = encoded(native["payloads"][mode]) != encoded(
            native["payloads"]["stock"]
        )
        for scope in ("cpu", "wall"):
            row[f"{mode}_{scope}_ms"] = native["timings"][mode][0][f"{scope}_ns"] / 1e6
    row["hint_replaced_center"] = native["traces"]["causal"][lane]["selected"] != ordinary
    for scope in ("cpu", "wall"):
        row[f"scout_{scope}_ms"] = measurement["scout_times"][0][f"{scope}_ns"] / 1e6
    return row


def score_synthetic(name, receipt):
    data, plant = receipt["measurement"], receipt["target"]
    native = data["native"]
    target = {
        "integer_epoch_sample": plant["epoch"],
        "fractional_epoch_offset_samples": 0,
        factor_cross.CFO: plant["cfo_hz"],
    }
    for lane, ranks in enumerate(data["centers"]):
        row = dict(
            control=name,
            receiver=lane,
            iq_sha256=receipt["iq_sha256"],
            raw_proposals=len(ranks),
            target_epoch=plant["epoch"],
            target_cfo_hz=plant["cfo_hz"],
        )
        row.update(
            timing_hits(
                plant["epoch"],
                dict(
                    ordinary=native["traces"]["off"][lane]["ordinary"],
                    raw=ranks,
                    sham=data["sham_centers"][lane],
                ),
            )
        )
        for mode in MODES:
            candidates = native["payloads"][mode]["rows"][lane]["candidates"]
            factors = [_from_native(i, c) for i, c in enumerate(candidates)]
            gated = [c for c in factors if c is not None and c[factor_cross.GATE]]
            row[f"{mode}_gate_count"] = len(gated)
            row[f"{mode}_plant_recovered"] = (
                any(oracle_start.target_matches(c, target, exact_cfo=True) for c in gated)
                if plant["plant"]
                else None
            )
        yield row


def write_csv(path, rows):
    out = io.StringIO(newline="")
    csv_writer = csv.DictWriter(out, fieldnames=list(dict.fromkeys(k for r in rows for k in r)))
    csv_writer.writeheader()
    csv_writer.writerows(rows)
    write(path, out.getvalue().encode())


def describe(values):
    return dict(
        n=len(values),
        median=median(values),
        p90=quantiles(values, n=10, method="inclusive")[-1],
    )


def summary(measured, rows, synth, controls):
    groups = {}
    for kind in ("miss", "matched"):
        group = [r for r in rows if r["kind"] == kind and r["status"] == "processed"]
        flags = {
            k: sum(r[k] for r in group)
            for k, value in group[0].items()
            if isinstance(value, bool) and k != "hint_replaced_center"
        }
        groups[kind] = dict(n=len(group), **flags)
    scout = [
        m for r in measured if r["status"] == "processed" for m in r["measurement"]["scout_times"]
    ]
    runs = [r for r in rows if r["status"] == "processed"]
    cost = {}
    for scope in ("cpu", "wall"):
        cost[f"scout_{scope}_ms"] = describe([t[f"{scope}_ns"] / 1e6 for t in scout])
        for mode in MODES:
            cost[f"{mode}_{scope}_ms"] = describe([r[f"{mode}_{scope}_ms"] for r in runs])
        cost[f"raw_plus_native_{scope}_ms"] = describe(
            [r[f"scout_{scope}_ms"] + r[f"causal_{scope}_ms"] for r in runs]
        )
    return dict(
        status="stage_only",
        hardware="CPU 4, host x86, single thread, nice 10",
        position_attempted=False,
        measured_real_visits=len(runs),
        planned_real_visits=len(rows),
        no_other_raw_windows=True,
        real=groups,
        controls=synth,
        whole_dual_rx_timing=cost,
        warm_tracemalloc_peak_bytes={
            name: r["measurement"]["allocator_peak_bytes"]
            for name, r in controls.items()
            if "allocator_peak_bytes" in r["measurement"]
        },
    )


def plot(document):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    fig, axs = plt.subplots(1, 3, figsize=(12.5, 3.65), layout="constrained")
    styles = (
        ("ordinary", "Wide differential", "#64748B"),
        ("raw", "Three-frame coherence", "#036E79"),
        ("sham", "Shifted sham", "#C47636"),
    )
    x = np.arange(len(BUCKETS))
    for ax, kind, title in zip(
        axs[:2],
        ("miss", "matched"),
        ("Capture positives missed by wide", "Capture positives kept by wide"),
        strict=True,
    ):
        row = document["real"][kind]
        for pos, (key, label, color) in enumerate(styles):
            present = [
                (j, row[f"{key}_{depth}_{tol}"])
                for j, (depth, tol) in enumerate(BUCKETS)
                if f"{key}_{depth}_{tol}" in row
            ]
            ix, count = zip(*present, strict=True)
            bars = ax.bar(np.asarray(ix) + (pos - 1) * 0.24, count, 0.22, label=label, color=color)
            ax.bar_label(bars, fontsize=8, padding=2)
        ax.set(
            title=f"{title} (n={row['n']})",
            ylim=(0, row["n"] + 1),
            xticks=x,
            xticklabels=[f"Top {d}\n±{t}" for d, t in BUCKETS],
            yticks=range(0, row["n"] + 1, row["n"] // 4),
            xlabel="Proposal depth and tolerance (samples)",
        )
        ax.set_ylabel("Visits within epoch tolerance")
        ax.spines[["top", "right"]].set_visible(False)
    axs[0].legend(frameon=False, fontsize=8)
    ax = axs[-1]
    cost = document["whole_dual_rx_timing"]
    keys = ("stock_cpu_ms", "scout_cpu_ms", "raw_plus_native_cpu_ms")
    labels = ("Wide native", "Coherence scout", "Scout + hinted native")
    bars = ax.barh(
        labels, [cost[k]["median"] for k in keys], color=["#64748B", "#036E79", "#036E79"]
    )
    ax.axvline(20, linestyle="--", color="#913A38", linewidth=1)
    for bar in bars:
        v = bar.get_width()
        ax.text(
            v - 0.45,
            bar.get_y() + bar.get_height() / 2,
            f"{v:.1f}",
            color="white",
            ha="right",
            va="center",
        )
    ax.set(title="Median CPU per dual-RX visit", xlabel="Host CPU time (ms)", xlim=(0, 33))
    ax.invert_yaxis()
    ax.text(
        20.55,
        0.52,
        "Visit duration",
        transform=ax.get_xaxis_transform(),
        color="#913A38",
        fontsize=8,
    )
    ax.spines[["top", "right"]].set_visible(False)
    missed = document["real"]["miss"]
    fig.suptitle(
        "Raw three-frame timing coherence · 24 authenticated saved-IQ visits\n"
        f"Rank-one hint recovered {missed['causal_passes']} of {missed['n']} missed targets"
    )
    fig.savefig(REPORT / "stage.png", dpi=160)
    fig.savefig(REPORT / "stage.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


def publish(work):
    plan, _ = bind(work)
    names = (*(f"{c}.json.gz" for c in CASES), "controls.json.gz")
    replay = []
    for case, name in zip(CASES, names[:-1], strict=True):
        realized = capture(work, name)
        if len(realized) != len(plan["cases"][case]) or any(
            any(r.get(k) != value for k, value in expected.items())
            for r, expected in zip(realized, plan["cases"][case], strict=True)
        ):
            raise ValueError("Raw measurements differ from the frozen schedule")
        replay.extend(realized)
    raw = [score_real(r) for r in replay]
    controls = capture(work, names[-1])
    synth = [row for name, receipt in controls.items() for row in score_synthetic(name, receipt)]
    document = summary(replay, raw, synth, controls)
    for name in names:
        write(REPORT / name, (work / name).read_bytes())
    save_json(REPORT / "qualification.json", document)
    write_csv(REPORT / "stage.csv", raw)
    write_csv(REPORT / "controls.csv", synth)
    plot(document)
    save_json(
        REPORT / "stage-figure.json",
        dict(
            version=1,
            id="frame-coherence",
            title="Raw three-frame timing coherence",
            sample="24 dual-RX visits from four recordings, plus 14 synthetic controls",
            boundary="Dual-RX saved CI16 → 40,000-sample coherence → real wide GLRT",
            note="The blind hint recovered 0 of 16 missed capture targets. Position unmeasured.",
            seal="prediction-lock.json",
            image="stage.png",
            pdf="stage.pdf",
            csv="stage.csv",
        ),
    )
    files = (
        *names,
        "PROTOCOL.md",
        "README.md",
        "templates.json",
        "input-lock.json.gz",
        "qualification.json",
        "stage.csv",
        "controls.csv",
        "stage.png",
        "stage.pdf",
        "stage-figure.json",
    )
    sources = (Path(__file__), ROOT / "tests/pipeline_eval/test_frame_coherence.py")
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=CASES,
            files={name: _sha(REPORT / name) for name in files},
            sources={str(path.relative_to(ROOT)): _sha(path) for path in sources},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=WORK)
    publish(parser.parse_args().work)
