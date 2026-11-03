"""Tighten UTC anchor bounds from known samples preceding host delivery.

Conditional on the capture's declared sample rate, the last sample in a
delivered window cannot occur after that window's delivery timestamp. These
are causal metadata bounds, not RF/GPS timing estimates or zero-latency claims.
"""

import numpy as np
from ds23_bracketed_clock import clock_interval


def delivery_interval(document,origin_utc_ns):
    original=clock_interval(document,origin_utc_ns)
    if 'source' not in document:
        return dict(original,original_interval=original,delivery_bound_used=False,
                    reason='per-window delivery/counter pairs absent from public adaptive tracking contract')
    source=document['source'];fs=source['sample_rate_hz'];anchor=document['clock_anchor']
    clocks=document['delivery_clocks']
    if fs<=0 or not clocks:raise ValueError('declared sample rate and delivery clocks required')
    host=[anchor['before'],anchor['after'],*clocks]
    offsets=[c['realtime_ns']-c['monotonic_ns'] for c in host]
    spread=max(offsets)-min(offsets)
    if spread>2_000_000_000:raise ValueError('unqualified host clock discontinuity')
    lower=(anchor['before']['monotonic_ns']+min(offsets)-origin_utc_ns)/1e9
    upper=original['upper_s'];witness=None
    for probe in source['probes']:
        visit=probe['visit_index']
        if not 0<=visit<len(clocks):raise ValueError('probe visit lacks matching delivery clock')
        count=(probe['probe_start_ms']+source['probe_ms'])*fs/1000
        if abs(count-round(count))>1e-6:raise ValueError('probe has fractional sample support')
        last=probe['valid_start_counter']+round(count)-1
        if last<anchor['sample_counter']:raise ValueError('probe precedes clock anchor')
        # Integer counter subtraction occurs before any UTC-to-seconds cast.
        elapsed=(last-anchor['sample_counter'])/fs
        delivery=clocks[visit]['monotonic_ns']+max(offsets)
        bound=(delivery-origin_utc_ns)/1e9-elapsed
        if bound<upper:
            upper=float(bound);witness=dict(visit=visit,last_sample_counter=last,
                host_delivery_monotonic_ns=clocks[visit]['monotonic_ns'],counter_elapsed_s=elapsed)
    if upper<lower:raise ValueError('declared clock rate and delivery chronology have no feasible UTC origin')
    return dict(lower_s=float(lower),upper_s=float(upper),width_s=float(upper-lower),
        origin_utc_ns=origin_utc_ns,original_interval=original,delivery_bound_used=witness is not None,
        witness=witness,host_clock_offset_spread_ns=spread,
        conditional_on_declared_sample_rate=True,no_minimum_network_latency_assumed=True,
        no_GPS_RF_fit_or_TLE_used=True)
