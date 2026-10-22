"""Promote original, independently curved short tracks in a research view."""

import copy
import numpy as np


def promote(data,problem,offers):
    occupied={o for i,sl in zip(problem.members,problem.slices,strict=True)
        for o,use in zip(data['scan'].tracks[i]['observation_ids'],data['keep'][sl],strict=True) if use}
    occupied.update(o for e in data['entries'] for o in e['observation_ids'])
    scan=copy.copy(data['scan']);scan.curved=list(scan.curved)
    node=copy.deepcopy(data['node']);keep=list(data['keep']);powers=list(data['powers']);added=[]
    for offer in offers:
        i=offer['track_index'];track=scan.tracks[i];ids=set(track['observation_ids'])
        if i in scan.curved or ids&occupied:raise ValueError('short curve must be a wholly unused original source')
        if not offer['curvature']['qualified']:raise ValueError('independently supported curvature required')
        j=offer['candidate_index'];scan.curved.append(i)
        node['seed']['rows'].append(dict(component=track['key'],candidate_index=j,candidate_norad=offer['norad'],active_curvature=True,points=len(ids)))
        node['aliases'].append(offer['alias']);keep.extend([True]*len(ids));occupied.update(ids)
        weights=[data['powers'][k] for k,(r,sl) in enumerate(zip(problem.rows,problem.slices,strict=True)) if r['candidate_index']==j and problem.keep[sl].any()]
        owners={(scan.tracks[o['track_index']]['receiver'],scan.tracks[o['track_index']]['channel']) for o in offers if o['candidate_index']==j}
        power=min(weights) if weights else 1. if len({rx for rx,ch in owners})>=2 else .6 if len(owners)>=2 else .2
        powers.append(power);added.append(dict(component=track['key'],candidate_index=j,norad=offer['norad'],alias=offer['alias'],power=power,points=len(ids)))
    labels=sorted({r['candidate_index'] for r in node['seed']['rows']})
    return dict(data,scan=scan,node=node,keep=np.asarray(keep,bool),powers=np.asarray(powers),means=data['all_means'][labels]),added
