from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3.scan import ScanLikelihood


@pytest.fixture
def handoff(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("mixture_joint_start")


def test_mixture_units_map_to_identical_hardware_predictions(handoff):
    mixture = import_module("mixture_position")
    scan = SimpleNamespace(norads=[1, 2, 3], rx_basis=[np.zeros((7, 4))])
    units = np.linspace(-.9, .9, 8)
    state = handoff.receiver_state(scan, units)
    times = np.linspace(12., 288., 7)
    for receiver in (1, 2):
        for channel in (3, 7):
            track = dict(times=times, receiver=receiver, channel=channel, rf_hz=11.4e9)
            expected = mixture.lane_design(track, times)[:, :8] @ units
            np.testing.assert_allclose(ScanLikelihood.hardware(scan, track, state["beta"]), expected,
                                       rtol=2e-15, atol=1e-10)
    assert not np.any(state["phases"]) and not np.any(state["smooth"]) and not state["extra"]
    with pytest.raises(ValueError, match="eight bounded"):
        handoff.receiver_state(scan, np.zeros(9))


def test_start_rebuilds_full_track_assignments_and_refines_once(handoff, monkeypatch):
    scan = SimpleNamespace(norads=[10, 20, 30], rx_basis=[np.zeros((7, 4))], radio_sigma_hz=150.)
    prepared = {"noise": {}}
    region = SimpleNamespace(latlon=tuple)
    mixture_point = [4., -7.]
    call_order = []

    def cheap(value, offered, *, arms):
        assert value is prepared and offered is region and arms == ("c0",)
        call_order.append("mixture")
        return dict(status="complete", node_count=30, arms={"c0": dict(
            east_north_km=mixture_point, latlon=mixture_point, score=25., matched_sample_rms_hz=81.,
            sampled_owner_points=10, receiver_prior_units=np.zeros(8),
            tracks=[dict(retained=True, index=2, alias=8)],
        )})

    def explore(current, state, at, name, *, compact_update):
        assert current is scan and not state["phases"].any()
        assert name == "receiver_smooth" and not compact_update
        assert at.tolist() == mixture_point
        call_order.append("full_explore")
        state["phases"][1] = -4.
        return dict(state=state, rows=[dict(candidate_index=1)]), dict(candidate_hypotheses=7)

    def anchor(current, seed, name, fitted, at):
        assert current is scan and seed["rows"][0]["candidate_index"] == 1
        assert at.tolist() == mixture_point and name == "receiver_smooth" and fitted is False
        call_order.append("full_alias")
        return SimpleNamespace(alias=[-3])

    def model(current, node, sigma, fitted, *, reference):
        assert current is scan and node["aliases"] == [-3] and not fitted
        assert sigma == 150. and reference.tolist() == [-4.]
        return SimpleNamespace(state=lambda point: {"phases": np.array([0., 17., 0.])})

    def fit(_model, point, *, iterations):
        assert iterations == 48 and point.tolist() == mixture_point
        call_order.append("one_exact_fit")
        return dict(parameters=np.array([3., -6.]), score=100., residual_rms_hz=68.)

    monkeypatch.setattr(handoff, "propose", cheap)
    monkeypatch.setattr(handoff.v5_core, "scan_context", lambda *_: scan)
    monkeypatch.setattr(handoff.discovery, "explore", explore)
    monkeypatch.setattr(handoff, "AnchoredFamilies", anchor)
    monkeypatch.setattr(handoff.position, "NormalPosition", model)
    monkeypatch.setattr(handoff.position, "fit", fit)
    node, point, reference, receipt = handoff.cold_start(prepared, region, object())
    assert call_order == ["mixture", "full_explore", "full_alias", "one_exact_fit"]
    assert node["aliases"] == [-3] and point.tolist() == [3., -6.] and reference == {1: 15.}
    assert receipt["proposed_supported_tracks"] == 1 and receipt["refined_rms_hz"] == 68.


def test_zero_proposal_computes_no_fitted_mixture(handoff, monkeypatch):
    mixture = import_module("mixture_position")
    calls = []

    def evaluate(_rows, _sigma, beta, *, derivatives):
        calls.append((len(beta), derivatives))
        return .5, [], np.eye(len(beta)), np.zeros_like(beta)

    monkeypatch.setattr(mixture, "update", evaluate)
    single = mixture.fit_node([], 150., arms=("c0",))
    assert tuple(single) == ("c0",) and set(calls) == {(8, True), (8, False)} and len(calls) == 8
    assert mixture.fit_node([], 150.)["c0"] == single["c0"]
