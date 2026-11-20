"""Run original phase-release with an optional private track continuity policy."""

import json
import os
import runpy
import sys
from pathlib import Path
from time import monotonic, process_time

here = Path(__file__).parent
H = runpy.run_path(str(here / "locked_assignments_worker.py"))


def run(root, output, pin, gapfile, enabled, flags):
    cap_path = H["group"]()
    cap = H["resources"](cap_path)
    if (
        os.sched_getaffinity(0) != {pin}
        or os.nice(0) != 10
        or (
            cap["memory.max"] != 512 * 2**20 or cap["memory.swap.max"] or cap["memory.swap.current"]
        )
    ):
        raise ValueError("unexpected affinity, priority, memory or swap")
    began, cpu = monotonic(), process_time()
    gaps = json.loads(gapfile.read_bytes()) if enabled else []
    runpy.run_path(str(root))["activate"](root)
    policy = runpy.run_path(str(here.parent / "variants/drop_reconnect.py"))
    from leo.analysis.localization_v3.tracks import active_curvature

    from leo.application import localization_v3 as factory

    initial = factory.prepare_tracks
    observed = {}

    def prepare(document, config):
        prepared = initial(document, config)
        repaired, gains = policy["fixed_links"](prepared, gaps, config, active_curvature)
        observed["gains"] = gains
        observed["observations"] = [r["observation_id"] for r in repaired["observations"]]
        observed["track_groups"] = [
            dict(
                key=row["key"],
                ids=row["observation_ids"],
                curved=index in repaired["curved_indices"],
            )
            for index, row in enumerate(repaired["tracks"])
        ]
        return repaired

    factory.prepare_tracks = prepare
    try:
        state = H["observe"](root, flags)
    finally:
        factory.prepare_tracks = initial
    result = state["production"]
    if result["status"] == "ok":
        role, node, entries, _, _ = H["configuration"](state)
        final = H["point_map"](state["context"], node, entries)
        observed.update(
            conservative=state["conservative"],
            final=final,
            fit_path=role,
            cavity_offered=result["metrics"]["cavity_offered"],
            cavity_adopted=state.get("adopted", False),
            cavity_trials=state.get("trials", []),
            signed={a: H["point"](x) for a, x in state["context"]["arms"].items()},
        )
    H["save"](
        output / "outcome.json",
        dict(
            result=result,
            observation=observed,
            bounds=dict(
                start=cap,
                end=H["resources"](cap_path),
                cpu_s=process_time() - cpu,
                wall_s=monotonic() - began,
                pin=pin,
            ),
        ),
    )


if __name__ == "__main__":
    _, root, output, pin, gapfile, mode, *flags = sys.argv
    run(Path(root), Path(output), int(pin), Path(gapfile), mode == "corrected", flags)
