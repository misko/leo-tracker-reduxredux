"""Bounded causal candidate ensemble; research only, no GPS model selection."""
import argparse
import copy
import hashlib
import importlib.util
import json
import signal
import subprocess
import sys
import time
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
OLD=REPO/'reports/2026_11_02_algo07_top10_outliers'
DATA=Path('/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_11_01_ds26_ds27_causal_variants')
sys.path[:0]=[str(ROOT/'family'),str(ROOT/'solver')]
from prototype import candidate_context, select_family
from solver import fit
from algo07_science import engine as e
from algo06_science.common import read,write
from algo07_history import collect_private


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def freeze():
    p=ROOT/'combined_protocol.json'
    if p.exists():raise FileExistsError(p)
    files=[Path(__file__),ROOT/'solver/solver.py',ROOT/'family/prototype.py']
    write(p,dict(revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        created_utc_ns=time.time_ns(),source_sha256={str(f):sha(f) for f in files},
        cases=['DS26-0070','DS26-0309'],arms=['c0','fitted_c'],physical_SD_scales=[1,2,4],
        solver='damped_half',rounds=15,maxiter=35,maxfun=140,
        target='first generic ALGO07 RF influence-selected family',
        candidates='incumbent plus all whole-family proposals from prior complete causal RF screen; exclude already-owned destinations',
        candidate_selection='full-data RF discovery, fixed before this experiment; development evidence, not independent discovery',
        history='same full causal history union across all retained hypotheses, including incumbent',
        starts='same published fitted-c position; mapped phase references per identity, same within each c pair',
        mixture='diagnostic generalized-ELBO weights over both-arm-qualified models; equal ID prior, SD prior .6/.3/.1; not calibrated identity probabilities',
        qualification='phase closure, optimizer, base/exact/mixture residual gates, phase interior, unchanged fitted IDs and no unrelated owner loss/reassignment',
        no_match='if no paired model qualifies, unresolved; no forced or averaged endpoint',
        predictive_requirement='no promotion based on generalized-ELBO ensemble; whole-group predictive checks required',
        truth='postfit reporting only; never chooses identity, scale, start, solver or model weight'))


