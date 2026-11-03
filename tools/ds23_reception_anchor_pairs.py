"""Unique opposite-RX native peak from a curved anchor and frozen calibration."""

from ds23_frame_registration import wrap


def counterpart(anchor,targets,expected_offset_hz,fs,*,frequency_tolerance_hz=750.,epoch_tolerance_ns=80.):
    if fs<=0 or frequency_tolerance_hz<=0 or epoch_tolerance_ns<=0:raise ValueError('positive sample rate and fixed matching tolerances required')
    eligible=[p for p in targets if abs(float(wrap(p['epoch']-anchor['epoch'],fs/750)))/fs<=epoch_tolerance_ns*1e-9
        and abs(float(wrap(p['cfo']-anchor['cfo']-expected_offset_hz)))<=frequency_tolerance_hz]
    return eligible[0] if len(eligible)==1 else None
