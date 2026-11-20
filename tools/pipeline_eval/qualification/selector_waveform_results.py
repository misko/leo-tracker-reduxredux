"""Score and compare the complete lane-selector replay with its frozen prepared predecessor."""

import argparse
import csv
import gzip
import json
from pathlib import Path
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import local_output, save_json
from ..scoring import ARMS, distribution
from ..variants import prepared_hotpath_peaks
from . import capture_whole_results as whole
from . import prepared_capture_waveform_results as prepared
from . import selector_waveform as trial
from .full_v5_check import _sha
from .prefix_figures import csv_file

CHART = "lane-peak-selector-waveform"
STAGE = "lane-peak-selector-waveform-timing"
BASE_ASSEMBLE = whole.assemble
BASE_COMPACT = whole.compact_rows
RENDER = whole.generate
PREDECESSOR = trial.prepared.METHOD


def baseline_file(lock, name):
    path = trial.PREVIOUS / name
    return whole_iq.checked(path, lock["comparison"]["prepared"][str(path)])


def baseline_rows(lock, name):
    with baseline_file(lock, name).open(newline="") as stream:
        return list(csv.DictReader(stream))


def assemble(case, lock, shards):
    native, counts = BASE_ASSEMBLE(case, lock, shards)
    digest = trial.BASE.recording.digest
    selector = lock["sources"][str(Path(prepared_hotpath_peaks.__file__))]
    provenance = native["provenance"]
    source = native["source"]
    detector = digest([provenance["detector_sha256"], selector])
    analysis = digest([source["analysis_manifest_sha256"], detector])
    provenance.update(
        scope="fresh original capture detector with prepared FFT and exact lane peak selector",
        detector_sha256=detector,
        run_id="replay-" + analysis[7:39],
    )
    source["analysis_manifest_sha256"] = analysis
    return native, counts


def compact_rows(work, lock, audit):
    rows, clocks, historical = BASE_COMPACT(work, lock, audit)
    path = baseline_file(lock, "positions.jsonl.gz")
    (old,) = [r for r in whole.rows_from(path) if r["method"] == PREDECESSOR]
    if old["id"] != trial.prepared.IDENT or any(old[k] != rows[0][k] for k in whole.MINIMAL):
        raise ValueError("prepared position does not share the complete input bindings")
    return rows + [old], clocks, historical | {"prepared_sha256": _sha(path)}


def paired_timing(previous, previous_cache, current, current_cache):
    def index(rows):
        result = {int(r["visit"]): r for r in rows}
        if len(result) != len(rows):
            raise ValueError("duplicate visit in the timing or cache receipt")
        return result

    previous, current, previous_cache, current_cache = map(
        index, (previous, current, previous_cache, current_cache)
    )
    if (
        previous.keys() != previous_cache.keys()
        or current.keys() != current_cache.keys()
        or not current.keys() <= previous.keys()
    ):
        raise ValueError("timing support differs from authenticated cache support")
    result = []
    for visit in sorted(current):
        a, b, ca, cb = previous[visit], current[visit], previous_cache[visit], current_cache[visit]
        if a["status"] != b["status"] or ca["status"] != a["status"] or cb["status"] != b["status"]:
            raise ValueError("timing and cache receipts disagree on capture validity")
        row = dict(visit=visit, status=b["status"])
        for name, timing, cache in (("prepared", a, ca), ("selector", b, cb)):
            cpu, wall, coarse = (
                float(timing["cpu_ms"]),
                float(timing["wall_ms"]),
                int(cache["coarse_cpu_ns"]) / 1e6,
            )
            if int(timing["folded_calls"]) != int(cache["calls"]) or not 0 <= coarse <= cpu:
                raise ValueError("coarse work does not fit inside complete detector CPU")
            row.update(
                {
                    f"{name}_{f}": v
                    for f, v in (
                        ("cpu_ms", cpu),
                        ("wall_ms", wall),
                        ("coarse_ms", coarse),
                        ("other_cpu_ms", cpu - coarse),
                    )
                }
            )
        result.append(row)
    return result


