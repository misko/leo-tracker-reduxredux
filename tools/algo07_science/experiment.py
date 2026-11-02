"""Frozen ALGO07 science; source provenance is recorded in origin_manifest.json."""
import copy
from pathlib import Path
import numpy as np
from algo06_science.common import read, ARMS
from . import previous
ORIGINAL_BUILD=previous.build
PRIOR=Path('.')


def remap(d,z,case,h):
    """Apply per-source hypotheses, preserving native masks and other owners."""
    from sgp4.api import Satrec
    from leo.sky.propagation import ElementSetCatalogue
    from analyze_dsx01_fixed_site import ecef_states
    dd=dict(d,node=copy.deepcopy(d['node']),entries=copy.deepcopy(d['entries']),problems={})
    scan=copy.copy(d['scan']);dd['scan']=scan;ledger=read(PRIOR/case/'tle-ledger.json')['causal'];base=d['problems']['fitted_c'][0]
    for n in sorted(set(h['mapping'].values())):
        if n in scan.norads:continue
        record=ledger[str(n)];cat=ElementSetCatalogue((str(n),),(n,),(Satrec.twoline2rv(*record['lines']),))
        pos,vel,good=ecef_states(cat,scan.receipt['origin_utc_ns'],scan.sky['time_s'])
        if not good.all():raise ValueError('causal candidate propagation failed')
        scan.norads=np.r_[scan.norads,n];scan.sky=dict(scan.sky,position_km=np.concatenate([scan.sky['position_km'],pos]),velocity_km_s=np.concatenate([scan.sky['velocity_km_s'],vel]),phase_sigma_s=np.r_[scan.sky['phase_sigma_s'],1.])
        scan.elements=dict(scan.elements,**{str(n):dict(lines=record['lines'],provenance={k:v for k,v in record.items() if k!='lines'})})
        dd['node']['seed']['state']['phases']=np.r_[dd['node']['seed']['state']['phases'],0.]
    for row in dd['node']['seed']['rows']:
        key=row['component']
        if key in h['mapping']:
            n=h['mapping'][key];row.update(candidate_norad=n,candidate_index=list(scan.norads).index(n))
    for k,row in enumerate(base.rows):
        if row['component'] in h['aliases']:dd['node']['aliases'][k]=h['aliases'][row['component']]
    family_destinations={}
    for row in base.rows:
        family_destinations.setdefault(row['candidate_norad'],set()).add(h['mapping'].get(row['component'],row['candidate_norad']))
    for e in dd['entries']:
        if e['component'] in h['mapping']:
            e['norad']=h['mapping'][e['component']];e['candidate_index']=list(scan.norads).index(e['norad'])
        elif len(family_destinations.get(e['norad'],set()))==1:
            e['norad']=next(iter(family_destinations[e['norad']]));e['candidate_index']=list(scan.norads).index(e['norad'])
    labels=sorted({r['candidate_index'] for r in dd['node']['seed']['rows']});oldmeans=dict(zip(base.labels,d['means']))
    dd['means']=np.array([oldmeans.get(j,0.) for j in labels])
    for a in ARMS:
        old,x=d['problems'][a];refs=dict(zip(old.labels,old.reference));ref=np.array([refs.get(j,h['phases'].get(str(int(scan.norads[j])),0.)) for j in labels])
        dd['problems'][a]=(old,x);p,_=ORIGINAL_BUILD(dd,z,a,ref);dd['problems'][a]=(p,x)
    return dd
