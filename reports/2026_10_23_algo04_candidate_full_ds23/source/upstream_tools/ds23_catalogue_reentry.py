"""Complete unused-curvature groups, ranked before identity replacement gains."""

import numpy as np


def complete_groups(p,occupied,minimum_points=12,minimum_span_s=10):
    groups={}
    for k,(row,i,sl) in enumerate(zip(p.rows,p.members,p.slices,strict=True)):
        t=p.scan.tracks[i]
        if np.asarray(p.keep[sl]).any() or len(t['times'])<minimum_points or np.ptp(t['times'])<minimum_span_s:
            continue
        if occupied.intersection(t['observation_ids']):continue
        groups.setdefault(row['candidate_index'],[]).append(k)
    eligible=[]
    for j,rows in groups.items():
        owners={(p.scan.tracks[p.members[k]]['receiver'],p.scan.tracks[p.members[k]]['channel']) for k in rows}
        if len(owners)<2:continue
        eligible.append(dict(original_index=int(j),rows=rows,owners=len(owners),
            added_points=sum(len(p.scan.tracks[p.members[k]]['times']) for k in rows)))
    return sorted(eligible,key=lambda g:(-g['added_points'],g['original_index'],tuple(g['rows'])))


def selected_indices(scores,incumbent,maximum=3):
    costs=np.asarray(scores,float)
    if costs.ndim!=1 or not 0<=incumbent<len(costs):raise ValueError('one catalogue score per label required')
    best=[int(j) for j in np.argsort(costs,kind='stable') if np.isfinite(costs[j])][:maximum]
    return ([incumbent]+[j for j in best if j!=incumbent])
