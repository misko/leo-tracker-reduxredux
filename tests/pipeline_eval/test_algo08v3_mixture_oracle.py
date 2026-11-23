from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture
def oracle(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("mixture_oracle")


def test_oracle_supports_only_one_eligible_pair_and_never_adds_a_point(oracle):
    owners = {"a": (150, 1), "b": (170, 0), "c": (150, 1), "some_other_track": (150, 1)}
    assert oracle.choose_subset(["a", "b", "c", "unknown"], owners, {(150, 1), (170, 0)}) == ((150, 1), ["a", "c"])
    assert oracle.choose_subset(["a", "b", "c"], owners, {(150, 0), (170, 0)}) == ((170, 0), ["b"])
    assert oracle.choose_subset(["b", "a"], owners, {(150, 1), (170, 0)}) == ((150, 1), ["a"])


def test_label_capture_keeps_signed_curved_aliases_separate_from_predictive(oracle):
    problem = SimpleNamespace(
        rows=[dict(candidate_norad=123)], members=[0], slices=[slice(0, 2)], alias=[-1],
        keep=np.array([True, False]), scan=SimpleNamespace(tracks=[dict(observation_ids=["a", "discarded"])]),
    )
    context = {"problems": {arm: (problem, None) for arm in ("c0", "fitted_c")}}
    rows = [dict(observation_id="a", norad=123, role="conditional"),
            dict(observation_id="b", norad=127, role="predictive")]
    packet = {"rows": {"c0": rows, "fitted_c": rows}}
    assert oracle.capture_labels(context, packet) == {
        "curved": {"a": (123, -1)}, "roles": {"conditional": 1, "predictive": 1},
    }
    contradictory = {"rows": dict(packet["rows"], fitted_c=[dict(rows[0], norad=888), rows[1]])}
    with pytest.raises(ValueError, match="published owners"):
        oracle.capture_labels(context, contradictory)


def test_strict_oracle_aliases_are_evaluated_after_frozen_receiver_offset(oracle):
    period = oracle.PERIOD
    row = dict(design=np.full((5, 1), period / 2), raw=np.array([np.full(5, -.75 * period)]),
               tangent=np.zeros((1, 5)), phase=np.zeros(1))
    _, aliases, _ = oracle.candidate_aliases(row, np.array([1.]))
    np.testing.assert_array_equal(aliases, [[0, 1, 2]])
    _, aliases, _ = oracle.candidate_aliases(row, np.array([-1.]))
    np.testing.assert_array_equal(aliases, [[-1, 0, 1]])
