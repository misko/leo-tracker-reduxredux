from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3 import reassociation_fit as fitting
from leo.analysis.localization_v3.reassociation_policy import fit_rows_complete


def fixture(monkeypatch, fault=None):
    base = SimpleNamespace(members=[0], slices=[slice(0, 2)], keep=np.array([True, True]))
    context = dict(
        problems={"fitted_c": (base, None)},
        scan=SimpleNamespace(tracks=[dict(observation_ids=["a", "b"])]),
    )
    calls = []

    def fit(context, owners, arm, start, constrained, rounds):
        assert constrained and rounds == 15
        calls.append((arm, start))
        if fault == "exception" and len(calls) == 2:
            raise ValueError("failed fit")
        return dict(
            qualified=True,
            reference=[],
            x=[1.0, 2.0],
            latlon=[3.0, 4.0],
            tracks=[dict(observation_ids=["a", "a"] if fault == "duplicate" else ["a", "b"])],
            reassigned_ids=["a"] if fault == "reassignment" else [],
            proposed_owners={"a": 2, "b": 1},
            objective=3.0,
        )

    monkeypatch.setattr(fitting, "fit", fit)
    monkeypatch.setattr(fitting, "build", lambda *a: (base, dict(families=[])))
    monkeypatch.setattr(
        fitting,
        "family_score",
        lambda *a, **k: (0.0, [dict(phase_boundary_mass=0.01 if fault == "boundary" else 0.001)]),
    )
    owners = {a: {"a": 1, "b": 1} for a in ("c0", "fitted_c")}
    starts = dict(published=[0.0, 0.0], family_omitted=[1.0, 1.0])
    return context, owners, starts, calls


def test_matched_schedule_and_isolated_callbacks(monkeypatch):
    context, owners, starts, calls = fixture(monkeypatch)
    snapshots = []

    def callback(row):
        snapshots.append(deepcopy(row))
        row["qualified"] = False
        row["tracks"][0]["observation_ids"].clear()

    rows = fitting.fit_rows(context, owners, starts, set(), on_row=callback)
    assert calls == [(arm, start) for arm in ("c0", "fitted_c") for start in starts.values()]
    assert fit_rows_complete(rows) and all(r["qualified"] for r in rows)
    assert len(snapshots) == 4
    assert len({r["native_ids_sha256"] for r in rows}) == 1


@pytest.mark.parametrize("fault", ["exception", "duplicate", "reassignment", "boundary"])
def test_failed_or_unqualified_rows_are_not_silently_dropped(monkeypatch, fault):
    context, owners, starts, calls = fixture(monkeypatch, fault)
    rows = fitting.fit_rows(context, owners, starts, set())
    assert len(rows) == 4 and len(calls) == 4
    assert any(not r["qualified"] for r in rows)
    if fault in ("exception", "duplicate"):
        assert not fit_rows_complete(rows)
    else:
        assert fit_rows_complete(rows)
        assert fitting.paired(rows) == dict(c0=None, fitted_c=None)


def test_only_declared_old_family_may_be_reassigned(monkeypatch):
    context, owners, starts, _ = fixture(monkeypatch, "reassignment")
    rows = fitting.fit_rows(context, owners, starts, {1})
    assert all(r["qualified"] for r in rows)


def test_pair_chooses_best_qualified_row_per_arm():
    rows = [
        dict(arm=arm, qualified=qualified, objective=score)
        for arm in ("c0", "fitted_c")
        for qualified, score in [(True, 9), (False, 1), (True, 5)]
    ]
    assert {arm: row["objective"] for arm, row in fitting.paired(rows).items()} == dict(
        c0=5, fitted_c=5
    )
