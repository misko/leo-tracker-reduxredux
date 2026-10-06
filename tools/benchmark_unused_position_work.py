"""Bounded saved-input parity for position work removal; no publication or RF."""

import dataclasses
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np

from leo.analysis.adaptive_tle_prediction import build_prediction_banks
from leo.cli.adaptive_tle_position import _point_factory
from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
from leo.operations.tle_archive import TleArchiveReader
from leo.storage.prediction_scratch import PredictionScratch
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    baseline, candidate, output = map(Path, sys.argv[1:4])
    modules = {
        variant: (
            load(variant + "_score", root / "analysis/adaptive_tle_position.py"),
            load(variant + "_predict", root / "analysis/adaptive_tle_prediction.py"),
        )
        for variant, root in (("baseline", baseline), ("candidate", candidate))
    }
    rows = []
    for sid in ("scan-fw-cc609ed603589e6e", "scan-fw-aadec7177d989684"):
        reader = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
        try:
            prepared = prepare_adaptive_tle_position_inputs(
                sid, inputs=reader, archive=TleArchiveReader(Path("/var/lib/leo/tle"))
            )
        finally:
            reader.close()
        tracks = []
        for track in prepared.tracks[:2]:
            ix = np.unique(
                np.linspace(0, len(track.times_s) - 1, min(128, len(track.times_s))).astype(int)
            )
            tracks.append(
                dataclasses.replace(
                    track,
                    observation_ids=tuple(track.observation_ids[i] for i in ix),
                    times_s=track.times_s[ix],
                    measured_hz=track.measured_hz[ix],
                    training_mask=track.training_mask[ix],
                )
            )
        with PredictionScratch(Path("/srv/postgres-nvme/leo-analysis-scratch")) as scratch:
            banks, _ = build_prediction_banks(
                prepared.catalogue,
                prepared.candidate_indices[:1024],
                prepared.start_utc_ns,
                tracks,
                allocate_array=scratch.allocate,
                finalize_array=scratch.finalize,
            )
            for latitude, longitude in ((38.5816, -121.4944), (39.5296, -119.8138)):
                results = {}
                row = {"session": sid, "latitude": latitude, "longitude": longitude}
                order = (
                    ("baseline", "candidate") if len(rows) % 2 == 0 else ("candidate", "baseline")
                )
                for variant in order:
                    scoring, prediction = modules[variant]
                    start = time.process_time()
                    evaluator = prediction.RegionalTrackPredictionEvaluator(
                        banks, _point_factory(latitude, longitude)
                    )
                    points = [
                        dataclasses.asdict(scoring.score_point(e, n, evaluator(e, n)))
                        for e, n in ((0.0, 0.0), (-100.0, 0.0), (100.0, 0.0))
                    ]
                    result = scoring.adaptive_best_first_search(
                        lambda coords, scoring=scoring, evaluator=evaluator: [
                            scoring.score_point(e, n, evaluator(e, n)) for e, n in coords
                        ],
                        radius_km=100,
                        region_size_km=200,
                        levels_km=(100, 50),
                        budget_points=8,
                    )
                    results[variant] = {"points": points, "search": dataclasses.asdict(result)}
                    row[variant + "_cpu_s"] = time.process_time() - start
                row["exact_parity"] = results["baseline"] == results["candidate"]
                row["matched_track_counts"] = [
                    p["matched_track_count"] for p in results["candidate"]["points"]
                ]
                rows.append(row)
                output.write_text(json.dumps(rows, indent=2) + "\n")
                print(json.dumps(row), flush=True)
                assert row["exact_parity"], "position scores/search changed"


if __name__ == "__main__":
    main()
