from confirm_ds23_curve_predictive_guard import proposal_jobs


def test_confirmation_fold_jobs_preserve_no_proposal_cases_without_scheduling_them():
    cases=['A','B','C']
    proposals={'A':None,'B':{},'C':None}
    families={'A':{4},'B':{3,1},'C':{2}}
    assert proposal_jobs(cases,proposals,families)==[
        ('B',1,'baseline'),('B',1,'expanded'),('B',3,'baseline'),('B',3,'expanded')]
    assert cases==['A','B','C']
