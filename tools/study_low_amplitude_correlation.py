"""Separate RX2 covariance investigation; no recovery/position policy adoption."""

import argparse
from pathlib import Path
import numpy as np

import debug_fast_graph_unassociated as report
from benchmark_graph_covariance import load_case,refit
from correlated_curve_prediction import gaussian,shared_kernel
from probe_high_channel_correlated_noise import validation


def learn(d,target,excluded):
    p,x=d['problems']['c0'];scan=d['scan'];focus=scan.tracks[p.members[target]];c=p.calculate(x)
    n=len(p.members);raw=c['conditional_residual_hz']+c['features'][:,-n:]@c['coefficient'][-n:]
    rows=[]
    for r,i,sl in zip(p.rows,p.members,p.slices):
        t=scan.tracks[i];use=p.keep[sl]&(t['times']>=focus['times'].min()-12)&(t['times']<=focus['times'].max()+12)
        if t['receiver']!=focus['receiver'] or r['candidate_norad'] in excluded or use.sum()<10:continue
        rows.append(dict(component=t['key'],norad=r['candidate_norad'],track_index=i,times=t['times'][use],
            raw=raw[sl][use],scale=p.point_noise[sl][use]/scan.radio_sigma_hz))
    if len({r['norad'] for r in rows})<2:raise ValueError('at least two independent training satellite families required')
    t=np.concatenate([r['times'] for r in rows]);y=np.concatenate([r['raw'] for r in rows]);scale=np.concatenate([r['scale'] for r in rows])
    owners=np.repeat(np.arange(len(rows)),[len(r['times']) for r in rows]);families=np.repeat([r['norad'] for r in rows],[len(r['times']) for r in rows])
    constant=300.**2*(owners[:,None]==owners[None,:]);trials=[]
    for scope in ('white','receiver','family'):
        for amp in ((0.,) if scope=='white' else (10.,20.,40.,80.)):
            for tau in ((1.,) if scope=='white' else (.25,.5,1.,2.,5.,10.)):
                kernel=shared_kernel(t,np.zeros(len(t)) if scope!='family' else families,amp,tau)
                for white in (10.,20.,30.,40.,60.,80.,120.):
                    score=gaussian(y,constant+kernel+np.diag((white*scale)**2))['objective']
                    penalty=0. if scope=='white' else 2*np.log(len(t))+2*np.log(2)
                    trials.append(dict(scope=scope,amplitude_hz=amp,timescale_s=tau,white_hz=white,objective=score,selection_score=score+penalty))
    null=min((r for r in trials if r['scope']=='white'),key=lambda r:r['selection_score'])
    best=min((r for r in trials if r['scope']!='white'),key=lambda r:r['selection_score'])
    return dict(rows=rows,null=null,correlated=best,qualified=best['selection_score']<null['selection_score'],trials=trials,
        excluded_families=excluded,calibration_arm='c0, frozen for both c arms')


def run(args):
    from investigate_ds23_adaptive_failures import phase_widths
    from probe_ds23_causal_phase_mean import forecast_phase_mean
    out=args.output;out.mkdir(parents=True,exist_ok=False);d=load_case(args.root,'DS24-0018')
    p,_=d['problems']['c0'];target=next(k for k,r in enumerate(p.rows) if 'RX2-CH3-T000' in r['component']);norad=p.rows[target]['candidate_norad']
    calibration=learn(d,target,[norad]);report.write(out/'calibration.json',calibration)
    counts={j:sum(len(r['times']) for r in calibration['rows'] if r['norad']==j) for j in {r['norad'] for r in calibration['rows']}}
    candidates=sorted(counts,key=lambda j:(-counts[j],j))[:2]
    for held in candidates:
        keep=d['keep'].copy();extras=[]
        for k,(r,i,sl) in enumerate(zip(p.rows,p.members,p.slices)):
            if r['candidate_norad']!=held:continue
            t=d['scan'].tracks[i]
            if keep[sl].all() and t['receiver']==2 and len(t['times'])>=12 and np.ptp(t['times'])>=24:
                extras.append(dict(track_index=i,component=t['key'],candidate_index=r['candidate_index'],norad=held,
                    alias=int(p.alias[k]),points=len(t['times']),observation_ids=t['observation_ids']))
            keep[sl]=False
        if not extras:
            report.write(out/(str(held)+'.json'),dict(status='no_eligible_complete_curve',norad=held));continue
        entries=[e for e in d['entries'] if e['norad']!=held]
        _,receipts=phase_widths(d['scan'],p.labels);means=forecast_phase_mean(receipts,d['model']['shrinkage'])
        pair,problems=refit(d,keep,policy='nominal',entries=entries,means=np.asarray(means))
        fold=dict(d,keep=keep,entries=entries,means=np.asarray(means),problems=problems)
        model=learn(fold,target,[norad,held])
        predictions={name:validation(fold,extras,m) for name,m in [('white',model['null']),('correlated',model['correlated'])]}
        report.write(out/(str(held)+'.json'),dict(status='complete',norad=held,calibration=model,predictions=predictions,
            held_points=sum(e['points'] for e in extras),training_fold=pair,
            caveat='All held-family RF calibration removed, causal prior means restored. Identities and graph fixed. No target recovery adopted.'))
        print('Whole-family',held,{a:predictions['white'][a]['joint']['objective']-predictions['correlated'][a]['joint']['objective'] for a in ('c0','fitted_c')},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    run(p.parse_args())
