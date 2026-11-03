"""Realize declared predictive observation subsets as actual numerical rows.

Research adapter; no persisted tracking contract or frozen estimator changes.
Curved tracks and their array slots stay unchanged. Partial predictive views
are appended under explicit derived keys, with their original source recorded.
"""

import copy
import hashlib
import json
import numpy as np
from leo.analysis.research.retained_track_likelihood import whitening


def realize_predictive_subsets(scan,entries):
    result=copy.copy(scan)
    for field in ['tracks','rx_basis','white','index']:
        setattr(result,field,list(getattr(scan,field)))
    output=[];receipts=[]
    for entry in entries:
        index=entry['track_index'];track=scan.tracks[index]
        requested=entry['observation_ids'];original=track['observation_ids']
        if (len(set(requested))!=len(requested) or len(set(original))!=len(original)
                or not set(requested).issubset(original) or entry['points']!=len(requested)
                or not requested):
            raise ValueError('distinct nonempty declared predictive IDs must match source rows and count')
        use=np.array([o in set(requested) for o in original])
        selected=np.asarray(original)[use].tolist()
        if selected!=requested:raise ValueError('predictive IDs must retain source time order')
        if use.all():
            output.append(dict(entry));continue
        digest=hashlib.sha256(json.dumps(requested,separators=(',',':')).encode()).hexdigest()[:12]
        key=track['key']+'-PRED-SUBSET-'+digest
        changed=dict(track,key=key,source_component=track['key'],
            times=np.asarray(track['times'])[use].copy(),values=np.asarray(track['values'])[use].copy(),observation_ids=selected,
            start_s=float(np.asarray(track['times'])[use][0]),end_s=float(np.asarray(track['times'])[use][-1]),
            quality_status='research_predictive_subset_of_original_curve')
        if len(track.get('indices',[]))==len(use):changed['indices']=np.asarray(track['indices'])[use].tolist()
        new_index=len(result.tracks);result.tracks.append(changed)
        result.rx_basis.append(np.asarray(scan.rx_basis[index])[use].copy())
        result.white.append(whitening(changed['times']));result.index.append(np.asarray(scan.index[index])[use].copy())
        output.append(dict(entry,track_index=new_index,component=key,source_component=entry['component']))
        receipts.append(dict(source_component=entry['component'],derived_component=key,
            original_points=len(original),retained_points=len(selected),omitted_ids=[o for o in original if o not in set(requested)]))
    return result,output,receipts


def assert_realized_predictive_membership(scan,entries,excluded_ids=()):
    used=[]
    for entry in entries:
        track=scan.tracks[entry['track_index']]
        if track['observation_ids']!=entry['observation_ids'] or len(track['times'])!=entry['points']:
            raise ValueError('predictive metadata differs from actual numerical rows')
        used.extend(track['observation_ids'])
    if set(used)&set(excluded_ids):raise ValueError('predictive numerical rows reuse excluded RF IQ')
    return used
