import probe_ds23_iteration013_existing_recovery as study


def test_original_track_diagnostics_bind_the_new_batch():
    module=study.configure('diagnostics')
    assert module.OUT==study.runner.RAW/'all_track_diagnostics'
    assert module.diagnostic.runner is study.runner
    assert study.runner.engine.baseline.OUT==study.runner.RAW


def test_native_paths_reuse_the_current_qualified_parent():
    module=study.configure('paths')
    assert module.OUT==study.runner.RAW/'graph_seeded_paths'
    assert module.paths.runner is study.runner
    assert module.paths.OUT==module.OUT
