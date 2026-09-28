import json
import numpy as np
import pytest
import run_search as runner
from score_distances import distance_km


def test_coordinate_origin_and_distance():
    assert runner.coordinates(38.,-121.,0,0)==pytest.approx((38.,-121.))
    moved=runner.coordinates(38.,-121.,5,12)
    assert distance_km((38.,-121.),moved)==pytest.approx(13.,abs=1e-8)


def test_frozen_calibration_drops_test_truth_fields_and_never_fits_test(tmp_path,monkeypatch):
    cal=[]
    for i in range(12):
        cal.append(dict(session_id=f'cal-{i//2}',split='cal',track_id=f't-{i//2}',observation_id=str(i),
            receiver_id='rx0' if i%2==0 else 'rx1',channel=1,edge='lower',sample_rate_hz=2500000,
            anchor_margin=.1+.01*i,matched=i%3!=0,log_margin_ratio_rx1_rx0=.2*i+(-.3 if i%2 else .3),
            east=.1*i-.5,up=.8))
    d=runner.model_eval.fit_detection_models(cal)['M1'];c=runner.model_eval.fit_continuous_models(cal)['M1']
    prior={'detection':{'models':{'M1':{'coefficients':list(d.coefficients)}}},
           'continuous':{'models':{'M1':{'coefficients':list(c.coefficients)}}}}
    hold=dict(cal[0],session_id='test',split='holdout',east=999.,up=-123.,candidate_ids=[999999],latitude_deg=37.,longitude_deg=-122.)
    (tmp_path/'results.json').write_text(json.dumps(prior))
    (tmp_path/'model_rows.json').write_text(json.dumps(cal+[hold]))
    monkeypatch.setattr(runner,'SOURCE',tmp_path)
    d1,c1,var,rows,_=runner.frozen_models_and_endpoints()
    assert d1==d and c1==c and var>0
    assert rows['test'][0]['east']==0 and rows['test'][0]['up']==0
    assert not {'candidate_ids','latitude_deg','longitude_deg'} & rows['test'][0].keys()
    hold.update(anchor_margin=1e9,matched=True,east=-999.)
    (tmp_path/'model_rows.json').write_text(json.dumps(cal+[hold]))
    d2,c2,var2,_,_=runner.frozen_models_and_endpoints()
    assert d1==d2 and c1==c2 and var==var2
