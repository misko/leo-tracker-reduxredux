"""Observe paced native-to-position runs with a local curvature predicate."""

import hashlib
import os
import runpy
import sys
from pathlib import Path
from time import monotonic, process_time

here = Path(__file__).parent
H = runpy.run_path(str(here / "locked_assignments_worker.py"))


def run(root, folder, pin, enabled, flags):
    cap = H["group"]()
    before = H["resources"](cap)
    if (
        os.sched_getaffinity(0) != {pin}
        or os.nice(0) != 10
        or (
            before["memory.max"] != 512 * 2**20
            or before["memory.swap.max"]
            or before["memory.swap.current"]
        )
    ):
        raise ValueError("expected physically capped single-core receiver")
    began, cpu_start = monotonic(), process_time()
    runpy.run_path(str(root))["activate"](root)
    predictor = runpy.run_path(str(here.parent / "variants/time_curvature.py"))
    from leo.analysis.localization_v3 import scan, tracks

    from leo.application import localization_v3 as factory

    prepare = factory.prepare_tracks
    original = tracks.active_curvature
    original_scan = scan.active_curvature
    actual = {}
    maximum = None

    def curvature(track):
        if enabled and "key" in track:
            return predictor["active"](track, maximum)
        return original(track)

    def observe_prepare(document, config):
        nonlocal maximum
        maximum = config.max_gap_s
        prepared = prepare(document, config)
        dataset = prepared["tracks"]
        matched = hashlib.sha256()
        for t in dataset:
            matched.update(t["key"].encode())
            for oid in t["observation_ids"]:
                matched.update(oid.encode())
            for array in (t["times"], t["values"]):
                matched.update(array.tobytes())
        actual.update(
            graph_sha256=matched.hexdigest(),
            observations=len(prepared["observations"]),
            tracks=len(dataset),
            graph_points=prepared["graph_points"],
            stock_curved=[t["key"] for t in dataset if original(t)],
            selected_curved=[dataset[k]["key"] for k in prepared["curved_indices"]],
            maximum_gap_s=maximum,
        )
        return prepared

    try:
        factory.prepare_tracks = observe_prepare
        tracks.active_curvature = scan.active_curvature = curvature
        data = H["observe"](root, flags)
    finally:
        factory.prepare_tracks = prepare
        tracks.active_curvature, scan.active_curvature = original, original_scan
    result = data["production"]
    if result["status"] == "ok":
        role, node, entries, _, _ = H["configuration"](data)
        actual.update(
            final=H["point_map"](data["context"], node, entries),
            conservative=data["conservative"],
            role=role,
            cavity_adopted=data.get("adopted", False),
            cavity_trials=data.get("trials", []),
        )
    H["save"](
        folder / "outcome.json",
        dict(
            result=result,
            observation=actual,
            bounds=dict(
                start=before,
                end=H["resources"](cap),
                cpu_s=process_time() - cpu_start,
                wall_s=monotonic() - began,
                pin=pin,
            ),
        ),
    )


if __name__ == "__main__":
    _, root, folder, pin, _dummy, mode, *flags = sys.argv
    run(Path(root), Path(folder), int(pin), mode == "corrected", flags)
