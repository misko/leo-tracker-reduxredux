"""Audit structured native residuals against shared-model posterior uncertainty.

The target-induced parameter shift is diagnostic only. No calibration, identity,
position or membership is changed. Other tracks are in-sample witnesses.
"""
import argparse
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from annotate_predictive_only import context
from native_predictive_branch import native_context
from include_predictive_annotations import annotation_noise_context
from ds23_frequency_events import make_event_problem,attach_event_predictive
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features
from probe_ds23_frequency_events import cached
from leo.analysis.research.retained_track_likelihood import profile,whitening
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen


def assess(raw,times):
    terms=profile(raw,np.zeros(len(raw)),*whitening(times),bias_sigma=300.)
    noise={k:np.asarray(v)[0].item() for k,v in batch_noise_screen(terms['innovations'],times).items()}
    return dict(RMS_hz=float(terms['rms'][0]),bias_hz=float(terms['bias'][0]),residual_hz=terms['residual'][0],noise=noise)


def conditional_shift(raw,features,gram,sigma,bias_sigma=300.):
    """Exact target-marginal Gaussian diagnostic; never an acceptance rule."""
    cov_cross=np.linalg.solve(gram,features.T)
    covariance=features@cov_cross+np.diag(np.asarray(sigma)**2)+bias_sigma**2
    root=np.linalg.cholesky(covariance);innovation=np.linalg.solve(root,raw)
    alpha=np.linalg.solve(root.T,innovation)
    shift=cov_cross@alpha
    return dict(innovation=innovation,shift=shift,bias_hz=bias_sigma**2*alpha.sum(),
        posterior_shift_mahalanobis=float(np.sqrt(shift@gram@shift)),
        quadratic=float(innovation@innovation),logdet=float(2*np.log(np.diag(root)).sum()))


