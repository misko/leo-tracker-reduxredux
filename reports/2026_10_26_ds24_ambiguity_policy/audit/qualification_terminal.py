"""Artifact-only four-owner audit: nomination, cavity, bounds and necessary gates."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
from scipy.linalg import solve_triangular
from scipy.special import logsumexp
from leo.analysis.research.retained_track_likelihood import whitening

ROOT=Path(__file__).resolve().parent.parent
SCI=ROOT/'qualification'
sys.path.insert(0,str(SCI))
import qualify as q
read=lambda p:json.loads(Path(p).read_bytes())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()


def arrays(path):
    with np.load(path,allow_pickle=False) as data:return {k:data[k] for k in data.files}


def null_density(raw,C,times):
    root=np.linalg.cholesky(C);basis=np.polynomial.legendre.legvander(2*(times-times.min())/np.ptp(times)-1,4)*q.k.PERIOD/np.sqrt(6)
    design=np.vstack((solve_triangular(root,basis,lower=True),np.eye(5)))
    rhs=np.vstack((solve_triangular(root,(raw[None]+np.arange(-4,5)[:,None]*q.k.PERIOD).T,lower=True),np.zeros((5,9))))
    residual=rhs-design@np.linalg.lstsq(design,rhs,rcond=None)[0]
    rr=np.linalg.qr(design,mode='reduced')[1]
    cost=np.sum(residual**2,axis=0)+2*np.log(np.diag(root)).sum()+2*np.log(abs(np.diag(rr))).sum()+len(raw)*np.log(2*np.pi)
    return float(-2*(logsumexp(-.5*cost)-np.log(9)))


def order(rows,null):
    if not null['independent_dense_passed']:return None
    models=[('unresolved',None,-.5*(null['objective']+1e-6),-.5*(null['objective']-1e-6))]
    for row in rows:
        if row.get('empty_support_certified') and row.get('certified_visibility'):
            models.append(('physical',row['norad'],-np.inf,-np.inf));continue
        lo,hi=row.get('full_support_lower_log_integral'),row.get('full_support_upper_log_integral')
        if not row.get('certified_visibility') or lo is None or hi is None or not np.isfinite([lo,hi]).all() or lo>hi:return None
        models.append(('physical',row['norad'],lo,hi))
    for i,row in enumerate(models):
        margin=row[2]-max(x[3] for j,x in enumerate(models) if i!=j)
        if margin>0:return row[0],row[1],margin
    return None


def main():
    start=time.monotonic();checks=[];slots=[];details=[];null_errors=[]
    def check(name,passed,**detail):checks.append(dict(name=name,passed=bool(passed),**detail))
    protocol=read(SCI/'protocol.json');seal=read(SCI/'RF_seal.json');run=read(SCI/'execution.json');meta=read(SCI/'metadata.json')
    check('exact frozen source/actual prior and terminal RF hashes',
        sha(SCI/'protocol.json')==seal['protocol_sha256']=='af8700aab11de54c900ea8cd204c3487c5b64a5c71227bd9503a18aa5deb00d2' and
        all(sha(p)==h for p,h in protocol['source_input_hashes'].items()) and all(sha(p)==h for p,h in seal['files'].items()))
    screen_receipt=read(SCI/'screen_receipt.json');all_outcomes=[s for arm in run['arms'] for s in arm['slots']]
    check('all eight owner/arm outcomes and original600second cumulative denominator retained',
        len(all_outcomes)==8 and len({(s['case'],a['arm']) for a in run['arms'] for s in a['slots']})==8 and
        abs(run['cumulative_worker_seconds']-screen_receipt['cumulative_prefix_seconds']-sum(a['seconds'] for a in run['arms']))<1e-8 and
        run['cumulative_worker_seconds']<=600 and run['total_owner_arm_slots']==8 and run['total_candidate_slots']==64 and
        run['position_fits']==0 and not run['GPS_used'] and run['operational_identity_admissions']==0)
    for target in protocol['targets']:
        case=target['case'];folder=SCI/case;entry=read(folder/'entry.json');trace=read(folder/'original_trace.json')
        original_parent=read(q.r.SOURCE/'family_cavity/position'/f'{case}.json')
        node=original_parent['selected']['node'] if original_parent['accepted'] else original_parent['baseline_node']
        entries=original_parent['selected']['entries'] if original_parent['accepted'] else original_parent['baseline_entries']
        track_lookup={t['key']:t for t in read(q.r.SOURCE/case/'tracks.json')}
        coverage=read(q.PRIOR/'ownership'/case/'parent.json')['coverage']
        catalogue=arrays(folder/'catalogue.npz');screen=read(folder/'c0_screen.json');pool=screen['candidate_indices'];norads=screen['candidate_norads']
        check(case+': whole native source and archived gauge/canonical rejection provenance',
            entry['observation_ids']==target['observation_ids']==trace['native_ids'] and len(set(trace['native_ids']))==target['points'] and
            trace['graph_native_gauge_max_error_Hz']<1e-6 and
            trace['canonical']['compatible']==next(t for t in meta['targets'] if t['case']==case)['archived_nomination_compatible'] and
            all(not set(target['observation_ids'])&set(coverage[a]['accepted_observation_ids']) for a in q.ARMS))
        for arm in q.ARMS:
            current_screen=read(folder/(arm+'_screen.json'))
            ranked=sorted([i for i,x in enumerate(current_screen['coarse_scores']) if x is not None],
                key=lambda i:(current_screen['coarse_scores'][i],int(catalogue['norads'][i])))
            check(case+'/'+arm+': ordinary full-catalogue rank arithmetic, no nominee/reserve',
                current_screen['catalogue_count']==len(catalogue['norads']) and not current_screen['forced_or_reserved_candidate'] and
                ranked==current_screen['ranked_visible_indices'] and ranked[:8]==current_screen['candidate_indices'] and
                current_screen['candidate_norads']==[int(catalogue['norads'][i]) for i in ranked[:8]])
            base=arrays(folder/(arm+'_original.npz'));comp=arrays(folder/(arm+'_conditional.npz'));cavity=read(folder/(arm+'_cavity.json'))
            check(case+'/'+arm+': same saved c0 RF coordinates/IDs/q and proper conditional arrays',
                np.array_equal(base['x'],original_parent['policy_arms']['c0']['endpoint_east_north_km']) and
                base['native_ids'].tolist()==target['observation_ids'] and len(comp['raw'])==target['points'] and
                np.array_equal(comp['q'],base['q']) and np.linalg.eigvalsh(comp['covariance']).min()>0)
            old=coverage[arm];removed_curved=set()
            for row in node['seed']['rows']:
                if row['candidate_index'] in pool:removed_curved |= set(track_lookup[row['component']]['observation_ids'])&set(old['curved_observation_ids'])
            removed_predictive={oid for e in entries if e['candidate_index'] in pool for oid in e['observation_ids']}
            residual_ok=all(r['compatible'] for r in cavity['diagnostic_gates']['tracks']) and all(r['compatible'] for r in cavity['diagnostic_predictive_gates'])
            check(case+'/'+arm+': symmetric whole-pool family cavity and unchanged parent gate semantics',
                removed_curved==set(cavity['removed_curved_ids']) and removed_predictive==set(cavity['removed_predictive_ids']) and
                set(cavity['calibration_ids'])==set(old['curved_observation_ids'])-removed_curved and
                set(cavity['predictive_ids'])==set(old['predictive_observation_ids'])-removed_predictive and
                cavity['original_remaining_gates_pass']==residual_ok and q.w.hard_parent(cavity))
            null=read(folder/(arm+'_null.json'));err=abs(null_density(comp['raw'],comp['covariance'],base['times'])-null['independent_dense_objective']);null_errors.append(err)
            check(case+'/'+arm+': independent proper null determinant/least-squares/nine-alias replay',
                err<=1e-6 and null['independent_dense_passed']==(null['independent_dense_error']<=1e-7),objective_error=err)
            result_path=folder/(arm+'_result.json');result=read(result_path) if result_path.exists() else None
            for n in norads:
                cp=folder/(arm+'_'+str(n)+'_checkpoint.json');support=folder/(arm+'_'+str(n)+'_support.json')
                state='completed_comparison' if result else ('primary_checkpoint_only' if cp.exists() else ('interrupted_primary' if support.exists() else 'not_attempted'))
                slots.append(dict(case=case,arm=arm,norad=n,state=state))
                if cp.exists():
                    row=read(cp)
                    check(case+'/'+arm+'/'+str(n)+': immutable primary candidate index/whole-pool binding',
                        row['norad']==n and row['candidate_index']==pool[norads.index(n)] and
                        (row.get('status')=='failed' or row.get('visible_mass_renormalized') is False))
            if result is None:
                failure=read(folder/(arm+'_failure.json'))
                check(case+'/'+arm+': unavailable primary-timeout preserves all partials without promotion',
                    case in ['DS24-0014','DS24-0017'] and failure['status']=='unavailable' and 'TimeoutError' in failure['error'] and
                    failure['physical_candidate_denominator']==8 and not (folder/(arm+'_adequacy_checkpoint.json')).exists())
                continue
            rows=result['candidates'];winner=order(rows,null);certificate=result['evidence_order_certificate']
            check(case+'/'+arm+': matched ordinary c0 pool and independent finite-model evidence-order bounds',
                [r['norad'] for r in rows]==norads and winner is not None and certificate['proved'] and
                winner[:2]==(certificate['winner_kind'],certificate['winner_norad']) and
                abs(winner[2]-certificate['minimum_log_evidence_margin'])<1e-10 and
                not certificate['absolute_score_precision_implied'] and not certificate['operational_identity_assignment'])
            diag=result['source_diagnostic'];gate_ok=[]
            for view,field in [('conservative','conservative_raw_hz'),('fullmode','fullmode_raw_hz')]:
                expected=q.adequacy.source_gate(np.asarray(diag[field]),base['times'],whitening(base['times']),np.asarray(diag['nominal_elevation_deg']))
                stored=diag[view+'_gate']
                gate_ok.append(stored['compatible'])
                check(case+'/'+arm+': original necessary '+view+' residual/noise gates replay from saved arrays',
                    expected['primitive']==stored['primitive'] and expected['compatible']==stored['compatible'] and
                    max(abs(expected[k]-stored[k]) for k in ['rms_hz','bias_hz','raw_RMS_hz'])<1e-8 and
                    all(abs(float(expected['noise'][k])-float(stored['noise'][k]))<1e-10 for k in stored['noise']))
            check(case+'/'+arm+': diagnostic phase/shape does not qualify identity or parent calibration',
                -15<=diag['phase_s']<=15 and diag['alias'] in range(-4,5) and not diag['global_MAP_certified'] and
                not diag['shape_means_calibrated'] and not diag['target_radio_mean_updated'] and not diag['original_growth_supported'] and
                not result['identity_qualified'] and not result['position_admission'] and not result['original_accepted_IDs_changed'] and
                result['original_remaining_residual_gates_pass']==residual_ok and not gate_ok[0])
            details.append(dict(case=case,arm=arm,winner=result['raw_physical_winner'],finite_pool_log_margin=winner[2],
                conservative_gate=gate_ok[0],fullmode_diagnostic_gate=gate_ok[1],cavity_parent_residual_gates=residual_ok,
                removed_curved=len(removed_curved),removed_predictive=len(removed_predictive),identity_qualified=False))
    statuses=Counter(s['state'] for s in slots)
    check('all64 candidate slots and four complete/four unavailable owner-arm outcomes retained',
        len(slots)==64 and statuses==Counter(completed_comparison=32,primary_checkpoint_only=16,interrupted_primary=4,not_attempted=12) and
        Counter(s['status'] for s in all_outcomes)==Counter(complete=4,unavailable=4))
    receipt=dict(all_passed=all(r['passed'] for r in checks),checks=checks,seconds=time.monotonic()-start,
        source_sha256=sha(__file__),protocol_sha256=sha(SCI/'protocol.json'),RF_seal_sha256=sha(SCI/'RF_seal.json'),
        candidate_slot_states=dict(statuses),all64_candidate_slots=slots,completed_owner_arm_details=details,
        maximum_independent_null_objective_error=max(null_errors),new_orbit_propagation_calls=0,new_position_fits=0,
        geographic_truth_read=False,scope='Cavity relative evidence and necessary residual gates; no qualified identity, restored-parent corroboration or operational addition.')
    with (ROOT/'audit/qualification_terminal.json').open('x') as f:json.dump(receipt,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(dict(all_passed=receipt['all_passed'],checks=len(checks),seconds=receipt['seconds'],states=dict(statuses),
        failed=[r for r in checks if not r['passed']])))


if __name__=='__main__':main()
