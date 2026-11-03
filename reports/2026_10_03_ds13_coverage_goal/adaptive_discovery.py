"""Derivative-guided timing proposals over the full bank, scored as local tracks.

This first run is DEVELOPMENT ONLY: it holds the existing full-data nuisance fit
fixed. It must not be presented as training-only or held-out validation.
"""
import argparse
import json
from pathlib import Path
import sys
import time

import numpy as np
from benchmark import ROOT,OLD,PROTOCOL,ALIAS_HZ,SESSIONS,canonical_rows,digest,split_masks
from training_bootstrap import training_view


def root_offsets(offset,residual,rate,visible,half_range=20.):
    """Conservative coarse retrieval followed by a derivative timing proposal."""
    residual=np.asarray(residual);rate=np.asarray(rate)
    safe=np.abs(rate)>1.
    result=offset+np.divide(residual,rate,out=np.zeros_like(residual),where=safe)
    eligible=visible & safe & (np.abs(residual)<=np.abs(rate)*.75+600) & (np.abs(result)<=half_range)
    return result,eligible


def timing_modes(offsets,groups,bin_s=.05):
    """Group-deduplicated timing votes; all supported modes, no NORAD shortlist."""
    if not len(offsets):return []
    bins=np.rint(np.asarray(offsets)/bin_s).astype(int)
    pairs=np.unique(np.column_stack([bins,groups]),axis=0)
    grid=np.arange(-400,401)
    # A mode gets support from +/-0.1 s, but each probe contributes once.
    counts=np.array([len(np.unique(pairs[np.abs(pairs[:,0]-b)<=2,1])) for b in grid])
    modes=[];remaining=counts.copy()
    while remaining.max(initial=0)>=10:
        j=int(np.argmax(remaining));b=grid[j]
        near=np.abs(bins-b)<=2
        modes.append((float(np.median(np.asarray(offsets)[near])),int(counts[j])))
        remaining[np.abs(grid-b)<=4]=0
    return modes


