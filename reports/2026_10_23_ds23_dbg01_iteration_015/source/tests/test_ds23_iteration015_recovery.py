import pytest
import probe_ds23_iteration015_recovery as study


def test_next_batch_reuses_temporal_and_event_rules_without_changing_the_driver(monkeypatch):
    monkeypatch.setattr(study.runner,'configure',lambda:None)
    assert study.configure('paths') is study.previous.paths
    assert study.paths.paths.runner is study.runner
    assert study.configure('cross_band_step') is study.cross_band
    assert study.cross_band.runner is study.runner and study.step_binding.default.runner is study.runner
    assert study.cross_band.OUT==study.runner.RAW/'cross_band_shared_step'


def test_unknown_stage_cannot_launch_an_unbounded_search():
    with pytest.raises(ValueError,match='unknown015'):study.configure('unbounded')
