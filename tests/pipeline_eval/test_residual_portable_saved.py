from pathlib import Path

import pytest


@pytest.fixture
def trial(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2]/"reports/ALGO08/v3"))
    import residual_portable_saved

    return residual_portable_saved


def test_all_four_ordinary_orbits_are_exact_with_a_replayed_new_residual(trial):
    old = {name: "orbit" for name in trial.ORBIT_SHEETS} | {"position": "old"}
    new = old | {"position": "updated"}
    records = lambda rows: {name: {"sha256": value} for name, value in rows.items()}
    keys = trial.committed_orbits(records(old), records(new), dict(ordinary=old, residual_layout=new))
    assert set(name for name, same in keys.items() if same) == set(trial.ORBIT_SHEETS)
    wrong = new | {next(iter(trial.ORBIT_SHEETS)): "different orbit"}
    with pytest.raises(ValueError, match="four original orbit"):
        trial.committed_orbits(records(old), records(wrong), dict(ordinary=old, residual_layout=wrong))
    with pytest.raises(ValueError, match="eight-PNG sets"):
        trial.committed_orbits(records(old), records(wrong), dict(ordinary=old, residual_layout=new))
