"""Bounded, conditional DS26-0265 family exclusion and identity audit.

No new associations, production edits, GPS access, or baseline preservation claim.
"""
import hashlib
import json
import signal
import time
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import logsumexp

from annotate_predictive_only import context, prediction_models
from annotate_track_predictively import corrected, fit_training
from debug_fast_graph_unassociated import read, memberships
from investigate_ds23_adaptive_failures import phase_widths
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.grouped_prediction import replay_split
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.predictive_track import gaussian_log_density, mixture_prediction
from leo.analysis.research.retained_track_likelihood import PERIOD
from leo.analysis.research.track_recovery_diagnostics import profile_rate, shortlist
from prototype_dsx01_continuous_position import latlon

OUT = Path(__file__).resolve().parent
ROOT = Path('/srv/bulk/leo/research/algo03-full-evaluation-20261030/cases/DS26-0265/candidate-v2/recovery')
TID = '36f621d91e81526b1ce4'
ARMS = ('c0', 'fitted_c')


def exclude_family(rows, slices, keep, norad):
    """Remove all active family points, preserving every other membership bit."""
    original = np.asarray(keep, bool)
    result = original.copy()
    removed = np.zeros(len(original), bool)
    for row, sl in zip(rows, slices, strict=True):
        if row['candidate_norad'] == norad:
            removed[sl] = original[sl]
            result[sl] = False
    np.testing.assert_array_equal(original & ~removed, result)
    return result, removed


def mask_sha(mask):
    return hashlib.sha256(np.asarray(mask, np.uint8).tobytes()).hexdigest()


def compact_score(score):
    return {k:v for k,v in score.items() if k != 'training_mixture_weights'}


def density(d, p, x, index, candidate, train, held, alias=None):
    t = d['scan'].tracks[index]
    means, cov, lp, phases, elevations, receipt = prediction_models(
        d,p,x,index,candidate,phase_step=.1,uncalibrated_phase_mixture=True)
    if alias is None:
        bank = {k:d['scan'].sky[k][[candidate]] for k in ('position_km','velocity_km_s')}
        bank['time_s'] = d['scan'].sky['time_s']
        f,_ = paired_phase_frequency(bank,t['times'],np.zeros(len(train),int),np.array([0.]),*latlon(x))
        choose=train if train.sum()>=3 else np.ones(len(train),bool)
        alias = int(profile_rate(corrected(p,x,index)[choose],t['rf_hz']/11.5e9*f[choose],t['times'][choose])['alias'][0])
    score = mixture_prediction(t['values']+alias*PERIOD,means,cov,lp,train,held)
    weights = score['training_mixture_weights']
    phase = float(weights@phases)
    full_lp=lp+np.array([gaussian_log_density(t['values']+alias*PERIOD-m,c) for m,c in zip(means,cov,strict=True)])
    full_weights=np.exp(full_lp-logsumexp(full_lp));full_phase=float(full_weights@phases)
    return dict(score=compact_score(score), alias=alias,
        phase_mean_s=phase, phase_sigma_s=float(np.sqrt(weights@((phases-phase)**2))),
        phase_boundary_mass=float(weights[abs(phases)>=14.9].sum()), prior=receipt,
        descriptive_all_data_phase_mean_s=full_phase,
        descriptive_all_data_phase_sigma_s=float(np.sqrt(full_weights@((phases-full_phase)**2))),
        descriptive_all_data_boundary_mass=float(full_weights[abs(phases)>=14.9].sum()),
        minimum_elevation_deg=float(elevations[weights>1e-6].min()))


