"""Seal the host release, scout coverage, timings and compatibility evidence."""

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path
from statistics import median

from ..__main__ import ROOT, save_json, write
from . import scout_budget_build, scout_budget_eval
from .full_v5_check import PRODUCERS, _sha

REPORT = scout_budget_eval.REPORT
MODES = scout_budget_eval.MODES


def unpack(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def summarize(sweeps):
    rows = [r for sweep in sweeps for r in sweep["rows"] if r["status"] == "processed"]
    references = [r for sweep in sweeps for r in sweep["archive"]["receivers"]]
    result = {}
    final_matches = {}
    for mode in MODES:
        calls = [
            p
            for sweep in sweeps
            for i, r in enumerate(v for v in sweep["rows"] if v["status"] == "processed")
            for p in r["timings"][mode][int(i == 0) :]
        ]
        stages = Counter()
        for p in calls:
            for r in p["rows"]:
                stages.update(r)
        cpu = [p["detector_cpu_ms"] for p in calls]
        wall = [p["wall_s"] * 1000 for p in calls]
        support = [r["scout_coverage"][mode] for r in references]
        fits = [r["native_fit"][mode] for r in references]
        final_matches[mode] = {
            (sweep["id"], r["visit"], r["receiver"], m["production_rank"])
            for sweep in sweeps
            for r in sweep["archive"]["receivers"]
            for m in r["native_fit"][mode]["positive_matches"]
        }
        result[mode] = dict(
            late_calls=len(calls),
            total_cpu_ms=sum(cpu),
            median_cpu_ms=median(cpu),
            maximum_cpu_ms=max(cpu),
            median_wall_ms=median(wall),
            maximum_wall_ms=max(wall),
            cpu_within_20_ms=sum(t <= 20 for t in cpu),
            wall_within_20_ms=sum(t <= 20 for t in wall),
            stages_cpu_ms=dict(stages),
            native_positives=sum(r["native_positive"] for r in fits),
            tracked_positives_above_absolute_400khz=sum(
                abs(x[2]) > 400_000 for row in rows for rx in row["positives"][mode] for x in rx
            ),
            archive_positives=sum(r["archive_positive_count"] for r in references),
            archive_positive_epochs_in_scout=sum(p["exact"] for r in support for p in r),
            archive_top_positive_receivers=sum(bool(r) for r in support),
            archive_top_positive_in_scout=sum(
                min(r, key=lambda y: y["rank"])["exact"] for r in support if r
            ),
            unmatched_epoch_nearest_center=[
                p["nearest_circular_samples"] for r in support for p in r if not p["exact"]
            ],
            matched_final=len(final_matches[mode]),
            raw_cfo_matches=sum(
                abs(m["raw_cfo_delta_hz"]) < 1000 for r in fits for m in r["positive_matches"]
            ),
        )
    return dict(
        processed=len(rows),
        scheduled=sum(len(sweep["rows"]) for sweep in sweeps),
        scout_center_counts=dict(Counter(len(rx) for r in rows for rx in r["centers"])),
        changed_native_payloads=sum(not r["exact"] for r in rows),
        modes=result,
        gained_matched_records=sorted(final_matches["scout16"] - final_matches["control"]),
        lost_matched_records=sorted(final_matches["control"] - final_matches["scout16"]),
    )


def plant_summary(smoke):
    output = {}
    for name, row in smoke["results"].items():
        output[name] = {
            mode: dict(
                positive_counts=[len(rx) for rx in row["positives"][mode]],
                planted_matches=[
                    [
                        sum(abs(p[1] - epoch) <= 2 and abs(p[2] - cfo) < 1000 for p in rx)
                        for rx in row["positives"][mode]
                    ]
                    for epoch, cfo, _ in row.get("planted", [])
                ],
            )
            for mode in MODES
        }
    return output


def publish(work):
    if scout_budget_eval.sources() != json.loads((REPORT / "source-lock.json").read_bytes()):
        raise ValueError("The declared science source lock changed")
    sweeps = [unpack(REPORT / f"{case}-held.json.gz") for case in PRODUCERS]
    smoke = unpack(REPORT / "smoke.json.gz")
    for scope in sweeps:
        raw = work / f"{scope['id']}-held" / "fresh-before-archive.json.gz"
        if _sha(raw) != scope["fresh_receipt_sha256"] or unpack(raw) != scope["rows"]:
            raise ValueError("Sealed native samples differ from pre-archive receipt")
    release = scout_budget_eval.release(work)
    save_json(REPORT / "release.json", release)
    for mode in MODES:
        write(REPORT / f"{mode}-build.json", (work / mode / "build-receipt.json").read_bytes())
    tests = (
        ROOT / "tests/pipeline_eval/test_scout_budget.py",
        ROOT / "tests/pipeline_eval/test_scout_budget_centers.c",
    )
    save_json(REPORT / "test-lock.json", {p.name: _sha(p) for p in tests})
    save_json(
        REPORT / "qualification.json",
        dict(
            held=summarize(sweeps),
            cases={x["id"]: summarize([x]) for x in sweeps},
            synthetic=plant_summary(smoke),
            no_whole_recording=True,
        ),
    )
    names = (
        "source-lock.json",
        "test-lock.json",
        "PROTOCOL.md",
        "release.json",
        "control-build.json",
        "scout16-build.json",
        "smoke.json.gz",
        "compatibility.json",
        "qualification.json",
        *(f"{c}-{split}.json.gz" for c in PRODUCERS for split in ("held", "dev")),
    )
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=list(PRODUCERS),
            files={name: _sha(REPORT / name) for name in names},
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work", type=Path, default=scout_budget_build.ROOT)
    publish(p.parse_args().work)
