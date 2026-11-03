import math
from evaluate import CENTER, destination, distance_m, quantile, summarize

def test_geography_and_interpolation():
    assert distance_m(CENTER,destination(0,0)) < 1e-6
    assert abs(distance_m(CENTER,destination(3,4))-5000)<.1
    assert quantile([0,10],.9)==9

def test_failed_points_do_not_improve_primary_metrics():
    result=summarize([
        {"qualified":True,"error_m":2000.,"status":"complete","seconds":1.},
        {"qualified":False,"error_m":1.,"status":"optimizer_unqualified","seconds":2.},
        {"qualified":False,"error_m":None,"status":"timeout","seconds":90.},
    ])
    assert result["qualified"]==1 and result["planned"]==3
    assert result["median_m"]==2000.
    assert result["sub_km_qualified_over_planned"]==0.
    assert result["returned_points"]==2
