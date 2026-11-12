"""Exact control-pair reuse with a narrow numerical-backend identity port."""

import hashlib
import json
from copy import deepcopy

from leo.analysis.localization_v3.inclusion_controls import _fingerprint
from leo.analysis.localization_v3.scan import ScanLikelihood
from leo.contracts.localization_v5 import inclusion_control_policy


class ControlReuseFailure(BaseException):
    """Cache integrity failures must bypass scientific rejection handlers."""


def control_key(kind, context, inventory, count, option, known_bound, binding):
    scan = context['scan']
    if (context.get('numerical_policy') is not None or 'problem_factory' in context
            or type(scan) is not ScanLikelihood or type(count) is not int
            or kind not in ('fit_shared', 'fit_new')
            or (kind == 'fit_shared' and option is not False)
            or (kind == 'fit_new' and option not in ('lbfgsb', 'powell'))
            or getattr(scan, 'bound', None) is not known_bound
            or any(callable(value) for name, value in vars(scan).items() if name != 'bound')):
        return None
    state = dict(vars(scan))
    if not 0 < count <= len(state['tracks']):
        return None
    state['bound'] = dict(manifest_sha256=binding)
    for name in ('tracks', 'white', 'rx_basis'):
        state[name] = state[name][:count]
    if any(entry['track_index'] >= count for entry in context['entries']):
        return None
    value = dict(kind=kind, option=option, count=count, scan=state,
                 context={name: context[name] for name in
                          ('node', 'keep', 'powers', 'means', 'model', 'entries')},
                 policy=inventory['policy'])
    try:
        raw = json.dumps(_fingerprint(value), sort_keys=True).encode()
    except TypeError:
        return None
    return hashlib.sha256(raw).hexdigest()


class CompleteControlCache:
    """Only complete matched arm results may replace a repeated computation."""

    def __init__(self, known_bound, bound_identity):
        self._bound, self._identity = known_bound, bound_identity
        self._binding = deepcopy(bound_identity())
        self._pairs = {}
        self._counts = dict(requests=0, computed=0, reused=0, failed=0, unkeyable=0)

    @property
    def policy(self):
        return inclusion_control_policy()

    def context(self, context, kind, option):
        return context

    def pair(self, compute, control, kind, context, inventory, count, option):
        if not control:
            return compute()
        self._counts['requests'] += 1
        try:
            if self._identity() != self._binding:
                raise ControlReuseFailure('Bound numerical identity changed during control reuse')
            key = control_key(kind, context, inventory, count, option, self._bound, self._binding)
            if key is None:
                self._counts['unkeyable'] += 1
            if key is not None and key in self._pairs:
                value = deepcopy(self._pairs[key])
                self._counts['reused'] += 1
                return value
            value = compute()
            if type(value) is not dict or set(value) != {'c0', 'fitted_c'}:
                raise ControlReuseFailure('Complete matched control pair required')
            if key is not None:
                self._pairs[key] = deepcopy(value)
            self._counts['computed'] += 1
            return value
        except BaseException:
            self._counts['failed'] += 1
            raise

    def counts(self):
        counts = dict(self._counts)
        counts['in_progress'] = counts['requests'] - sum(
            counts[key] for key in ('computed', 'reused', 'failed'))
        return counts
