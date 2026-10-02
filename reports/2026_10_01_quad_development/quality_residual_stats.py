"""Small descriptive rank statistics; no fitted quality calibration."""
import numpy as np


def ranks(values):
    x=np.asarray(values,float)
    if not np.isfinite(x).all(): raise ValueError('nonfinite rank input')
    order=np.argsort(x,kind='stable'); result=np.empty(len(x),float)
    i=0
    while i<len(x):
        j=i+1
        while j<len(x) and x[order[j]]==x[order[i]]: j+=1
        result[order[i:j]]=(i+j-1)/2
        i=j
    return result


def summarize(rows):
    x=ranks([r['median_margin'] for r in rows]); y=ranks([r['energy_per_dimension'] for r in rows])
    rho=float(np.corrcoef(x,y)[0,1]) if len(x)>1 and np.ptp(x)>0 and np.ptp(y)>0 else None
    good=bad=ties=0
    for i,a in enumerate(rows):
        for b in rows[i+1:]:
            if a['norad']!=b['norad']: continue
            product=(a['median_margin']-b['median_margin'])*(a['energy_per_dimension']-b['energy_per_dimension'])
            if product<0: good+=1
            elif product>0: bad+=1
            else: ties+=1
    concordance=good/(good+bad) if good+bad else None
    halves={}
    for name,predicate in [('below_0_5',lambda v:v<.5),('at_least_0_5',lambda v:v>=.5)]:
        values=[r['energy_per_dimension'] for r in rows if predicate(r['median_margin'])]
        halves[name]=dict(tracks=len(values),median_energy_per_dimension=float(np.median(values)) if values else None)
    return dict(spearman=rho,within_satellite_concordant=good,within_satellite_discordant=bad,
                within_satellite_ties=ties,within_satellite_concordance=concordance,threshold_groups=halves,
                directional_gate=bool(rho is not None and rho<0 and concordance is not None and concordance>.5))
