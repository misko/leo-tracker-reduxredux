from run_ds23_dbg01_iteration_005 import batch_cases,configure,RAW


def test_next_debug_batch_keeps_the_evaluation_population_and_skips_closed_cases():
    ranked=[81,326,35,41,111,390,405,221,322,272,68,69]
    rows=[dict(case=f'DS23-{n:04}',policy='equal_assignment_priors',arm='fitted_c',
        policy_error_km=str(20-k)) for k,n in enumerate(ranked)]
    assert batch_cases(rows)==['DS23-0272','DS23-0068']
    assert len(rows)==12


def test_iteration_five_has_an_isolated_current_label_context():
    configure()
    import run_ds23_dbg01_iteration_002 as engine
    assert engine.RAW==engine.baseline.OUT==engine.dbg.PARENT==RAW
    assert engine.baseline.setup is engine.current_setup
