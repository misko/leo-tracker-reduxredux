from copy import deepcopy

import pytest

from leo.analysis.localization_v5.joint_schedule import JointScheduleFailure
from leo.contracts.localization_v5 import joint_schedule_policy, validate_joint_schedule_work
from leo.operations.localization_v5_joint import JointScheduleFactory
from tests.analysis.test_localization_v5_control_reuse import fixture
from tests.analysis.test_localization_v5_joint_schedule import experiment


def test_factory_reports_bound_actual_experiments_without_claiming_skipped_fits():
    context, _, bound = fixture()
    factory = JointScheduleFactory(bound, joint_schedule_policy())
    values = experiment()
    policy = factory(context, 'lbfgsb')
    assert policy.omit_factorized(values)
    values['factorized'] = {}
    policy.finish(values, True)
    second = factory(context, 'powell')
    second.finish({}, False)
    work = factory.provenance()
    assert work['counts'] == dict(started=2, completed=1, failed=1, in_progress=0, ineligible=0,
                                 factorized_computed=0, factorized_omitted=1,
                                 factorized_incomplete=0, factorized_not_reached=1)
    factory.policy['order'].clear()
    assert factory.policy == joint_schedule_policy()
    bound.manifest['changed'] = True
    with pytest.raises(JointScheduleFailure, match='manifest binding'):
        factory.provenance()


@pytest.mark.parametrize('change', ['binding', 'policy', 'count_bool', 'count_sum', 'row_bool',
                                   'false_omission', 'missing', 'extra'])
def test_work_rejects_corrupted_identity_or_actual_work(change):
    context, _, bound = fixture()
    factory = JointScheduleFactory(bound, joint_schedule_policy())
    factory(context, 'lbfgsb')
    expected = factory.provenance()
    work = deepcopy(expected)
    if change == 'binding':
        work['backend_manifest_sha256'] = 'other'
    elif change == 'policy':
        work['policy']['order'].reverse()
    elif change == 'count_bool':
        work['counts']['started'] = True
    elif change == 'count_sum':
        work['counts']['completed'] += 1
    elif change == 'row_bool':
        work['experiments'][0]['completed_arms'] = False
    elif change == 'false_omission':
        work['experiments'][0].update(eligible=False, factorized='omitted',
                                       reason='numerical_retry_ruled_out')
    elif change == 'missing':
        del work['experiments'][0]['state']
    else:
        work['extra'] = True
    with pytest.raises(ValueError):
        validate_joint_schedule_work(work, factory.policy, expected['backend_manifest_sha256'])
