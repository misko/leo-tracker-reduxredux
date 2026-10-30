import pytest
from leo.contracts.digests import canonical_digest
from audit_tracking_capture_provenance import acquisition_evidence


def test_compatibility_adaptive_label_does_not_override_raw_fast_acquisition():
    m=dict(sample_rate_hz=2500000,configuration=dict(policy_id='ordered-continuous-20ms-v1'),window_count=2)
    inv=dict(kind='fast-scan-source',recording_name='recording',window_count=2,segments=[dict(manifest_digest=canonical_digest(m))])
    d=dict(provenance=dict(run_id='run'),source=dict(capture_mode='adaptive',sample_rate_hz=2500000,input_manifest_sha256=canonical_digest(inv)))
    assert acquisition_evidence(d,inv,[m])['capture_mode']=='fast'
    with pytest.raises(ValueError,match='original acquisition'):acquisition_evidence(d)
    with pytest.raises(ValueError,match='manifest digest'):acquisition_evidence(d,inv,[dict(m,sample_rate_hz=10000000)])


def test_direct_scanner_contract_retains_its_capture_mode():
    d=dict(capture_mode='adaptive',sample_rate_hz=10000000,session_id='scan')
    assert acquisition_evidence(d)['capture_mode']=='adaptive'