def exact(d,p,x,index,offer,phase_limit=30.):
    t=d['scan'].tracks[index];j=offer['candidate_index'];y=corrected(p,x,index)
    bank={k:d['scan'].sky[k][[j]] for k in ('position_km','velocity_km_s')};bank['time_s']=d['scan'].sky['time_s']
    def evaluate(phi):
        f,e=paired_phase_frequency(bank,t['times'],np.zeros(len(t['times']),int),np.array([phi]),*latlon(x))
        terms=profile_rate(y,t['rf_hz']/11.5e9*f,t['times'])
        return terms,f,e
    # Uniform full-domain grid and deterministic local refinement for all nominees.
    grid=np.arange(-phase_limit,phase_limit+.01,1.)
    vals=np.array([evaluate(phi)[0]['cost'][0] for phi in grid]);best=int(vals.argmin())
    lo,hi=grid[max(0,best-1)],grid[min(len(grid)-1,best+1)]
    fit=minimize_scalar(lambda z:float(evaluate(z)[0]['cost'][0]),bounds=(lo,hi),method='bounded',options={'xatol':.001,'maxiter':32})
    terms,f,e=evaluate(fit.x)
    return dict(candidate_index=j,norad=int(d['scan'].norads[j]),phase_s=float(fit.x),phase_limit_s=phase_limit,
        rms_hz=float(terms['rms_hz'][0]),cost=float(terms['cost'][0]),bias_hz=float(terms['bias_hz'][0]),
        alias=int(terms['alias'][0]),minimum_elevation_deg=float(e.min()),times_s=t['times'],
        corrected_observation_hz=y,orbit_hz=t['rf_hz']/11.5e9*f,residual_hz=terms['residual_hz'][0])


def discovery(d,pair,index):
    """Nominate over both calibration endpoints plus shared regional positions."""
    t=d['scan'].tracks[index];phases=np.arange(-30.,30.01,5.)
    knots=np.linspace(t['times'].min(),t['times'].max(),13)
    positions={a:x for a,(p,x,meta) in pair.items()}
    positions.update({f'{e}_{n}':np.array([e,n]) for e in (-10.,0.,10.) for n in (-10.,0.,10.)})
    offers=[]
    for name,x in positions.items():
        freq=[];elev=[]
        for phase in phases:
            f,e=phase_frequency_grid(d['scan'].sky,knots,*latlon(x),phase_seconds=phase)
            freq.append(f);elev.append(e)
        for arm,(p,xx,meta) in pair.items():
            found=shortlist(corrected(p,xx,index),t['times'],t['rf_hz']/11.5e9,
                np.array(freq),np.array(elev),knots,phases,top=6)
            offers.extend(dict(q,position=name,arm=arm) for q in found)
    ids={q['candidate_index'] for q in offers}
    ids.add(int(np.flatnonzero(d['scan'].norads==52311)[0]))
    return sorted(ids),offers


