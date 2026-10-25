"""Immutable I/O and protocol checks for the bounded movement experiment."""
import hashlib
import json
from pathlib import Path

import numpy as np

SEEDS = (2026102504, 2026102505)
MODELS = ('baseline', 'sharedRF50')
ARMS = ('c0', 'fitted_c')
SCALES = (1., float(np.sqrt(2.)), 2.)
CONTROLS = Path('/srv/bulk/leo/research/ds24-receiver-orbit-controls-20261025')
ORIGINAL = Path('/srv/bulk/leo/research/ds24-receiver-shift-witness-20261025/heldout')
PLAN = Path('/home/mouse9911/gits/leo-tracker-reduxredux/plans/ds24-movement-execution-plan.md')


def encode(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(type(value).__name__)


def canonical(value):
    return json.dumps(value, default=encode, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def value_digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, default=encode, indent=2, allow_nan=False) + '\n'
    with path.open('x') as stream:
        stream.write(payload)


def binding(path):
    path = Path(path).resolve()
    return dict(path=str(path), sha256=digest(path))


def verify_bindings(bindings):
    for item in bindings:
        if digest(item['path']) != item['sha256']:
            raise ValueError('sealed dependency changed: ' + item['path'])


def load_sealed(root):
    root = Path(root).resolve()
    protocol = read(root/'protocol.json')
    seal = read(root/'freeze_seal.json')
    if digest(root/'protocol.json') != seal['protocol_sha256']:
        raise ValueError('protocol seal mismatch')
    verify_bindings(protocol['bindings'])
    if protocol['seeds'] != list(SEEDS) or protocol['arms'] != list(ARMS) or protocol['models'] != list(MODELS):
        raise ValueError('scientific matrix changed')
    if protocol['sigma_multipliers'] != list(SCALES):
        raise ValueError('score scales changed')
    if protocol['position_steps'] != 48 or protocol['phase_rounds'] != 5:
        raise ValueError('scientific budget changed')
    if protocol['job_seconds_cap'] != 240 or protocol['batch_seconds_cap'] != 2700:
        raise ValueError('execution cap changed')
    if protocol['gain_tolerance'] != 1e-8 or protocol['GPS_used'] is not False:
        raise ValueError('policy changed')
    return protocol


def job_key(case, seed, fold):
    return f'{case}_seed{int(seed)}_fold{int(fold)}'


def result_path(root, case, seed, fold):
    return Path(root)/'results'/(job_key(case, seed, fold) + '.json')


def require_job(protocol, case, seed, fold):
    matching = [j for j in protocol['jobs'] if (j['case'], j['seed'], j['fold']) == (case, int(seed), int(fold))]
    if len(matching) != 1:
        raise ValueError('job outside sealed matrix')
    return matching[0]


def finite_numeric_tree(value):
    if isinstance(value, dict):
        return all(finite_numeric_tree(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return all(finite_numeric_tree(v) for v in value)
    if isinstance(value, (float, np.floating)):
        return bool(np.isfinite(value))
    if isinstance(value, np.ndarray):
        return value.dtype.kind not in 'fc' or bool(np.isfinite(value).all())
    return True
