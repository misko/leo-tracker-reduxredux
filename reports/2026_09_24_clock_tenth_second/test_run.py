import importlib.util
from pathlib import Path
import numpy as np
P=Path(__file__).with_name("run.py"); S=importlib.util.spec_from_file_location("tenth_test",P); R=importlib.util.module_from_spec(S); S.loader.exec_module(R)
def test_exact_integer_derived_grid():
 np.testing.assert_array_equal(R.TAUS,np.array([-1.5,-1.4,-1.3,-1.2,-1.1,-1.,-.9,-.8,-.7,-.6,-.5]))
 assert np.count_nonzero(R.TAUS==-1)==1
def test_tenth_grid_recovers_known_curved_shift_and_ignores_held_mutation():
 parent=R.load(R.ENGINE,"tenth_parent_test"); review=R.load(R.ENGINE.with_name("test_review.py"),"tenth_review_fixture"); engine,expected=review._engine(moving=True); taus=np.arange(10,21)/10
 before,_,_=engine.profile(0,0,taus,held=True,assignments=True); assert taus[parent.select_tau(before,taus)]==expected
 track=engine.sessions[0]["tracks"][0]; track["measured"][~track["train"]]+=1e6; after,_,_=engine.profile(0,0,taus,held=True,assignments=True)
 np.testing.assert_allclose(after,before); assert parent.select_tau(after,taus)==parent.select_tau(before,taus)
