"""Supplementary same-panel compatibility check for the #1 and #6 prototypes."""

import argparse
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
STREAM = STUDY / "01_stream"
sys.path[:0] = [str(STUDY), str(STREAM), str(STUDY / "06_coreset")]
from bench import CASES
import cold_replay as cold
import coreset
from prototype import Replay, clock, delta


LATLON_TOL_DEG = 1.e-10
RMS_TOL_HZ = 1.e-8
GRID_SCORE_TOL = 1.e-10


def run_case(case):
    started = clock()
    archive = cold.INPUT / case / "native.json"
    with archive.open(encoding="utf-8") as file:
        replay = Replay(file)
        header = delta(started)
        deadline = replay.archive.meta["duration_s"]
        stages = replay.advance(deadline)
        if not replay.exhausted:
            raise ValueError(f"{case} has probes beyond its declared final sample")
        stage_start = clock()
        document, info = replay.freeze()
        stages["freeze_segments"] = delta(stage_start)
    stages["archive_open_and_header"] = header
    stage_start = clock()
    bank, receipt = cold.build_bank(case, dict(replay.archive.meta, duration_s=deadline),
                                    check_approximation=False)
    stages["causal_orbit_bank"] = delta(stage_start)
    stage_start = clock()
    data = cold.descriptors(document, bank)
    if data is None:
        raise ValueError(f"{case} has no satellite descriptors to reproduce prototype #1")
    stages["shortlist"] = delta(stage_start)
    stage_start = clock()
    bias = cold.bias_vote(data)
    stages["common_bias"] = delta(stage_start)
    shared_wall = delta(started)["wall_s"]

    stage_start = clock()
    chosen, provisional, evaluated = coreset.select_tracks(data, bias)
    selection_wall = delta(stage_start)["wall_s"]
    geometry, subset, inliers, winners = coreset.replay_fit(data, chosen, bias, shared_wall, selection_wall)
    primary_time = delta(started)

    stage_start = clock()
    full_rows = np.arange(len(data["ti"]))
    full_selection_wall = delta(stage_start)["wall_s"]
    full, full_subset, full_inliers, full_winners = coreset.replay_fit(
        data, full_rows, bias, shared_wall, full_selection_wall)
    full_time = delta(stage_start)

    geometry["conditioning"] = coreset.conditioning(coreset.take(subset, inliers), winners[inliers])
    geometry["provisional_satellites"] = provisional[chosen].tolist()
    geometry["selector_center_candidate_evaluations"] = data["ids"].size
    geometry["selector_information_blocks"] = coreset.SURROGATE_CANDIDATES * len(data["ti"])
    geometry["selector_candidate_set_evaluations"] = evaluated
    full["conditioning"] = coreset.conditioning(coreset.take(full_subset, full_inliers), full_winners[full_inliers])
    full["additional_wall_s"] = full_time["wall_s"]

    return dict(case=case, **primary_time, arms=geometry.pop("arms"), air_deadline_s=deadline,
                stream=info, bank=receipt, bank_numeric_bytes=sum(a.nbytes for a in bank.values()),
                shared_wall_s=shared_wall, shared_stages=stages, shared_descriptor_tracks=len(data["ti"]),
                shared_bias_candidate_evaluations=82 * data["ids"].size,
                geometry12=geometry, full_control=full)


def check_reproduction(row, previous):
    """Require exact streamed evidence and winner order, with strict fit tolerances."""
    case = row["case"]
    full = row["full_control"]
    assert row["stream"] == previous["stream"], (case, "stream evidence")
    assert row["bank"] == previous["bank"], (case, "causal TLE bank")
    assert full["grid_tracks"] == previous["descriptor_tracks"], (case, "descriptor count")
    assert full["retained_satellites"] == previous["selected_satellites"], (case, "satellite assignment order")
    grid_diff = abs(full["grid_score"] - previous["common_prefit_grid_score"])
    assert grid_diff <= GRID_SCORE_TOL, (case, "grid score", grid_diff)
    differences = {}
    for arm, fit in full["arms"].items():
        stored = previous["arms"][arm]
        assert fit["status"] == stored["status"], (case, arm, "solver status")
        if fit["status"] == "estimate":
            endpoint_diff = max(abs(a - b) for a, b in zip(fit["latlon"], stored["latlon"], strict=True))
            rms_diff = abs(fit["rms_hz"] - stored["rms_hz"])
            assert endpoint_diff <= LATLON_TOL_DEG, (case, arm, "endpoint", endpoint_diff)
            assert rms_diff <= RMS_TOL_HZ, (case, arm, "RMS", rms_diff)
            for field in ("tracks", "satellites", "on_boundary", "rms_kind"):
                assert fit[field] == stored[field], (case, arm, field)
            differences[arm] = dict(max_abs_endpoint_diff_deg=endpoint_diff, abs_rms_diff_hz=rms_diff)
        else:
            assert fit["reason"] == stored["reason"], (case, arm, "abstention reason")
    return dict(status="passed", stream_and_satellite_order_exact=True, abs_grid_score_diff=grid_diff,
                arm_differences=differences)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "result.json")
    args = parser.parse_args()
    rows = []
    for case in CASES:
        row = run_case(case)
        rows.append(row)
        print(case, f"{row['wall_s']:.3f} s", {arm: fit["status"] for arm, fit in row["arms"].items()}, flush=True)

    previous = json.loads((STREAM / "result.json").read_text(encoding="utf-8"))["cases"]
    by_case = {row["case"]: row for row in previous}
    reproduction = {row["case"]: check_reproduction(row, by_case[row["case"]]) for row in rows}
    result = dict(method="Supplementary prototype #1 streaming tracker to prototype #6 geometry coreset",
                  timing_scope="Single-thread host wall from native detector archive open through linking, "
                               "freeze, causal bank, descriptors, bias, geometry selection, grid and both fits. "
                               "Full control adds its measured grid/fit after shared stages. "
                               "Conditioning and reproduction checks are outside both clocks.",
                  cases=rows, checks=dict(full_control_reproduction=reproduction,
                                         tolerances=dict(latlon_deg=LATLON_TOL_DEG, rms_hz=RMS_TOL_HZ,
                                                         grid_score=GRID_SCORE_TOL)))
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Reproduced saved full-track endpoints and assignments on {len(reproduction)} scans.")


if __name__ == "__main__":
    main()
