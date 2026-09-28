"""Pure post-evaluation comparison; reference coordinates never enter a search."""
import math
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'2026_09_27_roof_geometry_confirmation'))
from score_confirmation import distance_km


def compare(points, seed, reference):
    if not points: raise ValueError('empty grid')
    keys=[(p['east_km'],p['north_km']) for p in points]
    if len(keys)!=len(set(keys)): raise ValueError('duplicate grid coordinate')
    if (seed['east_km'],seed['north_km']) not in keys: raise ValueError('grid omits original D seed')
    for p in points:
        if not all(math.isfinite(p[k]) for k in ('east_km','north_km','latitude_deg','longitude_deg')):
            raise ValueError('nonfinite coordinate')
        if not all(math.isfinite(p['scores'][arm]) for arm in ('D','D_plus_geometry')):
            raise ValueError('nonfinite score')
    def choose(arm):return min(points,key=lambda p:(p['scores'][arm],p['east_km'],p['north_km']))
    def error(p):return distance_km((p['latitude_deg'],p['longitude_deg']),reference)
    d,j=choose('D'),choose('D_plus_geometry')
    s,de,je=error(seed),error(d),error(j)
    return dict(seed_error_km=s,local_d_error_km=de,local_joint_error_km=je,
        refinement_change_km=de-s,geometry_ranking_change_km=je-de,
        selected={'D':d,'D_plus_geometry':j},evaluated_points=len(points))
