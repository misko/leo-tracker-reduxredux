"""Exact control-pair reuse scoped to one predictive recovery invocation."""

import dataclasses
import hashlib
import json
from copy import deepcopy

import numpy as np

from leo.analysis.localization_v3.scan import ScanLikelihood


def _fingerprint(value):
    if isinstance(value, np.ndarray):
        if value.dtype.hasobject:
            raise TypeError('Object arrays cannot bind control reuse')
        return dict(type='array', dtype=value.dtype.str, shape=list(value.shape),
                    sha256=hashlib.sha256(value.tobytes(order='C')).hexdigest())
    if isinstance(value, np.generic):
        return _fingerprint(np.asarray(value))
    if dataclasses.is_dataclass(value):
        return {f.name: _fingerprint(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(k): _fingerprint(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_fingerprint(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return {'set_values': sorted((_fingerprint(v) for v in value), key=repr)}
    if isinstance(value, float):
        return dict(type='float', hex=value.hex())
    if value is None or isinstance(value, (int, str, bool)):
        return value
    raise TypeError(type(value).__name__)


def control_key(kind, context, inventory, count, option):
    """Bind all control dependencies, including cached orbit values and noise.

    Appended target rows are excluded only from the three extended graph lists:
    control likelihoods use original members/entries, and membership evaluation
    truncates to count. Stateful policies and alternative factories bypass reuse.
    Unknown scan attributes remain part of the key; unsupported values bypass it.
    """
    d = context
    if (d.get('numerical_policy') is not None or 'problem_factory' in d
            or type(d['scan']) is not ScanLikelihood or (kind == 'fit_shared' and option)):
        return None
    scan = dict(vars(d['scan']))
    if not 0 < count <= len(scan['tracks']):
        return None
    for name in ('tracks', 'white', 'rx_basis'):
        scan[name] = scan[name][:count]
    if any(e['track_index'] >= count for e in d['entries']):
        return None
    state = dict(kind=kind, option=option, count=count, scan=scan,
                 context={k: d[k] for k in ('node', 'keep', 'powers', 'means', 'model', 'entries')},
                 policy=inventory['policy'])
    try:
        raw = json.dumps(_fingerprint(state), sort_keys=True).encode()
    except TypeError:
        return None
    return hashlib.sha256(raw).hexdigest()


class InclusionControlCache:
    """Keep copied complete arm results; never share mutable returned arrays."""

    def __init__(self):
        self._pairs = {}

    def pair(self, compute, control, kind, context, inventory, count, option):
        if not control:
            return compute()
        key = control_key(kind, context, inventory, count, option)
        if key is None:
            return compute()
        if key in self._pairs:
            return deepcopy(self._pairs[key])
        value = compute()
        self._pairs[key] = deepcopy(value)
        return value
