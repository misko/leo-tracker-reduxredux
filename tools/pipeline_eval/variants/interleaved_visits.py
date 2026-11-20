"""Schedule three of every four visits to each RF channel before calling GLRT."""

import sys
from collections import Counter
from functools import partial
from pathlib import Path

METHOD = "interleaved_visits"
CHANNELS = 8


def scheduled(visit, channel):
    """Use only the public eight-channel scan clock, preserving both receivers together."""
    if type(visit) is not int or visit < 0 or type(channel) is not int:
        raise ValueError("expected an integer visit and channel")
    if channel != visit % CHANNELS + 1:
        raise ValueError("this schedule requires the recorded eight-channel sweep order")
    return (visit // CHANNELS + channel - 1) % 4 != 0


def select_document(document):
    """Apply the acquisition rule to complete native probes, retaining original clocks."""
    source, provenance = document["source"], document["provenance"]
    count = provenance["window_count"]
    if type(count) is not int or count < 0 or len(document["delivery_clocks"]) != count:
        raise ValueError("expected one clock record per acquisition visit")
    lanes = {}
    kept = []
    for row in source["probes"]:
        visit, channel, rx = (row[k] for k in ("visit_index", "channel", "receiver_id"))
        include = scheduled(visit, channel)
        if visit >= count or type(rx) is not int or rx not in (0, 1):
            raise ValueError("invalid native visit or receiver")
        bit = 1 << rx
        if lanes.get(visit, 0) & bit:
            raise ValueError("duplicate receiver in native visit")
        lanes[visit] = lanes.get(visit, 0) | bit
        if include:
            kept.append(row)
    excluded = [e["visit"] for e in provenance["excluded_windows"]]
    if (
        any(mask != 3 for mask in lanes.values())
        or len(lanes) != provenance["processed_windows"]
        or len(lanes) + len(excluded) != count
        or any(type(i) is not int for i in excluded)
        or set(lanes).union(excluded) != set(range(count))
    ):
        raise ValueError("native probes and exclusions must account for every dual-receiver visit")
    channels = range(1, CHANNELS + 1)
    valid = Counter(visit % CHANNELS + 1 for visit in lanes)
    retained = Counter(row["channel"] for row in kept if row["receiver_id"] == 0)
    metrics = dict(
        full_visits=count,
        valid_visits=len(lanes),
        retained_visits=len(kept) // 2,
        retained_by_channel=[retained[c] for c in channels],
        valid_by_channel=[valid[c] for c in channels],
    )
    return dict(document, source=dict(source, probes=kept)), metrics


def run(case, work_dir):
    from tools.pipeline_eval.__main__ import local_output
    from tools.pipeline_eval.variants import orbit_projector, v5_lean

    work = local_output(Path(work_dir))
    work.mkdir(parents=True, exist_ok=True)
    library = work / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    return v5_lean.run_bound_worker(case, work, Path(__file__), worker_args=(str(library),))


def worker(request, result, library):
    from unittest.mock import patch

    from tools.pipeline_eval.variants import v5_core, v5_secant_fit

    selected = partial(v5_core.worker, select_document=select_document)
    with patch.object(v5_core, "worker", selected):
        v5_secant_fit.worker(request, result, library, "secant")


if __name__ == "__main__":
    worker(*sys.argv[1:])
