from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3 import reassociation_remap as mapping
from tests.operations.test_causal_tle_catalogue import at_day


def fixture(monkeypatch):
    rows = [
        dict(component="a", candidate_norad=1, candidate_index=0),
        dict(component="b", candidate_norad=3, candidate_index=2),
    ]
    scan = SimpleNamespace(
        norads=np.array([1, 2, 3]), origin_utc_ns=1, sky=dict(time_s=np.array([0.0, 1.0]))
    )
    problem = SimpleNamespace(rows=rows, labels=[0, 2], reference=np.array([4.0, 6.0]))
    context = dict(
        scan=scan,
        node=dict(
            seed=dict(rows=deepcopy(rows), state=dict(phases=np.array([4.0, 0.0, 6.0]))),
            aliases=[0, 1],
        ),
        entries=[
            dict(component="attached", norad=1, candidate_index=0),
            dict(component="unrelated", norad=3, candidate_index=2),
        ],
        means=np.array([7.0, 9.0]),
        problems={a: (problem, np.array([1.0, 2.0])) for a in ("c0", "fitted_c")},
        model=dict(shrinkage=0.5),
        keep=np.array([True, False, True]),
    )

    def build(d, arm, ref):
        labels = sorted({r["candidate_index"] for r in d["node"]["seed"]["rows"]})
        return SimpleNamespace(labels=labels, reference=ref), d

    monkeypatch.setattr(mapping, "build", build)
    monkeypatch.setattr(mapping, "phase_widths", lambda scan, labels: (None, []))
    monkeypatch.setattr(mapping, "forecast_phase_mean", lambda *a: np.array([11.0, 13.0]))
    h = dict(mapping={"a": 2}, aliases={"a": -1}, phases={"2": 8.0})
    return context, h


def test_remap_moves_attached_evidence_and_preserves_unrelated_native_mask(monkeypatch):
    context, hypothesis = fixture(monkeypatch)
    result = mapping.remap(context, hypothesis, {})
    assert result["node"]["seed"]["rows"][0]["candidate_norad"] == 2
    assert result["node"]["aliases"] == [-1, 1]
    assert result["entries"][0]["norad"] == 2
    assert result["entries"][1] == context["entries"][1]
    assert np.array_equal(result["keep"], context["keep"])
    assert result["means"].tolist() == [11.0, 9.0]
    assert result["problems"]["c0"][0].reference.tolist() == [8.0, 6.0]
    assert context["means"].tolist() == [7.0, 9.0]
    assert context["node"]["aliases"] == [0, 1] and context["entries"][0]["norad"] == 1
    assert context["node"]["seed"]["rows"][0]["candidate_norad"] == 1


def test_new_candidate_propagation_failure_cannot_mutate_incumbent(monkeypatch):
    context, hypothesis = fixture(monkeypatch)
    hypothesis["mapping"]["a"] = 44714
    lines = [line for line in at_day(232).splitlines() if line.startswith(("1 ", "2 "))]
    monkeypatch.setattr(mapping, "ecef_states", lambda *a: (None, None, np.array([False])))
    with pytest.raises(ValueError, match="propagation failed"):
        mapping.remap(context, hypothesis, {"44714": dict(lines=lines)})
    assert context["scan"].norads.tolist() == [1, 2, 3]
    assert context["node"]["seed"]["rows"][0]["candidate_norad"] == 1
