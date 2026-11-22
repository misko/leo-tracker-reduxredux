"""Screen each RF lane for repetition over three native pilot frames."""
import argparse
from contextlib import ExitStack
import hashlib
import json
from math import log
from pathlib import Path
from time import process_time_ns

import numpy as np
from .receiver_benchmark import Receiver, read_archive, read_simulated_prefix


PERIOD = 40000  # Three periods at 750 Hz on the native 10 MS/s clock.
STRIDE = 16
SAMPLES = PERIOD // STRIDE
NULL_THRESHOLD = -log(.05 / 10) / (SAMPLES - 1)


def coherence(samples, lane):
    iq = samples[:,lane,:].reshape(5,PERIOD,2)[:,::STRIDE,:]
    z = iq[:,:,0].astype(np.complex64)
    z.imag = iq[:,:,1]
    z -= z.mean(axis=1,keepdims=True)
    gram = z @ z.conj().T
    power = gram.diagonal().real.copy()
    if np.any(power <= 0):
        return None  # Degenerate input gets the full detector.
    ratios = np.abs(gram)**2 / (power[:,None] * power[None,:])
    np.fill_diagonal(ratios, 0.)
    return float(np.max(ratios))


def result(rows, threshold):
    skipped = [r for r in rows if r["score"] is not None and r["score"] < threshold]
    baseline = sum(r["native_ns"] for r in rows)
    cpu = baseline - sum(r["native_ns"] for r in skipped) + sum(r["screen_ns"] for r in rows)
    return dict(lanes=len(rows), factors=sum(r["factors"] for r in rows), skipped=len(skipped),
                lost_factors=sum(r["factors"] for r in skipped), full_native_cpu_s=baseline/1e9,
                screen_cpu_s=sum(r["screen_ns"] for r in rows)/1e9, estimated_native_ratio=cpu/baseline)


def trial(source, receiver_path, assets):
    receivers, rows = {}, []
    with ExitStack() as stack:
        for info, samples in source:
            edge = info["edge"]
            if edge not in receivers:
                asset = np.fromfile(assets/(edge+".f32"), dtype="<f4")
                receiver = Receiver(receiver_path, asset)
                stack.callback(receiver.close)
                receivers[edge] = receiver, asset
            t, a = info["target"], info["acquisition"]
            center = t["rf_center_hz"] - t["lnb_lo_hz"] - a["actual_if_center_hz"]
            for lane in (0,1):
                start = process_time_ns()
                score = coherence(samples,lane)
                elapsed = process_time_ns()-start
                factors, cpu, _ = receivers[edge][0].timed(samples,lane,center)
                rows.append(dict(case=info["case"], visit=info["visit"], lane=lane, score=score,
                                 factors=len(factors), native_ns=cpu, screen_ns=elapsed))
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("physical","separate","simulated","receiver","assets"):
        parser.add_argument(name,type=Path)
    args = parser.parse_args()
    if hashlib.sha256(args.receiver.read_bytes()).hexdigest() != "107909cc17e994950f7ffb2dce215114959565d5874122d958a6480132c242a5":
        raise ValueError("Expected the frozen research receiver")
    panels = {}
    for key, source in (("physical",read_archive(args.physical,80)), ("separate",read_archive(args.separate,64)),
                        ("simulated",read_simulated_prefix(args.simulated,40))):
        panels[key] = trial(source,args.receiver,args.assets)
    cutoff = min(r["score"] for r in panels["physical"] if r["factors"] and r["score"] is not None)
    summary = {}
    for key, rows in panels.items():
        oracle = min(r["score"] for r in rows if r["factors"] and r["score"] is not None)
        summary[key] = dict(prespecified=result(rows,NULL_THRESHOLD), development=result(rows,cutoff),
                            within_sample_oracle=result(rows,oracle), oracle_threshold=oracle)
    print(json.dumps(dict(null_threshold=NULL_THRESHOLD, development_threshold=cutoff, summary=summary, rows=panels),
                     allow_nan=False))
