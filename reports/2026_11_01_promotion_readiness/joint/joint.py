"""Bounded, RF-only two-family replacement diagnostic. No production writes."""
import argparse
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[2]
SEALED = REPO / 'reports/2026_11_01_reconsideration_population'
sys.path.insert(0, str(SEALED))
import evaluate as ev

rec = ev.rec
ARMS = ev.ARMS
read, write, sha = ev.read, ev.write, ev.sha
ev.OUT = OUT


def target_rule(ranking):
    """Frozen inherited RF influence trigger; no scan or identity constants."""
    return [r['norad'] for r in sorted(ranking, key=lambda r: (-r['rank_score'], r['norad']))
            if r['rank_score'] >= .5 and r['points'] >= 30 and r['tracks'] >= 2][:2]


def pair_rule(targets, screens, active):
    """Top two full-data whole-family RF nominees per target, no singleton gate."""
    if len(targets) != 2:
        return [], []
    nominees = []
    for n in targets:
        proposals = [p for p in screens[n].get('proposals', []) if 'prediction_limit' not in p]
        whole = screens[n].get('whole', {})
        proposals.sort(key=lambda p: (sum(whole[a][str(p['norad'])]['training_score'] for a in ARMS), p['norad']))
        nominees.append(proposals[:2])
    result, excluded = [], []
    for parts in itertools.product(*nominees):
        destinations = [p['norad'] for p in parts]
        reason = None
        if len(set(destinations)) != 2:
            reason = 'duplicate destination family'
        elif set(destinations) & (set(active) - set(targets)):
            reason = 'destination already owned by an untouched family'
        name = '__'.join(p['name'] for p in parts)
        if reason:
            excluded.append(dict(name=name, reason=reason))
            continue
        result.append(dict(name=name, targets=targets, destinations=destinations,
            mapping={k:v for p in parts for k,v in p['mapping'].items()},
            aliases={k:v for p in parts for k,v in p['aliases'].items()},
            phases={k:v for p in parts for k,v in p['phases'].items()},
            allowed_families=sorted(set(targets)),
            singleton_predictive={p['name']:p['predictive'] for p in parts},
            nomination_penalty=sum(p['penalty'] for p in parts)))
    for p in result:
        p['pair_search_penalty'] = float(2*np.log(max(2,len(result))))
        p['penalty'] = p['nomination_penalty'] + p['pair_search_penalty']
    return result, excluded


def omitted(d, targets):
    keep=d['keep'].copy()
    for r,s in zip(d['problems']['fitted_c'][0].rows,d['problems']['fitted_c'][0].slices):
        if r['candidate_norad'] in targets: keep[s]=False
    return dict(d,keep=keep,entries=[e for e in d['entries'] if e['norad'] not in targets],
                families=[f for f in d['families'] if f.entries[0]['norad'] not in targets])


