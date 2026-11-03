"""Family-excluded radio calibration and cross-RX relative channel-rate tests.

Satellite positions are not estimated here. Existing scan RF positions serve
only as conditional calibration anchors. Each tested family's points are absent
from all radio-calibration fits. No GPS is imported or used.
"""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time
import numpy as np
from scipy.linalg import helmert
from ds23_channel_rate_transfer import designs,fit,baseline_prediction,transfer
from ds23_channel_clock_screen import predictive_score
from ds23_frequency_events import make_event_problem
from probe_ds23_channel_clock_screen import SOURCES
from probe_ds23_sign_carrier_position import context_signed
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_21_ds23_channel_rate_transfer'
BULK=Path('/srv/bulk/leo/research/ds23-channel-rate-transfer-20261021')


def one(job):
    case=job['case'];cohort=job['cohort'];path=BULK/(case['case']+'.json')
    if path.exists():return read(path)
    started=time.monotonic()
    def timeout(*_):raise TimeoutError('120 second conditional RF channel-rate cap exhausted')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(120)
    try:
        scan,node,mask,powers,means,hyper,entries,signed,binding=context_signed(case['case'])
        saved=signed['policy_arms']['c0'];x=np.array(saved['endpoint_east_north_km']);reference=np.array(saved['phase_reference'])
        base=make_event_problem(scan,node,mask,'c0',reference,powers,means,hyper,[])
        family_labels=np.asarray(base.labels)[base.flat_labels];families=sorted(set(family_labels[mask]));rows=[];rejected=[]
        for family in families:
            channels={}
            for rx in [1,2]:
                counts={};bounds={}
                for row,i,sl in zip(base.rows,base.members,base.slices,strict=True):
                    t=scan.tracks[i];use=mask[sl]
                    if row['candidate_index']!=family or t['receiver']!=rx or not use.any():continue
                    ch=t['channel'];counts[ch]=counts.get(ch,0)+int(use.sum());bounds.setdefault(ch,[]).extend(t['times'][use])
                channels[rx]={ch for ch,n in counts.items() if n>=8 and np.ptp(bounds[ch])>=20.}
            common=sorted(channels[1]&channels[2])
            if len(common)<2:continue
            train_radio=mask&(family_labels!=family);r=reference.copy();history=[]
            for _ in range(5):
                p=make_event_problem(scan,node,train_radio,'c0',r,powers,means,hyper,[])
                state=p.state(x);next_phase=np.clip(state['phases'][p.labels],-15,15)
                history.append(float(np.max(abs(next_phase-r))));r=next_phase
            if history[-1]>.01:
                rejected.append(dict(family=int(family),reason='family-excluded calibration phase did not converge',phase_changes=history));continue
            data={}
            for rx in [1,2]:
                arrays={k:[] for k in ['times','values','sigma','channels','fragments']}
                for k,(row,i,sl) in enumerate(zip(base.rows,base.members,base.slices,strict=True)):
                    t=scan.tracks[i];use=mask[sl]
                    if row['candidate_index']!=family or t['receiver']!=rx or t['channel'] not in common or not use.any():continue
                    q=t['rf_hz']/11.5e9
                    radio=scan.hardware(t,state['beta'])+q*scan.rx_basis[i]@state['smooth'][rx-1]
                    arrays['times'].extend(t['times'][use]);arrays['values'].extend((base.values[sl][use]-radio[use])/q)
                    arrays['sigma'].extend(base.point_noise[sl][use]/q/np.sqrt(powers[k]))
                    arrays['channels'].extend([t['channel']]*int(use.sum()));arrays['fragments'].extend([t['key']]*int(use.sum()))
                data[rx]={k:np.asarray(v) for k,v in arrays.items()}
            if min(len(d['times']) for d in data.values())<30:continue
            all_times=np.r_[data[1]['times'],data[2]['times']];center=float(np.mean(all_times));scale=max(1.,float(np.ptp(all_times)/2))
            for rx,d in data.items():
                d['base'],d['clock']=designs(d['times'],d['channels'],d['fragments'],common,sorted(set(d['fragments'])),center_s=center,scale_s=scale)
                utc=(int(scan.receipt['origin_utc_ns'])%15_000_000_000)/1e9+d['times'];d['slots']=np.floor(utc/15).astype(int)
            folds=[]
            for fold in [0,1,2]:
                receivers={}
                for rx,d in data.items():
                    test=d['slots']%3==fold;train=~test
                    if train.sum()<10 or test.sum()<3:break
                    null=fit(d['base'][train],np.zeros((train.sum(),0)),d['values'][train],d['sigma'][train])
                    model=fit(d['base'][train],d['clock'][train],d['values'][train],d['sigma'][train])
                    receivers[rx]=dict(train=train,test=test,null=null,model=model,training_clock_gain=null['score']-model['score'])
                if len(receivers)!=2:continue
                transfers=[]
                for source_rx in [1,2]:
                    target_rx=3-source_rx;d=data[target_rx];source=receivers[source_rx];target=receivers[target_rx]
                    train,test=target['train'],target['test']
                    a,c=transfer(source['model'],target['null'],d['base'][train],d['clock'][train],d['sigma'][train],d['base'][test],d['clock'][test],d['sigma'][test])
                    b,e=baseline_prediction(target['null'],d['base'][test],d['sigma'][test]);values=d['values'][test]
                    width=source['model']['base_width'];coefficient=np.array(source['model']['coefficient'])[width:]
                    transfers.append(dict(source_RX=source_rx,target_RX=target_rx,source_training_clock_gain=source['training_clock_gain'],
                        source_clock_contrast_mean=coefficient,source_clock_contrast_covariance=np.array(source['model']['covariance'])[width:,width:],
                        source_channel_rates_hz_s=helmert(len(common),full=False).T@coefficient,
                        held_score_gain=predictive_score(b,e,values)-predictive_score(a,c,values),
                        baseline_squared_error=float(np.sum((values-b)**2)),transferred_squared_error=float(np.sum((values-a)**2)),
                        held_points=int(test.sum()),target_baseline_score=predictive_score(b,e,values),transferred_score=predictive_score(a,c,values)))
                folds.append(dict(fold=fold,transfers=transfers))
            paired=[r for r in case['paired_points'] if r['candidate_index']==family and r['channel'] in common]
            rows.append(dict(family=int(family),norad=int(scan.norads[family]),channels=common,
                points_by_RX={str(rx):len(d['times']) for rx,d in data.items()},span_s=float(np.ptp(all_times)),folds=folds,
                independent_native_frame_pairs=len(paired),native_pair_span_s=float(np.ptp([r['time_s'] for r in paired])) if paired else 0.,
                family_excluded_calibration_phase_changes=history,original_tested_family_points_never_update_radio_calibration=True,
                data={str(rx):{k:v for k,v in d.items() if k not in ['base','clock']} for rx,d in data.items()}))
        result=dict(case=case['case'],cohort=cohort,status='complete',rows=rows,rejected=rejected,
            signed_incumbent_sha256=sha(binding),no_GPS_future_TLE_new_RF_or_position_update=True,
            RF_position_fixed_to_original_conditional_mode_not_independent_identity_proof=True)
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(case=case['case'],cohort=cohort,status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-started;write(path,result);print(case['case'],result['status'],len(result.get('rows',[])),result.get('error'),flush=True);return result


def main():
    OUT.mkdir(exist_ok=True);BULK.mkdir(exist_ok=True)
    jobs=[dict(cohort=name,case=c) for name,path in SOURCES.items() for c in read(path)['rows']]
    protocol=dict(cases_by_cohort={name:sorted(c['case'] for c in read(path)['rows']) for name,path in SOURCES.items()},workers=6,per_case_seconds=120,
        baseline='one smooth family quartic per receiver and300Hz Gaussian original-fragment constants',
        clock='zero-sum channel contrasts shared across receivers, fixed1Hz/s prior SD',
        tested_family_excluded_from_all_five_radio_calibration_refreshes=True,positions_fixed_to_existing_RF_mode=True,
        only_original_active_curved_points=True,common_channels_minimum=2,minimum_channel_points_per_RX=8,minimum_channel_span_s=20.,minimum_family_points_per_RX=30,
        three_absolute15s_UTC_slot_folds=True,source_RX_only_updates_clock_mean_and_covariance=True,
        target_fits_only_its_trend_and_fragment_constants=True,
        original_radio_only_noise_and_replication_powers_used=True,
        independent_native_frame_registration_required_for_final_qualification=True,
        no_GPS_or_future_TLE_or_new_RF_or_position_fit=True,
        source_sha256={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_channel_rate_transfer.py']},inputs_sha256={name:sha(p) for name,p in SOURCES.items()})
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('frozen channel-rate transfer protocol changed')
    if not path.exists():write(path,protocol)
    with ProcessPoolExecutor(max_workers=6) as pool:cases=[f.result() for f in as_completed([pool.submit(one,j) for j in jobs])]
    rows=[dict(r,case=c['case'],cohort=c['cohort']) for c in cases for r in c.get('rows',[])];penalty=float(2*np.log(max(2,len(rows))))
    for row in rows:
        transfers=[r for f in row['folds'] for r in f['transfers']];gain=sum(r['held_score_gain'] for r in transfers)
        directional={str(rx):sum(r['held_score_gain'] for r in transfers if r['source_RX']==rx) for rx in [1,2]}
        checks=dict(all_three_slot_folds=len(row['folds'])==3,at_least_four_of_six_transfer_gains_positive=sum(r['held_score_gain']>0 for r in transfers)>=4,
            both_transfer_directions_positive=all(v>0 for v in directional.values()),total_held_gain_exceeds_family_search_penalty=gain>penalty,
            native_pairs_have_independent_curved_anchor_registration=row['independent_native_frame_pairs']>=8 and row['native_pair_span_s']>=20.,
            at_least_four_source_fits_prefer_clock=sum(r['source_training_clock_gain']>0 for r in transfers)>=4)
        row.update(held_score_gain=gain,held_gains_by_source_RX=directional,checks=checks,qualified=all(checks.values()))
    write(OUT/'evaluation.json',dict(cases=cases,rows=rows,all_terminal=True,failures=[c for c in cases if c['status']!='complete'],
        candidate_families=len(rows),qualified_families=sum(r['qualified'] for r in rows),family_search_penalty=penalty,
        no_clock_or_position_model_adopted=True,protocol_sha256=sha(path)))
    print('CHANNEL_RATE_TRANSFER',len(rows),'families; qualified',sum(r['qualified'] for r in rows),flush=True)


if __name__=='__main__':main()
