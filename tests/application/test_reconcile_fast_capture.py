from leo.acquisition.authority import LocalCaptureAuthority,RadioResource,CaptureTaskKind
from leo.application.reconcile_fast_capture import reconcile
from leo.storage.fast_scan import FastScanStore


def test_abandoned_status_is_reconciled_without_inventing_a_sealed_capture(tmp_path):
    authority=LocalCaptureAuthority(tmp_path/'control',(RadioResource('radio','serial','uri'),));store=FastScanStore(tmp_path)
    for name in ('abandoned','recent','completed'):
        store.update_automatic(name,state='recording' if name!='completed' else 'complete')
    facts=[dict(run_id='abandoned',state='invalid',updated_utc_ns=1,error='old invalid checkpoint'),
           dict(run_id='recent',state='running',updated_utc_ns=2_999_999_999_999),
           dict(run_id='completed',state='running',updated_utc_ns=1)]
    result=reconcile(authority,'radio',facts,store,now_ns=3_000_000_000_000)
    assert result['repaired']==['abandoned']
    assert store.automatic_status('abandoned')['state']=='failed'
    assert store.automatic_status('recent')['state']=='recording'
    assert store.automatic_status('completed')['state']=='complete'


def test_an_active_acquisition_owner_prevents_reconciliation(tmp_path):
    authority=LocalCaptureAuthority(tmp_path/'control',(RadioResource('radio','serial','uri'),));store=FastScanStore(tmp_path)
    store.update_automatic('old',state='recording')
    with authority.claim(('radio',),task_id='live',task_kind=CaptureTaskKind.SCANNER_SWEEP):
        result=reconcile(authority,'radio',[dict(run_id='old',updated_utc_ns=1)],store,now_ns=3_000_000_000_000)
    assert result['state']=='deferred' and store.automatic_status('old')['state']=='recording'
