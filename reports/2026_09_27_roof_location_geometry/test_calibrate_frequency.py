import importlib.util,sys
from pathlib import Path
import numpy as np
P=Path(__file__).with_name('calibrate_frequency.py');s=importlib.util.spec_from_file_location('cf',P);m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m)
def test_robust_location_resists_outlier():
 assert abs(m.robust_location([0,1,-1,500]))<30
def test_shortlist_uses_training_only():
 pred=np.array([[0,0,0],[10,10,-1000]],float);meas=np.zeros(3);mask=np.array([1,1,0],bool)
 a=m.shortlist(pred,meas,mask,[1,1],[1,2]);pred[:,2]=[9999,-9999];b=m.shortlist(pred,meas,mask,[1,1],[1,2])
 assert [(x['candidate_id'],x['training_nll']) for x in a]==[(x['candidate_id'],x['training_nll']) for x in b]
def test_student_nll_is_finite_and_ordered():
 assert np.isfinite(m.student_nll([0,1])) and m.student_nll([0,1])<m.student_nll([0,1000])
