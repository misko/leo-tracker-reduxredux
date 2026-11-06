"""Exact repeated controls on a view without the discovery-only geometry cache."""

import dataclasses
import hashlib
import json
from copy import copy, deepcopy

import numpy as np

from leo.analysis.localization_v3.scan import ScanLikelihood


def _fingerprint(value):
    if isinstance(value, np.ndarray):
        if value.dtype.hasobject or value.dtype.fields:
            raise TypeError('Unsupported array dtype in control key')
        data = value if value.flags.c_contiguous else value.tobytes(order='C')
        return dict(type='array', dtype=value.dtype.str, shape=list(value.shape),
                    sha256=hashlib.sha256(data).hexdigest())
    if isinstance(value, np.generic):
        return _fingerprint(np.asarray(value))
    if dataclasses.is_dataclass(value):
        return dict(type=type(value).__module__ + '.' + type(value).__qualname__,
                    fields={f.name: _fingerprint(getattr(value, f.name))
                            for f in dataclasses.fields(value)})
    if isinstance(value, dict):
        return {json.dumps(_fingerprint(k), sort_keys=True): _fingerprint(v)
                for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [_fingerprint(v) for v in value]
        if isinstance(value, (set, frozenset)):
            items.sort(key=repr)
        return dict(type=type(value).__name__, values=items)
    if isinstance(value, float):
        return dict(type='float', hex=value.hex())
    if value is None or isinstance(value, (int, str, bool)):
        return value
    raise TypeError(type(value).__name__)


def eligible(d, kind, option):
    return (d.get('numerical_policy') is None and 'problem_factory' not in d
            and type(d['scan']) is ScanLikelihood
            and not (kind == 'fit_shared' and option)
            and not any(callable(v) for v in vars(d['scan']).values()))


def control_key(kind, context, inventory, count, option):
    d = context
    if not eligible(d, kind, option) or 'geometry' in vars(d['scan']):
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
    def __init__(self):
        self._pairs = {}

    def context(self, d, kind, option):
        if not eligible(d, kind, option):
            return d
        scan = copy(d['scan'])
        # Physical exclusion makes the key describe the actual computation.
        # Fixed-family controls construct their own phase geometry. Discovery
        # and family weighting still receive the complete original scan.
        vars(scan).pop('geometry', None)
        return dict(d, scan=scan)

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
