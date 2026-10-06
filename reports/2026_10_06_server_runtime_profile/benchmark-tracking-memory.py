import dataclasses
import hashlib
import inspect
import json
import resource
import sys
import time
from pathlib import Path

import numpy as np

from leo.analysis.adaptive_tle_position import AdaptiveTrackPrediction, score_track_prediction
from leo.analysis.adaptive_tle_prediction import build_prediction_banks
from leo.storage.prediction_scratch import PredictionScratch

started = time.monotonic()
cpu_started = time.process_time()
mode = sys.argv[1]
if mode == "score":
    rng = np.random.default_rng(721)
    k, t, n = 256, 11, 4000
    track = AdaptiveTrackPrediction(
        "memory-parity", tuple(map(str, range(n))), np.linspace(0, 30, n),
        rng.normal(size=n), np.arange(n) % 3 != 0,
        np.arange(k), np.arange(t, dtype=float),
        rng.normal(size=(k, t, n)), np.ones(k, dtype=bool),
    )
    score_started = time.monotonic()
    score_cpu_started = time.process_time()
    for _ in range(5):
        score = score_track_prediction(track)
    score_seconds = (time.monotonic() - score_started) / 5
    score_cpu_seconds = (time.process_time() - score_cpu_started) / 5
    result = dataclasses.asdict(score)
    result["qualifying_observation_ids"] = len(result["qualifying_observation_ids"])
else:
    from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
    from leo.operations.tle_archive import TleArchiveReader
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    reader = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    try:
        prepared = prepare_adaptive_tle_position_inputs(
            sys.argv[2], inputs=reader, archive=TleArchiveReader(Path("/var/lib/leo/tle"))
        )
    finally:
        reader.close()
    tracks = []
    for source in prepared.tracks[:2]:
        ix = np.unique(np.linspace(0, len(source.times_s) - 1, min(128, len(source.times_s))).astype(int))
        tracks.append(dataclasses.replace(
            source, observation_ids=tuple(source.observation_ids[i] for i in ix),
            times_s=source.times_s[ix], measured_hz=source.measured_hz[ix],
            training_mask=source.training_mask[ix],
        ))
    with PredictionScratch(Path("/srv/postgres-nvme/leo-analysis-scratch")) as scratch:
        ports = (dict(allocate_array=scratch.allocate, finalize_array=scratch.finalize)
                 if "allocate_array" in inspect.signature(build_prediction_banks).parameters
                 else dict(retain_array=scratch.retain))
        banks, receipt = build_prediction_banks(
            prepared.catalogue, prepared.candidate_indices[:1024], prepared.start_utc_ns,
            tracks, **ports,
        )
        result = {"session": prepared.session_id, "evidence": prepared.evidence_sha256,
                  "receipt": dataclasses.asdict(receipt), "banks": []}
        result["receipt"].pop("elapsed_s")
        for bank in banks:
            result["banks"].append({name: {"shape": getattr(bank, name).shape,
                "sha256": hashlib.sha256(np.ascontiguousarray(getattr(bank, name))).hexdigest()}
                for name in ("candidate_ids", "position_km", "velocity_km_s",
                             "coarse_position_km", "coarse_candidate_rows")})
        from leo.analysis.adaptive_tle_position import score_point
        from leo.analysis.adaptive_tle_prediction import RegionalTrackPredictionEvaluator
        from leo.cli.adaptive_tle_position import _point_factory
        evaluator = RegionalTrackPredictionEvaluator(banks, _point_factory(38.5816, -121.4944))
        result['point_scores'] = [dataclasses.asdict(score_point(east, north, evaluator(east, north)))
                                  for east, north in ((0., 0.), (-100., 0.), (100., 0.))]
print(json.dumps({"mode": mode, "seconds": time.monotonic() - started,
                  "cpu_seconds": time.process_time() - cpu_started,
                  "score_seconds": score_seconds if mode == "score" else None,
                  "score_cpu_seconds": score_cpu_seconds if mode == "score" else None,
                  "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
                  "result": result}))
