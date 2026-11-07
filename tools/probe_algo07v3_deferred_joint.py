"""External prototype for paired fits with receipt delivery at original boundaries."""

import json
from copy import deepcopy

from leo.analysis.localization_v3.numerical_policy import NumericalPolicy


class JointPairFailure(BaseException):
    """Malformed execution cannot become a scientific fallback."""


def exact(value):
    try:
        return json.dumps(value, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise JointPairFailure('Numerical receipt is not finite canonical data') from error


def delta(before, after):
    if not isinstance(after, dict) or set(after) != set(before):
        raise JointPairFailure('Numerical receipt fields changed')
    lists = ('reference_updates', 'optimizer_calls')
    constants = set(before) - {*lists, 'problem_count'}
    if any(exact(before[k]) != exact(after[k]) for k in constants):
        raise JointPairFailure('Numerical policy configuration changed')
    increment = after['problem_count']
    if type(increment) is not int or increment < before['problem_count']:
        raise JointPairFailure('Numerical problem count was rewritten')
    result = {'problem_count': increment - before['problem_count']}
    for key in lists:
        if not isinstance(after[key], list) or exact(after[key][:len(before[key])]) != exact(
                before[key]):
            raise JointPairFailure('Numerical receipt prefix was rewritten')
        result[key] = deepcopy(after[key][len(before[key]):])
    return result


class DeferredJointFits:
    """One method's c0 and fitted-c fits; parent audits remain strictly serial.

    An ordered process mapper finishes and reaps both children before returning.
    Each fit's numerical delta is appended when the original controller requests
    that arm, so the intervening parent audit retains its original receipt slot.
    This class is an external prototype, not used by the owned controller.
    """

    def __init__(self, context, probe, method, optimizer, operation, mapper):
        self.context, self.probe = context, probe
        self.method, self.optimizer = method, optimizer
        self.operation, self.mapper = operation, mapper
        # The stage runner may install a fresh policy after construction.
        self.policy = None
        self.enabled = None
        self.origin = None
        self.configuration = None
        self.pending = None
        self.expected = None
        self.next_arm = 'c0'

    def fit(self, arm):
        if arm != self.next_arm:
            raise JointPairFailure('Original ordered calibration arm required')
        if arm == 'c0':
            self.policy = self.context.get('numerical_policy')
            self.enabled = (self.mapper is not None and 'problem_factory' not in self.context
                            and (self.policy is None or type(self.policy) is NumericalPolicy))
            if self.enabled and self.policy:
                self.configuration = (self.policy.reference_limit_s, self.policy.centered_lbfgsb,
                                      self.policy.joint_contraction_optimized)
        if not self.enabled:
            value = self.operation(self.context, self.probe, arm, self.method,
                                   optimizer=self.optimizer)
            self.next_arm = 'fitted_c' if arm == 'c0' else None
            return value
        owner = self.context.get('numerical_policy')
        # Numerical replay installs a new empty owned policy for every stage.
        if owner is not self.policy and (
                self.policy is None or type(owner) is not NumericalPolicy
                or exact(owner.receipt) != exact(self.origin)
                or (owner.reference_limit_s, owner.centered_lbfgsb,
                    owner.joint_contraction_optimized) != self.configuration):
            raise JointPairFailure('Unexpected stage numerical policy')
        if arm == 'c0':
            before = deepcopy(self.policy.receipt) if self.policy else None
            self.origin = deepcopy(before)

            def run(child_arm):
                local = dict(self.context)
                if self.policy:
                    local['numerical_policy'] = deepcopy(self.policy)
                value = self.operation(local, self.probe, child_arm, self.method,
                                       optimizer=self.optimizer)
                receipt = local['numerical_policy'].receipt if self.policy else None
                return child_arm, value, receipt

            try:
                completed = list(self.mapper(run, ('c0', 'fitted_c')))
            except Exception as error:
                raise JointPairFailure('Joint fit process execution failed') from error
            if self.context.get('numerical_policy') is not self.policy:
                raise JointPairFailure('Mapper replaced owning numerical policy')
            if len(completed) != 2:
                raise JointPairFailure('Both complete joint fits required')
            if self.policy and exact(self.policy.receipt) != exact(before):
                raise JointPairFailure('Mapper mutated owning numerical receipt')
            checked = []
            for expected, record in zip(('c0', 'fitted_c'), completed, strict=True):
                if not isinstance(record, tuple) or len(record) != 3 or record[0] != expected:
                    raise JointPairFailure('Joint fit transport or arm order changed')
                _, value, receipt = record
                if not self.policy and receipt is not None:
                    raise JointPairFailure('Unexpected numerical receipt')
                checked.append((value, delta(before, receipt) if self.policy else None))
            self.pending = checked
            self.expected = before
        value, changes = self.pending[0 if arm == 'c0' else 1]
        if owner:
            # Allow only append-only intervening audit work, preserving its position.
            delta(self.expected if owner is self.policy else self.origin, owner.receipt)
            merged = deepcopy(owner.receipt)
            for key in ('reference_updates', 'optimizer_calls'):
                merged[key].extend(deepcopy(changes[key]))
            merged['problem_count'] += changes['problem_count']
            owner.receipt.clear()
            owner.receipt.update(merged)
            self.expected = deepcopy(merged)
        self.next_arm = 'fitted_c' if arm == 'c0' else None
        if arm == 'fitted_c':
            self.pending = None
        return value
