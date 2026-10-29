import pytest
from run_native_branch_annotations import select_jobs


def test_preserves_claims_and_prioritizes_unseen_scans_without_position_inputs():
    def job(scan,bid,n):return dict(job=dict(job_id=scan),branch=dict(branch_id=bid,points=n))
    old=job('a','old',100);alternative=job('a','alternate',200)
    b=job('b','b',50);b2=job('b','b2',40);c=job('c','c',30)
    jobs=[old,alternative,b,b2,c]
    assert select_jobs(jobs,[old],2)==[b,c]
    assert select_jobs(jobs,[old],3)==[b,c,alternative]
    assert select_jobs(jobs,[old],3,allow_same_scan=True)==[b,b2,c]
    # An incomplete attempt is still a claim, irrespective of its outcome.
    assert select_jobs(jobs,[old,b,c,alternative],8)==[b2]
    with pytest.raises(ValueError):select_jobs(jobs,[],9)
