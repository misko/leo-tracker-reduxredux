"""Combine prior dual-IQ clocks at the pre-detector routing boundary."""

import gzip
import json
from math import isclose
from pathlib import Path
from statistics import mean

from .. import whole_iq
from ..__main__ import ROOT
from ..scoring import distribution
from ..variants.selective_capture import visit_pairs
from .full_v5_check import _sha
from .margin_admission_inputs import WIDE, read
from .support_cross_trial import checked

LINEAGE = ROOT / "reports/2026_11_19_receiver_screening/detector-origins/lineage"
RECOVERY = Path("/home/mouse9911/.cache/leo-scout-qa-Jk10ZLm9/recovery")
COMPLETE = Path("/srv/bulk/leo-dev/scout-comparison-l7wQ2aPF/run")
MILLISECONDS = 1000
DEADLINE = 20


def full_wide_cost(ident, entry, document, published):
    run = (RECOVERY if ident == "DS26-0014" else COMPLETE) / ident / "control"
    timing = read(run / "raw.json")
    checks = ("counts", "raw_authority", "clock_sha256", "excluded_sha256", "probes_sha256")
    if (
        any(timing[k] != published[k] for k in checks)
        or timing["native_sha256"].removeprefix("sha256:") != entry["wide_native_sha256"]
    ):
        raise ValueError("full wide timing is bound to different native factors")
    entries = dict(visit_pairs(document["source"]["probes"]))
    measured, files = {}, {"raw.json": _sha(run / "raw.json")}
    for i, lane in enumerate(timing["lanes"]):
        recorded = run / "recording" / f"replayed-{i}.jsonl"
        files[recorded.name] = _sha(recorded)
        with recorded.open() as stream:
            data = (
                row
                for row in map(json.loads, stream)
                if row["kind"] == "visit" and row["status"] == "processed"
            )
            for row, (wall, cpu) in zip(data, lane["native_timings_s"], strict=True):
                visit = row["visit"]
                if visit in measured or tuple(row["probes"]) != entries[visit]:
                    raise ValueError("dual-visit clocks do not follow the original wide factors")
                measured[visit] = (cpu * MILLISECONDS, wall * MILLISECONDS)
    if set(measured) != entries.keys() or len(measured) != published["dual_calls"]:
        raise ValueError("missing original wide call telemetry")
    cpu, wall = list(zip(*measured.values(), strict=True))
    for values, label in ((cpu, "detector_call_cpu_ms"), (wall, "detector_call_wall_ms")):
        summary = distribution(values)
        if any(
            not isclose(summary[key], published[label][key], abs_tol=1e-8)
            for key in published[label]
        ):
            raise ValueError("dual-call timings do not reproduce the sealed distribution")
    if sum(x <= DEADLINE for x in wall) != published["within_20ms"]:
        raise ValueError("dual-call timing misses do not reproduce the sealed count")
    return measured, files


def capture_panel():
    manifest = read(LINEAGE / "source-lock.json")["files"]
    cohorts = {}
    for ident in ("DS26-0036", "DS29-0082", "DS26-0237", "DS29-0174"):
        name = f"{ident}.json.gz"
        path = whole_iq.checked(LINEAGE / name, manifest[name])
        data = json.loads(gzip.decompress(path.read_bytes()))
        cohorts[ident] = dict(
            sha256=manifest[name],
            visits=[
                dict(visit=row["visit"], calls=row["timings"]["capture"])
                for row in data["rows"]
                if row["timings"]["capture"]
            ],
        )
    return cohorts


def route_cost(measured, selected, total_selector_ms, old_cpu_point, old_cpu_min, old_cpu_max):
    cpu, wall = zip(*measured.values(), strict=True)
    wide_removed = sum(measured[v][0] for v in selected)
    count = len(cpu)
    wide_on_time = sum(t <= DEADLINE for t in wall)
    departed_on_time = sum(measured[v][1] <= DEADLINE for v in selected)
    retained = sum(cpu) - wide_removed + total_selector_ms

    def estimate(clock):
        return (retained + len(selected) * clock) / count

    return dict(
        admitted=count,
        routed=len(selected),
        routed_fraction=len(selected) / count,
        actual_stock_cpu_ms=mean(cpu),
        routed_wide_counterfactual_cpu_ms=wide_removed,
        selector_cpu_ms=total_selector_ms,
        estimated_cpu_ms=estimate(old_cpu_point),
        box_low_cpu_ms=estimate(old_cpu_min),
        box_high_cpu_ms=estimate(old_cpu_max),
        original_capture_cpu_ms=old_cpu_point,
        estimated_headroom_ms=DEADLINE - estimate(old_cpu_point),
        actual_wide_wall_le_20ms=wide_on_time,
        modeled_mixed_wall_le_20ms=wide_on_time - departed_on_time,
    )


def estimates(selection, work):
    complete = read(checked(WIDE, "resources.json"))
    capture = capture_panel()
    sample = {
        ident: [call for visit in info["visits"] for call in visit["calls"]]
        for ident, info in capture.items()
    }
    clocks = [c for rows in sample.values() for c in rows]
    if any(row["wall_ms"] <= DEADLINE for row in clocks):
        raise ValueError("deadline model requires validation against the original timing sample")
    low, high = (f(c["cpu_ms"] for c in clocks) for f in (min, max))
    means = {ident: mean(c["cpu_ms"] for c in rows) for ident, rows in sample.items()}
    fits, authority = [], {}
    for ident, entry in selection["cases"].items():
        raw = whole_iq.checked(work / f"{ident}-wide.json", entry["wide_native_sha256"])
        measured, files = full_wide_cost(ident, entry, read(raw), complete[ident]["control"])
        authority[ident] = files
        for mode, decisions in entry["decisions"].items():
            chosen = {r["visit"] for r in decisions}
            point = means.get(ident, mean(means.values()))
            fits.append(
                dict(
                    id=ident,
                    condition=mode,
                    clock_source="same recording" if ident in means else "equal cohort transfer",
                    **route_cost(
                        measured, chosen, entry["selector_cpu_ms"][mode], point, low, high
                    ),
                )
            )
    return fits, dict(
        wide_clock_files=authority,
        original_capture_cohorts=capture,
        pooled_capture_cpu_range_ms=[low, high],
        pooled_capture_wall_min_ms=min(c["wall_ms"] for c in clocks),
    )
