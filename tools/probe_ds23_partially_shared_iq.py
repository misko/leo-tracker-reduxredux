"""Test both, either or neither pilot correspondence on pinned training IQ."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import hashlib
import signal
import time
import numpy as np

from ds23_partially_shared_iq import PartiallySharedIQ
from ds23_fractional_differential_phase import fractional_geometry
from ds23_joint_component_rf import common_segments
from probe_ds23_phase_marginal_iq import SOURCE,RAW,OUT as PHASE
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_21_ds23_partially_shared_iq'
BULK=Path('/srv/bulk/leo/research/ds23-partially-shared-iq-20261021')
MODES={'both_shared':[True,True],'only_0_shared':[True,False],
    'only_1_shared':[False,True],'neither_shared':[False,False]}


def one(row):
    index,entry=row['index'],row['entry'];path=BULK/f'probe{index:03d}.json'
    if path.exists():return read(path)
    began=time.monotonic()
    def timeout(*_):raise TimeoutError('240second partial correspondence RF cap')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(240)
    try:
        with np.load(entry['panel'],allow_pickle=False) as panel:values=panel[entry['window_key']]
        assert 'sha256:'+hashlib.sha256(values.tobytes()).hexdigest()==entry['raw_window_sha256']
        samples=np.array([values[:,r,0].astype(float)+1j*values[:,r,1] for r in [0,1]])
        epochs=np.asarray(row['aligned_epochs']);fs=entry['sample_rate_hz'];edge=entry['edge']
        geometry=[fractional_geometry(y,fs,edge,epochs[k,r],dict(
            CFO_hz=entry['components'][k]['peaks'][r]['fractional_tracking_cfo_hz'],
            offset_samples=0.,modulation_ppm=0.)) for r,y in enumerate(samples) for k in [0,1]]
        segments=common_segments(geometry)
        raw=next(r for r in read(RAW/'evaluation.json')['rows'] if r['index']==index)
        previous=next(r for r in read(PHASE/'evaluation.json')['rows'] if r['index']==index)
        folds=[]
        for fold in row['folds']:
            parity=fold['parity'];support=[ix for k,ix in enumerate(segments) if k%2==parity]
            held=[ix for k,ix in enumerate(segments) if k%2!=parity]
            old=next(f for f in previous['folds'] if f['parity']==parity)
            seed=np.asarray(next(f for f in raw['folds'] if f['parity']==parity)['models']['separate']['fit']['parameters'])
            models={}
            for name,shared in MODES.items():
                problem=PartiallySharedIQ(samples,fs,edge,epochs.T,support,old['noise_variance'],
                    old['source_gain_variance'],separate_clocks=True,shared_components=shared)
                trials=[problem.fit(seed,sigma_start=s,maxiter=60) for s in ([.15,.7] if any(shared) else [.0])]
                fit=min(trials,key=lambda f:f['training_NLL'])
                predictions=[problem.predict(fit,held,source_receiver=r) for r in [0,1]]
                replay=problem.statistics(fit['full_parameters'],fixed_sigma=None if fit['fit_phase_variance'] else 0.,gradient=False)['NLL']
                if abs(replay-fit['training_NLL'])>1e-6:raise ValueError('partial model training replay failed')
                models[name]=dict(fit=fit,trials=trials,predictions=predictions,training_replay_difference=replay-fit['training_NLL'])
            comparisons=[]
            for name in ['only_0_shared','only_1_shared','neither_shared']:
                gains=[models[name]['predictions'][r]['NLL']-models['both_shared']['predictions'][r]['NLL'] for r in [0,1]]
                comparisons.append(dict(null_model=name,both_shared_vs_null_held_gain=gains))
            folds.append(dict(parity=parity,models=models,comparisons=comparisons,
                noise_variance=old['noise_variance'],source_gain_variance=old['source_gain_variance']))
        checks=dict(both_shared_beats_all_partial_models_every_fold_and_RX=all(
            min(q['both_shared_vs_null_held_gain'])>0 for f in folds for q in f['comparisons']),
            all_model_RF_fits_interior=all(not m['fit']['boundary'] for f in folds for m in f['models'].values()),
            all_model_optimizers_converged=all(m['fit']['converged'] for f in folds for m in f['models'].values()),
            both_shared_phase_variance_interior=all(not f['models']['both_shared']['fit']['phase_variance_boundary'] for f in folds))
        result=dict(index=index,case=entry['case'],entry=entry,status='complete',folds=folds,checks=checks,
            conditional_two_component_candidate=all(checks.values()),
            no_absolute_clock_precision_or_position_factor_qualified=True)
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(index=index,case=entry['case'],status='failed',entry=entry,error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-began;write(path,result)
    print(index,entry['case'],result['status'],result.get('conditional_two_component_candidate'),result.get('error'),flush=True)
    return result


def main():
    OUT.mkdir(exist_ok=True);BULK.mkdir(exist_ok=True)
    protocol=dict(source_sha256=sha(SOURCE),raw_source_sha256=sha(RAW/'evaluation.json'),phase_source_sha256=sha(PHASE/'evaluation.json'),
        source_tools={n:sha(ROOT/'tools'/n) for n in [Path(__file__).name,'ds23_partially_shared_iq.py','ds23_phase_marginal_iq.py']},
        workers=6,per_window_seconds=240,modes=MODES,iterations_per_start=60,sigma_starts=[.15,.7],
        independent_target_component_has_independent_circular_Gaussian_gain_per_frame=True,
        unmatched_complex_channel_phase_gauge_fixed=True,training_gain_power_and_thermal_noise_fixed_across_models=True,
        same_native_training_only_RF_separate_clock_seed_each_model=True,
        held_target_signal_gains_and_receiver_phase_never_fitted=True,
        independent_source_and_target_carrier_contrasts_for_unmatched_components=True,
        no_GPS_TLE_satellite_ID_new_RF_or_position_used=True,
        positive_held_scores_are_not_absolute_frequency_uncertainty_validation=True)
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('frozen partial-correspondence protocol changed')
    if not path.exists():write(path,protocol)
    with ProcessPoolExecutor(max_workers=6) as pool:
        rows=[f.result() for f in as_completed([pool.submit(one,r) for r in read(SOURCE)['rows']])]
    write(OUT/'evaluation.json',dict(rows=sorted(rows,key=lambda r:r['index']),all_terminal=True,
        protocol_sha256=sha(path),no_position_estimate_changed=True))


if __name__=='__main__':main()
