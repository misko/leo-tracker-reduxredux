"""Inventory physical correction support for the nominated satellite families."""
import sys
import numpy as np
from run_trials import RELEASE, STUDY, targets, read, write
sys.path[:0]=[str(RELEASE/'tools'),str(RELEASE/'src')]
from diagnose_all_large_tracks import context

rows=[]
for t in targets():
    inv=read(t['inventory']);d=context(inv);p,x=d['problems']['c0']
    trial=read(STUDY/t['case']/'conditional'/'target_0.json');target=trial['target_entries'][0];j=target['candidate_index']
    active=[]
    for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
        if row['candidate_index']==j and p.keep[sl].any():
            track=p.scan.tracks[i]
            active.append(dict(component=track['key'],points=int(p.keep[sl].sum()),
                start=float(track['times'][p.keep[sl]].min()),end=float(track['times'][p.keep[sl]].max())))
    rows.append(dict(case=t['case'],norad=target['norad'],orbital_modes_available=j in p.supported,
        mode_metadata=p.mode_metadata.get(j),active_family_tracks=active))
write(STUDY/'physical-support.json',rows)
print(rows)
