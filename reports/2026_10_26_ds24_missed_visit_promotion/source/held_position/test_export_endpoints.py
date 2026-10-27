"""A terminated case cannot masquerade as an audited endpoint."""
import pytest
from export_endpoints import audit_job

def test_cap_without_read_receipt_is_retained_as_incomplete(tmp_path):
    row=audit_job(dict(root=str(tmp_path),case='DS24-test',variant='baseline',status='capped'))
    assert row['status']=='capped'
    assert not row['endpoint_available'] and row['read_audit_complete'] is False

def test_completed_endpoint_requires_process_read_receipts(tmp_path):
    with pytest.raises(AssertionError):
        audit_job(dict(root=str(tmp_path),case='DS24-test',variant='baseline',status='complete'))
