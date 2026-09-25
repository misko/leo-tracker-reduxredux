from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


def module():
    path = Path(__file__).with_name("run.py")
    spec = importlib.util.spec_from_file_location("i22_test", path)
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
    first = m.fit_train_rates(low, np.zeros(3), object(), RateOrbit)
    second = m.fit_train_rates(high, np.zeros(3), object(), RateOrbit)
    assert first["converged"]
    assert second["converged"]
    assert first["rates_s_h"] == pytest.approx(second["rates_s_h"], abs=1e-12)


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
