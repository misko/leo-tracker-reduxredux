"""Bounded full-data-only EM configuration search; no source changes."""

from dataclasses import asdict, replace
from pathlib import Path
import hashlib
import json
import time
import traceback

import evaluate_polynomial_tracklets as evaluator
from leo.analysis.em_tracklets import fit_lane
from leo.analysis.polynomial_tracklets import TrackConfig


OUTPUT = Path(__file__).resolve().parent
ROOT = OUTPUT.parents[2]
SOURCE = ROOT / "src/leo/analysis/em_tracklets.py"
TRIALS = [
    ("slope08000-pen18-degree4", dict(max_slope_hz_s=8000)),
    ("slope12000-pen18-degree4", dict(max_slope_hz_s=12000)),
    ("slope16000-pen18-degree4", dict(max_slope_hz_s=16000)),
    ("slope12000-pen10-degree4", dict(max_slope_hz_s=12000, track_penalty=10,
                                      breakpoint_penalty=5)),
    ("slope16000-pen10-degree4", dict(max_slope_hz_s=16000, track_penalty=10,
                                      breakpoint_penalty=5)),
    ("slope12000-pen06-degree4", dict(max_slope_hz_s=12000, track_penalty=6,
                                      breakpoint_penalty=5)),
    ("slope12000-pen10-degree3", dict(max_slope_hz_s=12000, track_penalty=10,
                                      breakpoint_penalty=5, max_degree=3)),
    ("slope12000-pen10-degree4-seed1702", dict(max_slope_hz_s=12000, track_penalty=10,
                                               breakpoint_penalty=5, random_seed=1702)),
]


def main():
    rows, provenance = evaluator.load_observations(evaluator.DEFAULT_INPUT)
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    summaries = []
    started = time.process_time()
    for name, changes in TRIALS:
        target = OUTPUT / name
        target.mkdir(exist_ok=True)
        config = replace(TrackConfig(), **changes)
        summary = dict(name=name, config=asdict(config), source_sha256=source_hash,
                       input_provenance=provenance, selection="full-data fit only; no holdout")
        before_cpu, before_wall = time.process_time(), time.perf_counter()
        try:
            if before_cpu - started > 265:
                raise RuntimeError("CPU search budget exhausted before this trial")
            result, exports = evaluator.evaluate_lanes(rows, config, fitter=fit_lane)
            (target / "results.json").write_text(json.dumps(result, default=evaluator.json_default))
            (target / "exports.json").write_text(json.dumps(exports, default=evaluator.json_default))
            summary.update(status="complete", assigned=result["assigned"],
                           track_count=result["track_count"], residual_quality=result["residual_quality"],
                           runtime_s=result["runtime_s"])
        except Exception:
            summary.update(status="failed", error=traceback.format_exc())
        summary.update(cpu_s=time.process_time() - before_cpu,
                       wall_s=time.perf_counter() - before_wall)
        (target / "trial.json").write_text(json.dumps(summary, indent=2))
        summaries.append(summary)
        (OUTPUT / "search.json").write_text(json.dumps(summaries, indent=2))
        print("TRIAL", json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
