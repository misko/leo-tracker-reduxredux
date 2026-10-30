"""Matched position sensitivity to target points; diagnostic, not validation."""
import argparse
import copy
import hashlib
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from predictive_graph_bundle import validated_bundle_context
from predictive_new_family import NewFamily,resolution_audit
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import cached,summary
from phase_reference_checks import phase_refresh
from leo.analysis.research.retained_track_likelihood import whitening


def masks(times,member,residual):
    """Selection uses the frozen c0 residual, never evaluation location."""
    times=np.asarray(times);member=np.asarray(member);residual=np.asarray(residual)
    if not len(times)==len(member)==len(residual) or not np.isfinite(residual).all():
        raise ValueError('matching finite inputs required')
    k=int(np.argmax(abs(residual)));blocks=np.floor(times/12).astype(int)
    result={'all':np.ones(len(times),bool),'omit_largest_residual':np.arange(len(times))!=k,
            'omit_its_12s_block':blocks!=blocks[k]}
    result.update({f'member_{m}_only':member==m for m in np.unique(member)})
    if any(np.count_nonzero(v)<4 for v in result.values()):raise ValueError('too few target points')
    return result,k


def subset_view(scan,entry,keep):
    """Append a diagnostic target; leave the calibration graph untouched."""
    source=scan.tracks[entry['track_index']];keep=np.asarray(keep,bool)
    if len(keep)!=len(source['times']) or np.count_nonzero(keep)<4:raise ValueError('invalid target subset')
    t=np.asarray(source['times'])[keep];track=dict(source,
        times=t.copy(),values=np.asarray(source['values'])[keep].copy(),
        observation_ids=[o for o,k in zip(source['observation_ids'],keep,strict=True) if k],
        key=source['key']+'-DIAGNOSTIC',start_s=float(t[0]),end_s=float(t[-1]))
    track.pop('pieces',None)
    if 'bundle_member_indices' in track:track['bundle_member_indices']=np.asarray(track['bundle_member_indices'])[keep].copy()
    changed=copy.copy(scan);changed.tracks=[*scan.tracks,track]
    changed.rx_basis=[*scan.rx_basis,np.asarray(scan.rx_basis[entry['track_index']])[keep].copy()]
    changed.white=[*scan.white,whitening(t)]
    e=dict(entry,track_index=len(scan.tracks),component=track['key'],points=len(t),observation_ids=track['observation_ids'])
    return changed,e


def run(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False)
    pr=read(args.trial/'protocol.json');old=read(args.trial/'new_family.json')
    inv=read(args.inventory);d=context(inv)
    if len(pr['targets'])!=1 or len(pr['graph_bundle_sources'])!=1:raise ValueError('one frozen bundle required')
    validation=Path(pr['graph_bundle_sources'][0]);d,target=validated_bundle_context(d,inv,validation)
    entry=pr['targets'][0];track=d['scan'].tracks[entry['track_index']]
    if track['observation_ids']!=entry['observation_ids']:raise ValueError('target changed')
    diag=old['arms']['c0']['family']['diagnostics'][0]
    selections,k=masks(track['times'],target['member_indices'],np.asarray(diag['raw_residual_hz'])-diag['profile_bias_hz'])
    write(out/'protocol.json',dict(source_trial=str(args.trial),job=pr['job'],target=entry,
        largest_residual_index=k,largest_residual_id=entry['observation_ids'][k],
        masks={n:np.flatnonzero(v) for n,v in selections.items()},
        selection='frozen c0 largest absolute residual; fixed timestamp 12-second block; original fragment membership',
        diagnostic_only=True,random_holdout=False,authorizes_removal=False,GPS_used=False,future_TLE=False,
        matched_c_arms=True,start=[0,0],phase_step_s=pr['phase_step_s'],phase_rounds=5,maxiter=48,maxfun=240,
        source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [args.inventory,args.trial/'protocol.json',args.trial/'new_family.json']}))
    for name,keep in selections.items():
        scan,e=subset_view(d['scan'],entry,keep)
        family=NewFamily(scan,[e],d['model'],phase_step=pr['phase_step_s'],allow_uncalibrated_label=pr['uncalibrated_label'])
        pair={}
        for arm in ('c0','fitted_c'):
            x=np.zeros(2);reference=np.zeros(len(d['means']));history=[]
            for _ in range(5):
                kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
                p=make_event_problem(d['scan'],d['node'],d['keep'],arm,reference,d['powers'],d['means'],d['model'],[],**kw)
                attach_event_predictive(p,d['entries'],d['powers']);cached(p)
                def objective(z):
                    c=p.calculate(z)
                    return c['negative_twice_elbo']+float(np.sum(np.minimum(0,c['elevation'][p.keep])**2)/4)+family.evaluate(p,z,d['powers'],d['entries'])
                opt=minimize(objective,x,method='L-BFGS-B',bounds=[(-12.5,12.5)]*2,
                    options=dict(maxiter=48,maxfun=240,eps=.001,ftol=1e-10,gtol=1e-4,maxls=20))
                x=np.asarray(opt.x);reference,check=phase_refresh(p.state(x)['phases'][p.labels],reference)
                history.append(dict(endpoint_east_north_km=x,objective=float(opt.fun),success=bool(opt.success),message=str(opt.message),nfev=opt.nfev,**check))
            row=summary(p,x,d['entries'])
            row.update(history=history,family=family.evaluate(p,x,d['powers'],d['entries'],details=True,refine_phase=True),
                phase_resolution_audit=resolution_audit(family,p,x,d['powers'],d['entries'],d['model']))
            pair[arm]=row
            print(name,arm,'points',e['points'],'endpoint',x,'success',opt.success,flush=True)
        write(out/(name+'.json'),dict(variant=name,points=e['points'],observation_ids=e['observation_ids'],arms=pair,diagnostic_only=True,no_association_credit=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('inventory','trial','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
