from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from fractions import Fraction
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
CASES_SHA256 = "5bc58aab84ce75d3704d08a294333010745caec382da5f059b04c9e5a5473188"


def load_json(name: str) -> dict:
    return json.loads((HERE / name).read_text())


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_builder():
    spec = importlib.util.spec_from_file_location("lag3_build_controls", HERE / "build_controls.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_frozen_inventory_and_score_independent_truth() -> None:
    payload = load_json("cases.json")
    design = load_json("design.json")
    assert sha256(HERE / "cases.json") == CASES_SHA256
    assert payload["status"] == "frozen_no_detector_outcomes"
    assert payload["case_count"] == 20
    assert payload["receiver_case_count"] == 40
    assert payload["iq_bytes"] == 72_002_560
    assert payload["iq_bytes"] < 100_000_000
    assert len({case["case_id"] for case in payload["cases"]}) == 20
    assert len({case["seed"] for case in design["cases"]}) == 20
    assert {case["rate_hz"] for case in payload["cases"]} == {2_500_000, 5_000_000}
    for rate in (2_500_000, 5_000_000):
        selected = [case for case in payload["cases"] if case["rate_hz"] == rate]
        assert len(selected) == 10
        assert {case["edge"] for case in selected} == {"lower", "upper"}
        assert {case["injected"]["kind"] for case in selected} == {
            "pilot",
            "noise",
            "tone",
            "two_pilot",
            "pilot_tone",
        }
        single_cfos = sorted(
            component["cfo_hz"]
            for case in selected
            if case["injected"]["kind"] == "pilot"
            for component in case["injected"]["receivers"][0]["components"]
            if component["type"] == "pilot"
        )
        assert -399_000.0 in single_cfos and 0.0 in single_cfos and 399_000.0 in single_cfos
    serialized = json.dumps(payload).lower()
    for forbidden in ("detector_score", "detector_result", "observed_positive", "glrt_result"):
        assert forbidden not in serialized
    assert all(not case["expected"]["detector_positive_required"] for case in payload["cases"])
    assert any(case["expected"]["ambiguity"] == "either" for case in payload["cases"])
    assert any(case["expected"]["expected_proposal_present"] is None for case in payload["cases"])


def test_raw_hash_geometry_counter_alignment_and_quantization() -> None:
    payload = load_json("cases.json")
    for case in payload["cases"]:
        raw = case["raw_npy"]
        path = HERE / raw["path"]
        assert path.is_file()
        assert ".." not in Path(raw["path"]).parts
        assert "sha256:" + sha256(path) == raw["sha256"]
        values = np.load(path, mmap_mode="r", allow_pickle=False)
        count = case["rate_hz"] * case["dwell_ms"] // 1000
        assert values.dtype.str == raw["dtype"] == "<i2"
        assert list(values.shape) == raw["shape"] == [count, 2, 2]
        assert case["source_end_counter_exclusive"] - case["source_start_counter"] == count
        assert path.stat().st_size == raw["bytes"]
        for receiver in case["injected"]["receivers"]:
            assert receiver["clipped_components"] == 0
            assert receiver["prequantization_peak_component"] < 32768
            assert math.isfinite(receiver["noise_complex_mean_power"])


def test_physical_frame_lattice_and_fractional_epoch_convention() -> None:
    payload = load_json("cases.json")
    observed_rounding_phases = {2_500_000: set(), 5_000_000: set()}
    for case in payload["cases"]:
        rate = case["rate_hz"]
        for receiver in case["injected"]["receivers"]:
            for component in receiver["components"]:
                if component["type"] != "pilot":
                    continue
                epoch = Fraction(str(component["epoch_relative_samples"]))
                integer = component["integer_epoch_samples"]
                fractional = component["fractional_epoch_samples"]
                assert math.isclose(float(epoch - integer), fractional, abs_tol=1e-12)
                assert -0.5 <= fractional < 0.5
                period = Fraction(rate, 750)
                for coordinate in component["frame_coordinates"]:
                    physical = epoch + coordinate["frame_index"] * period
                    assert math.isclose(
                        float(physical), coordinate["physical_start_samples"], abs_tol=1e-9
                    )
                    assert math.isclose(
                        float(physical - coordinate["nearest_sample"]),
                        coordinate["fractional_delay_samples"],
                        abs_tol=1e-9,
                    )
                    assert abs(coordinate["fractional_delay_samples"]) <= 0.5
                    observed_rounding_phases[rate].add(
                        round(coordinate["fractional_delay_samples"] - fractional, 6)
                    )
    for phases in observed_rounding_phases.values():
        assert any(math.isclose(abs(value), 1 / 3, abs_tol=1e-6) for value in phases)
    fractions = {
        round(component["fractional_epoch_samples"], 2)
        for case in payload["cases"]
        for component in case["injected"]["receivers"][0]["components"]
        if component["type"] == "pilot"
    }
    assert {-0.49, 0.49} <= fractions


def test_absolute_oscillator_uses_continuous_counter_phase() -> None:
    builder = load_builder()
    rate = 5_000_000
    cfo = -399_000.0
    counter = 12_001_203_337
    phase = -0.328125
    values = builder.absolute_oscillator(4096, rate, cfo, counter, phase)
    step = np.exp(2j * np.pi * cfo / rate)
    assert np.max(np.abs(values[1:] - values[:-1] * step)) < 2e-10
    for index in (0, 1, 997, 4095):
        cycles = np.remainder(
            np.longdouble(str(phase))
            + np.longdouble(str(cfo))
            * np.longdouble(counter + index)
            / np.longdouble(rate),
            np.longdouble(1),
        )
        expected = np.exp(2j * np.pi * float(cycles))
        assert abs(values[index] - expected) < 2e-10


def test_source_lock_and_reproducible_materialization() -> None:
    builder = load_builder()
    lock = builder.verify_source_lock()
    assert lock["frozen_before_iq_materialization"] is True
    rebuilt = builder.build()
    assert rebuilt == load_json("cases.json")
    template_hashes = {
        (case["rate_hz"], case["edge"], component["template_sha256"])
        for case in rebuilt["cases"]
        for receiver in case["injected"]["receivers"][:1]
        for component in receiver["components"]
        if component["type"] == "pilot"
    }
    assert len(template_hashes) == 4
