"""Fixed, source-derived fine-search origin and native-CFO inverse response.

This is a research hypothesis, not certification of historical capture software.
The fine search inherits its lower boundary; it is not rounded to a zero grid.
"""

import numpy as np


def search_origin(sample_rate_hz, center_hz=0., step_hz=500.):
    if sample_rate_hz <= 0 or step_hz <= 0 or not np.isfinite(center_hz):
        raise ValueError('finite search geometry required')
    extent = 820312.5  # abs(edge_frequencies_hz(edge)).max(), both pilot edges
    width = min(800000., center_hz - extent + sample_rate_hz/2,
                sample_rate_hz/2 - center_hz - extent)
    if width <= 0:
        raise ValueError('pilot lies outside recorded bandwidth')
    return float((center_hz-width) % step_hz)


def correction(native_cfo_hz, response, origin_hz):
    f = np.asarray(native_cfo_hz, float)-origin_hz
    step = response['step_hz']
    center = np.floor(f/step+.5)*step
    actual = np.asarray(response['actual_offset_hz'], float)
    reported = np.asarray(response['reported_offset_hz'], float)
    if np.any(np.diff(reported) <= 0):
        raise ValueError('inverse response must be monotonic')
    return center+np.interp(f-center, reported, actual)-f


def corrected_track_values(track, observations_by_id, responses, edges, sample_rate_hz,
                           qualified_groups, recording_format):
    """Apply in canonical native coordinates, preserving original graph aliases."""
    lane = (track['receiver'], track['channel'])
    edge = edges[lane]
    group = f'{recording_format}/{sample_rate_hz}/{edge}'
    values = np.asarray(track['values'], float).copy()
    if group not in qualified_groups:
        return values
    native = np.asarray([observations_by_id[o]['measured_cfo_hz']
                         for o in track['observation_ids']])
    period = 1/4.4e-6
    if np.max(abs((native-values+period/2) % period-period/2)) > 1e-6:
        raise ValueError('native observations do not match original graph aliases')
    eligible = (abs(native)>1000) & (abs(native)<399000)
    delta = correction(native, responses[f'{sample_rate_hz}/{edge}'],
                       search_origin(sample_rate_hz))
    return values+np.where(eligible, delta, 0.)
