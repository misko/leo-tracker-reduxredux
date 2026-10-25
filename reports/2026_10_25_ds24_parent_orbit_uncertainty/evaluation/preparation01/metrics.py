"""Saved-output evaluation math; no inference or recording imports."""

import math

SITE = (37.849061591561885, -122.48574968092912)
CENTER = (37.906, -122.545)
ARMS = ('c0', 'fitted_c')
TIE_KM = 1e-6


def local_latlon(position):
    if len(position) != 2 or not all(math.isfinite(float(x)) for x in position):
        raise ValueError('finite east/north endpoint required')
    east,north = map(float,position)
    return (CENTER[0]+north/111., CENTER[1]+east/(111.32*math.cos(math.radians(CENTER[0]))))


def distance(position, site=SITE):
    if len(position) != 2 or not all(math.isfinite(float(x)) for x in position):
        raise ValueError('finite latitude/longitude required')
    p,q = [tuple(map(math.radians, pair)) for pair in (position,site)]
    a = math.sin((p[0]-q[0])/2)**2 + math.cos(p[0])*math.cos(q[0])*math.sin((p[1]-q[1])/2)**2
    return 12742.*math.asin(math.sqrt(min(1.,max(0.,a))))


def research_eligible(conservative_pair, converged_pair, complete_parent_IDs_preserved):
    flags=(conservative_pair,converged_pair,complete_parent_IDs_preserved)
    if not all(isinstance(x,bool) for x in flags):
        raise ValueError('explicit paired gates, convergence and complete accepted-ID checks required')
    return all(flags)


def operational_policy(reference):
    if set(reference) != set(ARMS):
        raise ValueError('exact saved reference pair required')
    return reference, 'original_reference'


def research_policy(reference, candidate, paired_research_qualified):
    """RF decision only; never reads coordinates, distance or an arm's error."""
    if not isinstance(paired_research_qualified,bool):
        raise ValueError('explicit paired RF qualification required')
    if set(reference) != set(ARMS):
        raise ValueError('exact saved reference pair required')
    if paired_research_qualified:
        if not isinstance(candidate,dict) or set(candidate) != set(ARMS):
            raise ValueError('qualified candidate pair unavailable')
        return candidate, 'candidate'
    return reference, 'exact_reference_fallback'


def percentile(values, fraction):
    v=sorted(values)
    if not v:return None
    index=(len(v)-1)*fraction;lo=math.floor(index);hi=math.ceil(index)
    return v[lo]+(v[hi]-v[lo])*(index-lo)


def summarize(errors, baseline):
    """Selected denominator stays fixed; missing outcomes stay missing."""
    if len(errors) != len(baseline):raise ValueError('paired denominators differ')
    usable=[e for e in errors if e is not None]
    if any(not math.isfinite(e) or e<0 for group in (errors,baseline) for e in group if e is not None):
        raise ValueError('invalid error')
    changes=[e-b for e,b in zip(errors,baseline,strict=True) if e is not None and b is not None]
    return dict(selected=len(errors),available=len(usable),missing=len(errors)-len(usable),
                mean_km=sum(usable)/len(usable) if usable else None,
                median_km=percentile(usable,.5),P95_km=percentile(usable,.95),
                maximum_km=max(usable) if usable else None,
                paired_available=len(changes),mean_paired_change_km=sum(changes)/len(changes) if changes else None,
                improved=sum(d < -TIE_KM for d in changes),
                worsened=sum(d > TIE_KM for d in changes),unchanged=sum(abs(d)<=TIE_KM for d in changes))