def run(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False);pr=read(args.inclusion/'protocol.json');saved=read(args.inclusion/'target_0.json')
    source=Path(pr['native_branches'])
    target=pr['targets'][0];bid=target['component'].split('-NATIVE-')[-1]
    discovery=read(source.parent/'protocol.json');inventory=next(Path(p) for p in discovery['input_sha256'] if p.endswith('/inventory.json'))
    inv=read(inventory);d=context(inv)
    if pr.get('noise_policy')=='annotation_fixed':d=annotation_noise_context(d)
    d,_=native_context(d,inv,source,bid);scan=d['scan'];answers={}
    write(out/'protocol.json',dict(inclusion=str(args.inclusion),inventory=str(inventory),native_source=str(source),
        target=target,position='saved RF-only target-trial endpoint',no_GPS=True,no_future_TLE=True,
        target_shift_is_diagnostic_only=True,witnesses_used_in_original_calibration=True,
        covariance='same local hierarchical Gaussian precision as predictive likelihood; native branch marginal before conditioning on other predictive branches'))
    for arm,row in saved['arms'].items():
        kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
        p=make_event_problem(scan,d['node'],d['keep'],arm,np.array(row['phase_reference']),d['powers'],d['means'],d['model'],[],**kw)
        attach_event_predictive(p,d['entries']+[target],d['powers']);cached(p);x=np.array(row['endpoint_east_north_km']);c=p.calculate(x)
        if abs(c['negative_twice_elbo']-row['negative_twice_elbo'])>1e-5:raise ValueError('position trial replay changed')
        g=p.noise_groups[p.keep];w=np.array(d['powers'])[g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
        u=c['features'][p.keep];gram=np.diag(c['coefficient_prior_precision'])+u.T@(u*w[:,None])
        entries=[];masks=[]
        for r,i,sl,a in zip(p.rows,p.members,p.slices,p.alias,strict=True):
            mask=p.keep[sl]
            if mask.sum()<4:continue
            t=scan.tracks[i];entries.append(dict(track_index=i,candidate_index=r['candidate_index'],norad=r['candidate_norad'],alias=a,component=t['key']))
            masks.append(mask)
        entries+=d['entries']+[target];masks += [np.ones(len(scan.tracks[e['track_index']]['times']),bool) for e in d['entries']+[target]]
        view,values,sigma,groups,slices=linear_geometry(p,entries);geo=geometry_features(view,x,0.)
        h=geo['features'];raw=values-view.q*geo['intercept']-h@c['coefficient'];sl=slices[-1];tt=scan.tracks[target['track_index']]
        diagnostic=conditional_shift(raw[sl],h[sl],gram,sigma[sl]*np.sqrt(2));shift=diagnostic['shift']
        before=assess(raw[sl],tt['times']);after=assess(raw[sl]-h[sl]@shift,tt['times'])
        whitened={k:np.asarray(v)[0].item() for k,v in batch_noise_screen(150*diagnostic['innovation'][None,:],tt['times']).items()}
        nh=p.hardware.shape[1];ns=p.smooth.shape[1];nf=len(p.labels);no=3*len(p.supported)
        bounds=[0,nh,nh+ns,nh+ns+nf,nh+ns+nf+no,h.shape[1]]
        contributions=[]
        for name,a,b in zip(['receiver_affine','receiver_smooth','satellite_phase','satellite_orbit','original_track_bias'],bounds[:-1],bounds[1:],strict=True):
            v=h[sl,a:b]@shift[a:b];contributions.append(dict(block=name,centered_RMS_hz=float(np.std(v)),correction_hz=v))
        witnesses=[]
        for e,mask,ss in zip(entries[:-1],masks[:-1],slices[:-1],strict=True):
            t=scan.tracks[e['track_index']];times=t['times'][mask]
            same_family=e['candidate_index']==target['candidate_index'];same_rx=t['receiver']==tt['receiver']
            if not (same_family or same_rx):continue
            left=max(times.min(),tt['times'].min());right=min(times.max(),tt['times'].max())
            overlap=(times>=left)&(times<=right)
            if not same_family and (overlap.sum()<8 or right-left<12):continue
            a=assess(raw[ss][mask],times);b=assess((raw[ss]-h[ss]@shift)[mask],times)
            witnesses.append(dict(component=e['component'],norad=e['norad'],receiver=t['receiver'],channel=t['channel'],same_family=same_family,
                same_receiver=same_rx,overlap_points=int(overlap.sum()),overlap_span_s=max(0.,float(right-left)),times_s=times,
                before=a,after_target_conditioning=b,shape_correction_RMS_hz=float(np.std((h[ss]@shift)[mask]))))
        answers[arm]=dict(target_times_s=tt['times'],target_before=before,target_after_diagnostic_conditioning=after,
            target_covariance_whitened_screen=whitened,posterior_shift=diagnostic,contributions=contributions,witnesses=witnesses,
            original_objective_replay=c['negative_twice_elbo'],original_target_compatible=row['targets'][0]['compatible'])
        print(inv['job']['label'],arm,'raw RMS',round(before['RMS_hz'],1),'conditional RMS',round(after['RMS_hz'],1),
            'marginal white screen',whitened['noise_screen_pass'],'shift',round(diagnostic['posterior_shift_mahalanobis'],2),
            'blocks',[(v['block'],round(v['centered_RMS_hz'],1)) for v in contributions],flush=True)
    write(out/'result.json',dict(job=inv['job'],branch_id=bid,arms=answers,diagnostic_only=True))
    fig,axs=plt.subplots(3,2,figsize=(14,11),layout='constrained')
    for col,arm in enumerate(['c0','fitted_c']):
        r=answers[arm];t=r['target_times_s'];axs[0,col].plot(t,r['target_before']['residual_hz'],'.-',label='Original predictive mean')
        axs[0,col].plot(t,r['target_after_diagnostic_conditioning']['residual_hz'],'.-',label='Diagnostic target-conditioned mean')
        axs[0,col].set_title(arm+' / target; conditioning is NOT accepted recovery')
        for group,ax in [('same_family',axs[1,col]),('other_family_same_receiver',axs[2,col])]:
            rows=[v for v in r['witnesses'] if v['same_family']==(group=='same_family')]
            for k,v in enumerate(rows):
                color=plt.cm.tab20(k%20);label=f"{v['norad']} RX{v['receiver']} CH{v['channel']}"
                ax.plot(v['times_s'],v['before']['residual_hz'],'.-',color=color,alpha=.7,label=label)
                ax.plot(v['times_s'],v['after_target_conditioning']['residual_hz'],'--',color=color,alpha=.6)
            ax.axvspan(t.min(),t.max(),color='grey',alpha=.1);ax.set_title(group.replace('_',' ')+f' ({len(rows)} curves)')
        for ax in axs[:,col]:ax.axhline(0,color='black',lw=.6);ax.grid(alpha=.2);ax.set(xlabel='Scan time (s)',ylabel='Bias-profiled residual (Hz)');ax.legend(fontsize=6,ncol=2)
    fig.suptitle(inv['job']['label']+' / target-induced shared-parameter correction\nWitness solid: original. Dashed: hypothetical transferred correction. Witnesses are in-sample, not independent validation.')
    fig.savefig(out/'transfer.png',dpi=140);plt.close(fig)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inclusion',type=Path,required=True);p.add_argument('--output',type=Path,required=True);run(p.parse_args())
