import numpy as np
from shape_controls import link_segments,extend_continuity


def test_crossing_and_time_adjacency_do_not_link_segments():
    first={'rows':list(range(20))}
    crossing={'rows':list(range(18,38))}
    adjacent={'rows':list(range(38,58))}
    assert len(link_segments([first,crossing,adjacent]))==3


def test_shared_support_links_without_counting_duplicate_points():
    parts=link_segments([{'rows':list(range(20))},{'rows':list(range(10,30))}])
    assert parts==[list(range(30))]


def test_continuity_extension_recovers_ends_without_absorbing_another_curve():
    t=np.arange(40,dtype=float)
    value=10000-100*t+2*t*t-.03*t*t*t
    value[[3,35]]+=10000
    data={'times':t,'measured':value}
    rows=extend_continuity(data,list(range(10,30)),list(range(40)))
    assert set(rows)==set(range(40))-{3,35}
