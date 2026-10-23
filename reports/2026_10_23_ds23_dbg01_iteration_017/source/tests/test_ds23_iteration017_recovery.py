import probe_ds23_iteration017_recovery as study


def test_every_reused_recovery_output_and_driver_targets017():
    for stage in ['diagnostics','paths','feasibility','extra','step_diagnostic','same_band_step','cross_band_step','source_integrity','augmented']:
        module=study.configure(stage)
        assert study.runner.RAW in module.OUT.parents
    assert study.paths.runner is study.runner
    assert study.paths.paths.runner is study.runner
