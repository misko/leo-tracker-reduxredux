"""Pure control authority tests; no recording or reference imports."""
import importlib.util
from pathlib import Path
import pytest

SPEC=importlib.util.spec_from_file_location('freeze163_test',Path(__file__).with_name('freeze.py'))
API=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(API)


def test_control_identity_and_policy():
    claim=dict(label='A',hypothesis='zero-c',mode='train0',arm='fitted-c',protocol_sha256=API.CONTROL_DIGEST)
    row=dict(claim,status='qualified',audit=dict(qualified=True))
    API.validate_control(row,claim,'A','zero-c','train0','fitted-c')
    assert API.POLICY['maximum_fits']==12*2*2*2*2
    assert API.POLICY['new_receipts']==192+96
    assert all('report' not in n and 'evaluation' not in n for n in API.SOURCE_FILES)


@pytest.mark.parametrize('key,value',[('label','B'),('hypothesis','fitted-c'),
    ('mode','train1'),('arm','zero-c'),('protocol_sha256','foreign')])
def test_foreign_claim_fails(key,value):
    claim=dict(label='A',hypothesis='zero-c',mode='train0',arm='fitted-c',protocol_sha256=API.CONTROL_DIGEST)
    row=dict(claim,status='qualified',audit=dict(qualified=True));claim[key]=value
    with pytest.raises(ValueError):API.validate_control(row,claim,'A','zero-c','train0','fitted-c')


@pytest.mark.parametrize('status,audit',[('failed',True),('unqualified',False),('qualified',False)])
def test_unavailable_control_never_filtered(status,audit):
    claim=dict(label='A',hypothesis='zero-c',mode='train0',arm='fitted-c',protocol_sha256=API.CONTROL_DIGEST)
    row=dict(claim,status=status,audit=dict(qualified=audit))
    with pytest.raises(ValueError):API.validate_control(row,claim,'A','zero-c','train0','fitted-c')