def timing_stats(rows):
    valid = [r for r in rows if r["status"] == "processed"]
    result = {}
    for mode in ("prepared", "selector"):
        totals = {}
        for metric in ("cpu_ms", "wall_ms", "coarse_ms", "other_cpu_ms"):
            samples = [r[f"{mode}_{metric}"] for r in valid]
            totals[metric] = distribution(samples)
            totals[metric]["sum_s"] = sum(samples) * 1e-3
            if metric in ("cpu_ms", "wall_ms"):
                totals[metric]["within_20"] = sum(v <= 20 for v in samples)
        result[mode] = totals
    if valid:
        result["prepared_minus_selector_cpu_ms"] = distribution(
            [r["prepared_cpu_ms"] - r["selector_cpu_ms"] for r in valid]
        )
    return result


def endpoint(result):
    if result["status"] != "ok":
        return None
    return {
        arm: dict(
            latlon=result["arms"][arm]["latlon"],
            conditional_rms_hz=result["arms"][arm]["rf_rms_hz"],
            frequency_score=result["metrics"][arm + "_frequency_score"],
            observations=result["metrics"]["observations"],
            tracks=result["metrics"]["tracks"],
            compact_projections=result["metrics"]["compact_projections"],
        )
        for arm in ARMS
    }


def compare(work, out, raw, grid):
    lock, _ = trial.BASE.configure(work)
    audit = whole_iq.read(out / "audit.json")
    previous = whole_iq.read(baseline_file(lock, "audit.json"))
    rows = paired_timing(
        baseline_rows(lock, "timing.csv"),
        baseline_rows(lock, "cache.csv"),
        list(csv.DictReader((out / "timing.csv").read_text().splitlines())),
        grid,
    )
    csv_file(out / "paired-timing.csv", rows)
    positions = {r["method"]: r["result"] for r in whole.rows_from(out / whole.POS)}
    actual, reference = (endpoint(positions[method]) for method in (trial.METHOD, PREDECESSOR))
    archive = endpoint(positions[whole.ARCHIVED]) if whole.ARCHIVED in positions else None
    actual_end = audit["position"].get("actual", {}).get("end")
    raw_start = whole_iq.read(work / "launch.json")["start_s"]
    previous_receipt = whole_iq.read(baseline_file(lock, "prediction-lock.json"))
    previous_launch = whole_iq.read(
        whole_iq.checked(
            trial.PREVIOUS / "receipts/launch.json",
            previous_receipt["files"]["receipts/launch.json"],
        )
    )
    stages = {}
    for mode, receipt, method in (
        ("prepared", previous["position"]["actual"], PREDECESSOR),
        ("selector", audit["position"].get("actual"), trial.METHOD),
        ("archive", audit["position"].get("archive"), whole.ARCHIVED),
    ):
        if receipt:
            end = receipt.get("end")
            stages[mode] = dict(
                wall_s=receipt["wall_s"],
                cgroup_cpu_s=end["cpu.stat.usage_usec"] / 1e6 if end else None,
                stage_wall_s=positions[method]["metrics"].get("stage_s"),
            )
    summary = dict(
        paired_visit_count=len(rows),
        paired_valid_count=raw["valid"],
        timings=timing_stats(rows),
        host_raw_wall_s=dict(prepared=previous["raw"]["wall_s"], selector=raw["wall_s"]),
        host_worker_cpu_s=dict(
            prepared=previous["raw"]["completed_worker_cpu_s"],
            selector=raw["completed_worker_cpu_s"],
        ),
        raw_start_monotonic_s=raw_start,
        measurement_to_coordinates_wall_s=dict(
            prepared=previous["position"]["actual"]["end"]["monotonic_s"]
            - previous_launch["start_s"],
            selector=(actual_end["monotonic_s"] - raw_start) if actual_end else None,
        ),
        position_timings=stages,
        position_endpoints=dict(selector=actual, prepared=reference, archive=archive),
        position_equal_to_prepared=actual == reference if actual and reference else None,
        position_equal_to_archive=actual == archive if actual and archive else None,
    )
    if "measured_native_sha256" in raw:
        before = json.loads(gzip.decompress(baseline_file(lock, "native.json.gz").read_bytes()))
        after = whole_iq.read(work / "measured.json")
        summary["measured_vs_prepared"] = whole.parity(after, before)
        summary["canonical_probe_sha256"] = {
            name: trial.BASE.recording.digest(document["source"]["probes"])
            for name, document in (("prepared", before), ("selector", after))
        }
    save_json(out / "comparison.json", summary)
    return summary


