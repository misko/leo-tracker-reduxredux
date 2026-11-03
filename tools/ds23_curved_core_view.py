"""Add a measured curved core as a derived research calibration view.

The unused source track remains present and masked out. Every incumbent
calibration row remains unchanged; no original persisted graph is rewritten.
"""

import copy

import numpy as np

from ds23_predictive_subsets import realize_predictive_subsets
from leo.analysis.research.retained_track_likelihood import PERIOD


def curved_core_view(data,problem,fragment,source_index):
    track=data['scan'].tracks[source_index];slot=problem.members.index(source_index)
    if np.asarray(data['keep'])[problem.slices[slot]].any():raise ValueError('curved source must be wholly unused for calibration')
    requested=fragment['observation_ids'];positions=[track['observation_ids'].index(o) for o in requested]
    delta=np.asarray(fragment['values'])-np.asarray(track['values'])[positions]
    alias=int(np.rint(np.mean(delta)/PERIOD))
    if not np.allclose(delta,alias*PERIOD,atol=1e-5,rtol=0):raise ValueError('HMM path changed native CFO values beyond one whole-curve alias')
    entry=dict(track_index=source_index,component=track['key'],candidate_index=fragment['candidate_index'],norad=fragment['norad'],
        alias=alias,points=len(requested),observation_ids=requested)
    scan,entries,receipts=realize_predictive_subsets(data['scan'],[entry]);derived=entries[0]
    if derived['track_index']==source_index:raise ValueError('proper core subset required')
    scan.curved=list(scan.curved)+[derived['track_index']]
    node=copy.deepcopy(data['node']);row=copy.deepcopy(problem.rows[slot])
    row.update(component=derived['component'],candidate_index=fragment['candidate_index'],candidate_norad=fragment['norad'],active_curvature=True,points=len(requested))
    node['seed']['rows'].append(row);node['aliases'].append(alias)
    changed=dict(data,scan=scan,node=node,keep=np.r_[data['keep'],np.ones(len(requested),bool)],powers=np.r_[data['powers'],data['powers'][slot]])
    old_ids={o for i,sl in zip(problem.members,problem.slices,strict=True)
        for o,use in zip(data['scan'].tracks[i]['observation_ids'],data['keep'][sl],strict=True) if use}
    if old_ids&set(requested):raise ValueError('curved core duplicates an incumbent likelihood observation')
    return changed,derived,receipts