def diag_module():
    spec=importlib.util.spec_from_file_location('old_diagnostics',OLD/'diagnostics/diagnose.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def evaluate_case(case):
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('1200s case cap')))
    signal.alarm(1200)
    protocol=read(ROOT/'combined_protocol.json')
    for p,h in protocol['source_sha256'].items():assert sha(p)==h,p
    out=ROOT/'combined'/case;out.mkdir(parents=True,exist_ok=True)
    bank=OLD/'eval'/case/'input/history-bank.json'
    e.configure(DATA,out,collect_history=lambda request:collect_private(bank,request));e.ROOTS['DS26']=DATA
    d,z,replay=e.load_case(case);old,rank=select_family(d,z)
    screenpath=OLD/'eval'/case/'output/SCAN'/str(old)/'screen.json'
    screen=read(screenpath)
    proposals=[h for h in screen['proposals'] if 'prediction_limit' not in h and len(set(h['mapping'].values()))==1
               and h['norad'] not in set(z['baseline_owners']['fitted_c'].values())]
    ledger=e.rec.causal_records(case,z)
    write(out/'ledgers'/case/'tle-ledger.json',dict(causal=ledger))
    hypotheses=[dict(name='incumbent',norad=old)]+proposals
    union=e.active_ids(d)|{h['norad'] for h in hypotheses}
    hd,history=e.complete_history(d,z,case,union,out/'shared_history')
    write(out/'plan.json',dict(case=case,source_case_sha256=sha(DATA/'inputs'/f'{case}.json'),
        target=old,ranking=rank,screen_sha256=sha(screenpath),history_sha256=sha(bank),
        hypotheses=hypotheses,replay=replay,history=history,protocol_sha256=sha(ROOT/'combined_protocol.json')))
    diag=diag_module();rows=[];start=np.asarray(d['problems']['fitted_c'][1])
    for h in hypotheses:
        base=hd if h['name']=='incumbent' else e.remap(hd,z,case,h)
        ref=base['problems']['fitted_c'][0].reference.copy()
        for scale in (1.,2.,4.):
            dd=candidate_context(base,z,scale,h['norad'])
            for arm in e.ARMS:
                row=fit(dd,z,arm,start=start,reference=ref)
                p,ctx=e.build(dd,z,arm,np.asarray(row['reference']))
                row.update(diag.gates(p,ctx,np.asarray(row['x']),z,arm))
                expected=sorted(o for i,s in zip(d['problems'][arm][0].members,d['problems'][arm][0].slices)
                    for o,k in zip(d['scan'].tracks[i]['observation_ids'],d['problems'][arm][0].keep[s]) if k)
                ids=sorted(o for i,s in zip(p.members,p.slices) for o,k in zip(p.scan.tracks[i]['observation_ids'],p.keep[s]) if k)
                assert ids==expected and len(ids)==len(set(ids))
                unrelated=[o for o in row['reassigned_ids'] if z['baseline_owners'][arm][o]!=old]
                row.update(case=case,arm=arm,hypothesis=h['name'],norad=h['norad'],SD_scale=scale,
                    native_ids_sha256=hashlib.sha256('\n'.join(ids).encode()).hexdigest(),
                    native_ids_preserved=True,unexpected_reassignments=unrelated)
                row['qualified']=bool(row['phase_closed'] and row['optimizer_success'] and row['all_gates_pass']
                    and not row['lost_ids'] and not unrelated)
                # RF result is persisted before GPS is evaluated.
                path=out/(f"{h['name']}-s{scale:g}-{arm}")
                write(path.with_suffix('.rf.json'),row)
                row['error_m']=diag.error(np.asarray(row['x']))
                write(path.with_suffix('.json'),row);rows.append(row)
                print(case,h['name'],scale,arm,'qualified',row['qualified'],'gap',row['phase_change_s'],flush=True)
    write(out/'results.json',rows)
    summarize(case)


def summarize(case):
    from scipy.special import logsumexp
    out=ROOT/'combined'/case;rows=read(out/'results.json');diag=diag_module()
    models={}
    for r in rows:models.setdefault((r['hypothesis'],r['SD_scale']),{})[r['arm']]=r
    eligible={k:v for k,v in models.items() if all(v.get(a,{}).get('qualified') for a in e.ARMS)}
    result=dict(case=case,scope='uncalibrated generalized-ELBO model ensemble; predictive validation required',
        pairs_tested=len(models),paired_qualified=len(eligible),hypotheses_considered=sorted({r['norad'] for r in rows}))
    for arm in e.ARMS:
        if not eligible:result[arm]=dict(status='unresolved',x=None,error_m=None);continue
        keys=list(eligible);cost=np.array([eligible[k][arm]['objective'] for k in keys])
        lp=np.array([np.log({1.:.6,2.:.3,4.:.1}[k[1]]) for k in keys])
        lw=-.5*cost+lp;w=np.exp(lw-logsumexp(lw))
        xy=np.array([eligible[k][arm]['x'] for k in keys]);mean=w@xy
        result[arm]=dict(status='diagnostic_ensemble',x=mean,error_m=diag.error(mean),
            models=[dict(hypothesis=k[0],SD_scale=k[1],weight=float(ww),x=v.tolist(),objective=float(c)) for k,ww,v,c in zip(keys,w,xy,cost)],
            between_model_covariance_km2=(xy-mean).T@((xy-mean)*w[:,None]),
            uncertainty_scope='between-model dispersion only; not total posterior covariance or identity probability')
    write(out/'ensemble.json',result)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--freeze',action='store_true');ap.add_argument('--case');a=ap.parse_args()
    freeze() if a.freeze else evaluate_case(a.case)
