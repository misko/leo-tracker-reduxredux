import importlib.util
from pathlib import Path
import numpy as np
import pytest
import sys

P=Path(__file__).with_name('direction_features.py');s=importlib.util.spec_from_file_location('df',P);m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m)

def test_enu_cardinal_geometry():
 u=m.unit_enu([90,0,0],[0,0,90]);assert np.allclose(u,[[1,0,0],[0,1,0],[0,0,1]],atol=1e-12)

def test_doppler_weights_marginalize_east_component():
 x=m.marginal_direction([90,270],[0,0],[0,np.log(3)])
 assert x['east']==pytest.approx(-.5) and x['effective_hypotheses']==pytest.approx(1.6)

def test_truth_branch_requires_explicit_diagnostic(monkeypatch):
 monkeypatch.setattr(m,'candidate_look_angles',lambda *a,**k:{(1,2):(90.,0.)})
 h=[m.DopplerHypothesis('t',1,2,0.)]
 with pytest.raises(ValueError):m.branch_direction_features(object(),h,branch_id='truth',latitude_deg=0,longitude_deg=0)
 assert m.branch_direction_features(object(),h,branch_id='truth',latitude_deg=0,longitude_deg=0,diagnostic_truth=True)[0]['east']==pytest.approx(1)

def test_branches_do_not_share_hypotheses(monkeypatch):
 def angles(_,ids,times,**kw):return {(int(i),int(t)):((90.,0.) if kw['longitude_deg']==1 else (270.,0.)) for i,t in zip(ids,times)}
 monkeypatch.setattr(m,'candidate_look_angles',angles);h=[m.DopplerHypothesis('t',1,2,0.)]
 a=m.branch_direction_features(object(),h,branch_id='sac',latitude_deg=0,longitude_deg=1)
 b=m.branch_direction_features(object(),h,branch_id='reno',latitude_deg=0,longitude_deg=2)
 assert a[0]['east']>0 and b[0]['east']<0

def test_reception_is_joined_after_direction_fit():
 rows=[{'track_id':'a','east':.2},{'track_id':'b','east':-.1}]
 assert m.reception_design_rows(rows,{'a':.7})==[{'track_id':'a','east':.2,'signed_rx_proxy':.7}]

def test_observation_ids_are_exposed(monkeypatch):
 monkeypatch.setattr(m,'candidate_look_angles',lambda *a,**k:{(1,2):(90.,0.)})
 h=[m.DopplerHypothesis('t',1,2,0.,'visit-4:probe-0')]
 x=m.branch_direction_features(object(),h,branch_id='sac',latitude_deg=0,longitude_deg=0)
 assert x[0]['observation_ids']==['visit-4:probe-0']
