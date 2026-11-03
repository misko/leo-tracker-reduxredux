"""Full-denominator three-record acquisition-family pilot gate."""
import numpy as np


def assess(rows):
    out={}
    for family in (0,1):
        group=[r for r in rows if r['family']==family]
        qualified=len(group)==3 and all(r[a]['qualified'] for r in group for a in ('doppler','signed'))
        result=dict(attempted_records=len(group),complete_qualified_pairs=sum(all(r[a]['qualified'] for a in ('doppler','signed')) for r in group),passed=False)
        if qualified:
            a=np.array([r['doppler']['error_m'] for r in group]);b=np.array([r['signed']['error_m'] for r in group]);extra=[r for r in group if r['cohort']=='additional']
            wins=int(np.sum(b<a))
            result.update(wins=wins,control_median_m=float(np.median(a)),signed_median_m=float(np.median(b)),control_p90_m=float(np.quantile(a,.9)),signed_p90_m=float(np.quantile(b,.9)),
                          passed=bool(wins>=2 and np.median(b)<=.95*np.median(a) and np.quantile(b,.9)<=np.quantile(a,.9) and len(extra)==1 and extra[0]['signed']['error_m']<extra[0]['doppler']['error_m']))
        out[str(family)]=result
    return out
