"""Cross-RX, withheld-slot prediction of periodic native CFO corrections.

Only native tracking contracts and UTC epochs are consumed. Current curved
anchor labels group candidate signals; neither orbital predictions, RF position
estimates nor GPS are used. This is not independent identity validation.
"""

from collections import defaultdict,Counter
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time
import numpy as np
from ds23_channel_clock_screen import fit,prediction,predictive_score,select,transfer
from ds23_frame_registration import PERIOD
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_21_ds23_channel_clock_screen'
BULK=Path('/srv/bulk/leo/research/ds23-channel-clock-screen-20261021')
SOURCES={
    'development':ROOT/'reports/2026_10_21_ds23_reception_anchor_ratio/evaluation.json',
    'scan_disjoint_confirmation':ROOT/'reports/2026_10_21_ds23_cross_RX_curves_confirmation/pairs/evaluation.json'}
TRACKING=ROOT/'reports/2026_10_19_algo02_ds23_full'


def native_curves(case):
    observations=read(TRACKING/case['case']/'observations.json');frequency=defaultdict(set)
    for o in observations:frequency[round(o['time_s'],6),o['channel']].add(o['actual_rf_hz'])
    groups=defaultdict(list);ambiguous=0;result=[]
    for row in case['paired_points']:
        available=frequency[round(row['time_s'],6),row['channel']]
        if len(available)!=1:raise ValueError('native receiver pair has ambiguous RF')
        groups[row['norad'],row['channel'],next(iter(available))].append(row)
    for key,rows in sorted(groups.items()):
        counts=Counter(r['time_s'] for r in rows);ambiguous+=sum(v for v in counts.values() if v>1)
        rows=sorted([r for r in rows if counts[r['time_s']]==1],key=lambda r:r['time_s'])
        t=np.array([r['time_s'] for r in rows])
        for ix in np.split(np.arange(len(t)),np.flatnonzero(np.diff(t)>10.)+1):
            if len(ix)<40 or np.ptp(t[ix])<45.:continue
            y=np.array([[r['native_peaks'][rx]['cfo'] for rx in [0,1]] for r in rows])[ix]
            y=np.unwrap(y*2*np.pi/PERIOD,axis=0)*PERIOD/(2*np.pi)
            result.append(dict(key=key,times=t[ix],values=y))
    return result,ambiguous


