import probe_ds23_iteration012_existing_recovery as study


def test_diagnostics_use_current_incumbent_and_output_root():
    module=study.configure('diagnostics')
    assert module.OUT==study.runner.RAW/'all_track_diagnostics'
    assert module.diagnostic.runner is study.runner
    assert study.runner.engine.baseline.OUT==study.runner.RAW


def test_paths_reuse_current_passing_graph_parent_and_native_algorithm():
    module=study.configure('paths')
    assert module.OUT==study.runner.RAW/'graph_seeded_paths'
    assert module.paths.runner is study.runner
    assert module.paths.OUT==module.OUT
