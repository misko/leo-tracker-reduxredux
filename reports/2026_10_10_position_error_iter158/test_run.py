"""Deadline placement and immutable inherited-port delegation."""
import pytest
import json
from run import run_member, wrap_ports


def test_each_arm_deadline_begins_before_construction():
    timeline=[]
    times=iter([10.,40.])
    def clock():
        value=next(times);timeline.append(('start',value));return value
    def reconstruct(arm):
        timeline.append(('construct',arm));return arm
    def check(arm, **kwargs):
        timeline.append(('check',arm,kwargs['begun']));return kwargs['begun']
    ports={'reconstruct':reconstruct, 'check':None, 'unchanged':object()}
    wrapped=wrap_ports(ports,check,clock=clock)
    assert wrapped['unchanged'] is ports['unchanged']
    for arm,expected in [('zero-c',10.),('fitted-c',40.)]:
        assert wrapped['reconstruct'](arm)==arm
        assert wrapped['check'](arm)==expected
    assert timeline==[('start',10.),('construct','zero-c'),('check','zero-c',10.),
                      ('start',40.),('construct','fitted-c'),('check','fitted-c',40.)]


def test_no_implicit_deadline_after_missing_reconstruction():
    wrapped=wrap_ports({'reconstruct':lambda:None},lambda **kwargs:None)
    with pytest.raises(ValueError,match='precede'):
        wrapped['check']()


def test_terminal_reuse_requires_matching_claim_and_never_calls_again(tmp_path):
    member={'label':'sample'}
    path=tmp_path/'sample.json'
    path.write_text(json.dumps(dict(label='sample',protocol_sha256='digest',status='complete')))
    with pytest.raises(FileNotFoundError):
        run_member(member,tmp_path,'digest',evaluate=lambda m:pytest.fail('called'))
    claim=tmp_path/'sample.claim.json'
    claim.write_text(json.dumps(dict(label='sample',protocol_sha256='foreign')))
    with pytest.raises(ValueError,match='claim'):
        run_member(member,tmp_path,'digest',evaluate=lambda m:pytest.fail('called'))
    claim.write_text(json.dumps(dict(label='sample',protocol_sha256='digest')))
    assert run_member(member,tmp_path,'digest',evaluate=lambda m:pytest.fail('called'))['status']=='complete'


def test_orphan_claim_is_not_retry_permission(tmp_path):
    (tmp_path/'sample.claim.json').write_text('{}')
    with pytest.raises(FileExistsError):
        run_member({'label':'sample'},tmp_path,'digest',evaluate=lambda m:pytest.fail('called'))
