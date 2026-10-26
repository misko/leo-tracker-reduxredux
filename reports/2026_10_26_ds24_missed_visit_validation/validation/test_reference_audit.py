"""Audit arithmetic preserves fractional timing with large native counters."""
from audit_prediction import relative_phase_samples


def test_phase_is_invariant_to_large_exact_counter_origin():
    donor=dict(start_counter=1000000,epoch_samples=1234.123456789)
    last=dict(start_counter=4540000,epoch_samples=3456.987654321)
    expected=relative_phase_samples(donor,last,10000000/750)
    for origin in (10**12,2**50):
        assert relative_phase_samples(dict(donor,start_counter=donor['start_counter']+origin),
            dict(last,start_counter=last['start_counter']+origin),10000000/750)==expected
