from run_ds23_dbg01_iteration_003 import batch_cases,configure,RAW


def test_next_cases_skip_closed_debug_cases_without_changing_benchmark_rows():
    ranked=[81,326,35,41,111,405,390,221]
    rows=[dict(case=f'DS23-{n:04}',policy='equal_assignment_priors',arm='fitted_c',
               policy_error_km=str(20-k)) for k,n in enumerate(ranked)]
    assert batch_cases(rows)==['DS23-0111','DS23-0390']
    assert len(rows)==8 and rows[5]['case']=='DS23-0405'


def test_iteration_three_reuses_current_context_and_has_separate_output():
    configure()
    import run_ds23_dbg01_iteration_002 as engine
    assert engine.RAW==engine.baseline.OUT==engine.dbg.PARENT==RAW
    assert engine.reentry.OUT==RAW/'single_curve_reentry'
    assert engine.baseline.setup is engine.current_setup
