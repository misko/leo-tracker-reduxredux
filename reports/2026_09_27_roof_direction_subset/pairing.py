"""Pure compatibility helpers: GLRT candidates are proxies, not satellite IDs."""
from __future__ import annotations
import math
import numpy as np

FRAME_S = 1 / 750
ALIAS_HZ = 1 / 4.4e-6
EPOCH_TOL_S = 2.2e-6
CFO_TOL_HZ = 10000.


def wrap(x, period):
    return x - round(x / period) * period


def passed(candidates):
    result = []; seen = set()
    for c in candidates:
        if not c.passed_fractional_margin_gate:
            continue
        key = (c.integer_epoch_sample + c.fractional_epoch_offset_samples,
               c.fractional_tracking_cfo_hz)
        if key not in seen:
            result.append(c); seen.add(key)
    return result


def differences(a, b, sample_rate_hz):
    dt = wrap((b.integer_epoch_sample + b.fractional_epoch_offset_samples
               - a.integer_epoch_sample - a.fractional_epoch_offset_samples) / sample_rate_hz, FRAME_S)
    df = wrap(b.fractional_tracking_cfo_hz - a.fractional_tracking_cfo_hz, ALIAS_HZ)
    return dt, df


def compatible(a, b, rate, bias):
    dt, df = differences(a, b, rate)
    return abs(dt) <= EPOCH_TOL_S and abs(wrap(df-bias, ALIAS_HZ)) <= CFO_TOL_HZ


def calibration_bias(pairs):
    values = [differences(a,b,rate)[1] for cs0,cs1,rate in pairs
              for a in passed(cs0) for b in passed(cs1)
              if abs(differences(a,b,rate)[0]) <= EPOCH_TOL_S]
    if not values:
        raise ValueError('no calibration epoch-compatible candidates')
    bins = np.arange(-ALIAS_HZ/2, ALIAS_HZ/2+5000, 5000)
    h, edges = np.histogram(values, bins=bins)
    i = int(np.argmax(h)); core = [v for v in values if edges[i] <= v < edges[i+1]]
    return dict(bias_hz=float(np.median(core)), epoch_compatible_pairs=len(values), modal_bin_pairs=len(core))


def probe_equal_bias(pairs, initial_bias):
    """Calibration-only robustness check; each eligible probe gets one vote."""
    votes=[]
    for cs0,cs1,rate in pairs:
        choices=[differences(a,b,rate) for a in passed(cs0) for b in passed(cs1)
                 if abs(differences(a,b,rate)[0]) <= EPOCH_TOL_S]
        if choices:
            _,df=min(choices,key=lambda q:(abs(wrap(q[1]-initial_bias,ALIAS_HZ)),abs(q[0])))
            if abs(wrap(df-initial_bias,ALIAS_HZ)) <= CFO_TOL_HZ:
                votes.append(df)
    return dict(bias_hz=float(np.median(votes)),probe_votes=len(votes)) if votes else None


def classify(cs0, cs1, rate, bias):
    a, b = passed(cs0), passed(cs1)
    if a and b:
        return 'both_compatible' if any(compatible(x,y,rate,bias) for x in a for y in b) else 'both_unmatched'
    return 'rx0_only' if a else 'rx1_only' if b else 'neither'


def counterpart(anchor, other_candidates, receiver_id, rate, bias):
    candidates = []
    for other in passed(other_candidates):
        a,b = (anchor, other) if receiver_id == 0 else (other, anchor)
        dt,df = differences(a,b,rate)
        if compatible(a,b,rate,bias):
            # Proximity chooses the counterpart, never its reception strength.
            candidates.append((abs(wrap(df-bias,ALIAS_HZ)), abs(dt), other.candidate_rank, other))
    candidates.sort(key=lambda x:x[:3])
    if not candidates:
        return dict(matched=False, compatible_candidate_count=0, log_margin_ratio_rx1_rx0=None)
    other = candidates[0][3]
    m0,m1 = (anchor.fractional_margin,other.fractional_margin) if receiver_id == 0 else (other.fractional_margin,anchor.fractional_margin)
    if min(m0,m1) <= 0:
        raise ValueError('non-positive passed-candidate margin')
    return dict(matched=True, compatible_candidate_count=len(candidates),
                counterpart_rank=other.candidate_rank,
                log_margin_ratio_rx1_rx0=math.log(m1/m0))


def provenance_key(source):
    return (source.source_group_id, source.source_sample_start,
            source.source_sample_end, source.support_center_utc_ns)
