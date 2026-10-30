"""Diagnose target residuals using receiver moments from incumbent data only.

No position, orbit, calibration, association or acceptance is changed. The
control endpoint excludes the target; the addition endpoint is conditional on
the previously fitted position and must not be called independent localization.
"""
import argparse,csv,hashlib,json
from pathlib import Path
import numpy as np
from scipy.linalg import cho_solve
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import cached
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features
from leo.analysis.research.predictive_track import condition_coefficients,receiver_design
from leo.analysis.research.retained_track_likelihood import profile
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from predictive_new_family import NewFamily
from diagnose_new_family_influence import family_options
from native_iq_refined_context import replay_refinement
from report_predictive_track_annotation import table


def trend_projection(times,residual,correction,covariance):
    t,r,delta,cov=(np.asarray(a,float) for a in (times,residual,correction,covariance))
    if t.ndim!=1 or len(t)<3 or r.shape!=t.shape or delta.shape!=t.shape or cov.shape!=(len(t),len(t)):
        raise ValueError('matching time, residual, correction and covariance required')
    if not all(np.isfinite(a).all() for a in (t,r,delta,cov)) or np.ptp(t)<=0:
        raise ValueError('finite data with nonzero time span required')
    centered=t-t.mean();weights=centered/(centered@centered)
    variance=float(weights@cov@weights)
    if variance < -1e-7:raise ValueError('negative receiver trend variance')
    return dict(original_slope_hz_s=float(weights@r),receiver_transfer_slope_hz_s=float(weights@delta),
                remaining_slope_hz_s=float(weights@(r-delta)),receiver_slope_sigma_hz_s=float(np.sqrt(max(variance,0))),
                receiver_transfer_centered_RMS_hz=float(np.std(delta)))


def receiver_moments(p,x,powers,entries):
    c=p.curved_calculate(x) if entries else p.calculate(x)
    coef=c['coefficient'];u=c['features'][p.keep];groups=p.noise_groups[p.keep]
    weights=np.asarray(powers)[groups]*c['noise_precision'][groups]/p.point_noise[p.keep]**2
    gram=np.diag(c['coefficient_prior_precision'])+u.T@(u*weights[:,None])
    covariance=cho_solve((np.linalg.cholesky(gram),True),np.eye(len(gram)))
    mean=coef.copy();posterior=covariance.copy()
    if entries:
        view,y,sigma,g,_=linear_geometry(p,entries);geo=geometry_features(view,x,0.);h=geo['features']
        raw=y-view.q*geo['intercept']-h@coef
        noise=np.diag(2*sigma*sigma)+300.**2*(g[:,None]==g[None,:])
        mean,posterior=condition_coefficients(coef,covariance,h,raw,noise)
    return coef,mean,posterior


def noise_summary(scan,index,residual):
    terms=profile(residual,np.zeros(len(residual)),*scan.white[index],bias_sigma=300.)
    screens=batch_noise_screen(terms['innovations'],scan.tracks[index]['times'])
    return dict(RMS_hz=float(terms['rms'][0]),bias_hz=float(terms['bias'][0]),
                noise={k:bool(v[0]) if v.dtype==bool else float(v[0]) for k,v in screens.items()},
                residual_hz=residual-float(terms['bias'][0]))


