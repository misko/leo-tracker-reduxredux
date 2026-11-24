from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture
def study(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("dense_family_refit")


def paired(rows):
    return dict(c0=rows, fitted_c=rows)


def test_contrast_requires_same_family_and_role_in_both_arms(study):
    old = paired([("curve", study.OLD, "conditional"), ("line", study.OLD, "predictive")])
    new = paired([("curve", study.NEW, "conditional"), ("line", study.NEW, "predictive")])
    assert study.contrast(old, new) == {"curve", "line"}

    with pytest.raises(ValueError, match="role-preserving"):
        study.contrast(old, dict(new, fitted_c=[("curve", study.NEW, "predictive")]))

    with pytest.raises(ValueError, match="two selected owners"):
        study.contrast(old, dict(new, fitted_c=new["c0"] * 2))


def test_whole_arcs_merge_into_incumbent_phase_without_changing_aliases_weights_or_mask(study):
    norads = np.array([study.NEW, study.OLD])
    kinds = (("curve", ["a", "masked"], 0), ("existing", ["b"], 1), ("line", ["c"], None))
    rows = [dict(component=key, active_curvature=True, candidate_index=j, candidate_norad=norads[j])
            for key, _, j in kinds if j is not None]
    aliases, weights, keep = [-1, 1], np.array([0.5, 1.]), np.array([True, False, True])
    entry = dict(component="line", candidate_index=0, norad=study.NEW, alias=3)
    candidate = dict(scan=SimpleNamespace(norads=norads, tracks=[dict(key=key, observation_ids=ids, rf_hz=11e9)
                    for key, ids, _ in kinds]), node=dict(seed=dict(rows=rows), aliases=aliases), powers=weights,
                    keep=keep, entries=[entry], means=np.array([0.5, -0.9]),
                    arms=paired(dict(phase_reference=np.array([0.6, -0.8]))))
    members = dict(curve=("conditional", study.NEW, {"a"}), existing=("conditional", study.OLD, {"b"}),
                   line=("predictive", study.NEW, {"c"}))

    trial, details = study.exchanged(candidate, members, {"a", "c"})
    assert trial["node"]["seed"]["rows"] == [dict(rows[0], candidate_index=1, candidate_norad=study.OLD), rows[1]]
    assert trial["entries"] == [dict(entry, candidate_index=1, norad=study.OLD)]
    assert trial["node"]["aliases"] is aliases
    assert trial["keep"] is keep
    assert trial["powers"] is weights
    assert trial["means"].tolist() == [-0.9]
    assert trial["arms"]["c0"]["phase_reference"].tolist() == [-0.8]
    assert details["curve"]["masked_ids"] == ["masked"]
    assert candidate["node"]["seed"]["rows"][0]["candidate_norad"] == study.NEW

    with pytest.raises(ValueError, match="arc"):
        study.exchanged(candidate, dict(members, line=("predictive", study.NEW, {"c", "extra"})), {"a", "c"})
