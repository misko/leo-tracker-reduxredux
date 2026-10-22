import report_ds23_family_cavity as report
from run_algo01_ds23_sample import write,read


def test_audit_checkpoint_reuses_only_matching_successful_checks(tmp_path,monkeypatch):
    write(tmp_path/'DS23-0001_nominations.json',dict(value=1))
    calls=[]
    def audit(case,**kwargs):
        calls.append(case);return dict(case=case,all_checked=True)
    monkeypatch.setattr(report,'audit_nomination',audit)
    args=('DS23-0001','nominations',tmp_path,'execution','dependencies')
    first=report.checkpoint_audit(*args)
    assert first['status']=='passed'
    assert report.checkpoint_audit(*args)==first and len(calls)==1
    write(tmp_path/'DS23-0001_nominations.json',dict(value=2))
    report.checkpoint_audit(*args)
    assert len(calls)==2
    report.checkpoint_audit(*args[:-1],'changed_dependencies')
    assert len(calls)==3


def test_audit_failure_is_saved_and_retried_without_geographic_evaluation(tmp_path,monkeypatch):
    write(tmp_path/'DS23-0001_nominations.json',{})
    def fail(case,**kwargs):raise AssertionError(('candidate',123,.003))
    monkeypatch.setattr(report,'audit_nomination',fail)
    args=('DS23-0001','nominations',tmp_path,'execution','dependencies')
    failed=report.checkpoint_audit(*args)
    assert failed['status']=='failed' and 'candidate' in failed['error']
    assert read(tmp_path/'position/audit_checkpoints/nominations/DS23-0001.json')==failed
    monkeypatch.setattr(report,'audit_nomination',lambda *a,**k:dict(repaired=True))
    assert report.checkpoint_audit(*args)['result']==dict(repaired=True)
