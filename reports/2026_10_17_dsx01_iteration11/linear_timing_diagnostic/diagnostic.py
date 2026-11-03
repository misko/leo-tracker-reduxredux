"""Metadata-only row selection and bounded linear-timing diagnostic primitives."""

import hashlib

import numpy as np

DELTAS_S = (-6., -4., -2., -1., 0., 1., 2., 4., 6.)
MAXIMUM_ROWS = 32
MAXIMUM_PER_LANE = 2
MAXIMUM_ORBIT_CALLS = 18
MAXIMUM_ELEVATION_CALLS = 18


def selection_key(observation_id):
    if not isinstance(observation_id, str) or not observation_id:
        raise ValueError('Nonempty original string observation IDs required')
    payload = b'linear-timing-metadata-v1\0' + observation_id.encode('utf-8')
    return hashlib.sha256(payload).hexdigest(), observation_id


def select_training_rows(metadata, train_mask):
    """Read only IDs/time/RF/RX/channel, never measured CFO or references."""
    ids = tuple(metadata.window_ids)
    time, rf, rx, channel = (np.asarray(getattr(metadata, name)) for name in
                            ('times_s', 'rf_hz', 'receiver', 'channel'))
    mask = np.asarray(train_mask)
    if mask.dtype != bool or mask.shape != (len(ids),) or not mask.any():
        raise ValueError('Nonempty aligned boolean TRAIN mask required')
    if any(a.shape != mask.shape for a in (time, rf, rx, channel)):
        raise ValueError('Aligned original metadata required')
    if any(not np.isfinite(a).all() for a in (time, rf, rx, channel)) or np.any(rf <= 0):
        raise ValueError('Finite metadata and positive actual RF required')
    if len(set(ids)) != len(ids):
        raise ValueError('Unique global observation IDs required')
    keys = [selection_key(name) for name in ids]
    lanes = {}
    for row in np.flatnonzero(mask):
        lane = (int(rx[row]), int(channel[row]), float(rf[row]))
        lanes.setdefault(lane, []).append(int(row))
    selected = []
    for rows in lanes.values():
        selected.extend(sorted(rows, key=lambda row: keys[row])[:MAXIMUM_PER_LANE])
    return np.asarray(sorted(selected, key=lambda row: keys[row])[:MAXIMUM_ROWS], int)


class CallLedger:
    """Debit before every port call; include failures and both delta-zero calls."""

    def __init__(self, persist):
        self.persist = persist
        self.calls = []

    def call(self, kind, arm, delta, function, *args, **kwargs):
        limits = {'orbit': MAXIMUM_ORBIT_CALLS, 'elevation': MAXIMUM_ELEVATION_CALLS}
        if kind not in limits or arm not in ('fitted-c', 'zero-c') or delta not in DELTAS_S:
            raise ValueError('Only declared port/arm/delta calls permitted')
        if any(r['kind'] == kind and r['arm'] == arm and r['delta_s'] == delta for r in self.calls):
            raise ValueError('No duplicate or retry calls permitted')
        if sum(r['kind'] == kind for r in self.calls) >= limits[kind]:
            raise ValueError('Declared port-call allowance exhausted')
        record = dict(kind=kind, arm=arm, delta_s=float(delta), status='started')
        self.calls.append(record)
        self.persist(self.calls)
        try:
            result = function(*args, **kwargs)
        except BaseException:
            record['status'] = 'failed'
            self.persist(self.calls)
            raise
        record['status'] = 'complete'
        self.persist(self.calls)
        return result


def summarize(exact_hz, linear_hz, sine, zero_sine, weight, zero_weight):
    arrays = [np.asarray(a, float) for a in
              (exact_hz, linear_hz, sine, zero_sine, weight, zero_weight)]
    if arrays[0].ndim != 2 or not arrays[0].size or any(a.shape != arrays[0].shape for a in arrays):
        raise ValueError('Nonempty aligned observation-candidate arrays required')
    if any(not np.isfinite(a).all() for a in arrays):
        raise ValueError('Finite diagnostic arrays required')
    exact, linear, sine, zero_sine, weight, zero_weight = arrays
    error = exact - linear
    quantiles = [0, 50, 90, 95, 99, 100]
    return dict(pairs=int(error.size), quantile_percent=quantiles,
                signed_error_hz=np.percentile(error, quantiles).tolist(),
                absolute_error_hz=np.percentile(abs(error), quantiles).tolist(),
                rms_error_hz=float(np.sqrt(np.mean(error**2))),
                maximum_absolute_error_hz=float(np.max(abs(error))),
                horizon_crossings=int(np.count_nonzero((sine >= 0) != (zero_sine >= 0))),
                soft_weight_changes=int(np.count_nonzero(weight != zero_weight)),
                maximum_soft_weight_change=float(np.max(abs(weight - zero_weight))))
