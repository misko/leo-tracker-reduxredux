"""Audit same-candidate fragment continuity using training data only."""
import argparse
import hashlib
import itertools
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
sys.path.insert(0,str(REPORTS/'2026_09_27_ds6_exact_timing'))
from robust import fit_offset


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def alias_align(offsets,spacing):
    offsets=np.asarray(offsets)
    aliases=np.rint((offsets-offsets[0])/spacing).astype(int)
    return offsets-aliases*spacing,aliases


def freeze():
    original=REPORTS/'2026_09_27_ds6_common_rate_validation/protocol.json'
    sessions=[r['session_id'] for r in json.loads(original.read_text())['selected']]
    files=[original,REPORTS/'2026_09_27_ds6_full_cfo/run_baseline.py',REPORTS/'2026_09_27_ds6_exact_timing/robust.py']
    files += [REPORTS/folder/f'{s}{suffix}.json' for s in sessions for folder,suffix in
        [('2026_09_27_ds6_full_cfo',''),('2026_09_27_ds6_cfo_dataset','-plan')]]
    protocol=dict(sessions=sessions,source_sha256=digest(Path(__file__)),
        files={str(p.relative_to(REPORTS)):digest(p) for p in files},
        assignment='Training MAP candidate at frozen baseline winner; posterior >=.99 within retained shortlist',
        groups='Same candidate index, receiver, channel, and actual RF; at least two high-confidence tracks',
        alias='Nearest integer normalized pilot alias (1/4.4us * 11.2GHz / actual RF), anchored to earliest fragment training offset',
        audit='Compare separate vs one common training-fitted offset on identical observations and fixed orbit; report held prediction and training offset spread',
        limitation='Conditional catalogue labels, not verified identities; no position fitting or reference coordinate loaded')
    with (HERE/'protocol.json').open('x') as f:json.dump(protocol,f,indent=2)


def run(session):
    output=HERE/f'{session}.json'
    if output.exists():raise FileExistsError(output)
    protocol=json.loads((HERE/'protocol.json').read_text())
    assert session in protocol['sessions'] and digest(Path(__file__))==protocol['source_sha256']
    for name,value in protocol['files'].items():assert digest(REPORTS/name)==value
    baseline=json.loads((REPORTS/'2026_09_27_ds6_full_cfo'/f'{session}.json').read_text())
    data=json.loads((REPORTS/'2026_09_27_ds6_cfo_dataset'/f'{session}-plan.json').read_text())
    best=baseline['best'];tau=best['x'][2];rec,up=site(best['latitude'],best['longitude'])
    archive=TleArchiveReader(Path('/var/lib/leo/tle'))
    snap=archive.select_latest_before(data['start_utc_ns']-505_000_000_000);assert snap.digest==data['snapshot_digest']
    payload,_=exclude_labelled_starlink_debris(archive.read(snap));cat=parse_element_sets(payload)
    rows=[]
    for t in data['tracks']:
        if t['track_id'] not in baseline['shortlists']:continue
        times=np.array(t['times_s']);mask=np.array(t['training_mask'],dtype=bool);y=np.array(t['measured_hz'])
        pos,vel,ids=propagate_candidate_states(cat,np.array(baseline['shortlists'][t['track_id']]),data['start_utc_ns'],times,np.array([tau]))
        pos,vel=pos[:,0],vel[:,0];unit=pos-rec;unit/=np.linalg.norm(unit,axis=-1)[...,None]
        visible=np.any((unit@up)[:,mask]>=0,axis=-1)
        pred=-REFERENCE_RF_HZ/LIGHT_KM_S*np.sum(unit*vel,axis=-1)
        residual=y[None,:]-pred;a,b=robust_scores(residual,mask);a=np.where(visible,a,-np.inf)
        idx=int(np.argmax(a));confidence=float(np.exp(a[idx]-logsumexp(a)))
        rows.append(dict(track_id=t['track_id'],receiver_id=t['receiver_id'],channel=t['channel'],rf_hz=t['rf_hz'],
            candidate_index=int(ids[idx]),norad_id=int(cat.satellite_numbers[ids[idx]]),confidence=confidence,
            offset=float(fit_offset(residual[idx,mask])),t=times,mask=mask,residual=residual[idx],
            start=float(times.min()),end=float(times.max())))
    key=lambda r:(r['receiver_id'],r['channel'],r['rf_hz'],r['candidate_index'])
    groups=[]
    eligible=sorted([r for r in rows if r['confidence']>=.99],key=key)
    for identity,values in itertools.groupby(eligible,key=key):
        members=sorted(values,key=lambda r:r['start'])
        if len(members)<2:continue
        spacing=REFERENCE_RF_HZ/identity[2]/4.4e-6
        aligned,aliases=alias_align([r['offset'] for r in members],spacing)
        residual=np.concatenate([r['residual']-n*spacing for r,n in zip(members,aliases,strict=True)])
        mask=np.concatenate([r['mask'] for r in members])
        a,b=robust_scores(residual,mask);common_held=float(b-a)
        separate_held=0.;separate_train=0.
        for r,n in zip(members,aliases,strict=True):
            c,d=robust_scores(r['residual']-n*spacing,r['mask']);separate_train+=float(c);separate_held+=float(d-c)
        groups.append(dict(receiver_id=identity[0],channel=identity[1],rf_hz=identity[2],candidate_index=identity[3],
            norad_id=members[0]['norad_id'],track_ids=[r['track_id'] for r in members],aliases=aliases.tolist(),
            normalized_alias_hz=spacing,aligned_offsets_hz=aligned.tolist(),offset_spread_hz=float(np.ptp(aligned)),
            span_s=max(r['end'] for r in members)-min(r['start'] for r in members),
            longest_fragment_s=max(r['end']-r['start'] for r in members),
            train_change=float(a)-separate_train,held_change=common_held-separate_held))
    result=dict(session_id=session,complete=True,protocol_sha256=digest(HERE/'protocol.json'),
        tracks=[{k:v for k,v in r.items() if k not in ['t','mask','residual']} for r in rows],groups=groups,
        repeated_groups=len(groups),linked_tracks=sum(len(g['track_ids']) for g in groups),
        total_held_change=sum(g['held_change'] for g in groups))
    with output.open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k not in ['tracks','groups']}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--freeze',action='store_true');parser.add_argument('--session');args=parser.parse_args()
    if args.freeze:freeze()
    else:run(args.session)
