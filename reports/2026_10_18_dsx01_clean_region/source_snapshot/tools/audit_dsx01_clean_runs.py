"""Postfit receipts: causal inputs, matched controls and numerical map limits."""

import hashlib
import json

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import Scan
from dsx01_inference_audit import ROOT, InferenceReadGuard, validate_history
from report_dsx01_clean_region import EXPECTED
from run_dsx01_clean_region import OUTPUT


def run():
    input_hashes = {}
    cases = {}
    for k in range(1, 6):
        case = f"DSX01-S0{k}"
        inference = Scan(case).inference_input_audit
        write(OUTPUT / case / "input_audit.json", inference)
        history = json.loads((OUTPUT / case / "causal_history.json").read_text())
        count = validate_history(history["past_versions"], history["cutoff_utc_ns"])
        stem = (
            "2026_10_17_dsx01_polynomial_satellite_dive"
            if k == 1
            else "2026_10_17_robust_curve_reassociation"
        )
        bank_receipt = json.loads(
            (ROOT / "reports" / stem / "frozen_inputs" / case / "receipt.json").read_text()
        )
        partition = ROOT / "reports/2026_10_17_robust_curve_reassociation/partition" / case
        receipt = json.loads((partition / "receipt.json").read_text())
        assert receipt["reference_position_used"] is False
        assert receipt["satellite_identity_or_tle_used"] is False
        assert (
            hashlib.sha256((partition / "curves.json").read_bytes()).hexdigest()
            == receipt["curves_sha256"]
        )
        assert receipt["original_tracks_sha256"] == bank_receipt["tracks_sha256"]
        cases[case] = dict(
            history_candidate_count=len(history["past_versions"]),
            history_records=count,
            radio_only_partition=True,
            inference_input_audit=inference,
        )
    completed, incomplete, warnings = [], [], []
    controls = []
    derivative_errors = []
    guard = InferenceReadGuard(OUTPUT)
    for k in range(1, 6):
        case = f"DSX01-S0{k}"
        for method in EXPECTED:
            path = OUTPUT / case / "surfaces" / method / "result.json"
            if not path.exists():
                incomplete.append(f"{case}/{method}")
                continue
            data = json.loads(path.read_text())
            derivative_errors += [r["relative_error"] for r in data.get("derivative_checks", [])]
            assert data["GPS_or_following_TLE_used"] is False
            assert "actual_report_inputs_read" in data
            for value in data["actual_report_inputs_read"]:
                guard.check_path(value)
                if value not in input_hashes:
                    input_hashes[value] = hashlib.sha256(
                        __import__("pathlib").Path(value).read_bytes()
                    ).hexdigest()
            c0, fc = data["arms"]["c0"], data["arms"]["fitted_c"]
            np.testing.assert_array_equal(c0["map_points"], fc["map_points"])
            assert len(c0["fit"]["attempts"]) == len(fc["fit"]["attempts"]) == 3
            for a, b in zip(c0["fit"]["attempts"], fc["fit"]["attempts"], strict=True):
                if a["history"] and b["history"]:
                    np.testing.assert_array_equal(
                        a["history"][0]["parameters"][:2], b["history"][0]["parameters"][:2]
                    )
            for arm, row in data["arms"].items():
                assert np.isfinite(row["loss"]).all()
                assert np.max(np.linalg.norm(row["map_points"], axis=1)) <= 10.000001
                assert np.max(abs(np.array(row["fit"]["parameters"][:2]))) <= 12.500001
                assert np.isfinite(row["gradient_at_center"]).all()
                if row["fit"].get("stopped") == "iteration_budget":
                    warnings.append(
                        dict(case=case, method=method, arm=arm, warning="endpoint iteration budget")
                    )
                profile = row.get("map_profile_stops", [])
                n = sum(s == "iteration_budget" for s in profile)
                if n:
                    warnings.append(
                        dict(
                            case=case,
                            method=method,
                            arm=arm,
                            warning="pixel profile iteration budget",
                            pixels=n,
                        )
                    )
            completed.append(f"{case}/{method}")
        base_path = OUTPUT / case / "surfaces/normal/result.json"
        base = json.loads(base_path.read_text())
        for name in ("diag_4", "frame_independent"):
            control_path = OUTPUT / case / "surfaces" / name / "result.json"
            if control_path.exists():
                control = json.loads(control_path.read_text())
                differences = [
                    float(
                        np.max(
                            np.abs(
                                np.array(base["arms"][a]["fit"]["parameters"])
                                - np.array(control["arms"][a]["fit"]["parameters"])
                            )
                        )
                    )
                    for a in ("c0", "fitted_c")
                ]
                delta = max(differences)
                assert delta == 0
                controls.append(dict(case=case, control=name, maximum_parameter_difference=delta))
    write(OUTPUT / "input_bindings.json", input_hashes)
    write(
        OUTPUT / "validation.json",
        dict(
            completed=completed,
            incomplete=incomplete,
            cases=cases,
            warnings=warnings,
            causal_history_records_validated=True,
            radio_only_partition_hashes_validated=True,
            forbidden_actual_input_paths=0,
            matched_c_primary_starts_and_map_points=True,
            endpoints_box_bounded=True,
            maps_radius_bounded=True,
            source_input_hash_count=len(input_hashes),
            no_claim_of_global_satellite_assignment_optimum=True,
            independent_control_checks=controls,
            sparse_derivative_checks=len(derivative_errors),
            maximum_sparse_relative_derivative_error=max(derivative_errors, default=0),
        ),
    )
    print(
        len(completed), "complete", len(incomplete), "pending", len(warnings), "numerical warnings"
    )


if __name__ == "__main__":
    run()
