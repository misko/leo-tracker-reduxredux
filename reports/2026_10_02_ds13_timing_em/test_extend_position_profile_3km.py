import numpy as np
from extend_position_profile_3km import wide_probes


def test_stratified_probes_reproducible_with_radial_and_quadrant_coverage():
    points=wide_probes()
    assert points==wide_probes() and points!=wide_probes(1)
    assert len(points)==12 and len({p['label'] for p in points})==12
    for band,(lo,hi) in enumerate(((500,1000),(1000,2000),(2000,3000))):
        for sector,p in enumerate(points[4*band:4*band+4]):
            assert lo<=np.hypot(p['east_m'],p['north_m'])<=hi
            angle=np.arctan2(p['east_m'],p['north_m'])%(2*np.pi)
            assert sector*np.pi/2<=angle<(sector+1)*np.pi/2
