"""Frozen cold solver on DS26 winners linked only from the start up to each deadline."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np

from check import MEMBERSHIP, OUTPUT, stream, wrap

sys.path.insert(0,str(OUTPUT.parent))
import cold_replay as cold


def winners(native):
    anchor = native["clock_anchor"]
    start = anchor["sample_counter"]
    before, after = (anchor[k]["realtime_ns"] for k in ("before","after"))
    src = native["source"]
    sample_rate = src["sample_rate_hz"]
    half_probe = src["probe_ms"]/2000.
    duration = (native["last_sample_counter"]-start)/sample_rate
    out = []
    for i,p in enumerate(src["probes"]):
        valid = [x for x in p["candidates"] if x["passed_fractional_margin_gate"] is True]
        if not valid:
            continue
        y = max(valid,key=lambda x:(x["fractional_margin"],-x["candidate_rank"]))["fractional_tracking_cfo_hz"]
        now = (p["valid_start_counter"]-start)/sample_rate + half_probe
        assert p["receiver_id"] in (0,1)
        out.append((i,1+p["receiver_id"],p["channel"],p["actual_rf_hz"],now,y))
    out.sort(key=lambda row:(row[4],row[1],row[2]))
    return out,dict(causal_cutoff_utc_ns=before,anchor_utc_ns=(before+after)//2,duration_s=duration),half_probe


def track_document(rows):
    owners, confirmations, evaluations, peak = stream(rows)
    tracks = defaultdict(list)
    for row in rows:
        if row[0] in owners:
            tracks[owners[row[0]]].append(row)
    record = dict(tracks=[],curved_indices=[])
    for _, group in sorted(tracks.items()):
        _,rx,ch,rf,_,_ = group[0]
        t = np.array([row[4] for row in group])
        y = np.array([row[5] for row in group])
        lifted = np.cumsum(np.r_[y[:1],np.array([wrap(x) for x in np.diff(y)])])
        x = t-t.mean()
        delta = lifted-lifted.mean()
        curved = (len(t)>=12 and np.ptp(t)>=20 and
                  np.sqrt(np.mean((delta-x*(x@delta)/max(x@x,1e-12))**2))>=250.)
        if curved:
            record["curved_indices"].append(len(record["tracks"]))
        record["tracks"].append(dict(times=t,values=lifted,receiver=rx,channel=ch,rf_hz=rf))
    info = dict(issued=len(owners),peak=peak,continuations=evaluations,fragments=len(tracks),
                curved=len(record["curved_indices"]), first_fragment_air_s=min((b for _,b in confirmations),default=None))
    return record,info


def at_deadline(case, rows, meta, half_probe, seconds):
    prefix = (meta["duration_s"] if seconds=="full" else float(seconds))
    block = [row for row in rows if row[4]+half_probe<=prefix+1e-8]
    start_wall, start_cpu = time.monotonic(), time.process_time()
    document, counts = track_document(block)
    track_cpu = time.process_time()
    bank, receipt = cold.build_bank(case, dict(meta,duration_s=prefix))
    bank_cpu = time.process_time()
    d = cold.descriptors(document,bank)
    result = dict(case=case,deadline=seconds,winners=len(block),**counts,bank=receipt)
    if d is None:
        result["arms"] = {arm:dict(status="no_curved_tracks") for arm in ("c0","fitted_c")}
    else:
        bias = cold.bias_vote(d)
        score,xy,winners,cost = cold.grid_vote(d,bias)
        selected = np.flatnonzero(cost < 12.)
        result["arms"] = {arm:cold.solve(d,selected,winners,bias,xy,fitted_c=arm=="fitted_c")
                          for arm in ("c0","fitted_c")}
        result["selected_satellites"] = d["ids"][selected,winners[selected]].tolist()
    result["time"] = dict(link_cpu_s=track_cpu-start_cpu,bank_cpu_s=bank_cpu-track_cpu,
                          rest_cpu_s=time.process_time()-bank_cpu,post_winner_wall_s=time.monotonic()-start_wall)
    return result
