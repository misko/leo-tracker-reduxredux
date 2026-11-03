import csv

from confirm_ds23_iteration010_short_curves import choose_cases,runner


def test_confirmation_selection_ignores_errors_and_excludes_debug_cases():
    rows=list(csv.DictReader(runner.engine.baseline.BENCHMARK.open()));selected=choose_cases(rows)
    altered=[dict(r,policy_error_km='9999',baseline_error_km='0') for r in reversed(rows)]
    assert choose_cases(altered)==selected and len(set(selected))==20
    assert not set(selected)&(set(runner.CLOSED)|{'DS23-0080','DS23-0257'})
