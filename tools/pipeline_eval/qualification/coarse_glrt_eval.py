"""Qualify adjacent-epoch coarse GLRT on previously unscored saved IQ."""

import argparse
import gzip
from pathlib import Path
from unittest.mock import patch

import numpy as np

from ..__main__ import ROOT, encoded, local_output, write
from ..variants import iq_stream
from . import coarse_glrt_build, ordinary_front_build, ordinary_front_eval, ordinary_glrt_eval
from .full_v5_check import NATIVE_LIBRARY, PRODUCERS, _sha

REPORT = ROOT / "reports/2026_11_19_receiver_screening/integration/coarse-glrt"
METHOD = "coarse_glrt_triplet"
SCHEDULE = tuple((s, (19, 21, 24, 27)) for s in (4, 8, 12))
MODES = ("control", METHOD)
CHUNK_PREFIX = ordinary_glrt_eval.CHUNK_PREFIX


def sources():
    paths = (
        Path(__file__),
        Path(coarse_glrt_build.__file__),
        coarse_glrt_build.HEADER,
        Path(ordinary_front_build.__file__),
        Path(ordinary_front_eval.__file__),
        Path(ordinary_glrt_eval.__file__),
        Path(iq_stream.__file__),
        REPORT / "PROTOCOL.md",
        NATIVE_LIBRARY,
        ordinary_front_build.ARM_CONTROL / "leo-native-glrt-short-window",
    )
    return {p.name: _sha(p) for p in paths}


def controls(window, plant):
    missed = plant(window, ((1173, -197_125, 8),), 426301).samples
    weak = plant(window, ((997, -114_250, 128),), 426302).samples
    t = np.arange(len(weak)) / window.sample_rate_hz
    cw = 760 * np.exp(2j * np.pi * 150_000 * t) + 260 * np.exp(-2j * np.pi * 265_000 * t)
    tones = np.rint(np.stack((cw.real, cw.imag), axis=-1)).astype(np.int32)[:, None, :]
    interference = np.clip(weak.astype(np.int32) + tones, -32768, 32767).astype("<i2")
    return dict(subthreshold_plant=missed, cw_and_real_pilot=interference)


def replay(case, work, arch):
    extras = {}
    pending = {}
    plant = ordinary_front_eval._test_signal
    bench = ordinary_front_eval.benchmark

    def prepare_controls(window, *args):
        ordinary = plant(window, *args)
        pending.update(data=controls(window, plant), last=ordinary.samples)
        return ordinary

    def benchmark(samples, call, index, repeats):
        result = bench(samples, call, index, 5 if repeats == 3 else repeats)
        if samples is pending.get("last"):
            for name, data in pending["data"].items():
                extras[name] = dict(
                    bench(data, call, index, 1),
                    iq_sha256=ordinary_front_eval._digest(data.tobytes()),
                )
        return result

    with (
        patch.multiple(
            ordinary_front_eval,
            METHOD=METHOD,
            MODES=MODES,
            SCHEDULE=SCHEDULE,
            benchmark=benchmark,
            _test_signal=prepare_controls,
        ),
        patch.object(iq_stream, "MAX_CHUNK_PREFIX", CHUNK_PREFIX),
    ):
        receipt = ordinary_front_eval.replay(case, work, arch)
    receipt["controls"].update(extras)
    return dict(receipt, build_receipt_sha256=_sha(work / arch / "build-receipt.json"))


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--case", choices=PRODUCERS, required=True)
    args.add_argument("--arch", choices=("host", "arm"), required=True)
    args.add_argument("--work", required=True, type=Path)
    options = args.parse_args()
    frozen = sources()
    if (REPORT / "source-lock.json").read_bytes() != encoded(frozen) + b"\n":
        raise ValueError("Coarse trial differs from its pre-score lock")
    receipt = replay(options.case, local_output(options.work), options.arch)
    if frozen != sources():
        raise ValueError("Coarse trial source changed during scoring")
    path = REPORT / f"{options.case}-{options.arch}.json.gz"
    write(path, gzip.compress(encoded(receipt), mtime=0))


if __name__ == "__main__":
    main()
