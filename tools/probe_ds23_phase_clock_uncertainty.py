"""Whole-frame uncertainty for RF-qualified additional-scan clock candidates."""

from pathlib import Path
import signal
import time
import numpy as np

from ds23_phase_marginal_iq import PhaseMarginalIQ
from ds23_phase_marginal_bootstrap import FrameResampledPhaseIQ
from ds23_rf_carrier_alias_grid import AliasBranchWorkspace
from ds23_joint_component_rf import common_segments
from ds23_joint_gain_controls import frame_coefficients
from ds23_fractional_differential_phase import fractional_geometry
from audit_ds23_phase_marginal_iq import factorized_joint_NLL
from probe_ds23_phase_clock_confirmation import OUT as SOURCE_OUT
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=SOURCE_OUT/'bootstrap'
BULK=Path('/srv/bulk/leo/research/ds23-phase-clock-uncertainty-20261021')
REPLICATES=63
WARM_STEPS=40


def one(row):
    entry=row['entry'];index=row['index'];path=BULK/f'probe{index:03d}.json'
    if path.exists():return read(path)
    began=time.monotonic()
    def timeout(*_):raise TimeoutError('300second phase-aware frame bootstrap cap')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(300)
    try:
        with np.load(entry['panel'],allow_pickle=False) as panel:values=panel[entry['window_key']]
        samples=np.array([values[:,r,0].astype(float)+1j*values[:,r,1] for r in [0,1]])
        fs,edge=entry['sample_rate_hz'],entry['edge'];epochs=np.asarray(row['aligned_epochs'])
        initial=[[dict(CFO_hz=entry['components'][k]['peaks'][r]['fractional_tracking_cfo_hz'],
            offset_samples=0.,modulation_ppm=0.) for k in [0,1]] for r in [0,1]]
        geometry=[fractional_geometry(y,fs,edge,epochs[k,r],initial[r][k]) for r,y in enumerate(samples) for k in [0,1]]
        segments=common_segments(geometry);noise=[];native=[];gain=None
        for r in [0,1]:
            ws=AliasBranchWorkspace(samples[r],fs,edge,epochs[:,r],segments)
            fitted=ws.joint_fit(initial[r],iterations=24);native.append(fitted)
            statistics=ws.statistics(fitted['parameters'],derivatives=False)
            noise.append(statistics['residual_energy']/max(1,statistics['sample_count']-3*len(segments)-3))
            if r==0:
                c,cov=frame_coefficients(samples[r],ws.columns(fitted['parameters']),segments)
                gain=np.maximum(np.mean(abs(c)**2-np.diagonal(cov,axis1=1,axis2=2).real,axis=0),1e-12)
        problem=PhaseMarginalIQ(samples,fs,edge,epochs.T,segments,noise,gain)
        trials=[problem.fit(np.asarray(f['models']['common_clock']['fit']['parameters']),
            sigma_start=f['models']['common_clock']['fit']['sigma_rad'],maxiter=60) for f in row['folds']]
        full=min(trials,key=lambda f:f['training_NLL']);replicates=[]
        rng=np.random.default_rng(2026102180+index)
        for k in range(REPLICATES):
            while True:
                draw=rng.integers(0,len(segments),len(segments))
                if len(np.unique(draw))>=4:break
            resampled=FrameResampledPhaseIQ(samples,fs,edge,epochs.T,segments,noise,gain,draw_indices=draw)
            fitted=resampled.fit(np.asarray(full['parameters']),sigma_start=full['sigma_rad'],maxiter=WARM_STEPS)
            independent=factorized_joint_NLL(resampled,np.asarray(fitted['parameters']),fitted['sigma_rad'])
            if abs(independent-fitted['training_NLL'])>1e-5:
                raise ValueError('bootstrap source-first density replay differs')
            replicates.append(dict(index=k,draws=draw,parameters=fitted['parameters'],sigma_rad=fitted['sigma_rad'],
                training_NLL=fitted['training_NLL'],boundary=fitted['boundary'],
                phase_variance_boundary=fitted['phase_variance_boundary'],converged=fitted['converged'],
                maximum_scaled_gradient=fitted['maximum_scaled_gradient'],
                factorized_replay_difference=independent-fitted['training_NLL']))
            write(BULK/f'probe{index:03d}_progress.json',dict(index=index,case=row['case'],completed=len(replicates),
                requested=REPLICATES,replicates=replicates,full_fit=full,seconds=time.monotonic()-began))
        frequencies=np.asarray([f['parameters'][:3] for f in replicates]);covariance=np.cov(frequencies,rowvar=False)
        result=dict(index=index,case=row['case'],entry=entry,status='complete',aligned_epochs=epochs,
            full_fit=full,full_start_trials=trials,full_native_fits=native,noise_variance=noise,source_gain_variance=gain,
            frames=len(segments),bootstrap_replicates=replicates,bootstrap_frequency_covariance=covariance,
            bootstrap_frequency_sigma_hz=np.sqrt(np.diag(covariance)),
            fold_clock_difference_hz=abs(row['folds'][0]['models']['common_clock']['fit']['receiver_clock_hz'][0]
                -row['folds'][1]['models']['common_clock']['fit']['receiver_clock_hz'][0]),
            bounded_replicates=sum(r['boundary'] or r['phase_variance_boundary'] for r in replicates),
            unconverged_replicates=sum(not r['converged'] for r in replicates),
            rank_deficient_replicates=None,full_RF_covariance_rank_not_estimated=True,
            source_first_density_replays=len(replicates),
            native_RF_acquisition_gain_power_noise_variance_and_carrier_alias_conditioned=True,
            full_phase_variance_and_RF_parameters_refitted_each_replicate=True,
            bootstrap_is_engineering_uncertainty_not_absolute_CFO_coverage=True)
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(index=index,case=row['case'],entry=entry,status='failed',error=repr(exc),
            completed_bootstrap_refits=len(replicates) if 'replicates' in locals() else 0)
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-began;write(path,result)
    print(index,row['case'],result['status'],result.get('bootstrap_frequency_sigma_hz'),result.get('error'),flush=True)
    return result


def main():
    OUT.mkdir(exist_ok=True);BULK.mkdir(exist_ok=True);source=SOURCE_OUT/'evaluation.json'
    selected=[r for r in read(source)['rows'] if r.get('conditional_two_component_candidate')]
    protocol=dict(source_sha256=sha(source),selected_indices=[r['index'] for r in selected],
        selection_uses_RF_null_predictions_and_bound_convergence_checks_before_positions=True,
        full_native_alias_iterations=24,full_phase_fit_steps=60,bootstrap_replicates=REPLICATES,bootstrap_warm_steps=WARM_STEPS,
        per_window_seconds=300,whole_paired_frame_resampling=True,
        proper_gain_prior_and_noise_variance_fixed_from_full_native_training=True,
        conditional_uncertainty_not_absolute_frequency_coverage=True,
        source_tools={n:sha(ROOT/'tools'/n) for n in [Path(__file__).name,'ds23_phase_marginal_bootstrap.py','ds23_phase_marginal_iq.py']})
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('frozen phase-clock uncertainty protocol changed')
    if not path.exists():write(path,protocol)
    rows=[one(r) for r in selected]
    write(OUT/'evaluation.json',dict(rows=rows,all_terminal=True,protocol_sha256=sha(path),no_position_result_changed=True))


if __name__=='__main__':main()
