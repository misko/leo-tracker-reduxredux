"""Complete the authorized higher-penalty EM trials and selected controls."""

from dataclasses import replace
from pathlib import Path
import json
import time

import numpy as np

from compare_tracklet_methods import synthetic_benchmark
from evaluate_polynomial_tracklets import (
    DEFAULT_INPUT, evaluate_lanes, json_default, load_observations, save_results,
)
from tune_full_data_tracklets import (
    annotate_full_data_quality, audit_real_result, run_search,
)
from leo.analysis.em_tracklets import fit_lane
from leo.analysis.polynomial_tracklets import TrackConfig
import score_search


def main():
    folder = Path(__file__).resolve().parent
    deadline = time.monotonic() + 150
    while True:
        data = json.loads((folder / "search.json").read_text())
        if len(data) >= 8:
            break
        if time.monotonic() > deadline:
            raise RuntimeError("Initial bounded search did not finish")
        time.sleep(1)
    (folder / "raw-search.json").write_text(json.dumps(data, indent=2))
    configs = [
        (f"slope08000-pen{penalty:02d}-degree4", replace(
            TrackConfig(), max_slope_hz_s=8000, track_penalty=penalty,
        )) for penalty in (26, 36)
    ]
    run_search("em", configs, output=folder.parent)
    extra = json.loads((folder / "search.json").read_text())
    (folder / "extra-search.json").write_text(json.dumps(extra, indent=2))
    score_search.main()
    records = json.loads((folder / "ranked-search.json").read_text()) + extra
    selected = max((r for r in records if "rank" in r), key=lambda r: tuple(r["rank"]))
    for filename in ("search.json", "ranked-search.json"):
        (folder / filename).write_text(json.dumps(records, indent=2))
    (folder / "selected.json").write_text(json.dumps(selected, indent=2))
    print("FINAL_SELECTED", json.dumps(selected), flush=True)
    validate_selected(folder, selected)


def validate_selected(folder, selected):
    cfg = TrackConfig(**selected["config"])
    cases = synthetic_benchmark(fit_lane, cfg)
    rows, provenance = load_observations(DEFAULT_INPUT)
    shuffled = [dict(row) for row in rows]
    rng = np.random.default_rng(20261017)
    for receiver in (1, 2):
        for channel in range(1, 9):
            indices = [i for i, r in enumerate(shuffled)
                       if (r["receiver"], r["channel"]) == (receiver, channel)]
            values = rng.permutation([shuffled[i]["measured_cfo_hz"] for i in indices])
            for i, value in zip(indices, values, strict=True):
                shuffled[i]["measured_cfo_hz"] = float(value)
    summary, exports = evaluate_lanes(shuffled, cfg, fit_lane)
    summary, exports = annotate_full_data_quality(summary, exports)
    audit_real_result(shuffled, summary, exports, cfg)
    summary["control"] = "CFO independently permuted within each receiver/channel; seed20261017"
    save_results(folder / "selected-shuffled-control", summary, exports)
    validation = dict(
        selected=selected, synthetic_cases=cases, shuffled_control={
            k: v for k, v in summary.items() if k != "lanes"
        }, input_provenance=provenance,
        policy="Full-data fitting and residual-only selection; no held-out run or selection",
    )
    (folder / "selected-validation.json").write_text(json.dumps(
        validation, indent=2, default=json_default, allow_nan=False,
    ))


if __name__ == "__main__":
    main()
