import numpy as np
from catalogue_trial import VISIT_STARTS,partition,constant_log_evidence
from phase_factor import phase_evidence

def test_visit_boundary_crossing_does_not_split_raw_support():
    VISIT_STARTS['synthetic']=np.array([.99,1.13,1.27,2.95,3.10])
    # First dwell spans two clock-second bins, but must have one assignment.
    m=partition('synthetic',np.array([.995,1.01,1.10]))
    assert np.all(m==m[0])

def test_single_training_phase_cannot_change_candidate_prior():
    model=np.arange(16*401,dtype=float).reshape(16,401,1)*.031
    result=phase_evidence([.47],model,[2.])
    np.testing.assert_allclose(result,0,atol=1e-14)

def test_constant_frequency_prior_prefers_correct_shape():
    good=np.array([[1000,1001,999],[1000,1400,600]],float)
    score=constant_log_evidence(good)
    assert score[0]>score[1]
