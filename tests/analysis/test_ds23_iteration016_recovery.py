import probe_ds23_iteration016_recovery as study


def test_reused_native_driver_binds016_and_retains_the_original_fitter(monkeypatch):
    monkeypatch.setattr(study.runner,'configure',lambda:None)
    fitter=study.paths.paths.refit
    assert study.configure('paths') is study.paths
    assert study.paths.paths.runner is study.runner and study.paths.paths.refit is fitter
    assert study.paths.OUT==study.runner.RAW/'graph_seeded_paths'
