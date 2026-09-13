"""Independent numerical review of the passive live observer's private files.

This checks retained software IQ and causal scheduling. It does not certify
the seed's RF identity, native arithmetic, original IQ ownership, or tracking.
Run the capture/startup/native reviewers separately for those claims.
"""
import copy
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from tests.starlink_glrt.test_tracking_solver import moments
from tests.starlink_glrt.test_native_solver import dense_fit
from validate_native_admission import rotated,check_rotation

BASE=Path(__file__).parent
RATE=2500000


def review(root,rows=None):
    root=Path(root)
    if rows is None: rows=[json.loads(line) for line in (root/'observer.jsonl').read_text().splitlines()]
    workers=[json.loads(line) for line in (root/'worker.jsonl').read_text().splitlines()]
    seeds={r['attempt']:r for r in workers if r['kind']==4}
    joins={r['attempt']:r for r in workers if r['kind']=='observer_join'}
    raw=(root/'observer.iq.ci16').read_bytes()
    assert len(raw)%13200==0
    iq=np.frombuffer(raw,dtype='<i2').reshape(-1,2)
    refs=np.fromfile(BASE/'direct-references.ci16',dtype='<i2').reshape(4,3300,4).astype(np.int64)
    assert hashlib.sha256(refs.astype('<i2').tobytes()).hexdigest()=='78b50e1aea5c350889b0798fc691491299925932e496a918cd5fbd3b9bc4faf2'
    bases=[]
    for r in refs:
        ref=r[:,0]+1j*r[:,1];der=r[:,2]+1j*r[:,3]
        bases.append(np.column_stack((ref,-der,1j*np.pi*1000/RATE*(2*np.arange(3300)-3299)*ref)))
    at=0;offset=0;episodes=[];checked=0;supported=0
    while at<len(rows):
        start=rows[at];assert start['kind']=='start';at+=1
        seed=seeds[start['attempt']]
        assert start['rate']==RATE and start['native_rate'] in (30000000,60000000)
        assert start['epoch']==seed['epoch'] and start['first_frame']==seed['last_seen']+9
        assert start['maximum_measurements']==200 and start['deadline_ns']-start['started_ns']==3000000000
        assert start['retained_total']*3300==offset
        measurements=[]
        while at<len(rows) and rows[at]['kind']=='measurement': measurements.append(rows[at]);at+=1
        terminal=rows[at];at+=1
        assert terminal['kind']=='terminal' and terminal['status'] in (0,-2,-3,-4,-5,-6)
        committed=terminal['measurements']
        assert 0<=len(measurements)-committed<=1 and len(measurements)<=200
        history=sorted(seed['history'][:seed['count']]);last_seen=seed['last_seen'];last_support=seed['last_supported']
        for index,r in enumerate(measurements):
            assert all(r[k]==start[k] for k in ('attempt','episode','epoch'))
            assert r['rate']==RATE and r['sequence']==index and r['frame']==start['first_frame']+9*index
            assert last_seen<r['frame']<=last_support+32
            recent=np.array([h for h in history if 0<=last_support-h[0]<96],dtype=float)
            assert len(recent)>=8
            x=recent[:,0]-last_support
            design=np.column_stack((x,np.ones(len(x))))
            fit=np.linalg.lstsq(design,recent[:,1:],rcond=None)[0]
            delay,frequency=np.array([r['frame']-last_support,1.])@fit
            nominal,rem=divmod((r['frame']-seed['first_frame'])*RATE,750)
            q16=round((delay+rem/750)*65536)
            quarter=round(q16/16384)
            whole,phase=divmod(quarter,4)
            assert (r['first'],r['reference_phase'])==(seed['anchor']+nominal+whole,phase)
            step=r['phase_step'];hz=(step if step<2**31 else step-2**32)*RATE/2**32
            assert abs(hz-frequency)<=RATE/2**32+1e-7
            if index==0: assert start['source_limit']==r['first']+7500000
            source=r['source']
            assert source['epoch']==start['epoch'] and source['valid']==1 and source['closed']==0
            assert source['first']<=r['first'] and r['first']+3300<=source['end']<=source['source_now']<=start['source_limit']
            assert source['observed_ns']<=r['recorded_ns']<=start['deadline_ns']
            assert r['iq_offset']==offset and r['iq_samples']==3300
            cut=iq[offset:offset+3300];assert len(cut)==3300;offset+=3300
            rotated_iq=rotated(cut,0,step)
            assert list(moments(rotated_iq,refs[phase]).words)==r['moments']
            if np.any(cut):
                correction,coherence,improved=dense_fit(bases[phase],rotated_iq)
                expected=[np.clip(correction[0],-.25,.25)*1e-6,np.clip(correction[1],-.25,.25)*1000,coherence,improved]
                actual=[r['delay_correction_s'],r['residual_cfo_hz'],r['coherence'],r['linearized_coherence']]
                np.testing.assert_allclose(actual,expected,rtol=2e-9,atol=2e-8)
                rejection=(32 if np.any(abs(correction)>=.25) else 0)|(64 if coherence<.05 else 0)
            else: rejection=4
            assert r['rejection']==rejection and r['accepted']==int(rejection==0)
            assert abs(r['cfo_hz']-hz-r['residual_cfo_hz'])<1e-7
            checked+=1
            if index<committed:
                last_seen=r['frame']
                if r['accepted']:
                    last_support=r['frame'];supported+=1
                    correction=r['first']-seed['anchor']-nominal+phase/4+r['delay_correction_s']*RATE-rem/750
                    history.append([r['frame'],correction,r['cfo_hz']]);history=history[-96:]
        assert all(terminal[k]==start[k] for k in ('attempt','episode','epoch'))
        assert (terminal['last_seen'],terminal['last_supported'])==(last_seen,last_support)
        assert terminal['retained_total']*3300==offset
        join=joins[start['attempt']]
        assert join['observer_joined']==1 and join['observer_status']==terminal['status']
        episodes.append(dict(epoch=start['epoch'],measurements=len(measurements),committed=committed,status=terminal['status']))
    assert offset==len(iq)
    return dict(status='pass',scope='independent_passive_observer_numerics_and_causality',
                native_tracking_qualified=False,episodes=episodes,moments_and_dense_fits_checked=checked,
                committed_supported=supported,iq_sha256=hashlib.sha256(raw).hexdigest())


if __name__=='__main__':
    rotation_checks=check_rotation()
    results={str(Path(p)):review(p) for p in sys.argv[1:]}
    mutations=0
    for p in sys.argv[1:]:
        rows=[json.loads(line) for line in (Path(p)/'observer.jsonl').read_text().splitlines()]
        first=next((i for i,r in enumerate(rows) if r['kind']=='measurement'),None)
        if first is None: continue
        for field in ('first','phase_step','coherence','iq_offset'):
            changed=copy.deepcopy(rows);changed[first][field]+=1
            try: review(p,changed)
            except (AssertionError,ValueError): mutations+=1
            else: raise AssertionError('undetected mutation '+field)
    result=dict(rotation_scalar_checks=rotation_checks,mutations_rejected=mutations,results=results)
    print(json.dumps(result,indent=2))