def predictive(d,z,targets,pairs,out):
    """Synchronized randomized groups under calibration omitting BOTH families.

    Each identity retains one shared phase and rate plus per-source offset.
    Both family scores are added within the same held groups; neither singleton
    must pass. Full-data discovery makes this conditional validation only.
    """
    base=d['problems']['fitted_c'][0]; tracks=[]; native=[]
    for r,i,s in zip(base.rows,base.members,base.slices):
        if r['candidate_norad'] in targets and base.keep[s].any():
            tracks.append((r['candidate_norad'],i,base.keep[s]))
            native += [o for o,u in zip(d['scan'].tracks[i]['observation_ids'],base.keep[s]) if u]
    ts=np.concatenate([d['scan'].tracks[i]['times'][u] for n,i,u in tracks])
    q=np.concatenate([np.full(sum(u),d['scan'].tracks[i]['rf_hz']/11.5e9) for n,i,u in tracks])
    groups=np.concatenate([np.full(sum(u),k) for k,(n,i,u) in enumerate(tracks)])
    owners=np.concatenate([np.full(sum(u),n) for n,i,u in tracks])
    partitions=rec.masks(ts,groups,unique=True)
    if len(partitions)!=5: raise ValueError('Five unique synchronized guarded partitions unavailable')
    write(out/'partitions.json',dict(seed=rec.SEED,seconds=ts,native_ids=native,groups=groups,owners=owners,partitions=partitions))
    ids=sorted(set(targets)|{n for p in pairs for n in p['destinations']})
    ledger=rec.causal_records(z['case'],z)
    nums,bank,failed=rec.bank_for({str(n):ledger[str(n)] for n in ids},z['scan_receipt']['origin_utc_ns'])
    if failed: raise ValueError('Joint shortlist propagation failed: '+repr(failed))
    pp=np.linspace(-30,30,151); od=omitted(d,targets); cavities={}; records=[]
    for arm in ARMS:
        cavity=rec.refit(od,z,arm,d['problems']['fitted_c'][1],rounds=15)
        cavities[arm]=cavity
        p,_=ev.build(od,z,arm,np.asarray(cavity['reference'])); x=np.asarray(cavity['x']);state=p.state(x)
        values=np.concatenate([(tr['values']-p.scan.hardware(tr,state['beta'])-tr['rf_hz']/11.5e9*p.scan.rx_basis[i]@state['smooth'][tr['receiver']-1])[u]
            for n,i,u in tracks for tr in [p.scan.tracks[i]]])
        raw={}
        for n in ids:
            j=int(np.flatnonzero(nums==n)[0]);bb=dict(time_s=bank['time_s'],
                position_km=np.broadcast_to(bank['position_km'][j],(len(pp),*bank['position_km'][j].shape)),
                velocity_km_s=np.broadcast_to(bank['velocity_km_s'][j],(len(pp),*bank['velocity_km_s'][j].shape)))
            f,e=rec.paired_phase_frequency(bb,np.tile(ts,len(pp)),np.repeat(np.arange(len(pp)),len(ts)),pp,*rec.latlon(x))
            raw[n]=(values[None,:]-f.reshape(len(pp),-1)*q,e.reshape(len(pp),-1))
        np.savez_compressed(out/(arm+'-predictive-raw.npz'),times_s=ts,q=q,groups=groups,owners=owners,
            phase_s=pp,values_hz=values,**{f'residual_{n}':r[0] for n,r in raw.items()},**{f'elevation_{n}':r[1] for n,r in raw.items()})
        for part in partitions:
            fitted={}
            for target in targets:
                mask=owners==target
                for n in sorted({target}|{p['destinations'][targets.index(target)] for p in pairs}):
                    residual,elevation=raw[n]
                    if elevation[:,mask].min()<0:
                        fitted[(target,n)]=None
                    else:
                        fitted[(target,n)]=rec.fit_predict(residual[:,mask],ts[mask],q[mask],groups[mask],part['train'][mask],part['test'][mask],pp)
            base_scores=[fitted[(n,n)] for n in targets]
            for hypothesis in pairs:
                candidate=[fitted[(n,v)] for n,v in zip(targets,hypothesis['destinations'])]
                valid=all(v is not None for v in base_scores+candidate)
                gain=(sum(v['predictive_score'] for v in base_scores)-sum(v['predictive_score'] for v in candidate)) if valid else None
                records.append(dict(arm=arm,fold=part['fold'],name=hypothesis['name'],gain=gain,
                    baseline=base_scores,candidate=candidate,status='complete' if valid else 'visibility_rejected'))
    write(out/'joint_cavity.json',cavities);write(out/'predictive_folds.json',records)
    summary={}
    for h in pairs:
        summary[h['name']]={}
        for arm in ARMS:
            rows=[r for r in records if r['arm']==arm and r['name']==h['name']]
            gains=[r['gain'] for r in rows if r['gain'] is not None]
            summary[h['name']][arm]=dict(gains=gains,mean=float(np.mean(gains)) if gains else None,wins=sum(g>0 for g in gains),
                pass_check=bool(len(gains)==5 and np.mean(gains)>0 and sum(g>0 for g in gains)>=4))
    write(out/'predictive_summary.json',summary)
    return cavities,summary


