import report_ds23_dbg01_iteration_017 as study


def test_reused_report_reads017_and_records_actual_sources_without_touching016():
    study.configure()
    r=study.renderer
    assert r.RAW==study.binding.runner.RAW
    assert r.OUT.name=='2026_10_23_ds23_dbg01_iteration_017' and r.ITERATION==17
    assert r.runner is study.binding.runner
    assert r.INCLUDE_INDEPENDENT and 'Independent predictive' in r.METHODS
    assert 'run_ds23_dbg01_iteration_017.py' in r.SOURCES
    assert 'report_ds23_dbg01_iteration_016.py' in r.SOURCES
