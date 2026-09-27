"""Component-owned construction tests for the TG11 diagnostic dataset."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from collections import Counter
from fractions import Fraction
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def load_builder():
    spec = importlib.util.spec_from_file_location("tg11_diagnostic_dataset_builder", HERE / "build_dataset.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_json(name: str) -> dict:
    return json.loads((HERE / name).read_text())


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def component(case: dict, receiver: int, trajectory: str) -> dict:
    return next(
        item for item in case["receivers"][receiver]["components"]
        if item["trajectory_id"] == trajectory
    )


def test_membership_is_fixed_complete_and_seed_disjoint() -> None:
    builder = load_builder()
    design = load_json("design.json")
    cases = builder.enumerate_specs(design)
    assert len(cases) == 52
    assert len({case["case_id"] for case in cases}) == 52
    assert Counter((case["split"], case["rate_hz"]) for case in cases) == {
        ("development", 2_500_000): 13,
        ("development", 5_000_000): 13,
        ("validation", 2_500_000): 13,
        ("validation", 5_000_000): 13,
    }
    seeds = [
        receiver["noise_seed"]
        for case in cases
        for receiver in case["receivers"]
    ]
    assert len(seeds) == len(set(seeds)) == 104
    dev_seeds = {
        receiver["noise_seed"] for case in cases if case["split"] == "development"
        for receiver in case["receivers"]
    }
    val_seeds = {
        receiver["noise_seed"] for case in cases if case["split"] == "validation"
        for receiver in case["receivers"]
    }
    assert dev_seeds.isdisjoint(val_seeds)
    assert all(case["source_start_counter"] > 2**53 for case in cases)
    serialized = json.dumps(cases).lower()
    for forbidden in ("detector_score", "detector_result", "observed_positive", "glrt_result"):
        assert forbidden not in serialized


def test_sequence_is_causal_and_keeps_the_complete_cache_key() -> None:
    builder = load_builder()
    design = load_json("design.json")
    cases = builder.enumerate_specs(design)
    for split in design["splits"]:
        for rate in design["rates_hz"]:
            selected = [case for case in cases if case["split"] == split
                        and case["rate_hz"] == rate and case["sequence_id"]]
            assert [case["sequence_index"] for case in selected] == [0, 1, 2, 3]
            assert len({case["edge"] for case in selected}) == 1
            assert len({case["channel"] for case in selected}) == 1
            assert len({case["session_id"] for case in selected}) == 1
            assert len({case["tuning_identity"] for case in selected}) == 1
            count = rate * 120 // 1000
            assert [case["source_start_counter"] for case in selected] == [
                selected[0]["source_start_counter"] + index * count for index in range(4)
            ]
            opposite = [case for case in cases if case["split"] != split
                        and case["rate_hz"] == rate and case["sequence_id"]]
            assert selected[0]["edge"] != opposite[0]["edge"]


def test_sequence_phase_is_integrated_for_persistent_trajectories() -> None:
    builder = load_builder()
    design = load_json("design.json")
    cases = builder.enumerate_specs(design)
    for split in design["splits"]:
        for rate in design["rates_hz"]:
            selected = [case for case in cases if case["split"] == split
                        and case["rate_hz"] == rate and case["sequence_id"]]
            count = rate * 120 // 1000
            rx0_a0 = component(selected[0], 0, "pilot-a")
            rx0_a1 = component(selected[1], 0, "pilot-a")
            expected = builder.advance_phase(
                Fraction(str(rx0_a0["phase_cycles_at_visit_start"])),
                rx0_a0["cfo_hz"], count, rate,
            )
            assert math.isclose(float(expected), rx0_a1["phase_cycles_at_visit_start"], abs_tol=1e-15)
            rx1_a0 = component(selected[0], 1, "pilot-a")
            rx1_a1 = component(selected[1], 1, "pilot-a")
            expected = builder.advance_phase(
                Fraction(str(rx1_a0["phase_cycles_at_visit_start"])),
                rx1_a0["cfo_hz"], count, rate,
            )
            assert math.isclose(float(expected), rx1_a1["phase_cycles_at_visit_start"], abs_tol=1e-15)
            rx1_b2 = component(selected[2], 1, "pilot-b")
            rx1_b3 = component(selected[3], 1, "pilot-b")
            expected = builder.advance_phase(
                Fraction(str(rx1_b2["phase_cycles_at_visit_start"])),
                rx1_b2["cfo_hz"], count, rate,
            )
            assert math.isclose(float(expected), rx1_b3["phase_cycles_at_visit_start"], abs_tol=1e-15)


def test_exact_ladder_and_stationary_strata_are_present() -> None:
    builder = load_builder()
    design = load_json("design.json")
    cases = builder.enumerate_specs(design)
    targets = set()
    for case in cases:
        if case["cohort"] == "ladder":
            targets.update(receiver["components"][0]["target_power_over_noise_db"]
                           for receiver in case["receivers"])
    assert targets == {-30.0, -24.0, -18.0, -12.0, -6.0, 0.0, 6.0, 12.0}
    for split in design["splits"]:
        for rate in design["rates_hz"]:
            selected = [case for case in cases if case["split"] == split and case["rate_hz"] == rate]
            assert {case["edge"] for case in selected} == {"lower", "upper"}
            assert Counter(case["cohort"] for case in selected) == {
                "ladder": 4,
                "negative-noise": 1,
                "negative-nuisance": 1,
                "multiple-hypothesis": 1,
                "symbol-region-support": 1,
                "symbol-region-interference": 1,
                "causal-sequence": 4,
            }
            support = next(case for case in selected if case["cohort"] == "symbol-region-support")
            assert component(support, 0, "early-pilot")["symbol_region"] == "early"
            assert component(support, 1, "late-pilot")["symbol_region"] == "late"


def test_symbol_masks_and_physical_frame_geometry() -> None:
    builder = load_builder()
    for rate in (2_500_000, 5_000_000):
        count = rate * 120 // 1000
        epoch = Fraction(317, 1) + Fraction(49, 100)
        early, early_intervals = builder.region_mask(count, rate, epoch, "early")
        late, late_intervals = builder.region_mask(count, rate, epoch, "late")
        assert early.any() and late.any() and not np.any(early & late)
        assert all(begin < stop for begin, stop in early_intervals + late_intervals)
        for region in ("full", "early", "late"):
            _, metadata, power = builder.pilot_geometry(
                count, rate, "lower", epoch, region, build=False
            )
            assert power > 0 and metadata["frame_coordinates"]
            assert metadata["symbol_region"] == region
            period = Fraction(rate, 750)
            for item in metadata["frame_coordinates"]:
                physical = epoch + item["frame_index"] * period
                assert math.isclose(float(physical), item["physical_start_samples"], abs_tol=1e-9)
                assert abs(item["fractional_delay_samples"]) <= 0.5


def test_frozen_manifest_hashes_geometry_truth_and_unopened_validation() -> None:
    builder = load_builder()
    design = load_json("design.json")
    lock = builder.verify_source_lock()
    payload = load_json("cases.json")
    specs = builder.enumerate_specs(design)
    assert payload["status"] == "frozen_no_detector_outcomes_development_materialized_validation_reserved"
    assert payload["case_count"] == 52 and payload["receiver_case_count"] == 104
    assert payload["materialized_case_count"] == 26
    assert payload["validation_iq_opened"] is False
    assert payload["detector_outcomes_present"] is False
    assert payload["membership_sha256"] == builder.membership_sha256(specs)
    assert payload["source_lock_sha256"] == digest(HERE / "source_lock.json")
    assert payload["design_sha256"] == lock["files"]["design.json"]
    assert payload["materialized_iq_bytes"] < design["bounded"]["maximum_materialized_bytes"]
    serialized = json.dumps(payload).lower()
    for forbidden in ("detector_score", "detector_result", "observed_positive", "glrt_result"):
        assert forbidden not in serialized
    for case in payload["cases"]:
        count = case["rate_hz"] * case["dwell_ms"] // 1000
        assert case["source_end_counter_exclusive"] - case["source_start_counter"] == count
        raw = case["raw_npy"]
        path = HERE / raw["path"]
        assert raw["shape"] == [count, 2, 2] and raw["dtype"] == "<i2"
        if case["split"] == "development":
            assert raw["materialized"] is True and path.is_file()
            assert digest(path) == raw["sha256"]
            values = np.load(path, mmap_mode="r", allow_pickle=False)
            assert values.dtype.str == "<i2" and list(values.shape) == raw["shape"]
            assert path.stat().st_size == raw["bytes"]
            assert all(receiver["clipped_components"] == 0 for receiver in case["receivers"])
        else:
            assert raw["materialized"] is False
            assert raw["sha256"] is None and raw["bytes"] is None
            assert not path.exists()
            assert all(receiver["materialized"] is False for receiver in case["receivers"])


def test_development_measured_pilot_power_matches_analytic_target() -> None:
    payload = load_json("cases.json")
    for case in payload["cases"]:
        if case["split"] != "development":
            continue
        for receiver in case["receivers"]:
            assert receiver["prequantization_peak_component"] < 32768
            assert math.isfinite(receiver["measured_noise_complex_mean_power"])
            for item in receiver["components"]:
                if item["type"] != "pilot":
                    continue
                assert math.isclose(
                    item["measured_power_over_nominal_noise_db"],
                    item["nominal_power_over_noise_db"],
                    abs_tol=2e-10,
                )
