import copy
import pytest

import compare_full_data_prototype as comparison


def reports():
    old = dict(status='passed', rows=[], coverage=[])
    new = dict(status='passed', rows=[], coverage=[])
    for scan in comparison.SCANS:
        for arm in comparison.ARMS:
            for report, field, name in [(old, 'case', 'fold-control'),
                                        (old, 'case', 'full-rebuilt-members'),
                                        (new, 'variant', 'restarted-full-scan')]:
                key = dict(scan=scan, arm=arm, **{field: name})
                report['rows'].append(dict(**key, windows=90, satellites=4, distance_m=1500,
                    converged=True, boundary=False, posterior_weighted_residual_rms_hz=100))
                report['coverage'].append(dict(**key, denominator=100, assigned=90,
                                               coverage=.9, satellites=4))
    return old, new


def test_join_is_complete_and_does_not_confuse_coverage_with_accuracy():
    rows = comparison.comparison_rows(*reports())
    assert len(rows) == 16*2*3
    for summary in comparison.summarize(rows):
        assert summary['scans'] == 16
        assert summary['median_coverage_pct'] == 90
        assert summary['below_1km'] == 0
        assert summary['converged'] == 16


def test_rejects_changed_denominator_or_missing_results():
    old, new = reports()
    altered = copy.deepcopy(new)
    altered['coverage'][0]['denominator'] = 99
    with pytest.raises(ValueError, match='denominators'):
        comparison.comparison_rows(old, altered)
    new['rows'].pop()
    with pytest.raises(ValueError, match='Missing or duplicate'):
        comparison.comparison_rows(old, new)
