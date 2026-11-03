"""Phase-aware clock and component-null tests on four additional saved scans."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import hashlib
import signal
import time
import numpy as np

from ds23_phase_marginal_iq import PhaseMarginalIQ
from ds23_partially_shared_iq import PartiallySharedIQ
from ds23_rf_carrier_alias_grid import AliasBranchWorkspace
from ds23_joint_component_rf import JointComponentWorkspace,common_segments
from ds23_joint_gain_controls import frame_coefficients
from ds23_fractional_differential_phase import fractional_geometry
from inventory_ds23_phase_clock_confirmation import OUT
from probe_ds23_partially_shared_iq import MODES
from run_algo01_ds23_sample import ROOT,read,write,sha

BULK=Path('/srv/bulk/leo/research/ds23-phase-clock-confirmation-20261021')


def one(job):
    index,entry=job['index'],job['entry'];path=BULK/f'probe{index:03d}.json'
    if path.exists():return read(path)
    began=time.monotonic()
    def timeout(*_):raise TimeoutError('360second saved-scan native alias/phase refit cap')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(360)
    try:
        with np.load(entry['panel'],allow_pickle=False) as panel:values=panel[entry['window_key']]
        if 'sha256:'+hashlib.sha256(values.tobytes()).hexdigest()!=entry['raw_window_sha256']:
            raise ValueError('saved IQ hash changed')
        samples=np.array([values[:,r,0].astype(float)+1j*values[:,r,1] for r in [0,1]])
        fs,edge=entry['sample_rate_hz'],entry['edge'];epochs=np.asarray([c['epochs'] for c in entry['components']])
        epochs[:,1]+=np.rint((epochs[:,0]-epochs[:,1])/(fs/750))*(fs/750)
        seeds=[[dict(CFO_hz=entry['components'][k]['peaks'][r]['fractional_tracking_cfo_hz'],
            offset_samples=0.,modulation_ppm=0.) for k in [0,1]] for r in [0,1]]
        geometry=[fractional_geometry(y,fs,edge,epochs[k,r],seeds[r][k]) for r,y in enumerate(samples) for k in [0,1]]
        segments=common_segments(geometry)
        if len(segments)<10:raise ValueError('ten distinct common native frames required')
        folds=[]
        for parity in [0,1]:
            support=[ix for k,ix in enumerate(segments) if k%2==parity];held=[ix for k,ix in enumerate(segments) if k%2!=parity]
            native=[];noise=[];coefficients=[];variances=[]
            for r in [0,1]:
                ws=AliasBranchWorkspace(samples[r],fs,edge,epochs[:,r],support)
                fitted=ws.joint_fit(seeds[r],iterations=24);native.append(fitted)
                stat=ws.statistics(fitted['parameters'],derivatives=False)
                noise.append(stat['residual_energy']/max(1,stat['sample_count']-3*len(support)-3))
                c,cov=frame_coefficients(samples[r],ws.columns(fitted['parameters']),support)
                coefficients.append(c);variances.append(np.diagonal(cov,axis1=1,axis2=2).real)
            gain=np.maximum(np.mean(abs(coefficients[0])**2-variances[0],axis=0),1e-12)
            parameters=[np.asarray(f['parameters']).reshape(2,3) for f in native]
            delta=parameters[1][:,0]-parameters[0][:,0]
            ratios=[]
            for k in [0,1]:
                weight=1/(variances[0][:,k]+variances[1][:,k])
                ratios.append(np.sum(weight*coefficients[0][:,k].conj()*coefficients[1][:,k])
                    /np.sum(weight*abs(coefficients[0][:,k])**2))
            ratios=np.asarray(ratios);code=np.r_[parameters[0][:,1:].ravel(),parameters[1][:,1:].ravel()]
            base=np.r_[parameters[0][:,0],delta,code,np.column_stack((ratios.real,ratios.imag)).ravel()]
            models={}
            for name,shared in MODES.items():
                problem=PartiallySharedIQ(samples,fs,edge,epochs.T,support,noise,gain,
                    separate_clocks=True,shared_components=shared)
                trials=[problem.fit(base,sigma_start=s,maxiter=60) for s in ([.15,.7] if any(shared) else [.0])]
                fitted=min(trials,key=lambda f:f['training_NLL'])
                models[name]=dict(fit=fitted,trials=trials,
                    predictions=[problem.predict(fitted,held,source_receiver=r) for r in [0,1]])
            if np.ptp(delta)<750:
                # A common model is only meaningful inside one physical RF branch.
                problem=PhaseMarginalIQ(samples,fs,edge,epochs.T,support,noise,gain)
                seed=np.r_[parameters[0][:,0],np.mean(delta),code,np.column_stack((ratios.real,ratios.imag)).ravel()]
                trials=[problem.fit(seed,sigma_start=s,maxiter=60) for s in [.15,.7]]
                fitted=min(trials,key=lambda f:f['training_NLL'])
                models['common_clock']=dict(fit=fitted,trials=trials,
                    predictions=[problem.predict(fitted,held,source_receiver=r) for r in [0,1]])
            records=[]
            if 'common_clock' in models:
                for name in MODES:
                    records.append(dict(null_model=name,common_vs_null_held_gain=[
                        models[name]['predictions'][r]['NLL']-models['common_clock']['predictions'][r]['NLL'] for r in [0,1]]))
            folds.append(dict(parity=parity,native_training_fits=native,noise_variance=noise,source_gain_variance=gain,
                raw_native_frequency_contrasts_hz=delta,models=models,comparisons=records))
        checks=dict(common_physical_branch_available=all('common_clock' in f['models'] for f in folds),
            all_native_RF_interiors=all(not m['boundary'] for f in folds for m in f['native_training_fits']),
            all_common_RF_phase_interiors=all('common_clock' in f['models'] and not f['models']['common_clock']['fit']['boundary']
                and not f['models']['common_clock']['fit']['phase_variance_boundary'] for f in folds),
            all_optimizers_converged=all(m['fit']['converged'] for f in folds for m in f['models'].values()),
            common_beats_all_nulls_every_fold_RX=all(len(f['comparisons'])==4 and all(
                min(q['common_vs_null_held_gain'])>0 for q in f['comparisons']) for f in folds))
        result=dict(index=index,case=entry['case'],entry=entry,status='complete',aligned_epochs=epochs,
            frames=len(segments),time_s=[ix.mean()/fs for ix in segments],folds=folds,checks=checks,
            conditional_two_component_candidate=all(checks.values()),
            no_absolute_CFO_uncertainty_or_position_factor_qualified=True)
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(index=index,case=entry['case'],entry=entry,status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-began;write(path,result)
    print(index,entry['case'],result['status'],result.get('conditional_two_component_candidate'),result.get('error'),flush=True)
    return result


def main():
    BULK.mkdir(exist_ok=True);inventory=OUT/'inventory.json'
    protocol=dict(inventory_sha256=sha(inventory),workers=4,per_window_seconds=360,
        source_tools={n:sha(ROOT/'tools'/n) for n in [Path(__file__).name,'ds23_partially_shared_iq.py',
            'ds23_phase_marginal_iq.py','ds23_rf_carrier_alias_grid.py','ds23_joint_component_rf.py']},
        source_selection_only_native_RF_before_clock_fit=True,minimum_each_native_margin=.1,
        original_point3_cohort_excluded=True,one_saved_window_per_additional_scan=True,
        source_and_target_joint_carrier_alias_grid_per_RX=[-1,0,1],iterations_per_native_alias=24,
        phase_fit_iterations=60,phase_starts_rad=[.15,.7],
        proper_training_only_TX_gain_power_same_in_all_models=True,matched_training_held_support_across_models=True,
        held_target_gain_and_phase_never_fit=True,no_GPS_TLE_satellite_identity_or_position_used=True,
        these_scans_were_previously_studied_with_other_RF_methods_and_are_not_new_sites=True,
        no_CFO_precision_or_position_improvement_claimed=True)
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('frozen additional-scan clock protocol changed')
    if not path.exists():write(path,protocol)
    jobs=[dict(index=k,entry=e) for k,e in enumerate(read(inventory)['selected'])]
    with ProcessPoolExecutor(max_workers=4) as pool:
        rows=[f.result() for f in as_completed([pool.submit(one,j) for j in jobs])]
    write(OUT/'evaluation.json',dict(rows=sorted(rows,key=lambda r:r['index']),all_terminal=True,
        protocol_sha256=sha(path),no_position_result_changed=True))


if __name__=='__main__':main()
