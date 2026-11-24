from importlib import import_module
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def design(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("visit_information_warm_start")


def test_equal_whole_blocks_are_selected_using_unchanged_physical_endpoints(design):
    points = 100
    gram = np.zeros((points, 12, 12))
    gram[24:32, 9:, 9:] = 100. * np.eye(3)
    times = 10_000_000_000 + np.arange(points) * 441_016
    uniform, weighted = design.choose(gram, times)
    assert len(uniform) == len(weighted) == 36
    assert set(range(8)) <= set(uniform) & set(weighted)
    assert set(range(88, 100)) <= set(uniform) & set(weighted)
    assert set(range(32, 40)) <= set(uniform)
    assert set(range(24, 32)) <= set(weighted)
    assert set(range(24, 32)).isdisjoint(uniform)


def test_lane_votes_preserve_sign_projections_and_share_ambiguous_candidates(design):
    def option(frequency):
        return dict(fractional_tracking_cfo_hz=frequency, integer_epoch_sample=1000,
                    fractional_epoch_offset_samples=.2, passed_fractional_margin_gate=True)

    lane = dict(receiver_id=0, channel=1, valid_start_counter=100, actual_rf_hz=11.25e9)
    original = dict(lane, candidates=[option(-27_000.)])
    multiple = dict(lane, candidates=[option(-27_000. + design.PERIOD), option(-27_000. - design.PERIOD)])
    no_factor = dict(lane, receiver_id=1, candidates=[])
    base, counts1 = design.exposure({0: [original, no_factor]}, 100, 200_100)
    repeated, counts2 = design.exposure({0: [multiple, no_factor]}, 100, 200_100)
    assert np.allclose(base, repeated, atol=1e-14)
    assert counts1[0, 0].tolist() == [1, 1]
    assert counts2[0, 0].tolist() == [1, 2]
    assert np.linalg.eigvalsh(design.information(base[0], False) - design.information(base[0], True))[0] >= -1e-14


def test_oracle_budget_never_double_counts_final_derivatives(design):
    parts = {role: dict(cpu_ns=clock) for role, clock in dict(derivative=40, final_derivative=30, removable=10,
                                                            trust_accepted=12, trust_rejected=8, starting=20).items()}
    one = {arm: parts for arm in ("c0", "fitted_c")}
    tape = dict(checks={"parity": True}, diagnostics=dict(cold=one, post_cold=one, signed=one, ordinary=one),
                solver_cpu_s=1., input_sha256="saved")
    audit = design.optimizer_budget(tape)
    assert audit["total_derivative_ns"] == 40
    assert audit["total_warm_ns"] == 120
    assert audit["per_stage"]["cold"]["c0"]["retained_start_and_final_derivative_ns"] == 50
