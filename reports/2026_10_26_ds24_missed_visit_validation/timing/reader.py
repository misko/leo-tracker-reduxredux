"""Public native source replay with sealed round1 candidate parity reuse."""
import hashlib
from pathlib import Path
import time
import numpy as np


def open_verified(slot,round1_window_outcome):
    from leo.storage.fast_scan import FastSegmentSource
    began=time.monotonic();authority=slot['raw_authority'];prior=round1_window_outcome
    if prior['request_id']!=slot['request_id'] or prior['status']!='complete':raise ValueError('round1 window receipt unavailable')
    receipt=prior['public_source_parity']
    if not receipt['full_reader_exhausted'] or not all(p['all_passed'] for p in receipt['parity'].values()):
        raise ValueError('round1 full paired parity prerequisite failed')
    if receipt['IQ_sha256']!=authority['index']['iq_sha256']:raise ValueError('round1 native IQ identity differs')
    index_digest='sha256:'+hashlib.sha256(Path(authority['index_path']).read_bytes()).hexdigest()
    if index_digest!=authority['index_sha256']:raise ValueError('public native index changed')
    port=FastSegmentSource(authority['segment'],start_sequence=authority['local_sequence'],stop_sequence=authority['local_sequence']+1)
    windows=tuple(port.windows())
    if len(windows)!=1:raise ValueError('bounded public reader did not exhaust exactly one native window')
    window=windows[0]
    if window.iq_sha256!=authority['index']['iq_sha256'] or window.acquisition!=authority['index']['acquisition'] or window.target!=authority['target']:
        raise ValueError('exhausted native window disagrees with frozen public authority')
    if window.sample_rate_hz!=authority['sample_rate_hz']:raise ValueError('native rate differs')
    # Runtime identity equality is a required pre-worker protocol check. This
    # reader does not silently invoke a fresh blind production_glrt acquisition.
    values=(window.samples[:,:,0]+1j*window.samples[:,:,1]).astype(np.complex64)
    return window,port.receiver_ids,values,dict(native_read_verify_seconds=time.monotonic()-began,
        full_reader_exhausted=True,source_IQ_sha256=window.iq_sha256,
        repeated_blind_acquisition_calls=0,round1_paired_candidate_parity_reused=True,
        prior_request_id=prior['request_id'],runtime_identity_check_owned_by_worker_protocol=True)
