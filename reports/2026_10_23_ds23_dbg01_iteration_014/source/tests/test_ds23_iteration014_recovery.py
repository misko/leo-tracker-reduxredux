import pytest
import probe_ds23_iteration014_recovery as study


def test_014_binding_keeps_the_existing_temporal_driver_and_fitter(monkeypatch):
    monkeypatch.setattr(study.runner,'configure',lambda:None)
    original=study.feasibility.refine
    assert study.configure('paths') is study.paths
    assert study.paths.paths.runner is study.runner
    assert study.configure('feasibility') is study.feasibility
    assert study.feasibility.binding is study.paths and study.feasibility.refine is original
    assert study.feasibility.OUT==study.runner.RAW/'temporal_feasibility'


def test_unknown_stage_cannot_start_a_different_search():
    with pytest.raises(ValueError,match='unknown recovery stage'):study.configure('unbounded')
