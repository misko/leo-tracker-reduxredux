"""Refine the same31 paired-frame draws with original bounds and scaled loss."""

from pathlib import Path
import signal
import time
import numpy as np

from ds23_phase_marginal_iq import PhaseMarginalIQ
from ds23_phase_marginal_bootstrap import FrameResampledPhaseIQ
from ds23_whitened_phase_fit import fit_phase_whitened
from ds23_fractional_differential_phase import fractional_geometry
from ds23_joint_component_rf import common_segments
from audit_ds23_phase_marginal_iq import factorized_joint_NLL
from probe_ds23_phase_clock_uncertainty_v2 import OUT as PREVIOUS
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=PREVIOUS.parent/'bootstrap_v3'
BULK=Path('/srv/bulk/leo/research/ds23-phase-clock-uncertainty-v3-20261021')


def one(row):
    began=time.monotonic();index=row['index'];entry=row['entry'];path=BULK/f'probe{index:03d}.json'
    if path.exists():return read(path)
    def timeout(*_):raise TimeoutError('240second fixed-draw whitened refinement cap')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(240)
    try:
        with np.load(entry['panel'],allow_pickle=False) as archive:raw=archive[entry['window_key']]
        samples=np.array([raw[:,r,0].astype(float)+1j*raw[:,r,1] for r in [0,1]])
        epochs=np.asarray(row['aligned_epochs']);fs=entry['sample_rate_hz'];edge=entry['edge']
        geometry=[fractional_geometry(y,fs,edge,epochs[k,r],dict(
            CFO_hz=entry['components'][k]['peaks'][r]['fractional_tracking_cfo_hz'],offset_samples=0.,modulation_ppm=0.))
            for r,y in enumerate(samples) for k in [0,1]]
        segments=common_segments(geometry);noise=row['noise_variance'];gain=row['source_gain_variance']
        center=np.asarray(row['full_fit']['parameters'])
        problem=PhaseMarginalIQ(samples,fs,edge,epochs.T,segments,noise,gain)
        full=fit_phase_whitened(problem,row['full_fit']['full_parameters'],bounds_center=center,maxiter=40)
        whitener=np.asarray(full['whitener']);replicates=[]
        for previous in row['bootstrap_replicates']:
            resampled=FrameResampledPhaseIQ(samples,fs,edge,epochs.T,segments,noise,gain,draw_indices=previous['draws'])
            start=np.r_[previous['parameters'],np.log(previous['sigma_rad'])]
            fit=fit_phase_whitened(resampled,start,bounds_center=center,whitener=whitener,maxiter=40)
            if fit['training_NLL']>previous['training_NLL']+1e-5:raise ValueError('refinement worsened unchanged-data density')
            replay=factorized_joint_NLL(resampled,np.asarray(fit['parameters']),fit['sigma_rad'])
            if abs(replay-fit['training_NLL'])>1e-5:raise ValueError('whitened density factorization replay failed')
            replicates.append(dict(index=previous['index'],draws=previous['draws'],parameters=fit['parameters'],
                sigma_rad=fit['sigma_rad'],training_NLL=fit['training_NLL'],converged=fit['converged'],
                boundary=fit['boundary'],phase_variance_boundary=fit['phase_variance_boundary'],
                maximum_whitened_gradient=fit['maximum_whitened_gradient'],
                maximum_scaled_gradient=fit['maximum_scaled_gradient'],factorized_replay_difference=replay-fit['training_NLL'],
                NLL_improvement=previous['training_NLL']-fit['training_NLL'],calls=fit['calls'],iterations=fit['iterations']))
            write(BULK/f'probe{index:03d}_progress.json',dict(completed=len(replicates),replicates=replicates,seconds=time.monotonic()-began))
        frequencies=np.asarray([r['parameters'][:3] for r in replicates]);covariance=np.cov(frequencies,rowvar=False)
        result=dict(row,full_fit=full,bootstrap_replicates=replicates,bootstrap_frequency_covariance=covariance,
            bootstrap_frequency_sigma_hz=np.sqrt(np.diag(covariance)),
            bounded_replicates=sum(r['boundary'] or r['phase_variance_boundary'] for r in replicates),
            unconverged_replicates=sum(not r['converged'] for r in replicates),
            maximum_whitened_gradient=max(r['maximum_whitened_gradient'] for r in replicates),
            same31draws_observations_likelihood_and_original_RF_bounds=True,
            source_first_density_replays=len(replicates),status='complete')
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(index=index,case=row['case'],entry=entry,status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-began;write(path,result)
    print(index,row['case'],result['status'],result.get('unconverged_replicates'),result.get('bootstrap_frequency_sigma_hz'),result.get('error'),flush=True)
    return result


def main():
    OUT.mkdir(exist_ok=True);BULK.mkdir(exist_ok=True);source=PREVIOUS/'evaluation.json'
    protocol=dict(source_sha256=sha(source),same31physical_draws=True,original_bootstrap_RF_bounds_preserved=True,
        maximum_steps=40,per_window_seconds=240,curvature_from_full_training_fit_only=True,
        source_tools={n:sha(ROOT/'tools'/n) for n in [Path(__file__).name,'ds23_whitened_phase_fit.py','ds23_phase_marginal_iq.py']},
        no_GPS_TLE_satellite_ID_position_or_new_RF_used=True,no_absolute_CFO_coverage_claimed=True)
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('frozen fixed-draw refinement protocol changed')
    if not path.exists():write(path,protocol)
    rows=[one(r) for r in read(source)['rows'] if r['status']=='complete']
    write(OUT/'evaluation.json',dict(rows=rows,all_terminal=True,protocol_sha256=sha(path),no_position_result_changed=True))


if __name__=='__main__':main()