def run():
    began=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('590 second audit cap')));signal.alarm(590)
    inv_path=next((ROOT/'all-large-track-recovery').glob('*/inventory.json'))
    inv=read(inv_path);annotation=read(ROOT/TID/'annotation/result.json');d=context(inv)
    p0,_=d['problems']['c0'];s=d['scan'];j=int(np.flatnonzero(s.norads==52311)[0])
    rows=[(k,r,i,sl) for k,(r,i,sl) in enumerate(zip(p0.rows,p0.members,p0.slices,strict=True)) if r['candidate_norad']==52311]
    assert len(rows)==1
    k,row,index,sl=rows[0];t=s.tracks[index]
    keep,removed=exclude_family(p0.rows,p0.slices,d['keep'],52311)
    widths,history=phase_widths(s,[j]);means=d['means'].copy()
    report=dict(scope='Conditional family exclusion diagnostic only; changed evidence mask; no baseline preservation or accepted association',
        GPS_used=False,new_RF=False,maximum_seconds=590,observations_and_priors_and_budgets_matched_between_c_arms=True,
        frozen_graph_and_aliases_and_other_prior_means=True,
        caveat='Incumbent graph, aliases and identities were selected using full scan RF. Exclusion removes equations, not upstream selection. Signed common phase means are causal TLE-history corrections, not RF-selected. Withheld-family standard prediction uses independent causal mixture mean0 (versus inherited signed mean -0.2233s), phase box +/-15s and physical orbital uncertainty. Nominal competitor discovery uses +/-30s and is descriptive.',
        source_sha256={str(z):hashlib.sha256(z.read_bytes()).hexdigest() for z in (inv_path,ROOT/TID/'annotation/result.json',Path(__file__))},
        family=dict(norad=52311,candidate_index=j,element=s.elements['52311'],phase_history=history,
            causal_sigma_s=float(widths[0]*d['model']['multiplier']),model=d['model'],
            inherited_mean_s=float(means[p0.labels.index(j)]),
            candidate_rows=[r for _,r,_,_ in rows],predictive_entries=[e for e in d['entries'] if e['norad']==52311],
            supported_orbit_modes=j in p0.supported,active_curvature=bool(index in s.curved),
            component=t['key'],graph_pieces=t['pieces'],times_s=t['times'],observation_ids=t['observation_ids'],
            removed_full_points=int(removed.sum()),full_original_points=int(d['keep'].sum()),
            full_remaining_points=int(keep.sum()),retained_channels=[[t['receiver'],t['channel']]]),
        baseline={},folds=[])
    def save():
        report['seconds']=time.monotonic()-began
        def convert(value):
            if isinstance(value,np.ndarray):return value.tolist()
            if isinstance(value,np.generic):return value.item()
            raise TypeError(type(value).__name__)
        (OUT/'audit.json').write_text(json.dumps(report,default=convert,allow_nan=False,indent=2)+'\n')
    for arm,(p,x) in d['problems'].items():
        c=p.calculate(x);res=c['conditional_residual_hz'][sl]
        curved,predictive,associated,owners=memberships(p,x,d['entries'])
        family_ids=sorted(oid for oid,norad in owners.items() if norad==52311)
        assert set(family_ids)==set(t['observation_ids'])
        report['baseline'][arm]=dict(endpoint=x,phase_s=float(p.state(x)['phases'][j]),
            rms_hz=float(np.sqrt(np.mean(res**2))),residual_hz=res,noise_precision=float(c['noise_precision'][k]),
            retained_52311_ids=family_ids,total_associated_ids=len(associated),
            keep_sha256=mask_sha(p.keep),objective_replay_difference=d['replay'][arm])
    history_root=Path(inv['job']['root'])/'causal_phase_history'
    history_source=read(history_root/'SCAN.json')
    report['family']['past_versions']=history_source['past_versions']['52311']
    report['family']['cutoff_utc_ns']=history_source['cutoff_utc_ns']
    report['family']['origin_utc_ns']=history_source['origin_utc_ns']
    report['family']['previous_provenance']=read(s.previous_tle_path.parent/'previous_receipt.json')['sources']['52311']
    assert all(max(v['epoch'],v['collected_utc_ns'])<=history_source['cutoff_utc_ns'] for v in report['family']['past_versions'])
    target=next(q for q in inv['tracks'] if q['track_id']==TID);target_i=target['track_index'];target_t=s.tracks[target_i]
    fulltimes=np.r_[p0.flat_times,target_t['times']];n=len(p0.flat_times)
    for fold in annotation['folds']:
        train,held=replay_split(fulltimes,fold['split']);original=d['keep']&train[:n]
        use,removed_fold=exclude_family(p0.rows,p0.slices,original,52311)
        ft,fh=replay_split(t['times'],fold['split'])
        record=dict(seed=fold['seed'],split=fold['split'],original_training_points=int(original.sum()),
            excluded_training_points=int(removed_fold.sum()),remaining_training_points=int(use.sum()),
            excluded_observation_ids=[oid for oid,r in zip(t['observation_ids'],removed_fold[sl],strict=True) if r],
            removed_family_not_training_points=[oid for oid,r in zip(t['observation_ids'],original[sl],strict=True) if not r],
            original_mask_sha256=mask_sha(original),excluded_mask_sha256=mask_sha(use),arms={},
            family_training_groups=np.unique(np.floor((t['times'][ft]-fold['split'].get('block_origin_s',0))/12)).tolist(),
            family_held_groups=np.unique(np.floor((t['times'][fh]-fold['split'].get('block_origin_s',0))/12)).tolist(),
            family_training_points=int(ft.sum()),family_held_points=int(fh.sum()))
        report['folds'].append(record);pair={}
        for arm in ARMS:
            p,x,meta=fit_training(d,d['node'],use,arm)
            assert not p.keep[sl].any();np.testing.assert_array_equal(p.keep,use)
            family_phase=float(p.state(x)['phases'][j]);r=dict(training=meta,held_66102=[],excluded_family_phase_s=family_phase)
            record['arms'][arm]=r;pair[arm]=(p,x,meta)
            for offer in fold['proposals']:
                score=density(d,p,x,target_i,offer['candidate_index'],train[n:],held[n:],alias=offer['alias'])
                r['held_66102'].append(dict(norad=offer['norad'],**score))
            # Predict all removed family points without conditioning on any of them.
            r['family_all_points_prior_predictive']=density(d,p,x,index,j,np.zeros(len(t['times']),bool),np.ones(len(t['times']),bool))
            print('FOLD',fold['seed'],arm,'removed',int(removed_fold.sum()),'delta',meta['final_phase_change_s'],flush=True);save()
        if 'catalogue_nominations' not in report:
            ids,nominations=discovery(d,pair,index);report['catalogue_nominations']=nominations
            report['candidate_indices']=ids
        for arm,(p,x,meta) in pair.items():
            r=record['arms'][arm];r['family_nominal_fits']=[exact(d,p,x,index,dict(candidate_index=idx)) for idx in report['candidate_indices']]
            r['family_nominal_fits'].sort(key=lambda q:q['cost'])
            r['family_predictive_competitors']=[]
            # Equal full-point predictive budget across the union of the top
            # nominal candidates from both c arms; no observations enter calibration.
        predictive_ids=set(report['candidate_indices'])
        for arm,(p,x,meta) in pair.items():
            r=record['arms'][arm]
            for idx in sorted(predictive_ids):
                q=density(d,p,x,index,idx,np.zeros(len(t['times']),bool),np.ones(len(t['times']),bool))
                grouped=density(d,p,x,index,idx,ft,fh) if ft.sum()>=3 and fh.any() else None
                r['family_predictive_competitors'].append(dict(norad=int(s.norads[idx]),grouped=grouped,**q))
            r['family_predictive_competitors'].sort(key=lambda q:q['score']['negative_twice_log_density'])
        save()
    report['completed']=True;save();signal.alarm(0)
    render(report)


