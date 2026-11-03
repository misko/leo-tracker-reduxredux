import probe_ds23_iteration018_recovery as study


def test_all_reused_stages_are_bound_to018_without_changing_prior_scientific_rules():
    for stage in ['diagnostics','paths','feasibility','extra','step_diagnostic','same_band_step','cross_band_step','source_integrity','augmented']:
        module=study.configure(stage)
        assert study.runner.RAW in module.OUT.parents
    assert study.paths.runner is study.runner
    assert study.paths.paths.runner is study.runner
