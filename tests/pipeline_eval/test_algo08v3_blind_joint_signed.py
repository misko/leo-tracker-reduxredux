from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture
def signed(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("blind_joint_signed")


def fixture(model):
    candidate = dict(scan=SimpleNamespace(origin_utc_ns=20, search_region=SimpleNamespace(half_width_km=12.5)),
                     node={"seed": {"rows": [{"candidate_index": 7}, {"candidate_index": 2}]}},
                     model=model, means=np.zeros(2), keep=np.array([True, False]), powers=np.ones(2), entries=[{}])
    prepared = dict(phase_history={"case": "SCAN"}, phase_forecast=dict(transitions=[{"validation_time_ns": 3}],
                     temporal_split_boundary_ns=2, prefix_distribution=model), sky={"metadata": {"cutoff_utc_ns": 15}})
    return candidate, prepared


def test_unqualified_history_never_refits(signed, monkeypatch):
    model = {"local": 1}
    candidate, prepared = fixture(model)
    monkeypatch.setattr(signed, "validate_history", lambda *_args, **_kwargs: (model, True))
    monkeypatch.setattr(signed, "qualify", lambda *_args: {"qualified": False})
    monkeypatch.setattr(signed, "fitted_pair", lambda *_args: pytest.fail("unqualified refit"))
    measured = {}
    assert signed.update(prepared, candidate, measured) is candidate
    assert measured["signed"]["status"] == "unqualified"


def test_signed_adoption_keeps_support_and_requires_both_gates(signed, monkeypatch):
    model = {"local": 1}
    candidate, prepared = fixture(model)
    monkeypatch.setattr(signed, "validate_history", lambda *_args, **_kwargs: (model, True))
    monkeypatch.setattr(signed, "qualify", lambda *_args: {"qualified": True})
    monkeypatch.setattr(signed, "adjust_means", lambda *_args: np.array([1., 2.]))
    seen = []
    monkeypatch.setattr(signed, "phase_widths", lambda _scan, labels: (seen.append(labels), []))
    fitted = {arm: {"history": [{"fit": {}}]} for arm in signed.ARMS}
    monkeypatch.setattr(signed, "fitted_pair", lambda *args: fitted)
    monkeypatch.setattr(signed, "readout", lambda row: row)
    for accepted in (False, True):
        monkeypatch.setattr(signed, "pair_passes", lambda *_args, **_kwargs: accepted)
        measured = {}
        selected = signed.update(prepared, candidate, measured)
        assert selected["keep"] is candidate["keep"] and selected["entries"] is candidate["entries"]
        assert measured["signed"]["status"] == ("accepted" if accepted else "rejected")
        assert (selected is candidate) == (not accepted)
    assert seen == [[2, 7], [2, 7]]
