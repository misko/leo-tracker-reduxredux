"""Replay matched controls and compare independent-family residual witnesses."""
import argparse
from pathlib import Path
import hashlib
import numpy as np
from debug_fast_graph_unassociated import read, write
from diagnose_all_large_tracks import context
from annotate_track_predictively import prior_means
from ds23_frequency_events import make_event_problem, attach_event_predictive
from probe_ds23_frequency_events import cached


def binned_comparison(target, witnesses, *, width=5.):
    """Descriptive correlation; two independent witness families per time bin."""
    tt=np.array(target['times_s']);rr=np.array(target['residual_hz']);bins=np.floor(tt/width).astype(int);rows=[]
    for b in np.unique(bins):
        samples=[];families=set()
        for witness in witnesses:
            mask=np.floor(np.array(witness['times_s'])/width).astype(int)==b
            if mask.any():
                samples.extend(np.array(witness['residual_hz'])[mask].tolist());families.add(witness['norad'])
        if len(families)>=2 and len(samples)>=3:
            rows.append(dict(time_s=(int(b)+.5)*width,target_hz=float(np.median(rr[bins==b])),
                             witness_hz=float(np.median(samples)),witness_families=sorted(families),points=len(samples)))
    a=np.array([r['target_hz'] for r in rows]);b=np.array([r['witness_hz'] for r in rows])
    corr=float(np.corrcoef(a,b)[0,1]) if len(rows)>=3 and np.std(a)>0 and np.std(b)>0 else None
    return dict(bins=rows,correlation=corr,width_s=width,minimum_witness_families=2,descriptive_only=True)


def run(args):
    args.output.mkdir(parents=True,exist_ok=False);jobs=read(args.inclusions/'protocol.json')['jobs'];sources={};results=[]
    for job in jobs:
        tid=job['track_id'];root=args.inclusions/tid
        for file in (root/'control.json',root/'target_0.json',Path(job['inventory'])):
            sources[str(file)]=hashlib.sha256(file.read_bytes()).hexdigest()
        control=read(root/'control.json');trial=read(root/'target_0.json');d=context(read(Path(job['inventory'])))
        means,_=prior_means(d,d['node']);arms={}
        for arm in ('c0','fitted_c'):
            v=control['arms'][arm];target=trial['arms'][arm]['targets'][0];entry=trial['target_entries'][0]
            kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
            p=make_event_problem(d['scan'],d['node'],d['keep'],arm,np.array(v['phase_reference']),d['powers'],means,d['model'],[],**kw)
            attach_event_predictive(p,d['entries'],d['powers']);cached(p);calc=p.calculate(np.array(v['endpoint_east_north_km']))
            delta=float(calc['negative_twice_elbo']-v['negative_twice_elbo'])
            if abs(delta)>1e-5:raise ValueError('control objective does not replay')
            witnesses=[]
            for k,(i,sl) in enumerate(zip(p.members,p.slices,strict=True)):
                track=d['scan'].tracks[i];norad=int(p.rows[k]['candidate_norad']);keep=p.keep[sl]
                # Exclude the target satellite entirely, including other RX/CH.
                if norad==entry['norad'] or not keep.any():continue
                mask=keep&(track['times']>=min(target['times_s']))&(track['times']<=max(target['times_s']))
                if not mask.any():continue
                witnesses.append(dict(component=track['key'],norad=norad,receiver=track['receiver'],channel=track['channel'],
                    times_s=np.array(track['times'])[mask],residual_hz=calc['conditional_residual_hz'][sl][mask]))
            groups={}
            for same_rx in (True,False):
                for same_band in (True,False):
                    name=('same_RX' if same_rx else 'other_RX')+('_same_band' if same_band else '_other_band')
                    group=[w for w in witnesses if (w['receiver']==entry['receiver'])==same_rx and
                           ((w['channel']<=4)==(entry['channel']<=4))==same_band]
                    groups[name]=dict(witnesses=group,**binned_comparison(target,group))
            arms[arm]=dict(target=target,groups=groups,control_objective_delta=delta,
                target_from_inclusion=True,witnesses_from_matched_control=True,independent_satellite_families_only=True)
        results.append(dict(track_id=tid,scan=job['label'],arms=arms))
        print(job['label'],{k:(len(g['bins']),g['correlation']) for k,g in arms['fitted_c']['groups'].items()},flush=True)
    write(args.output/'result.json',dict(results=results,sources=sources,acceptance_changed=False,
          scope='Original curved calibration witnesses only; excludes predictive-only witness curves',GPS_used=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inclusions',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);run(p.parse_args())
