"""Reuse the sky estimator, clustering uncertainty across nearby recordings."""
import sys
from pathlib import Path
import numpy as np

BASELINE = Path(__file__).resolve().parent.parent/'2026_10_04_t1_at_v1_replication'
sys.path.insert(0, str(BASELINE))
from receiver_sky_model import prepare, kernel


def temporal_kernel(events, grid, capture_epochs, *, bootstrap=250, bandwidth_deg=10.):
    """Same scan-balanced point estimate; whole three-hour-block bootstrap.

    Do not relabel adjacent scans as independent evidence. The old encounter
    blocks and observation weights remain unchanged when aggregating scans.
    At least five temporal clusters are required for a displayed estimate.
    """
    data = prepare(events)
    blocks = [int(capture_epochs[s]) // (3*3600*10**9) for s in data['scan_names']]
    unique, inverse = np.unique(blocks, return_inverse=True)
    clustered = {**data, 'scan_names': list(unique), 'scan': inverse[data['scan']]}
    result = kernel(clustered, grid, bandwidth_deg, bootstrap=bootstrap)
    result['time_block_count'] = result.pop('scans')
    result['total_time_blocks'] = len(unique)
    result['total_scans'] = len(data['scan_names'])
    result['uncertainty_unit'] = 'Three-hour UTC capture blocks, not individual GLRT windows or neighboring scans.'
    return result
