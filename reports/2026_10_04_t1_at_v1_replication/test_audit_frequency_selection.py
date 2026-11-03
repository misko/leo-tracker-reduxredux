import pytest
from frequency_associations import FrequencySearch
from test_frequency_selection_score import fixture
from audit_frequency_selection import validate_selection


def test_reconstruct_selection_and_reject_corrupt_residual():
    args=fixture();r=FrequencySearch(*args).run(3)
    r.update(scan='test',arm='fitted-c',original_rows=args[1].tolist(),heldout_original_rows=[],zero_frequency_control_exact=True)
    r['final'].update(denominator=len(args[1]),coverage=r['final']['assigned']/len(args[1]))
    r['rms_hz']=(sum(a['residual_hz']**2 for a in r['final']['assignments'])/r['final']['assigned'])**.5
    v=validate_selection(r);assert v['windows']==170
    r['final']['assignments'][0]['residual_hz']=500.
    with pytest.raises(AssertionError):validate_selection(r)
