from importlib import import_module
from pathlib import Path

import pytest


@pytest.fixture
def roof(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("shared_waveform_roof")


def test_optimistic_share_charges_singleton_residuals(roof):
    fake = [("iq", "sha256:original")]
    profile = dict(inputs=fake, comparisons={"half_grid": {"total_cpu_s": [[10., 10.]]}},
                   stages=[{"timing": {"calls": 17, "cpu_s": 5.}}])
    stereo = dict(inputs=fake, visits=6, differences=[], exact_installed_factors_by_rank=[],
                  repeats=[{"paths": {"paired_primary": 6, "paired_residual": 2, "one_residual": 1}}])
    row = roof.panel(profile, stereo, {"input_digests": fake})
    assert row["original_scouts_per_repeat"] == 17
    assert row["optimistic_native_reduction_if"] == pytest.approx(
        dict(share_primary=3./17, share_primary_and_paired_residuals=4./17, free_all_scouts=.5))


def test_solver_and_io_caps_remain_distinct(roof):
    warm = dict(elapsed_s=90., launch_to_detections_s=50., detections_to_terminal_s=30., terminal_to_exit_s=10.)
    row = roof.project(20., 42., 30., 70., warm, {"test": 10.})
    assert row["cold_callback_budget_cpu_s"] == 5.
    assert row["cold_outside_exceeds_half_elapsed_s"] == 7.
    assert row["warm_acquisition_elapsed_ceiling_s"]["halved_solver"] == 20.
    candidate = row["alternatives"]["test"]
    assert candidate["maximum_warm_solver_elapsed_s"] == 5.
    assert candidate["misses_cold_half_cpu_by_s"] == 5.
