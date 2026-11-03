"""Adapter from frozen campaign artifacts to existing pure Doppler model ports."""
import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from cohort import ROOT, ROOF, digest


def enable_research_model():
    paths = [ROOT/'reports'/name for name in ('2026_10_02_ds13_timing_em',
             '2026_10_02_multiscan_localization', '2026_10_02_localization_benchmark')]
    for path in reversed(paths):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))


class Data(SimpleNamespace):
    def predict(self, parameters, *, rows=None, satellites=None):
        enable_research_model()
        from prediction_jacobian import paired_prediction_jacobian
        if rows is None or satellites is None:
            raise ValueError('paired rows and satellite indices required')
        predicted, visible, _ = paired_prediction_jacobian(self, parameters, rows, satellites)
        return predicted, visible


def view(data, rows):
    rows = np.asarray(rows)
    result = copy.copy(data)
    for key in ('times', 'measured', 'rf', 'receiver', 'channel', 'group', 'margin', 'original_rows'):
        setattr(result, key, getattr(data, key)[rows].copy())
    return result


def load(directory, *, top_only=True):
    enable_research_model()
    from oracle_position_diagnostic import reference_coordinates
    observations_path = directory/'observations.json'
    refined_path = directory/'refinement/refined.json'
    bank_path = directory/'orbit-bank/states.npz'
    bank_receipt_path = directory/'orbit-bank/receipt.json'
    source = json.loads(observations_path.read_text())
    refined = json.loads(refined_path.read_text())
    bank = json.loads(bank_receipt_path.read_text())
    expected = digest(observations_path.read_bytes())
    if refined['summary']['status'] != 'complete' or refined['summary']['signature']['observations_sha256'] != expected:
        raise ValueError('refinement incomplete or from different observations')
    if bank['signature']['observations_sha256'] != expected or bank['arrays_sha256'] != digest(bank_path.read_bytes()):
        raise ValueError('orbit bank input binding failed')
    records = source['records']
    by_row = {r['row_index']: r for r in refined['records']}
    if len(by_row) != len(records) or set(by_row) != {r['row_index'] for r in records}:
        raise ValueError('refinement row inventory mismatch')
    for row in records:
        result = by_row[row['row_index']]
        if result['candidate_id'] != row['candidate_id'] or result['probe_key'] != row['probe_key']:
            raise ValueError('refined candidate identity mismatch')
    original = np.asarray([r['row_index'] for r in records], dtype=int)
    _, groups = np.unique([r['group_id'] for r in records], return_inverse=True)
    with np.load(bank_path, allow_pickle=False) as arrays:
        data = Data(nodes=arrays['nodes_s'].copy(), numbers=arrays['numbers'].copy(),
                    position=arrays['position_km'].copy(), velocity=arrays['velocity_km_s'].copy())
    data.times = np.asarray([r['time_s'] for r in records])
    data.measured = np.asarray([by_row[i]['output_hz'] for i in original])
    data.rf = np.asarray([r['rf_hz'] for r in records])
    data.receiver = np.asarray([r['receiver'] for r in records], int)
    data.channel = np.asarray([r['channel'] for r in records], int)
    data.margin = np.asarray([by_row[i]['refinement'].get('margin', by_row[i]['original_margin']) for i in original])
    data.group, data.original_rows = groups, original
    data.initial = np.zeros(6+len(data.numbers))
    data.initial[:2] = reference_coordinates(*ROOF)
    data.reference_time_s = 150.
    data.session_id = source['summary']['session_id']
    data.sources = {str(path):digest(path.read_bytes()) for path in (observations_path, refined_path, bank_path, bank_receipt_path, Path(__file__))}
    data.top_rows = np.asarray(refined['top_rows'], int)
    data.top_mask = np.isin(original, data.top_rows)
    data.origin_utc_ns = source['origin_utc_ns']
    if sum(data.top_mask) != len(np.unique(groups)):
        raise ValueError('top-one observations must cover each original passing window once')
    if top_only:
        data = view(data, data.top_mask)
        data.top_mask = np.ones(len(data.times), bool)
    return data
