from probe_ds23_iteration011_existing_recovery import configure,runner


def test_longest_track_diagnostic_binds_current_endpoints_and_current_output():
    m=configure('diagnostics')
    assert m.runner is runner and m.OUT==runner.RAW/'all_track_diagnostics'
    assert m.diagnostic.runner is runner and m.diagnostic.OUT==m.OUT


def test_temporal_recovery_uses_existing_rules_and_current_graph():
    m=configure('paths')
    assert m.runner is runner and m.OUT==runner.RAW/'graph_seeded_paths'
    assert m.paths.runner is runner and m.paths.OUT==m.OUT
    assert m.paths.METHODS=={'independent':0.,'persistent5s':5.}
