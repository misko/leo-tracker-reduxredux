"""Independent acquired-history and observer review against original saved IQ."""
import json,hashlib,sys
from pathlib import Path
import numpy as np
from tests.starlink_glrt.test_tracking_resolver import oracle
from tests.starlink_glrt.test_tracking_solver import moments
from tests.starlink_glrt.test_native_solver import dense_fit
from validate_native_admission import rotated
from review_live_observer_cadence import review as observer_review
from tools.review_glrt_cpu_startup import review_startup_carrier
BASE=Path(__file__).parent;root=Path(sys.argv[1])
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((root/'result.json').read_text())
if (root/'operator.json').exists():
    op=json.loads((root/'operator.json').read_text())
    build=json.loads((BASE/'paced-acquisition-host-v2-results/result.json').read_text())
    assert op['status']=='complete_review_pending' and op['temporary_files_removed']
    assert op['serial']=='1040005e0b100007100010000bf33a5d4d' and op['host']=='192.168.1.20'
    assert op['before']==op['after'] and op['new_rf_samples']==op['native_jobs']==0
    assert op['payload_sha256']['probe']==build['arm_sha256']
    advisory='** WARNING: connection is not using a post-quantum key exchange algorithm.\r\n** This session may be vulnerable to "store now, decrypt later" attacks.\r\n** The server may need to be upgraded. See https://openssh.com/pq.html\r\n'
    assert len(op['cases'])==3
    for case in op['cases']:
        assert case['exit_code']==0 and case['stderr'] in ('',advisory)
        for name,sha in case['sha256'].items():
            assert digest(root/f"{case['label']}-{case['cut']}"/name)==sha
refs=np.fromfile(BASE/'direct-references.ci16',dtype='<i2').reshape(4,3300,4).astype(np.int64)
bases=[]
for r in refs:
    z=r[:,0]+1j*r[:,1];d=r[:,2]+1j*r[:,3]
    bases.append(np.column_stack((z,-d,1j*np.pi*1000/2500000*(2*np.arange(3300)-3299)*z)))
checks=[]
for case in manifest['cases']:
    directory=root/f"{case['label']}-{case['cut']}"
    original=BASE/f"paced-original-seed-input-v1/{case['label']}.ci16"
    assert digest(original)==case['input_sha256']
    iq=np.fromfile(original,dtype='<i2').reshape(-1,2)[case['cut']*447851:]
    rows=[json.loads(line) for line in (directory/'worker.jsonl').read_text().splitlines()]
    seed=next(r for r in rows if r['kind']==1);resolved=next(r for r in rows if r['kind']==2)
    assert seed['copied']['source_now']<=2500000 and seed['starts']==[8,3341,6675,10008]
    hypotheses=oracle(refs[0,:,:2],iq[seed['first']:seed['first']+13316],seed['starts'])
    np.testing.assert_allclose(resolved['hypotheses'],hypotheses,rtol=2e-12,atol=2e-8)
    np.testing.assert_allclose([resolved[k] for k in ('best_shift','cfo_hz','coherence')],max(hypotheses,key=lambda h:h[2]),rtol=2e-12,atol=2e-8)
    retained=np.fromfile(directory/'worker.iq.ci16',dtype='<i2').reshape(-1,2);at=0;past=[]
    for row in rows:
        if row['kind'] not in (1,3):continue
        count=13316 if row['kind']==1 else 3300;first=row['first']
        assert row['iq_offset']==at and row['iq_samples']==count
        np.testing.assert_array_equal(retained[at:at+count],iq[first:first+count]);at+=count
        view=row['copied'] if row['kind']==1 else row['source']
        assert view['epoch']==1 and view['valid'] and not view['closed']
        assert view['first']<=first and first+count<=view['end']<=view['source_now']<=len(iq)
        assert view['observed_ns']<=row['recorded_ns']
        if row['kind']==1:continue
        z=rotated(iq[first:first+count],0,row['phase_step']);phase=row['reference_phase']
        assert list(moments(z,refs[phase]).words)==row['moments']
        correction,coherence,_=dense_fit(bases[phase],z)
        np.testing.assert_allclose(row['coherence'],coherence,rtol=2e-12,atol=2e-14)
        rejection=(32 if np.any(abs(correction)>=.25) else 0)|(64 if coherence<.05 else 0)
        assert row['rejection']==rejection and row['accepted']==int(rejection==0)
        step=row['phase_step'];step=step if step<2**31 else step-2**32
        cfo=step*2500000/2**32+np.clip(correction[1],-.25,.25)*1000
        np.testing.assert_allclose(row['cfo_hz'],cfo,rtol=2e-12,atol=2e-8)
        past.append(row)
    assert at==len(retained) and len(past)==case['past']
    startup=review_startup_carrier(resolved['cfo_hz'],past)
    observer=observer_review(directory,expected_spacing=3)
    obsrows=[json.loads(line) for line in (directory/'observer.jsonl').read_text().splitlines()]
    obsraw=np.fromfile(directory/'observer.iq.ci16',dtype='<i2').reshape(-1,2)
    for row in obsrows:
        if row['kind']=='measurement':
            np.testing.assert_array_equal(obsraw[row['iq_offset']:row['iq_offset']+3300],iq[row['first']:row['first']+3300])
    checks.append(dict(label=case['label'],cut=case['cut'],past=len(past),accepted_past=sum(r['accepted'] for r in past),observer=observer,startup=startup))
result=dict(status='pass',cases=checks,new_rf_samples=0,native_tracking_qualified=False,reviewer_sha256=digest(Path(__file__)),manifest_sha256=digest(root/'result.json'))
with (root/'independent-review-v2.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps(result,indent=2))
