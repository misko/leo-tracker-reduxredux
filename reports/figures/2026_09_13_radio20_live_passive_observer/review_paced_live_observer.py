"""Independent saved-IQ, FFT, integer-moment and dense-SVD ARM replay review."""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from tests.starlink_glrt.test_cpu_coarse import integer_grid, bank
from tests.starlink_glrt.test_tracking_resolver import oracle
from tests.starlink_glrt.test_tracking_solver import moments
from tests.starlink_glrt.test_native_solver import dense_fit
from tools.starlink_glrt_native_replay import rotate
from validate_native_admission import rotated,check_rotation
from review_startup_cfo import check as check_startup
from review_live_observer import review as review_observer

BASE = Path('/srv/bulk/leo/glrt-deployment-20260909/radio20-iq-tracking-20260912')
ROOT = Path(sys.argv[1]) if len(sys.argv) == 2 else BASE/'paced-original-seed-arm-v1-results'


def main():
    op = json.loads((ROOT/'operator.json').read_text())
    assert op['payload_sha256']['probe']==hashlib.sha256((BASE/'paced-live-observer-arm-v1').read_bytes()).hexdigest()
    for case in op['cases'].values():
        assert case['status']=='complete' and case['exit_code']==0
    host=op['scope']=='paced_saved_iq_host_no_iio'
    if not host: assert op['before'] == op['after'] and op['temporary_files_removed']
    assert op['new_rf_samples'] == 0 and op['status'] == 'replay_complete_review_pending'
    refs = np.fromfile(BASE/'direct-references.ci16',dtype='<i2').reshape(4,3300,4)
    bases = []
    for raw in refs:
        ref = raw[:,0].astype(float)+1j*raw[:,1]
        derivative = raw[:,2].astype(float)+1j*raw[:,3]
        t = (2*np.arange(3300)-3299)/5000000
        bases.append(np.column_stack((ref,-derivative,2j*np.pi*1000*t*ref)))
    result = dict(status='pass',scope='paced_saved_iq_causal_startup_and_live_observer_review',
                  execution_platform='host' if host else 'ARM',rotation_oracle_checks=check_rotation(),
                  new_rf_samples=0,native_jobs=0,live_tracking_qualified=False,cases={})
    for name in ('positive','control'):
        root = ROOT/name
        for filename,receipt in op['cases'][name]['artifacts'].items():
            payload=(root/filename).read_bytes()
            assert receipt=={'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}
        iq = np.fromfile(BASE/'paced-original-seed-input-v1'/f'{name}.ci16',dtype='<i2').reshape(-1,2)
        assert hashlib.sha256(iq.tobytes()).hexdigest() == op['inputs'][name]['sha256']
        origin = op['inputs'][name]['source_window']
        rows = [json.loads(s) for s in (root/'worker.jsonl').read_text().splitlines()]
        status = json.loads((root/'stdout.json').read_text())
        assert status['status'] == status['rf_samples'] == status['native_jobs'] == 0
        scan = rows[0];assert scan['kind'] == 'paced_scan' and scan['window_start'] == origin
        grid = np.fromfile(root/'grids.u32',dtype='<u4').reshape(11,3333)
        np.testing.assert_array_equal(grid,integer_grid(iq[:14000],bank()))
        scores = []
        for epoch,frequency,score,power in scan['peaks']:
            x = iq[epoch+22:epoch+3322].astype(float); z = x[:,0]+1j*x[:,1]
            ref = bases[0][:,0]
            expected = max(abs(np.fft.fft(z*np.conj(ref),16384))**2)/(np.vdot(z,z).real*np.vdot(ref,ref).real)
            np.testing.assert_allclose(power,expected,rtol=2e-12,atol=2e-15)
            scores.append(expected)
        assert scan['selected_rank'] == int(np.argmax(scores))
        owned = np.fromfile(root/'worker.iq.ci16',dtype='<i2').reshape(-1,2)
        seed = next(r for r in rows if r['kind'] == 1)
        resolved = next(r for r in rows if r['kind'] == 2)
        assert seed['repeat'] == seed['fraction'] == 0
        assert seed['first'] == origin+scan['peaks'][scan['selected_rank']][0]+14
        assert seed['start'] == seed['first']+8 and seed['starts'] == [8,3341,6675,10008]
        assert seed['copied']['source_now']-origin <= 2500000
        checked = 0; accepted = []; past = []
        for row in rows:
            if row['kind'] not in (1,3): continue
            count = row['iq_samples'];start = row['first'];offset = row['iq_offset']
            assert offset == checked and count == (13316 if row['kind'] == 1 else 3300)
            x = owned[offset:offset+count]
            np.testing.assert_array_equal(x,iq[start-origin:start-origin+count])
            view = row['copied'] if row['kind'] == 1 else row['source']
            assert view['first'] <= start and start+count <= view['end'] <= view['source_now']
            assert view['epoch'] == 3 and view['valid'] and not view['closed']
            assert view['observed_ns'] <= row['recorded_ns']
            checked += count
            if row['kind'] == 1:
                np.testing.assert_allclose(resolved['hypotheses'],oracle(refs[0,:,:2],x,seed['starts']),
                                           rtol=2e-12,atol=2e-8)
                continue
            z = rotated(x,0,row['phase_step'])
            phase = row['reference_phase']
            assert list(moments(z,refs[phase].astype(np.int64)).words) == row['moments']
            correction,coherence,improved = dense_fit(bases[phase],z)
            np.testing.assert_allclose(row['coherence'],coherence,rtol=2e-12,atol=2e-14)
            step = row['phase_step'];step = step if step < 2**31 else step-2**32
            cfo = step*2500000/2**32+np.clip(correction[1],-.25,.25)*1000
            np.testing.assert_allclose(row['cfo_hz'],cfo,rtol=2e-12,atol=2e-8)
            rejection = (32 if np.any(abs(correction)>=.25) else 0) | (64 if coherence < .05 else 0)
            assert row['rejection'] == rejection and row['accepted'] == int(rejection == 0)
            past.append(row)
            if row['accepted']:
                accepted.append((row,np.clip(correction[0],-.25,.25)*1e-6,cfo))
        assert checked == len(owned)
        startup=check_startup(resolved['cfo_hz'],past)
        terminal = next(r for r in rows if r['kind']=='paced_terminal')
        assert terminal['worker_status'] == status['worker_status']
        assert status['worker_status'] in ((1,-8) if name == 'positive' else (-6,))
        assert terminal['retained_past'] == len(past) <= 200
        assert terminal['supported_history'] == min(len(accepted),96)
        lead = None
        if name == 'positive':
            assert len(accepted) >= 8 and all(r['accepted'] for r in past[:8])
            proposals = [r for r in rows if r['kind'] == 4]
            assert 1 <= len(proposals) <= 2
            handoff = proposals[-1]
            assert handoff['count'] == min(len(accepted),96)
            assert handoff['anchor'] == accepted[0][0]['first']
            assert handoff['last_supported'] == accepted[-1][0]['frame']
            assert handoff['frame'] > handoff['last_seen'] and handoff['frame']+7 <= handoff['last_supported']+32
            expected_history = {}
            for row,delay,cfo in accepted[-96:]:
                offset = row['first']-handoff['anchor']-(row['frame']-handoff['first_frame'])*10000/3
                offset += row['reference_phase']/4+delay*2500000
                expected_history[row['frame']] = [offset,cfo]
            for frame,offset,cfo in handoff['history'][:handoff['count']]:
                np.testing.assert_allclose([offset,cfo],expected_history[frame],rtol=2e-12,atol=2e-8)
            recent = [r for r in handoff['history'][:handoff['count']] if handoff['last_supported']-r[0] < 96]
            assert len(recent) >= 8
            frames,offsets,_ = np.array(recent).T
            slope,intercept = np.polyfit(frames-handoff['last_supported'],offsets,1)
            prediction = handoff['anchor']+(handoff['frame']-handoff['first_frame'])*10000/3
            prediction += intercept+slope*(handoff['frame']-handoff['last_supported'])
            assert abs(handoff['start']-prediction) < 1
            assert handoff['start'] >= handoff['checked_source']['source_now']+12500
            for view in (handoff['checked_source'],terminal['source']):
                assert view['source_now'] <= origin+5000000
            lead = handoff['start']-terminal['source']['source_now']
            assert (lead >= 12500) == (status['worker_status'] == 1)
        else:
            assert not accepted and not any(r['kind'] == 4 for r in rows)
        observer=review_observer(root)
        observer_iq=np.fromfile(root/'observer.iq.ci16',dtype='<i2').reshape(-1,2)
        for row in map(json.loads,(root/'observer.jsonl').read_text().splitlines()):
            if row['kind']!='measurement': continue
            first=row['first']-origin;offset=row['iq_offset']
            np.testing.assert_array_equal(observer_iq[offset:offset+3300],iq[first:first+3300])
        if name=='positive':
            assert len(observer['episodes'])==1 and observer['committed_supported']>0
            assert observer['episodes'][0]['status']==status['observer_status']==-5
            assert observer['episodes'][0]['committed']==status['observer_measurements']
        else: assert not observer['episodes'] and status['observer_measurements']==0
        result['cases'][name] = dict(status='pass',worker_status=status['worker_status'],
            passive_observer=observer,acquisition_elapsed_ms=terminal['elapsed_ms'],
            startup_prediction_review=startup,
            grid_values_checked=int(grid.size),ranking_scores_checked=len(scores),resolver_hypotheses_checked=17,
            moment_heads_checked=len(past),dense_svd_fits_checked=len(past),accepted_observations=len(accepted),
            supported_history=terminal['supported_history'],worker_iq_samples_checked=checked,
            elapsed_ms=status['elapsed_ms'],scan_ms=scan['scan_ms'],rank_ms=scan['rank_ms'],
            seed_age_ms=(seed['copied']['source_now']-origin)/2500,handoff_lead_samples=lead,
            handoff_fresh=status['worker_status'] == 1,
            retained_handoff_proposals=sum(r['kind'] == 4 for r in rows),
            sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir() if p.is_file()})
    result['reviewer_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result['operator_sha256'] = hashlib.sha256((ROOT/'operator.json').read_bytes()).hexdigest()
    with (ROOT/'independent-review.json').open('x') as out: json.dump(result,out,indent=2);out.write('\n')
    print(json.dumps(result))


if __name__ == '__main__': main()