def render(report):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(3,2,figsize=(14,12),sharex=True)
    for row,fold in enumerate(report['folds']):
        for col,arm in enumerate(ARMS):
            ax=axes[row,col];r=fold['arms'][arm]
            fits=r['family_nominal_fits'];inc=next(q for q in fits if q['norad']==52311)
            for q in [inc]+[q for q in fits[:3] if q['norad']!=52311]:
                ax.plot(q['times_s'],q['residual_hz'],'.-',label=f"{q['norad']} RMS {q['rms_hz']:.1f} Hz; phase {q['phase_s']:.2f}s")
            ax.axhline(0,color='gray',linewidth=.5);ax.set_title(f"Seed {fold['seed']} / {arm}: 52311 excluded from equations")
            ax.set_ylabel('Nominal profiled residual (Hz)');ax.legend(fontsize=8)
    for ax in axes[-1]:ax.set_xlabel('Scan time (s)')
    fig.suptitle('RX2 CH8 T006: all 20 points, shared candidate search ±30 s; fixed trained receiver correction\nDescriptive nominal fits; frozen graph/priors; no GPS or identity acceptance',fontsize=12)
    fig.tight_layout();fig.savefig(OUT/'family-residuals.png',dpi=160);fig.savefig(OUT/'family-residuals.pdf');plt.close(fig)


if __name__=='__main__':run()
