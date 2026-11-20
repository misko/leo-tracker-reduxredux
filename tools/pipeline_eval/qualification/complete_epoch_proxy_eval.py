"""Pair the full-geometry short-tap proxy against authenticated capture and wide."""

import argparse
import gzip
import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np

from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import complete_epoch_proxy
from . import thinned_capture_eval as parent

REPORT = ROOT / "reports/2026_11_19_receiver_screening/receiver-core/complete-epoch-proxy"
CASES = parent.CASES
original_controls = parent.controls


def source_lock():
    original_lock = parent.REPORT / "source-lock.json"
    lock = parent.source_lock()
    if lock != json.loads(original_lock.read_bytes()):
        raise ValueError("paired replay sources or fixed roster differ from the original freeze")
    files = (
        original_lock,
        Path(__file__),
        Path(complete_epoch_proxy.__file__),
        REPORT / "PROTOCOL.md",
    )
    return dict(lock, proxy_sources={str(p.relative_to(ROOT)): parent._sha(p) for p in files})


def signed_controls(window):
    from leo.analysis.starlink.templates import qin_edge_pilot_frame

    result = original_controls(window)
    shape = window.samples.shape
    rate = window.sample_rate_hz
    frame = qin_edge_pilot_frame(rate, window.target["edge"])
    noise = np.random.default_rng(502031).normal(0, 500, shape)
    raw = np.zeros(shape[0], dtype=np.complex128)
    for index in range(15):
        start = 731 + round(index * rate / 750)
        count = min(raw.size - start, len(frame))
        raw[start : start + count] = frame[:count]
    raw *= 600 * np.exp(-2j * np.pi * 720_000 * np.arange(raw.size) / rate)
    iq = np.stack((raw.real, raw.imag), axis=-1)[:, None, :]
    iq = np.clip(np.rint(iq + noise), -32768, 32767).astype("<i2")
    result["negative_high"] = replace(window, samples=iq, iq_sha256=parent._digest(iq.tobytes()))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("freeze", *CASES))
    args = parser.parse_args()
    target = REPORT / "source-lock.json"
    lock = source_lock()
    if args.stage == "freeze":
        if target.exists():
            raise ValueError("the complete-epoch proxy plan already has a source lock")
        save_json(target, lock)
        return
    if json.loads(target.read_bytes()) != lock:
        raise ValueError("complete-epoch proxy source or roster differs from preflight")
    with (
        patch.object(parent.thinned_capture, "propose", complete_epoch_proxy.propose),
        patch.object(parent, "controls", signed_controls),
    ):
        result = parent.replay(args.stage, lock)
    result["candidate_alias"] = {"thinned": "complete_epoch_proxy18"}
    write(local_output(REPORT / f"{args.stage}.json.gz"), gzip.compress(encoded(result), mtime=0))


if __name__ == "__main__":
    main()