def timing_figure(out, work, raw, grid):
    prepared.add_cache(out, raw, grid)
    summary = compare(work, out, raw, grid)
    asset_names = ("comparison.json", "paired-timing.csv")
    receipt = whole_iq.read(out / "prediction-lock.json")
    receipt["files"].update({name: _sha(out / name) for name in asset_names})
    receipt["selector_publisher_sha256"] = _sha(Path(__file__))
    save_json(out / "prediction-lock.json", receipt)
    if not summary["paired_valid_count"]:
        return
    detail = (
        "Saved-IQ detector timings exclude decode, source authentication and position. "
        "Whole runs share the host and CPU assignments and ran at different times. "
        "The vertical line marks 20 ms."
    )
    title = "Exact lane peak selector on complete saved IQ"
    valid = summary["paired_valid_count"]
    fig, axes = whole.plot.canvas(
        title, f"DS26-0237 · {valid:,} matched valid dual-antenna visits", detail
    )
    for ax, metric, stage_title in zip(
        axes, ("cpu_ms", "wall_ms"), ("Detector CPU", "Detector wall"), strict=True
    ):
        metric_values = summary["timings"]
        pairs = [
            tuple(metric_values[mode][metric][p] for mode in ("prepared", "selector"))
            for p in ("p50", "p95")
        ]
        whole.plot.paired(
            ax,
            ["Median", "95th percentile"],
            pairs,
            title=stage_title,
            xlabel="Host milliseconds",
            fmt=".1f",
        )
        ax.axvline(20, color=whole.plot.DIAGNOSTIC, linewidth=1.4, linestyle="--")
    whole.plot.key(fig, "Prepared detector", "Prepared + lane selector")
    fig.savefig(out / "timing.png", dpi=165, facecolor="white")
    fig.savefig(out / "timing.pdf", facecolor="white", metadata={"CreationDate": None})
    whole.plot.plt.close(fig)
    files = ("timing.png", "timing.pdf", "timing.csv", "prediction-lock.json", *asset_names)
    save_json(out / "timing-lock.json", dict(files={name: _sha(out / name) for name in files}))
    save_json(
        out / "stage-figure.json",
        dict(
            version=1,
            id=STAGE,
            title=title,
            sample=f"{valid:,} matched valid visits of {raw['scheduled']:,} scheduled visits",
            boundary="Resident CI16 through both receivers' original detector and projection",
            note=detail,
            seal="timing-lock.json",
            image="timing.png",
            pdf="timing.pdf",
            csv="paired-timing.csv",
        ),
    )


def generate(out, *, evidence):
    spec = evidence / "figures.json"
    document = whole_iq.read(spec)
    (chart,) = document["charts"]
    chart.update(
        id=CHART,
        title="Position from the exact lane peak selector",
        caption="DS26-0237 used its original 25 km offer and causal catalogue. "
        "Both compared detectors replayed the original capture from authenticated saved IQ.",
    )
    chart["provenance"].append("comparison.json")
    for row in chart["series"]:
        if row["key"] == "one":
            row["label"] = "Fresh complete prepared + lane selector"
    # The source publisher may omit its archive series when a raw deadline is hit.
    chart["series"] = [row for row in chart["series"] if row["key"] != "one_native_factors"]
    chart["series"].append(
        dict(
            key="one_native_factors",
            file=whole.POS,
            value=PREDECESSOR,
            label="Earlier complete prepared detector",
            native_field="paired_capture_sha256",
            match=whole.MINIMAL,
        )
    )
    save_json(spec, document)
    RENDER(out, evidence=evidence)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("position", "publish"))
    parser.add_argument("--work", type=local_output, default=trial.WORK)
    args = parser.parse_args()
    with (
        trial.configured(),
        patch.multiple(whole, REPORT=trial.REPORT, assemble=assemble, compact_rows=compact_rows),
    ):
        if args.action == "position":
            whole.position(args.work)
        else:
            grid = prepared.cache(args.work)
            with patch.multiple(
                whole,
                timing_figure=lambda out, a: timing_figure(out, args.work, a, grid),
                generate=generate,
            ):
                whole.publish(args.work, trial.REPORT)


if __name__ == "__main__":
    main()
