"""Verified report-local loader for frozen additional-scan ephemerides."""
import json,sys
import numpy as np
from benchmark import ROOT,OLD,PROTOCOL,digest


def verify_artifacts(directory,receipt):
    for name in ('expanded.npz','observations.npz'):
        if digest(directory/name)!=receipt['artifacts'][name]:
            raise ValueError(f'Additional-scan artifact changed: {name}')


def load_additional(session):
    if session not in PROTOCOL['additional_scans']:raise ValueError('Scan not in frozen additional cohort')
    directory=ROOT/'additional-scans'/session;receipt=json.loads((directory/'receipt.json').read_text())
    if receipt['session_id']!=session:raise ValueError('Receipt session mismatch')
    if receipt['protocol_sha256']!=digest(ROOT/'frozen/protocol.json'):raise ValueError('Protocol changed')
    verify_artifacts(directory,receipt)
    sys.path.insert(0,str(OLD))
    import exhaustive_subset
    from all_visible_bank import ExpandedScanData,ARRAY_NAMES,OBSERVATION_NAMES
    from types import SimpleNamespace
    with np.load(directory/'expanded.npz',allow_pickle=False) as a:
        arrays={k:a[k].copy() for k in ARRAY_NAMES}
        source=SimpleNamespace(**{k:a[k].copy() for k in OBSERVATION_NAMES},
                               original_rows=a['original_rows'].copy(),reference_time_s=150.)
    data=ExpandedScanData(source,arrays,receipt)
    with np.load(directory/'observations.npz',allow_pickle=False) as a:
        for stored,name in (('measured_hz','measured'),('times_s','times'),('group','group'),('receiver','receiver'),('channel','channel'),('rf_hz','rf')):
            if not np.array_equal(a[stored],getattr(data,name)):raise ValueError('Frozen observation mismatch')
        if len(a['canonical_rows'])!=receipt['denominator']:raise ValueError('Denominator mismatch')
    return data,receipt