def coherent_segments(rows,times,groups,receiver,channel,residual):
    """One closest peak/group; bounded-gap, >=10-group lane segments."""
    answer=[]
    rows=np.asarray(rows,int)
    for rx,ch in sorted(set(zip(receiver[rows].tolist(),channel[rows].tolist()))):
        lane=rows[(receiver[rows]==rx)&(channel[rows]==ch)]
        best=[]
        for g in np.unique(groups[lane]):
            options=lane[groups[lane]==g]
            best.append(int(options[np.argmin(np.abs(residual[options]))]))
        best=np.array(sorted(best,key=lambda r:times[r]),int)
        for part in np.split(best,np.flatnonzero(np.diff(times[best])>5)+1):
            if len(part)>=10 and times[part[-1]]-times[part[0]]>=5:
                answer.append(dict(receiver=int(rx),channel=int(ch),groups=len(part),
                    start_s=float(times[part[0]]),end_s=float(times[part[-1]]),rows=part.tolist(),
                    rms_native_hz=float(np.sqrt(np.mean(residual[part]**2)))))
    return answer


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scan',choices=['A','B'],required=True)
    parser.add_argument('--fold',type=int,choices=range(5))
    parser.add_argument('--arm',choices=['fitted-c','zero-c'],default='fitted-c')
    parser.add_argument('--control',type=int,choices=range(20))
    args=parser.parse_args();started=time.monotonic()
    if args.control is not None and args.fold is not None:parser.error('Conditional controls and training folds are separate experiments')
    sys.path.insert(0,str(OLD))
    from exhaustive_subset import Case,circular_residual,load_expanded_scan,rf_features
    from prediction_jacobian import paired_prediction_jacobian
    if args.fold is None:
        case=Case(args.scan);d=case.data
        source=OLD/'exhaustive-subset'/f'{args.scan}-receipt.json'
        old=json.loads(source.read_text());fit=old['arms'][args.arm]['fit']
        features=case.features;output=ROOT/'development-discovery'
        scope=__doc__;original_rows=np.arange(len(d.times))
    else:
        d=load_expanded_scan(SESSIONS[args.scan])
        source=ROOT/'training-calibration'/f'fold-{args.fold}'/f'{args.scan}.json'
        old=json.loads(source.read_text());fit=old['arms'][args.arm]
        with np.load(ROOT/'frozen'/f'{args.scan}-observations.npz') as a:
            train,_=split_masks(a['times_s'],a['group'],args.fold)
            canonical=np.zeros(len(train),bool);canonical[a['canonical_rows']]=True
        d=training_view(d,train&canonical);original_rows=d.original_rows
        _,features=rf_features(d.rf,d.receiver,False)
        output=ROOT/'training-discovery'/f'fold-{args.fold}'/args.arm
        scope='Training-only full-bank adaptive timing proposals. Original matched-budget calibration; convergence status retained. Not held-out assignments.'
    control_source=None
    if args.control is not None:
        from control_data import with_control_observations
        control_source=ROOT/'validation-inputs'/f'{args.scan}-control-{args.control:02d}.npz'
        with np.load(control_source) as archive:control={k:archive[k] for k in archive.files}
        d=with_control_observations(d,control);original_rows=d.original_rows
        _,features=rf_features(d.rf,d.receiver,False)
        output=ROOT/'control-discovery'/f'replicate-{args.control:02d}'/args.arm
        scope='Conditional shuffled-control discovery: all visible satellites and adaptive timing rediscovered; receiver/RF calibration fixed from real-data fit. Not an end-to-end null test.'
    params=np.array(fit['parameters']);coeff=np.array(fit['rf_coefficient_hz_per_ghz'])
    selected=[int(np.flatnonzero(d.numbers==n)[0]) for n in old['catalog_numbers']]
    common=float(np.mean(params[6+np.array(selected)]))
    reps,mapping=canonical_rows(d.measured,d.group)
    rf_correction=features@coeff
    output.mkdir(parents=True,exist_ok=True)
    target=output/f'{args.scan}-proposals.json'
    if target.exists():raise FileExistsError(f'Preserve existing discovery: {target}')
    proposals=[];inventory=[]
    for begin in range(0,len(d.numbers),16):
        ids=np.arange(begin,min(begin+16,len(d.numbers)))
        rows=np.repeat(reps,len(ids));satellites=np.tile(ids,len(reps))
        votes=[[] for _ in ids];vote_groups=[[] for _ in ids]
        # Coarse grid plus per-edge derivative root: the 600 Hz margin is a
        # retrieval envelope, not a grid-point association threshold.
        for coarse in np.arange(-20.,20.001,1.):
            trial=params.copy();trial[6+ids]=common+coarse
            pred,visible,jac=paired_prediction_jacobian(d,trial,rows,satellites)
            pred=pred.reshape(len(reps),-1)+rf_correction[reps,None]
            residual=circular_residual(d.measured[reps,None],pred,ALIAS_HZ)
            root,eligible=root_offsets(coarse,residual,jac.tau.reshape(pred.shape),visible.reshape(pred.shape))
            for col in range(len(ids)):
                mask=eligible[:,col]
                votes[col].extend(root[mask,col].tolist());vote_groups[col].extend(d.group[reps[mask]].tolist())
        for col,index in enumerate(ids):
            modes=timing_modes(votes[col],vote_groups[col]);accepted=0
            for offset,support in modes:
                trial=params.copy();trial[6+index]=common+offset
                pred,visible,jac=paired_prediction_jacobian(d,trial,reps,np.full(len(reps),index))
                residual=circular_residual(d.measured[reps],pred+rf_correction[reps],ALIAS_HZ)
                # Refine shared timing using one closest hypothesis per probe;
                # these are development proposals, not validated associations.
                for _ in range(3):
                    near=visible&(np.abs(residual)<=600)
                    unique=[]
                    for g in np.unique(d.group[reps[near]]):
                        ix=np.flatnonzero(near&(d.group[reps]==g))
                        unique.append(ix[np.argmin(np.abs(residual[ix]))])
                    ix=np.array(unique,int)
                    if len(ix)<10:break
                    step=float(np.sum(jac.tau[ix]*residual[ix])/max(np.sum(jac.tau[ix]**2),1e-12))
                    step=float(np.clip(step,-.1,.1))
                    new=float(np.clip(trial[6+index]+step,common-20,common+20))
                    trial[6+index]=new
                    pred,visible,jac=paired_prediction_jacobian(d,trial,reps,np.full(len(reps),index))
                    residual=circular_residual(d.measured[reps],pred+rf_correction[reps],ALIAS_HZ)
                    if abs(step)<1e-5:break
                dense_residual=np.full(len(d.times),np.inf);dense_residual[reps]=residual
                good=reps[visible&(np.abs(residual)<=600)]
                segments=coherent_segments(good,d.times,d.group,d.receiver,d.channel,dense_residual)
                for segment in segments:
                    eligible=good[(d.receiver[good]==segment['receiver'])&(d.channel[good]==segment['channel'])
                        &(d.times[good]>=segment['start_s']-1e-7)&(d.times[good]<=segment['end_s']+1e-7)]
                    segment['eligible_rows']=eligible.tolist()
                    segment['eligible_residual_native_hz']=dense_residual[eligible].tolist()
                if segments:
                    accepted+=1
                    proposals.append(dict(catalog_number=int(d.numbers[index]),satellite_index=int(index),
                        total_timing_s=float(trial[6+index]),offset_s=float(trial[6+index]-common),
                        coarse_vote_support=support,segments=segments))
            inventory.append(dict(catalog_number=int(d.numbers[index]),root_votes=len(votes[col]),timing_modes=len(modes),accepted_modes=accepted))
        print(args.scan,'screened',int(ids[-1])+1,'/',len(d.numbers),'proposals',len(proposals),flush=True)
    result=dict(scope=scope,scan=args.scan,fold=args.fold,arm=args.arm,original_rows=original_rows.tolist(),
                control=args.control,control_sha256=digest(control_source) if control_source is not None else None,
                calibration_converged=None if args.fold is None else fit['attempts'][-1]['success'],
                source_sha256=digest(source),protocol_sha256=digest(ROOT/'frozen/protocol.json'),
                common_timing_s=common,inventory=inventory,proposals=proposals,elapsed_s=time.monotonic()-started)
    target.write_text(json.dumps(result,indent=2))
    unique={p['catalog_number'] for p in proposals}
    covered={row for p in proposals for s in p['segments'] for row in s['rows']}
    print(args.scan,'DONE','catalogs',len(unique),'optimistic nonexclusive row union',len(covered),'/',len(reps),'elapsed',result['elapsed_s'],flush=True)


if __name__=='__main__':main()