def freeze(cases):
    if (OUT/'protocol.json').exists(): raise FileExistsError('Protocol already frozen')
    inventory={}
    for case in cases:
        trigger=read(SEALED/case/'trigger.json');targets=target_rule(trigger['ranking'])
        if targets!=trigger['selected']: raise ValueError('Inherited trigger mismatch')
        paths=[SEALED/case/'trigger.json',SEALED/case/'result.json']+[SEALED/case/str(n)/'screen.json' for n in targets]
        root=ev.ROOTS[case[:4]]
        paths += [root/'inputs'/(case+'.json'),root/'catalogues'/(case+'.json'),root/'position'/case/'result.json']
        inventory[case]=dict(targets=targets,inputs={str(p):sha(p) for p in paths})
    write(OUT/'protocol.json',dict(revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        frozen_ns=time.time_ns(),cases=inventory,code_sha256=sha(__file__),
        imported_sha256={str(p):sha(p) for p in [SEALED/'evaluate.py',ev.PRIOR/'reconsider.py',Path(rec.ex.__file__),Path(ev.previous.__file__)]},
        rule='inherited top2 RF influence eligible targets, top2 full-family nominees by summed full RF scores, Cartesian distinct destinations, no singleton predictive prerequisite; no new discovery',
        penalty='sum inherited per-family discrete nominee penalties plus 2log(max(2,number feasible pairs)); applies to each c arm',
        history='original causal ALGO06 priors and missing-history fallback, no history completion in this bounded branch',
        predictive='5 unique random synchronized 5s held groups, 5s neighbor guards; joint-two-family-omitted RF calibration/position; train-only phase/alias/offset/rate; positive mean and >=4 wins in each arm; conditional on full-data nomination',
        budget='15 phase rounds,40 SLSQP iterations; same published fitted-c and joint-omitted fitted-c starts in both arms and controls',
        acceptance='inherited unmodified RF/exact orbit/gates/optimizer/phase<=.01s/no owners lost/no unintended reassignment/native evidence checks; both arms improve penalized objective over best qualified incumbent continuation and published bound; paired predictive check',
        no_truth='evaluation GPS used by inherited endpoint reporter only, never selection/ranking/starts',
        max_case_seconds=900,environment={k:os.environ.get(k) for k in ['PYTHONPATH','PYTHONDONTWRITEBYTECODE','OPENBLAS_NUM_THREADS','OMP_NUM_THREADS']},production_changed=False))


def run(case):
    began=time.monotonic();out=OUT/case;out.mkdir(parents=True,exist_ok=True)
    protocol=read(OUT/'protocol.json'); frozen=protocol['cases'][case]
    if sha(__file__)!=protocol['code_sha256']: raise ValueError('Frozen code changed')
    for path,digest in frozen['inputs'].items():
        if sha(path)!=digest: raise ValueError('Frozen source changed: '+path)
    attempt=out/'attempt.json'
    if attempt.exists():raise RuntimeError('Prior attempt exists; no automatic renewed budget')
    write(attempt,dict(started_ns=time.time_ns()))
    rec.CATALOGUES=ev.ROOTS[case[:4]]/'catalogues'
    d,z,replay=ev.load_case(case);z=dict(z,case=case);write(out/'replay.json',replay)
    baseline=read(SEALED/case/'baseline.json');write(out/'baseline.json',baseline)
    ledger=rec.causal_records(case,z);write(OUT/'ledgers'/case/'tle-ledger.json',dict(causal=ledger))
    screens={n:read(SEALED/case/str(n)/'screen.json') for n in frozen['targets']}
    pairs,excluded=pair_rule(frozen['targets'],screens,ev.active_ids(d))
    write(out/'pairs.json',dict(pairs=pairs,excluded=excluded))
    if not pairs:
        write(out/'result.json',dict(case=case,selected=None,final=baseline,reason='No admissible pair',production_changed=False));return
    cavity,validation=predictive(d,z,frozen['targets'],pairs,out)
    starts=dict(published=d['problems']['fitted_c'][1],joint_omitted=np.asarray(cavity['fitted_c']['x']))
    write(out/'starts.json',starts)
    control_rows=ev.fit_rows(d,z,starts,set(),out/'control_fits.json');control=ev.paired(control_rows)
    records=[]
    for h in pairs:
        folder=out/h['name'];folder.mkdir(exist_ok=True)
        try:
            dd=ev.remap(d,z,case,h)
            rows=ev.fit_rows(dd,z,starts,set(h['allowed_families']),folder/'fits.json');best=ev.paired(rows)
            qualified=bool(all(best.values()) and all(control.values()))
            bound={a:min(control[a]['objective'],baseline[a]['objective']) for a in ARMS} if all(control.values()) else {}
            gains={a:bound[a]-best[a]['objective']-h['penalty'] for a in ARMS} if qualified else {}
            predicted=all(validation[h['name']][a]['pass_check'] for a in ARMS)
            accepted=bool(qualified and predicted and all(v>0 for v in gains.values()))
            record=dict(name=h['name'],hypothesis=h,predictive=validation[h['name']],predictive_pass=predicted,
                pair=best,control=control,gains=gains,accepted=accepted,fits=str(folder/'fits.json'))
        except Exception as exc:
            record=dict(name=h['name'],accepted=False,reason=repr(exc))
        records.append(record);write(folder/'decision.json',record)
        print(case,h['name'],'accepted',record['accepted'],flush=True)
    selection=ev.choose(records,baseline)
    write(out/'result.json',dict(case=case,baseline=baseline,records=records,**selection,seconds=time.monotonic()-began,production_changed=False))
    print(case,'DONE',selection['selected'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action');parser.add_argument('cases',nargs='*');args=parser.parse_args()
    freeze(args.cases) if args.action=='freeze' else run(args.action)
