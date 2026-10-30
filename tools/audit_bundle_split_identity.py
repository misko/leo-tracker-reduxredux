"""Challenge a shared bundle with independent satellite labels for each member.

Competitor screening explicitly uses the member's frequencies, including held
values. This is bounded adversarial model search, not an unbiased held-out test.
The predictive distributions and receiver calibration still use training only.
"""
import argparse,hashlib
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from annotate_track_predictively import fit_training,nominate
from annotate_predictive_only import prediction_models
from predictive_graph_bundle import validated_bundle_context
from leo.analysis.research.grouped_prediction import replay_split
from leo.analysis.research.predictive_track import mixture_prediction
from leo.analysis.research.retained_track_likelihood import PERIOD


def aliased_prediction(observed,means,cov,lp,train,held,aliases):
    """Marginalize discrete aliases; never choose one by held residual."""
    aliases=np.asarray(aliases)
    if aliases.ndim!=1 or not len(aliases) or not np.issubdtype(aliases.dtype,np.integer) or len(set(aliases))!=len(aliases):
        raise ValueError('distinct integer alias hypotheses required')
    return mixture_prediction(observed,np.concatenate([means-a*PERIOD for a in aliases]),
        np.concatenate([cov]*len(aliases)),np.tile(lp,len(aliases))-np.log(len(aliases)),train,held)


def run(args):
    args.output.mkdir(parents=True,exist_ok=False);inv=read(args.inventory);d=context(inv)
    d,target=validated_bundle_context(d,inv,args.validation);r=read(args.validation/'result.json');pr=read(args.validation/'protocol.json')
    shared_norad=r['annotation']['norad'];p0,_=d['problems']['c0'];i=target['track_index'];track=d['scan'].tracks[i]
    write(args.output/'protocol.json',dict(job=inv['job'],target=target,shared_norad=shared_norad,
        source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.inventory,args.validation/'result.json',args.validation/'protocol.json')},
        candidates_per_member=args.candidates,training_unchanged=True,random_scanwide_blocks_s=12,guard_s=2,
        alias_prior='uniform over inherited alias minus one, inherited alias, inherited alias plus one',
        competitor_screening_uses_member_held_frequencies=True,screening_is_adversarial_not_unbiased_validation=True,
        conditional_on_frozen_bundle_and_bounded_competitor_search=True,GPS_used=False,future_TLE=False))
    rows=[];folds=[]
    for fold in r['folds']:
        split=fold['split'];train_base,_=replay_split(p0.flat_times,split)
        train_bundle,held_bundle=replay_split(track['times'],split)
        base={a:fit_training(d,d['node'],d['keep']&train_base,a) for a in ('c0','fitted_c')}
        winner=next(q for q in fold['proposals'] if q['norad']==shared_norad);j=winner['candidate_index']
        shared={}
        for arm,(p,x,_) in base.items():
            shared[arm]=prediction_models(d,p,x,i,j,uncalibrated_phase_mixture=True)
        fd=dict(seed=fold['seed'],split=split,members=[])
        for k,member in enumerate(target['members']):
            mi=member['track_index'];mt=d['scan'].tracks[mi];train,held=replay_split(mt['times'],split)
            if held.sum()<4:continue
            offers,nomination=nominate(d,base,mi,np.ones(len(mt['times']),bool),args.candidates)
            nomination['nomination_uses_held_points']=True
            md=dict(member=member['track_id'],nomination=nomination,alternatives=[])
            aliases=[winner['alias']+member['alias_lift']+v for v in (-1,0,1)]
            for arm,(p,x,meta) in base.items():
                means,cov,lp,*_=shared[arm];mask=held_bundle&(np.asarray(target['member_indices'])==k)
                score=mixture_prediction(track['values']+winner['alias']*PERIOD,means,cov,lp,train_bundle,mask)
                old=winner['arms'][arm]['bundle_member_scores'][member['track_id']]['negative_twice_log_density']
                if abs(score['negative_twice_log_density']-old)>1e-5:raise ValueError('shared training prediction failed replay')
                alternatives=[]
                for offer in offers:
                    jj=offer['candidate_index'];norad=int(d['scan'].norads[jj])
                    if norad==shared_norad:continue
                    m,c,l,ph,e,prior=prediction_models(d,p,x,mi,jj,uncalibrated_phase_mixture=True)
                    if not np.isfinite(l).any():continue
                    other=aliased_prediction(mt['values'],m,c,l,train,held,aliases)
                    alternatives.append(dict(norad=norad,score=other,prior=prior))
                alternatives.sort(key=lambda a:a['score']['negative_twice_log_density'])
                best=alternatives[0] if alternatives else None
                delta=best['score']['negative_twice_log_density']-score['negative_twice_log_density'] if best else None
                rows.append(dict(seed=fold['seed'],arm=arm,member=member['track_id'],held_points=int(held.sum()),
                    shared_norad=shared_norad,shared_score=score['negative_twice_log_density'],shared_RMS_hz=score['rms_hz'],
                    best_alternative_norad=best['norad'] if best else None,best_alternative_score=best['score']['negative_twice_log_density'] if best else None,
                    alternative_minus_shared=delta,supports_shared=delta is not None and delta>=10,training_phase_change_s=meta['final_phase_change_s']))
                md[arm]=dict(shared=score,alternatives=alternatives,aliases=aliases)
            fd['members'].append(md)
        folds.append(fd);write(args.output/f"seed-{fold['seed']}.json",fd)
        print(inv['job']['label'],fold['seed'],'split-identity audit complete',flush=True)
    covered={(v['member'],v['arm']) for v in rows};expected={(m['track_id'],a) for m in target['members'] for a in ('c0','fitted_c')}
    write(args.output/'result.json',dict(rows=rows,all_support_shared=covered==expected and bool(rows) and all(v['supports_shared'] for v in rows),
        no_position_update_authorized=True,exhaustive_catalogue_posterior=False,screening_uses_held_values=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('inventory','validation','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--candidates',type=int,default=6);run(p.parse_args())
