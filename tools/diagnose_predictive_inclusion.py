"""Replay predictive trials: raw gates versus covariance-aware diagnostics."""
import argparse
from pathlib import Path
import numpy as np
from scipy.linalg import cho_solve
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from ds23_frequency_events import make_event_problem,attach_event_predictive
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features
from probe_ds23_frequency_events import cached
from leo.analysis.research.predictive_track import mixture_prediction
from leo.analysis.research.retained_track_likelihood import profile,PERIOD
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from correlated_curve_prediction import gaussian


def one(inv,protocol,trial,out):
    d=context(inv);entries=d['entries']+trial['target_entries'];rows=[]
    for arm,v in trial['arms'].items():
        kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
        if trial.get('orphan_orbit_prior'):
            from probe_ds23_history_calibrated_phase import make_problem
            p0,_=d['problems']['c0']
            active={r['candidate_index'] for r,sl in zip(p0.rows,p0.slices,strict=True) if d['keep'][sl].any()}
            families=sorted({e['candidate_index'] for e in protocol['targets']}-active)
            def factory(*a,**k):
                original=d.get('problem_factory',make_problem)(*a,**k)
                q=make_problem(*a,**k,support_policy=d.get('support_policy','nominal'),predictive_orbital_families=families)
                q.constants[:]=original.constants
                return q
            kw={'base_problem_factory':factory}
        p=make_event_problem(d['scan'],d['node'],d['keep'],arm,np.array(v['phase_reference']),d['powers'],d['means'],d['model'],[],**kw)
        attach_event_predictive(p,entries,d['powers'])
        if trial.get('orphan_phase_refresh'):
            from predictive_orphan_phase import attach_orphan_phase
            attach_orphan_phase(p,entries,d['powers'],orbital=trial.get('orphan_orbit_prior',False))
        cached(p);x=np.array(v['endpoint_east_north_km']);c=p.calculate(x)
        if not np.isclose(c['negative_twice_elbo'],v['negative_twice_elbo'],rtol=1e-10,atol=1e-5):raise ValueError('saved fit replay mismatch')
        view,y,sigma,groups,slices=linear_geometry(p,entries);geometry=geometry_features(view,x,0.);h=geometry['features']
        weights=d['powers'][p.noise_groups[p.keep]]*c['noise_precision'][p.noise_groups[p.keep]]/p.point_noise[p.keep]**2
        u=c['features'][p.keep];gram=np.diag(c['coefficient_prior_precision'])+u.T@(u*weights[:,None])
        cov=np.diag(2*sigma*sigma)+300.**2*(groups[:,None]==groups[None,:])+h@cho_solve((np.linalg.cholesky(gram),True),h.T)
        mean=view.q*geometry['intercept']+h@c['coefficient'];old=np.arange(len(y))<sum(e['points'] for e in d['entries'])
        conditional=mixture_prediction(y,mean[None],cov[None],np.zeros(1),old,~old)
        offset=int(old.sum())
        failed={g['component'] for g in v['linear_gates'] if not g['compatible']}
        for entry,sl in zip(entries,slices,strict=True):
            incumbent=sl.start<offset
            if incumbent and entry['component'] not in failed:continue
            track=d['scan'].tracks[entry['track_index']];raw=c['linear_raw_prediction_residual_hz'][sl]
            terms=profile(raw,np.zeros(len(raw)),*d['scan'].white[entry['track_index']],bias_sigma=300.)
            noise=batch_noise_screen(terms['innovations'],track['times'])
            if incumbent:
                target=np.zeros(len(y),bool);target[sl]=True
                diagnostic=mixture_prediction(y,mean[None],cov[None],np.zeros(1),old&~target,target)
                cs=slice(None)
            else:
                diagnostic=conditional;cs=slice(sl.start-offset,sl.stop-offset)
            predictive_residual=diagnostic['held_residual_hz'][cs]
            whitened=gaussian(predictive_residual,diagnostic['held_covariance_hz2'][cs,cs])['whitened']
            whitened_noise=batch_noise_screen((whitened*150)[None],track['times'])
            rows.append(dict(arm=arm,component=entry['component'],norad=entry['norad'],incumbent=incumbent,times_s=track['times'],
                CFO_hz=track['values'],prediction_CFO_hz=y[sl]-raw-entry['alias']*PERIOD,
                raw_residual_hz=raw,profile_bias_hz=float(terms['bias'][0]),profile_RMS_hz=float(terms['rms'][0]),
                profile_noise={k:bool(v[0]) if v.dtype==bool else float(v[0]) for k,v in noise.items()},
                conditional_on_existing_predictive_residual_hz=predictive_residual,
                predictive_sigma_hz=diagnostic['prediction_sigma_hz'][cs],whitened=whitened,
                whitened_noise={k:bool(v[0]) if v.dtype==bool else float(v[0]) for k,v in whitened_noise.items()},
                calibration_coefficient_change_at_fixed_position=float(np.max(abs(c['coefficient']-p.curved_calculate(x)['coefficient'])))))
    write(out.with_suffix('.json'),dict(rows=rows,acceptance_unchanged=True,conditional_diagnostics_only=True))
    plot=[r for r in rows if r['arm']=='fitted_c'];fig,axs=plt.subplots(3,len(plot),figsize=(6*len(plot),10),squeeze=False,layout='constrained')
    for col,r in enumerate(plot):
        t=r['times_s'];ax=axs[0,col];ax.scatter(t,r['CFO_hz']/1000,s=15,label='GLRT');ax.plot(t,r['prediction_CFO_hz']/1000,c='#cc3311',label='Orbit + receiver prediction')
        ax.set(title=r['component'].split('-RF')[0]+' → '+str(r['norad']),ylabel='CFO (kHz)');ax.legend(fontsize=8)
        ax=axs[1,col];ax.scatter(t,r['raw_residual_hz']-r['profile_bias_hz'],s=15);ax.axhline(0,color='black',lw=.7)
        ax.set(ylabel='Profile residual (Hz)',title=f"RMS {r['profile_RMS_hz']:.1f} Hz; slope {r['profile_noise']['slope_z']:.2f}σ; step {r['profile_noise']['maximum_step_z']:.2f}σ")
        ax=axs[2,col];ax.scatter(t,r['whitened'],s=15);ax.axhline(0,color='black',lw=.7);ax.axhspan(-2,2,color='0.8',alpha=.3)
        ax.set(ylabel='Predictive whitened residual',title='Covariance-aware diagnostic; acceptance unchanged')
    for ax in axs.flat:ax.grid(alpha=.2);ax.set_xlabel('Scan time (s)')
    fig.savefig(out.with_suffix('.png'),dpi=130);plt.close(fig)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--orphan-phase-refresh',action='store_true');p.add_argument('--orphan-orbit-prior',action='store_true');a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    for case in (['ds24-0077'] if a.orphan_orbit_prior else ['ds24-0095','ds24-0077','v06']):
        prefix='predictive-orphan-orbit' if a.orphan_orbit_prior else ('predictive-orphan-phase' if a.orphan_phase_refresh else 'predictive-only-inclusion')
        folder=a.study/f'{prefix}-{case}-v1';protocol=read(folder/'protocol.json')
        inv=read(a.study/'all-large-track-recovery'/protocol['job']['job_id']/'inventory.json')
        for path in sorted(folder.glob('*.json')):
            trial=read(path)
            if trial.get('target_entries'):one(inv,protocol,trial,a.output/f'{case}-{path.stem}')