def one(job):
    name,case=job['cohort'],job['case'];target=BULK/(name+'_'+case['case']+'.json')
    if target.exists():return read(target)
    started=time.monotonic()
    def timeout(*_):raise TimeoutError('90 second saved-native clock screen cap exhausted')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(90)
    try:
        receipt=read(TRACKING/case['case']/'receipt.json');origin=receipt['origin_utc_ns']
        curves,ambiguous=native_curves(case);rows=[]
        for curve in curves:
            t,y=curve['times'],curve['values'];utc=(int(origin)%15_000_000_000)/1e9+t
            slots=np.floor(utc/15).astype(int)
            if len(set(slots))<4:continue
            folds=[]
            for fold in [0,1,2]:
                test=slots%3==fold;train=~test
                if test.sum()<3 or train.sum()<10:continue
                noise=[]
                for rx in [0,1]:
                    baseline=fit(t[train],y[train,rx],150.,origin)
                    predicted=prediction(baseline,t[train])[0]
                    noise.append(max(40.,float(np.sqrt(np.sum((y[train,rx]-predicted)**2)/(train.sum()-5)))))
                periods={}
                for period in [13.,15.,17.]:
                    models=[select(t[train],y[train,rx],noise[rx],origin,period)[0] for rx in [0,1]]
                    transfers=[]
                    for source_rx in [0,1]:
                        target_rx=1-source_rx;model=models[source_rx]
                        baseline=fit(t[train],y[train,target_rx],noise[target_rx],origin)
                        alternative=transfer(model,t[train],y[train,target_rx],sigma_hz=noise[target_rx])
                        a,c=prediction(alternative,t[test]);b,d=prediction(baseline,t[test]);values=y[test,target_rx]
                        transfers.append(dict(source_RX=source_rx+1,target_RX=target_rx+1,clock_model=model,
                            target_noise_sigma_hz=noise[target_rx],test_points=int(test.sum()),
                            baseline_held_score=predictive_score(b,d,values),alternative_held_score=predictive_score(a,c,values),
                            held_score_gain=predictive_score(b,d,values)-predictive_score(a,c,values),
                            baseline_held_squared_error=float(np.sum((values-b)**2)),alternative_held_squared_error=float(np.sum((values-a)**2))))
                    periods[str(int(period))]=dict(transfers=transfers,total_held_score_gain=sum(r['held_score_gain'] for r in transfers))
                folds.append(dict(fold=fold,training_points_per_RX=int(train.sum()),test_points_per_RX=int(test.sum()),
                    training_slots=sorted(set(slots[train].tolist())),test_slots=sorted(set(slots[test].tolist())),periods=periods))
            rows.append(dict(norad=curve['key'][0],channel=curve['key'][1],rf_hz=curve['key'][2],points_per_RX=len(t),span_s=float(np.ptp(t)),
                times=t,native_CFO_hz=y,folds=folds))
        result=dict(case=case['case'],cohort=name,status='complete',rows=rows,ambiguous_native_pairs_excluded=ambiguous,
            original_native_pairs_sha256=sha(SOURCES[name]),UTC_receipt_sha256=sha(TRACKING/case['case']/'receipt.json'),
            no_GPS_or_orbital_model_or_position_fit_used=True,source_pair_labels_are_conditional_original_curved_nominations=True)
    except Exception as exc:result=dict(case=case['case'],cohort=name,status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-started;write(target,result)
    print(name,case['case'],result['status'],len(result.get('rows',[])),result.get('error'),flush=True);return result


def main():
    OUT.mkdir(exist_ok=True);BULK.mkdir(exist_ok=True)
    jobs=[dict(cohort=name,case=c) for name,source in SOURCES.items() for c in read(source)['rows'] if c['status']=='complete']
    protocol=dict(cases_by_cohort={name:sorted(c['case'] for c in read(source)['rows']) for name,source in SOURCES.items()},workers=6,per_case_seconds=90,
        minimum_pairs=40,minimum_span_s=45.,minimum_distinct_15s_UTC_slots=4,maximum_pair_gap_s=10.,
        exact_native_CFO_alias_period_hz=PERIOD,ambiguous_same_time_native_pairs_excluded=True,
        baseline='independent quartic trend per receiver; fit on training points only',
        alternative='one constant repeating-ramp amplitude and one of30 reset phases learned on source RX only',
        amplitude_peak_to_peak_prior_sigma_hz=300.,phase_search_penalty='2log30',
        periods_s=[13.,15.,17.],folds='three absolute15s-UTC-slot residue classes; held slots absent in both source and target training',
        noise='each RX training-only quartic residual SD, floor40Hz; conditional uncertainty only',
        held_prediction='other receiver quartic trained on same training slots, source-only ramp amplitude transferred with covariance',
        no_orbit_or_GPS_or_position_or_new_RF_input=True,
        source_sha256={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_channel_clock_screen.py']},
        inputs_sha256={name:sha(p) for name,p in SOURCES.items()})
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('channel clock screen protocol changed')
    if not path.exists():write(path,protocol)
    with ProcessPoolExecutor(max_workers=6) as pool:cases=[f.result() for f in as_completed([pool.submit(one,j) for j in jobs])]
    n=sum(len(c.get('rows',[])) for c in cases);penalty=float(2*np.log(max(2,3*n)))
    for case in cases:
        for row in case.get('rows',[]):
            gains={p:sum(f['periods'][p]['total_held_score_gain'] for f in row['folds']) for p in ['13','15','17']}
            transfers=[r for f in row['folds'] for r in f['periods']['15']['transfers']]
            phases=np.array([r['clock_model']['phase_s'] for r in transfers]);amplitudes=np.array([r['clock_model']['amplitude_peak_to_peak_hz'] for r in transfers])
            spread=float(np.max(abs((phases[:,None]-phases[None,:]+7.5)%15-7.5))) if len(phases) else 15.
            checks=dict(all_three_block_folds=len(row['folds'])==3,all_source_clocks_pass_training_search_penalty=all(r['clock_model']['selected_over_baseline'] for r in transfers),
                all_six_cross_RX_held_score_gains_positive=bool(transfers) and all(r['held_score_gain']>0 for r in transfers),
                reset_phase_spread_at_most1s=spread<=1.,amplitude_sign_consistent=bool(len(amplitudes)) and (bool(np.all(amplitudes>0)) or bool(np.all(amplitudes<0))),
                held_gain_exceeds_all_curve_period_search_penalty=gains['15']>penalty,
                physical15s_period_beats_both_controls=gains['15']>max(gains['13'],gains['17']))
            row.update(total_period_held_score_gains=gains,checks=checks,qualified=all(checks.values()),phase_spread_s=spread)
    rows=[dict(r,case=c['case'],cohort=c['cohort']) for c in cases for r in c.get('rows',[])]
    write(OUT/'evaluation.json',dict(cases=cases,rows=rows,all_terminal=True,failures=[c for c in cases if c['status']!='complete'],
        eligible_curves=n,qualified_curves=sum(r['qualified'] for r in rows),all_curve_period_search_penalty=penalty,
        no_clock_or_position_correction_adopted=True,protocol_sha256=sha(path)))
    print('PERIODIC_CLOCK_SCREEN',n,'curves; qualified',sum(r['qualified'] for r in rows),flush=True)


if __name__=='__main__':main()
