"""Audit saved c pairs, bounded fits and frozen-transfer residual gates."""

import csv
import hashlib
import json
from collections import defaultdict

import numpy as np
from analyze_dsx01_fixed_site import group
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import PARTITION, ROOT
from prototype_dsx01_receiver_geometry import OUTPUT

from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen


def check_pair(a, b):
    for key in ("rows", "aliases", "starts"):
        if key in a and key in b:
            assert a[key] == b[key], key
    for f in (a, b):
        for trial in f["fits"]:
            history = trial["history"]
            scores = np.array([r["score"] for r in history])
            assert np.isfinite(scores).all() and np.all(np.diff(scores) < 0)
            for row in history:
                x = np.array(row["parameters"])
                assert np.isfinite(x).all() and np.max(abs(x[:2])) <= 12.5
        state = f.get("state")
        states = [state] if state is not None else f["states"].values()
        for state in states:
            assert max(abs(np.array(state["phases"]))) <= 15.00000001


def run():
    pairs = 0
    drift_controls = []
    inputs = {}
    roots = [
        OUTPUT,
        ROOT / "reports/2026_10_18_dsx01_receiver_phase",
        ROOT / "reports/2026_10_18_dsx01_mean_motion",
        ROOT / "reports/2026_10_18_dsx01_mean_motion/reference_aligned",
    ]
    for root in roots:
        for path in sorted(root.glob("DSX01-S0*/*/endpoints.json")):
            inputs[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
            d = json.loads(path.read_text())
            for key, a in d.items():
                if key.endswith("/c0"):
                    check_pair(a, d[key.removesuffix("/c0") + "/fitted_c"])
                    pairs += 1
    for root, glob in [
        (OUTPUT / "pooled", "*/mean_*_endpoints.json"),
        (OUTPUT / "pooled_exact_refinement", "endpoints.json"),
        (ROOT / "reports/2026_10_18_dsx01_receiver_consensus", "DSX01-S0*/*/endpoints.json"),
    ]:
        for path in sorted(root.glob(glob)):
            d = json.loads(path.read_text())
            check_pair(d["c0"], d["fitted_c"])
            pairs += 1
            inputs[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    for path in sorted(
        (ROOT / "reports/2026_10_18_dsx01_receiver_identity").glob(
            "DSX01-S0*/*/mean_*_iterations.json"
        )
    ):
        for record in json.loads(path.read_text()):
            check_pair(record["fits"]["c0"], record["fits"]["fitted_c"])
            pairs += 1
        inputs[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    for directory in sorted((OUTPUT / "pooled").iterdir()):
        if not directory.is_dir():
            continue
        a = json.loads((directory / "mean_0_endpoints.json").read_text())
        b = json.loads((directory / "mean_10_endpoints.json").read_text())
        pa = json.loads((directory / "mean_0_protocol.json").read_text())
        pb = json.loads((directory / "mean_10_protocol.json").read_text())
        assert pa["seed_sha256"] == pb["seed_sha256"]
        for arm in ("c0", "fitted_c"):
            assert [r["east_north_km"] for r in a[arm]["starts"]] == [
                r["east_north_km"] for r in b[arm]["starts"]
            ]
            assert len(a[arm]["grid"]) == len(b[arm]["grid"]) == 25
            assert len(a[arm]["names"]) == len(b[arm]["names"])
        drift_controls.append(directory.name)
    with (ROOT / "reports/2026_10_18_dsx01_retention_localization/per_scan.csv").open() as f:
        raw = {r["case"]: int(r["raw_points"]) for r in csv.DictReader(f)}
    accepted_points = accepted_segments = accepted_rows = 0
    observations = {}
    ownership_violations = []
    for case in raw:
        curves = json.loads((PARTITION / case / "curves.json").read_text())
        lookup = {t["key"]: t for t in curves}
        ids = [i for t in curves for i in t["observation_ids"]]
        assert len(ids) == len(set(ids)) and len(ids) <= raw[case]
        observations[case] = dict(
            raw_points=raw[case], partition_points=len(ids), unique_partition_points=len(set(ids))
        )
        for dirname, exact in [("pooled_transfer", False), ("pooled_exact_transfer", True)]:
            for path in sorted((OUTPUT / dirname / case).glob("*.json")):
                source = (
                    OUTPUT / "pooled_exact_refinement/endpoints.json"
                    if exact
                    else OUTPUT / "pooled" / path.stem / "mean_10_endpoints.json"
                )
                fits = json.loads(source.read_text())
                for arm, result in json.loads(path.read_text()).items():
                    state = fits[arm]["states"][case]
                    extra = {int(j) for j in state["extra"]}
                    owners = defaultdict(set)
                    groups = set()
                    rows = [r for r in result["rows"] if r["compatible"]]
                    for r in rows:
                        if r["active_curvature"]:
                            owners[r["candidate_index"]].add(lookup[r["component"]]["channel"])
                            groups.add(group(lookup[r["component"]]))
                    assoc_ids = []
                    for r in rows:
                        assert r["rms_hz"] <= 450 and abs(r["bias_hz"]) <= 3000
                        if r["candidate_index"] in extra and len(owners[r["candidate_index"]]) < 2:
                            ownership_violations.append(
                                [str(path), arm, r["component"], "orbital ownership"]
                            )
                        if not r["active_curvature"]:
                            assert group(lookup[r["component"]]) in groups
                            if abs(state["phases"][r["candidate_index"]]) > 0.001:
                                assert r["candidate_index"] in owners
                        cut = r["split_at"] if r["parts"] > 1 else -1
                        slices = [slice(None)] if cut <= 0 else [slice(0, cut), slice(cut, None)]
                        for sl in slices:
                            passed = batch_noise_screen(
                                np.array(r["innovations_hz"])[None, sl], np.array(r["times_s"])[sl]
                            )
                            assert passed["noise_screen_pass"][0], (path, arm, r["component"])
                            accepted_segments += 1
                        accepted_rows += 1
                        accepted_points += r["points"]
                        assoc_ids.extend(lookup[r["component"]]["observation_ids"])
                    assert len(assoc_ids) == len(set(assoc_ids)) == result["associated_points"]
                    assert len(assoc_ids) <= raw[case]
    assert not ownership_violations, ownership_violations
    result = dict(
        matched_c_pairs=pairs,
        matched_joint_drift_controls=drift_controls,
        joint_drift_controls_same_seed_bytes_nominations_grid_starts_and_dimension=True,
        bounded_monotone_paths=True,
        ownership_violations=ownership_violations,
        repeated_checks_across_methods_and_arms=True,
        accepted_rows_checked=accepted_rows,
        accepted_segments_checked=accepted_segments,
        accepted_points_checked=accepted_points,
        accepted_RMS_bias_mean_slope_quadratic_step_ACF_gates_rechecked=True,
        observation_ID_uniqueness=observations,
        inputs_sha256=inputs,
        tests_are_recorded_separately=True,
    )
    write(OUTPUT / "validation.json", result)
    print(
        "pairs",
        pairs,
        "accepted rows checked",
        accepted_rows,
        "unique/ownership/gates passed",
        flush=True,
    )
    return result


if __name__ == "__main__":
    run()
