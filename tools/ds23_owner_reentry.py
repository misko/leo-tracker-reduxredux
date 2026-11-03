"""Complete-curve selection with distinct receiver/channel owners."""

import numpy as np


def strongest_per_owner(group,p):
    """Keep a whole maximum-support curve per independent RX/channel owner."""
    choices={}
    for k in group['rows']:
        track=p.scan.tracks[p.members[k]];owner=(track['receiver'],track['channel'])
        rank=(-len(track['times']),-float(np.ptp(track['times'])),track['key'])
        if owner not in choices or rank<choices[owner][0]:choices[owner]=(rank,k)
    rows=sorted(v[1] for v in choices.values())
    return dict(group,rows=rows,added_points=sum(len(p.scan.tracks[p.members[k]]['times']) for k in rows))
