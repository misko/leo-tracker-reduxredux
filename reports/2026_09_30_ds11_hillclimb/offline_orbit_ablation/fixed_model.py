"""All-track identity-fixed diagnostic with separate orbit and label provenance."""
from pathlib import Path
import sys
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'offline_orbit_pilot'))
from orbit_model import Model,load,read,digest


def restrict(document,identities,labels):
    tids={t['track_id'] for t in document['tracks']}
    if tids!=set(labels):raise ValueError('labels must cover every track exactly')
    tracks=[];mapping={}
    for t in document['tracks']:
        tid=t['track_id'];norad=labels[tid]
        candidates=identities[tid]['candidate_norad']
        if candidates.count(norad)!=1:raise ValueError('fixed physical identity absent or repeated')
        slot=candidates.index(norad)
        tracks.append(dict(t,candidate_position_km=t['candidate_position_km'][slot:slot+1].copy(),candidate_velocity_km_s=t['candidate_velocity_km_s'][slot:slot+1].copy()))
        mapping[tid]=dict(candidate_norad=[norad])
    return dict(document,tracks=tracks),mapping


def build(index,states,labels):
    parent,initial,sources=load(index,states)
    sealed_path=HERE.parent/'offline_orbit_pilot/sealed.json';sealed=read(sealed_path)
    for p,h in sealed['sources'].items():assert digest(p)==h,p
    chosen=next(r['selected'] for r in sealed['rows'] if r['index']==index and r['arm']==labels)
    assert chosen is not None
    endpoint=read(chosen['path'])
    mapping={r['track_id']:r['norad'] for r in endpoint['diagnostics']['identities']}
    document,identities=restrict(parent.document,parent.identities,mapping)
    config=read(HERE.parent.parent/'2026_09_30_ds11_single10/plan.json')['config']
    sources.update({str(p):digest(p) for p in (Path(__file__),HERE/'PROTOCOL.md',sealed_path,Path(chosen['path']))})
    return Model(document,config,identities),initial,sources
