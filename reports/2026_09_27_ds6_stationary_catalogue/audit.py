"""Full visible-catalogue audit at frozen baseline winners, without truth."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy.special import logsumexp

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent
sys.path.insert(0,str(REPORTS/'2026_09_27_ds6_full_cfo'))
from run_baseline import (site,robust_scores,REFERENCE_RF_HZ,LIGHT_KM_S,TleArchiveReader,
    exclude_labelled_starlink_debris,parse_element_sets,propagate_candidate_states)
sys.path.insert(0,str(REPORTS/'2026_09_27_ds6_full_stationary'))
from fast_solver import scores as stationary_scores
sys.path.insert(0,str(REPORTS/'2026_09_27_ds6_element_freshness'))
from catalogue import catalogues


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def retained_mass(scores,ids,selected):
    mask=np.isin(ids,list(selected))
    return float(np.exp(logsumexp(scores[mask])-logsumexp(scores)))


def freeze():
    baseline=REPORTS/'2026_09_27_ds6_element_freshness'
    files=list(baseline.glob('scan-fw-*.json'))
    ranked=sorted([(json.loads(p.read_text())['minimum_anchor_top8_mass'],p) for p in files])
    selected=[p for _,p in ranked[:3]]
    full=REPORTS/'2026_09_27_ds6_full_stationary'
    sources=[full/'run_full.py',full/'fast_solver.py',full/'protocol.json',baseline/'catalogue.py']+selected
    sources += [full/p.name for p in selected]
    sources += [REPORTS/'2026_09_27_ds6_cfo_dataset'/f'{p.stem}-plan.json' for p in selected]
    for name in json.loads((full/'protocol.json').read_text())['files']:sources.append(REPORTS/name)
    protocol=dict(source_sha256=digest(Path(__file__)),files={str(p.relative_to(REPORTS)):digest(p) for p in sources},
        sessions=[p.stem for p in selected],selection='Three completed baseline scans with lowest minimum anchor retained mass; no geographic error used',
        audit='Exact propagation of all baseline-roster catalogue candidates visible at any training epoch at stationary winner and timing; fresh causal elements; same stationary scalar solver',
        outputs='Per-track retained posterior mass, missing training-best candidate, total full-vs-shortlist score difference',
        limitation='Completeness at frozen winners only, not global search or location refit')
    with (HERE/'protocol.json').open('x') as f:json.dump(protocol,f,indent=2)


def run(session):
    output=HERE/f'{session}.json'
    if output.exists():raise FileExistsError(output)
    protocol=json.loads((HERE/'protocol.json').read_text())
    assert session in protocol['sessions'] and digest(Path(__file__))==protocol['source_sha256']
    for name,value in protocol['files'].items():assert digest(REPORTS/name)==value
    result=json.loads((REPORTS/'2026_09_27_ds6_full_stationary'/f'{session}.json').read_text())
    baseline=json.loads((REPORTS/'2026_09_27_ds6_element_freshness'/f'{session}.json').read_text())
    data=json.loads((REPORTS/'2026_09_27_ds6_cfo_dataset'/f'{session}-plan.json').read_text())
    best=result['best'];tau=best['x'][2];rec,up=site(best['latitude'],best['longitude'])
    archive=TleArchiveReader(Path('/var/lib/leo/tle'))
    _,cat,provenance=catalogues(archive,data['start_utc_ns'],data['snapshot_digest'])
    assert provenance==baseline['element_provenance']
    rows=[]
    for t in data['tracks']:
        if t['track_id'] not in baseline['shortlists']:continue
        times=np.array(t['times_s']);mask=np.array(t['training_mask'],dtype=bool);y=np.array(t['measured_hz'])
        scores=[];joints=[];candidate_ids=[]
        for first in range(0,len(cat.satellite_numbers),256):
            indices=np.arange(first,min(first+256,len(cat.satellite_numbers)))
            pos,vel,ids=propagate_candidate_states(cat,indices,data['start_utc_ns'],times,np.array([tau]))
            pos,vel=pos[:,0],vel[:,0]
            unit=pos-rec;unit/=np.linalg.norm(unit,axis=-1)[...,None]
            visible=np.any((unit@up)[:,mask]>=0,axis=-1)
            if not visible.any():continue
            pred=-REFERENCE_RF_HZ/LIGHT_KM_S*np.sum(unit[visible]*vel[visible],axis=-1)
            a,b,checks=stationary_scores(y[None,:]-pred,mask)
            assert all(c['converged'] for c in checks)
            scores.extend(a.tolist());joints.extend(b.tolist());candidate_ids.extend(ids[visible].tolist())
        scores=np.array(scores);joints=np.array(joints);ids=np.array(candidate_ids)
        chosen=set(baseline['shortlists'][t['track_id']]);inside=np.isin(ids,list(chosen))
        full_train=float(logsumexp(scores));old_train=float(logsumexp(scores[inside]))
        full_held=float(logsumexp(joints)-full_train)
        old_held=float(logsumexp(joints[inside])-old_train)
        idx=int(np.argmax(scores))
        rows.append(dict(track_id=t['track_id'],visible_candidates=len(ids),retained_mass=retained_mass(scores,ids,chosen),
            training_best_candidate=int(ids[idx]),training_best_missing=int(ids[idx]) not in chosen,
            full_train_gain=full_train-old_train,full_held_change=full_held-old_held))
        print(json.dumps(dict(session=session,completed_tracks=len(rows),**rows[-1])),flush=True)
    audit=dict(session_id=session,complete=True,protocol_sha256=digest(HERE/'protocol.json'),tracks=rows,
        minimum_retained_mass=min(r['retained_mass'] for r in rows),
        training_best_missing_count=sum(r['training_best_missing'] for r in rows),
        total_full_train_gain=sum(r['full_train_gain'] for r in rows),
        total_full_held_change=sum(r['full_held_change'] for r in rows))
    with output.open('x') as f:json.dump(audit,f,indent=2)
    print(json.dumps({k:v for k,v in audit.items() if k!='tracks'}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--freeze',action='store_true');parser.add_argument('--session');args=parser.parse_args()
    if args.freeze:freeze()
    else:run(args.session)
