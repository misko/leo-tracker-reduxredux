from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


def module():
    path = Path(__file__).with_name("run.py")
    spec = importlib.util.spec_from_file_location("i23_test", path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


class Orbit:
    @staticmethod
    def quartic(nodes, phase):
        return nodes[:, 0]

    @staticmethod
    def doppler(receiver, position, velocity, search):
        return position[:, 0]


class RateOrbit(Orbit):
    @staticmethod
    def quartic(nodes, phase):
        out = nodes[:, 0].copy()
        out[:, 0] += phase
        return out


def prepared(held_value: float = 13.0):
    return SimpleNamespace(
        y=np.asarray([10.0, 12.0, held_value, 20.0, 22.0, 23.0]),
        train=np.asarray([True, True, False, True, True, False]),
        track=np.asarray(["s:a", "s:a", "s:a", "s:b", "s:b", "s:b"], object),
        source=np.asarray(["1", "1", "1", "2", "2", "2"], object),
        session=np.asarray(["s"] * 6, object),
        age_h=np.zeros(6),
        p_nodes=np.asarray([[[0.0, 0, 0]]] * 6),
        v_nodes=np.zeros((6, 1, 3)),
        weights={"s:a": 1, "s:b": 1},
    )


def test_cfo_uses_training_rows_only() -> None:
    m = module()
    kwargs = dict(
        receiver=np.zeros(3),
        search=object(),
        orbit=Orbit,
        rates_by_source={"1": 0.0, "2": 0.0},
        unsupported={"s": {"track_count": 0, "occupied_second_weight": 0.0}},
    )
    low = m.score_rates(prepared(13.0), **kwargs)
    high = m.score_rates(prepared(1013.0), **kwargs)
    assert low["track_scores"][0]["training_cfo_hz"] == pytest.approx(11.0)
    assert high["track_scores"][0]["training_cfo_hz"] == pytest.approx(11.0)
    assert high["equal_session_training_capped_loss"] == pytest.approx(
        low["equal_session_training_capped_loss"]
    )
    assert high["equal_session_held_capped_loss"] > low["equal_session_held_capped_loss"]


def test_unsupported_training_identity_stays_at_cap() -> None:
    m = module()
    result = m.score_rates(
        prepared(),
        np.zeros(3),
        object(),
        Orbit,
        {"1": 0.0, "2": 0.0},
        {"s": {"track_count": 1, "occupied_second_weight": 2.0}},
    )
    session = result["session_scores"][0]
    assert session["occupied_second_weight"] == 4.0
    assert session["unsupported_track_count"] == 1
    assert session["training_capped_loss"] >= 0.5
    assert session["held_capped_loss"] >= 0.5


def test_rate_membership_must_be_exact() -> None:
    m = module()
    with pytest.raises(ValueError, match="rate/source"):
        m.score_rates(
            prepared(),
            np.zeros(3),
            object(),
            Orbit,
            {"1": 0.0},
            {"s": {"track_count": 0, "occupied_second_weight": 0.0}},
        )


def test_rate_fit_cannot_read_held_values() -> None:
    m = module()
    low = prepared(13.0)
    high = prepared(1013.0)
    low.age_h = np.asarray([0.0, 1.0, 2.0, 0.0, 1.0, 2.0])
    high.age_h = low.age_h.copy()
    first = m.fit_train_rates(low, np.zeros(3), object(), RateOrbit, 1.0)
    second = m.fit_train_rates(high, np.zeros(3), object(), RateOrbit, 1.0)
    assert first["converged"]
    assert second["converged"]
    assert first["rates_s_h"] == pytest.approx(second["rates_s_h"], abs=1e-12)


def test_rate_fit_control_flow_uses_training_membership_only() -> None:
    m = module()
    ordinary = prepared()
    poisoned = prepared()
    poisoned.source = poisoned.source.copy()
    poisoned.track = poisoned.track.copy()
    poisoned.source[~poisoned.train] = ["held-only-a", "held-only-b"]
    poisoned.track[~poisoned.train] = ["held-track-a", "held-track-b"]
    ordinary.age_h = np.asarray([0.0, 1.0, 2.0, 0.0, 1.0, 2.0])
    poisoned.age_h = ordinary.age_h.copy()
    first = m.fit_train_rates(ordinary, np.zeros(3), object(), RateOrbit, 1.0)
    second = m.fit_train_rates(poisoned, np.zeros(3), object(), RateOrbit, 1.0)
    assert first["source_count"] == second["source_count"] == 2
    assert first["rates_s_h"] == pytest.approx(second["rates_s_h"], abs=1e-12)
    assert first["total_function_evaluations"] == second["total_function_evaluations"]


def test_boundary_count_uses_optimizer_aware_tolerance() -> None:
    m = module()
    assert m.boundary_tolerance_s_h(1.0) == pytest.approx(5 * m.RATE_XATOL_S_H)
    assert m.boundary_tolerance_s_h(10.0) >= 5 * m.RATE_XATOL_S_H


def test_rate_schedule_is_fixed_and_widens_to_one_second_per_hour() -> None:
    m = module()
    assert m.RATE_BOUNDS_S_H == (0.25, 0.50, 1.0)


def test_profile_grid_limits_coarse_phase_and_verifies_half_step() -> None:
    m = module()
    result = m.global_profile_minimize(lambda value: (value - 0.123) ** 2, 0.5, 27.0)
    assert result["grid"]["coarse_maximum_phase_step_s"] <= 0.05 + 1e-12
    assert result["grid"]["half_step_verification"]["passed"]


def test_global_profile_finds_minimum_missed_by_legacy_bounded_search() -> None:
    m = module()

    def multimodal(value: float) -> float:
        broad = (value - 0.35) ** 2 + 0.05
        narrow = 500.0 * (value + 0.40) ** 2
        return min(broad, narrow)

    result = m.global_profile_minimize(multimodal, 0.5)
    assert result["converged"]
    assert result["rate_s_h"] == pytest.approx(-0.4, abs=1e-5)
    assert result["training_objective"] < result["legacy_bounded"]["training_objective"]
    assert result["local_minimum_count"] >= 2


def test_global_profile_explicitly_considers_endpoints_and_zero() -> None:
    m = module()
    endpoint = m.global_profile_minimize(lambda value: value, 0.5)
    zero = m.global_profile_minimize(lambda value: value * value, 0.5)
    assert endpoint["rate_s_h"] == -0.5
    assert endpoint["winner_kind"] == "negative_endpoint"
    assert zero["rate_s_h"] == pytest.approx(0.0, abs=1e-8)


def test_json_seal_name_keeps_json_suffix(tmp_path: Path) -> None:
    m = module()
    source = tmp_path / "plan.json"
    source.write_text('{"value":1}\n')
    import hashlib

    source.with_suffix(".json.sha256").write_text(
        hashlib.sha256(source.read_bytes()).hexdigest() + "\n"
    )
    assert m.verified_json(source) == {"value": 1}
    legacy = source.with_suffix(".sha256")
    legacy.write_text(hashlib.sha256(source.read_bytes()).hexdigest() + "\n")
    assert m.verified_json(source, legacy) == {"value": 1}
