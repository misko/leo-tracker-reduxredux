from copy import deepcopy
import pytest
from check_one_start_blas_window import validate_previous_stage


def stage(suffix):
    return {'rows':[{'unit':d+'-B01-'+suffix,'both_accepted_equivalent':True} for d in ('DS9','DS10','DS11')]}


def test_only_correct_complete_stage_can_advance():
    validate_previous_stage(stage('S1'),2)
    validate_previous_stage(stage('D1'),4)
    for prior,size in ((stage('S1'),4),(stage('D1'),2),(stage('S1'),1)):
        with pytest.raises(ValueError):validate_previous_stage(prior,size)


def test_failure_missing_and_duplicate_outcomes_stop_expansion():
    original=stage('D1')
    failed=deepcopy(original);failed['rows'][1]['both_accepted_equivalent']=False
    missing=deepcopy(original);missing['rows'].pop()
    duplicate=deepcopy(original);duplicate['rows'][1]=duplicate['rows'][0]
    for prior in (failed,missing,duplicate):
        with pytest.raises(ValueError):validate_previous_stage(prior,4)
