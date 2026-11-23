"""Price an 8 ms signed antenna search followed by a conditional 12 ms restart."""

import argparse
from collections import Counter
from contextlib import ExitStack
import gzip
from math import isfinite, remainder
from pathlib import Path
from statistics import median
from time import process_time_ns
import json

import numpy as np

from .eight_ms_primary_trial import (
    BINDING, BINDING_SHA, HERE, PILOT_SHA, WEAK_ARCHIVE, WINDOWS,
    NativePath, arm_order, center, check_machine, encoded, read_archive, read_physical, verified, window, write,
)

PARENT_SHA = "a6b67123abe0a740b2843f08cc1cde7f603e6f18dd890ad15cc3b3243fc317b3"


def needs_restart(factors):
    if not factors:
        return True
    if len(factors) != 1 or factors[0][0] != 0:
        raise ValueError("Expected at most one signed primary")
    margin = factors[0][4] - factors[0][5]
    return not isfinite(margin) or margin < 0.050


def agrees(first, second):
    if not first or not second:
        return first == second
    a, = first
    b, = second
    return (a[0] == b[0] and abs(remainder((a[1]+a[2])-(b[1]+b[2]), 13333)) <= 2
            and abs(a[3]-b[3]) <= 250)


def progressive(search):
    first, cpu = search("8ms")
    restart = needs_restart(first)
    result = search("12ms")[0] if restart else first
    return result, first, cpu, restart


def lanes(panel, receipt, weak):
    if panel == "dense":
        verified(BINDING, BINDING_SHA)
        saved = receipt["dense"]
        scheduled = {(r["visit"], r["rx"]): r["slot"] for r in saved["lanes"].values()}
        for i, (row, samples) in enumerate(read_physical(BINDING, Path("/srv/bulk"), WINDOWS)):
            if row["sha256"] != receipt["input_sha256"]["chronological_dense_iq_sha256"][i]:
                raise ValueError("Dense waveform digest changed")
            visit = window(row, samples)
            for rx in (0, 1):
                left = saved["probes"]["12ms"][2*i+rx]
                if left["receiver_id"] != rx or left["visit_index"] != visit.acquisition["global_visit"]:
                    raise ValueError("Invalid dense probe identity")
                if scheduled[left["visit_index"], rx] != "full":
                    yield visit, rx, {arm: encoded(rows[2*i+rx]) for arm, rows in saved["probes"].items()}
    else:
        verified(weak, WEAK_ARCHIVE)
        for i, (row, samples) in enumerate(read_archive(weak, 18)):
            visit = window(row, samples)
            for rx in (0, 1):
                source = receipt["weak"]["records"][2*i+rx]
                if (source["rx"], source["id"], source["sample_sha256"]) != (rx, row["key"], row["sha256"]):
                    raise ValueError("Weak waveform or antenna changed")
                yield visit, rx, {arm: encoded({"candidates": [factor] if factor else []})
                                  for arm, factor in source["factors"].items()}


def compare(panel, inputs, engines):
    effects = Counter()
    rows = []
    for repeat in range(3):
        totals = Counter()
        for i, (visit, rx, expected) in enumerate(inputs):
            def search(arm):
                out, timing = engines[visit.target["edge"], arm].run(visit.samples, rx, center(visit))
                return out, timing[0]

            for arm in arm_order(i, repeat):
                begin = process_time_ns()
                if arm == "8ms":
                    result, short, eight_cpu, retried = progressive(search)
                    totals["candidate_ns"] += process_time_ns() - begin
                else:
                    direct, twelve_cpu = search("12ms")
                    totals["direct_ns"] += process_time_ns() - begin
            if (direct != expected["12ms"] or short != expected["8ms"]
                    or result != (direct if retried else short)):
                raise ValueError("Scheduled native factors differ from the archived paired binaries")
            mismatch = not agrees(direct, short)
            totals["ideal_native_ns"] += eight_cpu + (twelve_cpu if mismatch else 0)
            totals["direct_native_ns"] += twelve_cpu
            totals["eight_native_ns"] += eight_cpu
            if repeat == 0:
                effects["restarts"] += retried
                effects["necessary_restarts"] += mismatch
                effects["missed_restarts"] += mismatch and not retried
                effects["changed_factor"] += bool(result and direct and not agrees(result, direct))
                effects["lost_factor"] += bool(direct and not result)
                effects["new_factor"] += bool(result and not direct)
        rows.append(dict(totals))
    summary = {key: median(run[key] for run in rows)/1e6 for key in rows[0]}
    return dict(panel=panel, lanes=len(inputs), effects=dict(effects), repeats_ns=rows,
                median_ms={key.removesuffix("_ns"): value for key,value in summary.items()})


def run(weak, assets):
    machine = check_machine()
    prior = json.loads(gzip.decompress(verified(HERE / "measurements/eight-ms-primary.json.gz", PARENT_SHA)))
    panels = {}
    with ExitStack() as stack:
        engines = {}
        for arm, identity in prior["build"]["primary"].items():
            lib = Path(identity["binary"])
            verified(lib, identity["binary_sha256"])
            for edge, digest in PILOT_SHA.items():
                pilot = np.frombuffer(verified(assets / (edge+".f32"), digest), dtype="<f4")
                engine = NativePath(lib, pilot, "short_primary")
                stack.callback(engine.close)
                engines[edge, arm] = engine
        for panel, count in (("weak", 36), ("dense", 336)):
            samples = list(lanes(panel, prior, weak))
            if len(samples) != count:
                raise ValueError("Incomplete saved panel")
            panels[panel] = compare(panel, samples, engines)
    anchors = [row["12ms"]["native"]["native_cpu_ns"]["full"] for row in prior["dense"]["repeats"]]
    return dict(machine=machine, input_sha256=PARENT_SHA, panels=panels,
                archived_48_dense_anchor_cpu_ms=median(anchors)/1e6)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("weak", "assets", "output"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    write(args.output, run(args.weak, args.assets))