def run(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False);(out/'figures').mkdir();hashes={};rows=[];details=[];receipts=[]
    def load(path):
        hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();return read(path)
    for trial in args.trial:
        pr=load(trial/'protocol.json');control=load(trial/'control.json');addition=load(trial/'new_family.json')
        inv=load(args.study/'all-large-track-recovery'/pr['job']['job_id']/'inventory.json');d=context(inv)
        for source in pr.get('inactive_fragment_sources',[]):
            from inactive_graph_fragment import validated_inactive_context
            d,_=validated_inactive_context(d,inv,Path(source))
        for source in pr.get('graph_bundle_sources',[]):
            from predictive_graph_bundle import validated_bundle_context
            d,_=validated_bundle_context(d,inv,Path(source))
        for receipt in pr.get('measurement_refinements',[]):
            target=next(t for t in pr['targets'] if t['track_index']==receipt['track_index'])
            d=replay_refinement(d,target,receipt)
        family=NewFamily(d['scan'],pr['targets'],d['model'],**family_options(pr))
        target_ids={o for t in pr['targets'] for o in t['observation_ids']}
        case=pr['job']['job_id'];fig,axes=plt.subplots(len(pr['targets'])*2,2,figsize=(13,5*len(pr['targets'])),squeeze=False,layout='constrained')
        for col,role in enumerate(('control','new_family')):
            saved=control if role=='control' else addition
            for ai,arm in enumerate(('c0','fitted_c')):
                v=saved['arms'][arm];x=np.array(v['endpoint_east_north_km'])
                kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
                p=make_event_problem(d['scan'],d['node'],d['keep'],arm,np.array(v['phase_reference']),d['powers'],d['means'],d['model'],[],**kw)
                attach_event_predictive(p,d['entries'],d['powers']);cached(p)
                retained={o for i,sl in zip(p.members,p.slices,strict=True) for o,k in zip(d['scan'].tracks[i]['observation_ids'],p.keep[sl],strict=True) if k}
                retained.update(o for e in d['entries'] for o in e['observation_ids'])
                if target_ids&retained:raise ValueError('target leaks into receiver conditioning')
                fixed=family.evaluate(p,x,d['powers'],d['entries'],details=True)
                expected=v['negative_twice_elbo'];actual=p.calculate(x)['negative_twice_elbo']
                if role=='new_family':actual+=fixed['negative_twice_log_density']
                if abs(actual-expected)>1e-5:raise ValueError('saved objective failed replay')
                coef,mean,post=receiver_moments(p,x,d['powers'],d['entries'])
                for ti,(entry,diag) in enumerate(zip(pr['targets'],fixed['diagnostics'],strict=True)):
                    index=entry['track_index'];t=d['scan'].tracks[index]
                    u=receiver_design(t['times'],t['rf_hz'],t['receiver'],t['channel'],d['scan'].rx_basis[index],fitted_c=p.fitted_c)
                    h=np.zeros((len(t['times']),len(coef)));h[:,:u.shape[1]]=u
                    raw=np.array(diag['raw_residual_hz']);delta=h@(mean-coef);cov=h@post@h.T
                    original=noise_summary(d['scan'],index,raw);transferred=noise_summary(d['scan'],index,raw-delta)
                    row=dict(case=pr['job']['label'],job_id=case,component=t['key'],points=len(raw),endpoint=role,arm=arm,
                        old_predictive_tracks=len(d['entries']),old_predictive_families=len({e['candidate_index'] for e in d['entries']}),
                        original_RMS_hz=original['RMS_hz'],transferred_RMS_hz=transferred['RMS_hz'],
                        original_lag1=original['noise']['lag1_acf'],transferred_lag1=transferred['noise']['lag1_acf'],
                        original_noise_pass=original['noise']['noise_screen_pass'],transferred_noise_pass=transferred['noise']['noise_screen_pass'],
                        **trend_projection(t['times'],raw,delta,cov))
                    rows.append(row);details.append(dict(**row,times_s=t['times'],original=original,transferred=transferred,receiver_transfer_hz=delta,
                        target_pointwise_receiver_sigma_hz=np.sqrt(np.maximum(0,np.diag(cov)))))
                    ax=axes[2*ti+ai,col];ax.plot(t['times'],original['residual_hz'],'.-',label='Original receiver mean')
                    ax.plot(t['times'],transferred['residual_hz'],'.-',label='Incumbent-conditioned receiver mean')
                    ax.axhline(0,c='k',lw=.5);ax.grid(alpha=.2);ax.legend(fontsize=7)
                    ax.set(title=f"{t['key'].split('-RF')[0]} / {arm} / {role}",xlabel='Scan time (s)',ylabel='Residual after existing bias (Hz)')
                if not np.array_equal(coef,(p.curved_calculate(x) if d['entries'] else p.calculate(x))['coefficient']):
                    raise ValueError('receiver diagnostic mutated calibration')
                receipts.append(dict(trial=str(trial),role=role,arm=arm,objective_difference=float(actual-expected),target_disjoint_from_conditioning=True))
        fig.savefig(out/'figures'/f'{case}.png',dpi=145);plt.close(fig)
    with (out/'metrics.csv').open('x') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    write(out/'result.json',dict(rows=details,replay_receipts=receipts,source_hashes=hashes,position_refitted=False,acceptance_changed=False,
        target_updates_receiver=False,control_endpoint_target_excluded=True,addition_endpoint_is_target_informed=True,
        caveat='Conditional empirical Gaussian receiver uncertainty; orbital uncertainty and target noise excluded from slope sigma. Not calibrated confidence.'))
    selected=[r for r in rows if r['endpoint']=='new_family']
    gallery='\n\n'.join(f"![Receiver transfer {case}](figures/{case}.png)" for case in dict.fromkeys(r['job_id'] for r in rows))
    (out/'README.md').write_text('# Can other satellites explain the remaining receiver trend?\n\n'
        'This diagnostic replays the saved controls and additions, then conditions the receiver coefficient distribution on incumbent predictive evidence only. Target observations never enter this conditioning. It applies the resulting receiver mean to the target with its saved orbit, phase and position fixed. The existing per-track bias is reprofiled in both variants. No association or acceptance is changed.\n\n'
        +table(selected,['case','component','points','arm','original_RMS_hz','transferred_RMS_hz','original_lag1','transferred_lag1','transferred_noise_pass'])+'\n\n'
        +table(selected,['case','component','arm','original_slope_hz_s','receiver_transfer_slope_hz_s','remaining_slope_hz_s','receiver_slope_sigma_hz_s'])+'\n\n'
        +gallery+'\n\nAt control endpoints, position and receiver conditioning exclude the target. Addition endpoints use the previously target-informed position, so those comparisons are conditional diagnostics, not independent localization validation. The slope uncertainty is only the existing receiver posterior contribution; it excludes target measurement noise and orbital uncertainty. It cannot establish a calibrated probability of a bad association.\n\n'
        'The production likelihood already conditions its receiver moments on incumbent predictive observations, while physical gates use the original calibration mean. These plots measure that difference without relaxing a gate or adding a target-specific drift. Source hashes, replay receipts, all residuals and both c arms are in [result.json](result.json); [metrics.csv](metrics.csv) includes control endpoints.\n')
    print(json.dumps(selected,default=str),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--study',type=Path,required=True);p.add_argument('--trial',type=Path,nargs='+',required=True);p.add_argument('--output',type=Path,required=True)
    run(p.parse_args())
