"""Seal prepared-cache telemetry with the full waveform and position controls."""

import argparse
import json
from pathlib import Path
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import local_output, save_json
from . import capture_whole_results as whole
from . import prepared_capture_waveform as trial
from .full_v5_check import _sha
from .prefix_figures import csv_file

CHART = "prepared-original-waveform"
STAGE = CHART + "-timing"
ORIGINAL_ASSEMBLE = whole.assemble
ORIGINAL_FIGURE = whole.timing_figure
ORIGINAL_RENDER = whole.generate
ORIGINAL_CANVAS = whole.plot.canvas


def joined_cache(detector_rows, diagnostic_rows, valid_visits, *, complete=True):
    joined = []
    if len(diagnostic_rows) > len(detector_rows) or (
        complete and len(diagnostic_rows) != len(detector_rows)
    ):
        raise ValueError("raw and grid telemetry cover different visit counts")
    for index, (visit, telemetry) in enumerate(zip(detector_rows, diagnostic_rows, strict=False)):
        if (
            telemetry["ordinal"] != index
            or telemetry["calls"] != visit["grid_calls"]
            or telemetry["cache_hits"] + telemetry["cold_builds"] != telemetry["calls"]
            or (telemetry["calls"] > 0) != (visit["status"] == "processed")
            or (telemetry["cold_builds"] > 0) != (telemetry["filter_ffts"] > 0)
            or (telemetry["calls"] > 0) != (telemetry["input_ffts"] > 0)
        ):
            raise ValueError("cache reuse evidence disagrees with actual detector work")
        if visit["visit"] in valid_visits:
            joined.append(dict(visit=visit["visit"], status=visit["status"], **telemetry))
    return joined


def cache(work):
    lock, _ = trial.base.configure(work)
    shards, workers, _ = whole.collect(work, lock)
    schedule = {r["visit"] for _, rows in shards.values() for r in rows}
    output = []
    for cpu, _, _ in lock["workers"]:
        with (work / f"cpu-{cpu}.jsonl").open("rb") as stream:
            rows = [json.loads(line) for line in stream if line.endswith(b"\n")]
        log = (work / f"cpu-{cpu}.log").read_text().splitlines()
        lines = [
            json.loads(line.removeprefix(trial.TRACE))
            for line in log
            if line.startswith(trial.TRACE)
        ]
        selected = joined_cache(
            [r for r in rows if r["kind"] == "visit"],
            lines,
            schedule,
            complete=workers[str(cpu)]["exit_code"] == 0,
        )
        output.extend(dict(cpu=cpu, **r) for r in selected)
    if len(output) != len(schedule):
        raise ValueError("a measured authenticated chunk lacks its cache audit")
    return sorted(output, key=lambda row: row["visit"])


def assemble(case, lock, shards):
    native, counts = ORIGINAL_ASSEMBLE(case, lock, shards)
    native["provenance"]["scope"] = (
        "fresh original capture detector with prepared full-lattice FFT and verified refinement"
    )
    return native, counts


def add_cache(out, audited_raw, grid):
    csv_file(out / "cache.csv", grid)
    audit = whole_iq.read(out / "audit.json")
    summary = {
        k: sum(r[k] for r in grid)
        for k in (
            "calls",
            "cache_hits",
            "cold_builds",
            "filter_ffts",
            "input_ffts",
            "inverse_ffts",
            "spans",
        )
    }
    summary.update(
        coarse_cpu_s=1e-9 * sum(r["coarse_cpu_ns"] for r in grid),
        peak_workspace_bytes=max((r["peak_workspace"] for r in grid), default=0),
        measured_visit_count=len(grid),
    )
    if summary["calls"] != audited_raw["measured_folded_calls"]:
        raise ValueError("unaccounted original FFT work in complete archive ledger")
    audit["cache"] = summary
    save_json(out / "audit.json", audit)
    seal = whole_iq.read(out / "prediction-lock.json")
    seal["files"].update({name: _sha(out / name) for name in ("audit.json", "cache.csv")})
    seal["cache_publisher_sha256"] = _sha(Path(__file__))
    save_json(out / "prediction-lock.json", seal)


def figure(out, audit, grid):
    add_cache(out, audit, grid)

    def canvas(_, __, detail):
        return ORIGINAL_CANVAS(
            "Prepared original FFT on a complete lower-edge recording",
            "DS26-0237 · CPU and wall per valid dual-antenna visit",
            detail,
        )

    with patch.object(whole.plot, "canvas", canvas):
        ORIGINAL_FIGURE(out, audit)
    desc = out / "stage-figure.json"
    if desc.exists():
        save_json(
            desc,
            dict(
                whole_iq.read(desc),
                id=STAGE,
                title="Complete prepared original detector timings on DS26-0237",
            ),
        )


def render(out, *, evidence):
    spec = evidence / "figures.json"
    document = whole_iq.read(spec)
    (chart,) = document["charts"]
    chart.update(
        id=CHART,
        title="Prepared original detector from complete saved IQ",
        caption="DS26-0237 used its original 25 km offer and causal catalogue. "
        "The prepared FFT cache ran on every valid visit.",
    )
    chart["provenance"].append("cache.csv")
    save_json(spec, document)
    ORIGINAL_RENDER(out, evidence=evidence)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("position", "publish"))
    parser.add_argument("--work", type=local_output, default=trial.WORK)
    args = parser.parse_args()
    with trial.configured(), patch.multiple(whole, REPORT=trial.REPORT, assemble=assemble):
        if args.action == "position":
            whole.position(args.work)
        else:
            grid = cache(args.work)
            with patch.multiple(
                whole, timing_figure=lambda out, a: figure(out, a, grid), generate=render
            ):
                whole.publish(args.work, trial.REPORT)


if __name__ == "__main__":
    main()
