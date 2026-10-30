"""Refit frozen candidate competitions with a wider numerical phase reference."""
import argparse,copy,hashlib,time
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from annotate_track_predictively import fit_training,held_scores
from leo.analysis.research.grouped_prediction import replay_split,identity_consensus


def run(args):
    began=time.monotonic()
    inv=read(args.inventory);d=context(inv);base,_=d['problems']['c0'];source=read(args.source/'result.json');pr=read(args.source/'protocol.json')
    if source['job']['job_id']!=inv['job']['job_id']:raise ValueError('scan mismatch')
    k=next(k for k,r in enumerate(base.rows) if r['component']==source['component']);sl=base.slices[k]
    args.output.mkdir(parents=True,exist_ok=False)
    write(args.output/'protocol.json',dict(pr,reference_limit_s=30,source=str(args.source),
        frozen_candidates_aliases_splits_and_priors=True,new_nomination=False,new_TLE=False,orbit_bank_extended=False,
        start=[0,0],phase_rounds=5,steps=48,
        source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.inventory,args.source/'protocol.json',args.source/'result.json')}))
    folds=[]
    for fold in source['folds']:
        train,held=replay_split(base.flat_times,fold['split']);keep=d['keep']&train;keep[sl]=train[sl];proposals=[]
        for proposal in fold['proposals']:
            node=copy.deepcopy(d['node']);j=proposal['candidate_index']
            node['seed']['rows'][k].update(candidate_index=j,candidate_norad=proposal['norad']);node['aliases'][k]=proposal['alias'];arms={}
            for arm in ('c0','fitted_c'):
                p,x,meta=fit_training(d,node,keep,arm,reference_limit_s=30)
                arms[arm]=dict(**meta,scores=held_scores(p,x,held,sl,d['keep']),minimum_target_elevation_deg=float(p.conditional_frequency(x)[1][sl].min()))
            row=dict(candidate_index=j,norad=proposal['norad'],alias=proposal['alias'],arms=arms)
            proposals.append(row);write(args.output/f"{fold['seed']}-{proposal['norad']}.json",row)
            print(inv['job']['label'],fold['seed'],proposal['norad'],'complete',flush=True)
        row=dict(seed=fold['seed'],split=fold['split'],proposals=proposals);folds.append(row);write(args.output/f"seed-{fold['seed']}.json",row)
    result=dict(source,folds=folds,reference_limit_s=30,refit_source=str(args.source),no_accepted_associations=True,
        original_source_seconds=source.get('seconds'),seconds=time.monotonic()-began)
    write(args.output/'result.json',result)
    write(args.output/'consensus.json',identity_consensus(folds,score_name=source.get('identity_score_name','joint')))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('inventory','source','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
