import pytest
from continuation_scorecard import EXPECTED,FIELDS,summarize


def cohort(label):
    return [dict(zip(FIELDS,key),scan=label,distance_m=500.,converged=True,boundary=False)
            for key in sorted(EXPECTED)]


def test_identical_denominators_keep_failures_and_exclude_partial_scans():
    a=cohort('a');b=cohort('b');partial=cohort('partial')[:-1]
    b[0].update(converged=False,distance_m=1.)
    result=summarize(a+b+partial)
    assert result['complete_scans']==['a','b']
    assert result['common_converged_scans']==['a']
    first=result['configurations'][0]
    assert first['n']==2 and first['unconverged']==1
    assert first['converged_within_1km']==1
    assert first['median_saved_error_m']==250.5
    assert all(r['common_converged_median_m']==500 for r in result['configurations'])


def test_scorecard_rejects_duplicates_and_handles_empty_input():
    a=cohort('a')
    with pytest.raises(ValueError,match='Duplicate'):summarize(a+[a[0]])
    result=summarize([])
    assert result['complete_scans']==[]
    assert all(r['median_saved_error_m'] is None for r in result['configurations'])
