import numpy as np
from report import error_km,summarize


def test_haversine():
    assert error_km((37,-122),(37,-122))==0
    np.testing.assert_allclose(error_km((0,0),(0,1)),111.19492664455873)


def test_failure_denominator():
    s=summarize([.1,.7],3)
    assert s['localized']==2 and s['population']==3
    assert s['fraction_all_within_500m']==1/3
