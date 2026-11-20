from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification import orbit_prior_trial as trial
from tools.pipeline_eval.variants import orbit_prior
from tools.pipeline_eval.variants import robust_em as lean
from tools.pipeline_eval.variants import robust_orbit_fit as exact


def element(which, age, collected):
    return orbit_prior.Element((which, "line2"), age * orbit_prior.NS, collected * orbit_prior.NS)


def test_equal_epoch_along_track_disagreement_and_age(monkeypatch):
    calls = []

    def fake_sat(which, _):
        def propagate(jd, fraction):
            calls.append((jd, fraction))
            p = (120, 100, 50) if which == "old" else (100, 0, 0)
            return 0, p, (4, 0, 0)

        return SimpleNamespace(satnum=7, sgp4=propagate)

    monkeypatch.setattr(orbit_prior, "Satrec", SimpleNamespace(twoline2rv=fake_sat))
    evidence = orbit_prior.age_width(
        element("current", 50, 60),
        element("old", 40, 45),
        anchor_ns=70 * orbit_prior.NS,
        cutoff_ns=65 * orbit_prior.NS,
    )
    assert calls[0] == calls[1]
    assert evidence == dict(
        status="historical_pair",
        propagations=2,
        alignment_s=5.0,
        age_s=20.0,
        gap_s=10.0,
        width_s=pytest.approx(np.sqrt(101)),
    )


def test_fallback_and_reject_future_or_near_duplicate():
    ns = orbit_prior.NS
    times = dict(anchor_ns=70 * ns, cutoff_ns=65 * ns)
    current = element("current", 50, 60)
    assert orbit_prior.age_width(current, None, **times)["width_s"] == lean.PHASE_SD_S
    for before in (element("old", 40, 61), element("old", 46, 45), element("old", 50, 56)):
        with pytest.raises(ValueError, match="causal geometry history"):
            orbit_prior.age_width(current, before, **times)
    with pytest.raises(ValueError, match="unauthorized"):
        orbit_prior.age_width(element("current", 50, 66), None, **times)


def test_only_phase_geometry_regularization_is_changed(monkeypatch):
    matrices, objectives = [], []
    rows = [SimpleNamespace(orbit=3), SimpleNamespace(orbit=1)]
    state = SimpleNamespace(phase=np.array([0.0, 1.5, 0, 3.0]))
    a = np.diag([13.0, 7, 1 / lean.PHASE_SD_S, 1 / lean.PHASE_SD_S])

    def solver(matrix, right, *, bounds):
        matrices.append(matrix.copy())
        assert np.array_equal(right, [1, 2, 0, 0])
        assert bounds == (-7.5, 7.5)

    def fit(rows, n, half, arm):
        assert (n, half, arm) == (4, 12.5, "c0")
        matrix = a.copy()
        lean.lsq_linear(matrix, [1, 2, 0, 0], bounds=(-7.5, 7.5))
        assert np.array_equal(matrix, matrices[-1])

    def objective(*_):
        return 15.0, 10.0

    def operation():
        lean.fit(rows, 4, 12.5, "c0")
        objectives.append(exact._loss(rows, None, None, state))

    monkeypatch.setattr(lean, "lsq_linear", solver)
    monkeypatch.setattr(lean, "fit", fit)
    monkeypatch.setattr(exact, "_loss", objective)
    orbit_prior.fixed_fit(operation, [2.5] * 4)
    orbit_prior.fixed_fit(operation, [2.5, 1.5, 2.5, 3.0])
    assert np.array_equal(matrices[0], a)
    assert np.array_equal(matrices[1], np.diag([13, 7, 1 / 1.5, 1 / 3]))
    assert objectives[0] == (15.0, 10.0)
    assert objectives[1] == (pytest.approx(15 + 2 - 1.8), 10.0)


def test_extracts_only_complete_matched_tle_for_wanted_norad(monkeypatch):
    def parse(lines, collected):
        return lines, collected

    monkeypatch.setattr(orbit_prior, "from_lines", parse)
    raw = b"0 A\r\n1 00334 rest\r\n2 00334 tail\n0 B\n1 00001 line\n2 00009 other\n"
    assert list(trial.elements(raw, 99, {1, 334})) == [
        (334, (("1 00334 rest", "2 00334 tail"), 99))
    ]
