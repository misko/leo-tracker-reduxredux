"""Defer factorized diagnostics when paired acceptance and retry are decided."""

from copy import deepcopy

from leo.analysis.localization_v3.joint_recovery import joint_numerical_only
from leo.analysis.localization_v3.numerical_policy import NumericalPolicy
from leo.analysis.localization_v3.scan import ScanLikelihood

ARMS = ('c0', 'fitted_c')


class JointScheduleFailure(BaseException):
    """Execution-policy faults cannot become scientific rejection."""


def omission_reason(experiment):
    try:
        if any(m not in experiment or set(experiment[m]) != set(ARMS)
               for m in ('control', 'joint')):
            raise JointScheduleFailure('Both complete control and joint arms required')
        records = [experiment[m][a] for m in ('control', 'joint') for a in ARMS]
        if all(r['audit']['RF_qualified_arm'] for r in records):
            return 'joint_already_qualified'
        possible = all(
            not r['audit']['incumbent_owner_changes']
            and r['audit']['phase_check']['phase_change_s'] <= .01
            and all(v['all_pass'] for v in r['audit']['exact_incumbent_orbits'])
            and all(v for k, v in r['audit']['checks'].items() if k != 'incumbent_and_numerical')
            for r in records)
    except (KeyError, TypeError, AttributeError) as error:
        raise JointScheduleFailure('Malformed paired joint audit') from error
    return None if possible else 'numerical_retry_ruled_out'


def eligible(context, known_bound):
    if type(context) is not dict:
        return False
    scan = context.get('scan')
    policy = context.get('numerical_policy')
    return (type(scan) is ScanLikelihood and getattr(scan, 'bound', None) is known_bound
            and 'problem_factory' not in context
            and (policy is None or (type(policy) is NumericalPolicy
                 and not any(callable(v) for v in vars(policy).values())))
            and not any(callable(v) for k, v in vars(scan).items() if k != 'bound'))


class JointSchedule:
    def __init__(self, context, optimizer, known_bound, bound_identity):
        if optimizer not in ('lbfgsb', 'powell'):
            raise JointScheduleFailure('Known joint optimizer required')
        self._context, self._bound, self._identity = context, known_bound, bound_identity
        self._binding = bound_identity()
        self._eligible = eligible(context, known_bound)
        self.methods = (('control', 'joint', 'factorized') if self._eligible else
                        ('control', 'factorized', 'joint'))
        self._decision = False
        self._started = False
        self._row = dict(optimizer=optimizer, eligible=self._eligible, state='started',
                         factorized='not_reached', reason=None, completed_arms=0)

    def _check(self):
        if self._identity() != self._binding:
            raise JointScheduleFailure('Bound numerical identity changed during joint scheduling')
        if self._eligible and not eligible(self._context, self._bound):
            raise JointScheduleFailure('Eligible joint execution context changed')

    def omit_factorized(self, experiment):
        self._check()
        if self._decision:
            raise JointScheduleFailure('Factorized scheduling decision was repeated')
        self._decision = True
        reason = omission_reason(experiment) if self._eligible else None
        self._row['reason'] = reason
        if reason is not None:
            self._row['factorized'] = 'omitted'
            return True
        self._started = True
        return False

    def finish(self, experiment, completed):
        self._check()
        if type(completed) is not bool or self._row['state'] != 'started':
            raise JointScheduleFailure('One terminal joint scheduling state required')
        arms = experiment.get('factorized', {})
        done = sum(a in arms and set(arms[a]) == {'trial', 'audit'} for a in ARMS)
        self._row['completed_arms'] = done
        if self._row['factorized'] == 'omitted':
            if done or omission_reason(experiment) != self._row['reason']:
                raise JointScheduleFailure('Omitted factorized work has inconsistent evidence')
        else:
            self._row['factorized'] = ('computed' if done == 2 else
                                      'incomplete' if self._started else 'not_reached')
        if completed and self._row['factorized'] not in ('computed', 'omitted'):
            raise JointScheduleFailure('Completed joint experiment requires a factorized decision')
        self._row['state'] = 'completed' if completed else 'failed'

    def numerical_only(self, experiment):
        self._check()
        if self._row['state'] != 'completed':
            raise JointScheduleFailure('Complete paired experiment required before retry')
        if self._row['factorized'] == 'omitted':
            if omission_reason(experiment) != self._row['reason']:
                raise JointScheduleFailure('Joint retry evidence changed after omission')
            return False
        return joint_numerical_only(experiment)

    def snapshot(self):
        self._check()
        return deepcopy(self._row)
