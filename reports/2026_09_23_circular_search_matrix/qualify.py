#!/usr/bin/env python3
"""Verify the frozen truth-free inputs for the circular-search matrix."""

import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
COHORTS = {"single": (39, 1415), "quarter8": (198, 5890)}
CITIES = {"sacramento": 350.0, "reno": 750.0, "denver": 2500.0}


def read(path: Path):
    return json.loads(path.read_text())


def digest(path: Path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def verify():
    source = HERE / "source"
    verified = []
    for cohort, expected_counts in COHORTS.items():
        for city, radius_km in CITIES.items():
            directory = HERE / "inputs" / f"{cohort}-{city}"
            acquisition_path = directory / "acquisition-receipt.json"
            acquisition_result_path = directory / "acquisition-result.json"
            points_path = directory / "declared-circle-points.json"
            result_path = directory / "refinement-result.json"
            circle_path = directory / "circle-receipt.json"
            qualification_path = directory / "qualification.json"
            acquisition = read(acquisition_path)
            result = read(result_path)
            circle = read(circle_path)
            qualification = read(qualification_path)

            assert acquisition["schema"] == "circular-regional-acquisition/v1"
            assert acquisition["complete"] is True
            assert acquisition["position_truth_used"] is False
            assert acquisition["constraint_applied_before_scoring"] is True
            assert acquisition["radius_km"] == radius_km
            assert acquisition["points_digest"] == digest(points_path)
            assert acquisition["scoring_result_digest"] == digest(acquisition_result_path)
            assert acquisition["frozen_scorer_digest"] == digest(source / "replay_five_block_regional.py")
            assert acquisition["selected_radius_km"] <= radius_km
            assert math.isclose(acquisition["boundary_distance_km"], radius_km - acquisition["selected_radius_km"], abs_tol=1e-9)

            assert result["complete"] is True
            assert result["position_truth_used"] is False
            assert result["nominal_exact_orbits"] is True
            assert (result["track_count"], result["observation_count"]) == expected_counts
            assert result["fits"] and all(fit["converged"] is True for fit in result["fits"])
            assert result["source_result_digest"] == digest(acquisition_result_path)
            assert result["source_code_digest"] == digest(source / "refine_recent_joint_position.py")
            assert result["numerical_source_digest"] == digest(source / "regional_doppler.py")
            assert result["replay_source_digest"] == digest(source / "replay_regional_doppler.py")

            assert circle["schema"] == "circular-regional-refinement/v1"
            assert circle["complete"] is True and circle["position_truth_used"] is False
            assert circle["radius_km"] == radius_km
            assert circle["acquisition_result_digest"] == digest(acquisition_result_path)
            assert circle["acquisition_receipt_digest"] == digest(acquisition_path)
            assert circle["result_digest"] == digest(result_path)
            assert circle["frozen_refiner_digest"] == digest(source / "refine_recent_joint_position.py")
            assert circle["adapter_digest"] == digest(source / "refine_circular_regional_position.py")
            assert circle["selected_radius_km"] <= radius_km and circle["boundary_distance_km"] >= 0
            assert math.isclose(circle["boundary_distance_km"], radius_km - circle["selected_radius_km"], abs_tol=1e-9)
            assert math.isclose(circle["selected_radius_km"], math.hypot(result["selected"]["east_km"], result["selected"]["north_km"]), abs_tol=1e-9)

            assert qualification["schema"] == "circular-nominal-orbit-fit-qualification/v1"
            assert qualification["qualified"] is True
            assert qualification["position_truth_accessed"] is False
            assert qualification["all_modes_converged"] is True
            assert qualification["circle_constraint_satisfied"] is True
            assert qualification["result_digest"] == digest(result_path)
            assert qualification["circle_receipt_digest"] == digest(circle_path)
            verified.append(f"{cohort}-{city}")
    return verified


if __name__ == "__main__":
    print(json.dumps({"verified": verify()}, indent=2))
