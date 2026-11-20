"""Extract observed solver allocation sizes and plot the paired held-out positions."""

import argparse
import gzip
import json
from unittest.mock import patch

from ..__main__ import local_output
from . import prep_stream_figures
from .full_v5_check import _sha
from .prefix_figures import csv_file
from .solver_memory_trial import METHODS, PLAN, REPORT

SERIES = (
    (-0.18, "control", "Complete aligned control", "#486173"),
    (0.18, "tile", "Tiled coarse salvage", "#287a61"),
)


def row(prediction):
    m = prediction["result"]["metrics"]
    w = m.get("stream_recovery_measurement", {})
    before = w.get("largest_conservative_profile") or {}
    staged = {p["stage"]: p for p in w.get("stages", [])}
    coarse = m.get("solver_memory", {}).get("counters", {})
    first_bank = next(iter(w.get("banks", {}).get("ecef_states", [])), {})
    resident = m.get("early_memory", {}).get("independent_sample_max_kib", {})
    return dict(
        id=prediction["id"],
        method=prediction["method"],
        status=prediction["result"]["status"],
        cpu=prediction["cpu"],
        worker_cpu_s=prediction["worker_cpu_s"],
        worker_wall_s=prediction["worker_wall_s"],
        **{
            name + "_peak_rss_kib": staged.get(name, {}).get("after", {}).get("peak_rss_kib")
            for name in (
                "prepare_native_scan",
                "initial_selection",
                "salvage",
                "conservative_recovery",
                "history_policy",
                "nominate_families",
                "screen_candidates",
                "screen_reassociation_candidates",
            )
        },
        worker_peak_rss_kib=w.get("whole_worker", {}).get("peak_rss_kib"),
        sampled_anon_rss_kib=resident.get("RssAnon"),
        sampled_file_rss_kib=resident.get("RssFile"),
        salvage_cpu_s=staged.get("salvage", {}).get("cpu_s"),
        salvage_prediction_bytes=before.get("prediction_bytes", coarse.get("max_prediction_bytes")),
        salvage_profile_output_bytes=before.get(
            "returned_bytes", coarse.get("max_profile_output_bytes")
        ),
        tile_count=coarse.get("tiles"),
        late_eligible_state_bytes=48 * first_bank["rows"] * first_bank["knots"]
        if first_bank
        else None,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", type=local_output, default=REPORT)
    report = p.parse_args().report
    lock = json.loads((report / "prediction-lock.json").read_bytes())
    resources = []
    for role in METHODS:
        path = report / f"{role}-positions.jsonl.gz"
        if _sha(path) != lock["files"][path.name]:
            raise ValueError("figure did not receive its sealed predictions")
        resources.extend(
            row(r) for r in map(json.loads, gzip.decompress(path.read_bytes()).splitlines())
        )
    csv_file(report / "resources.csv", resources)
    with patch.multiple(prep_stream_figures, METHODS=METHODS, PLAN=PLAN, SERIES=SERIES):
        prep_stream_figures.positions(report)


if __name__ == "__main__":
    main()
