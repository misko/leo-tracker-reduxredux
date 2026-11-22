"""Check generated detector degeneracies and the three archived wrapped CFO regressions."""

import argparse
from collections import defaultdict
import json
from pathlib import Path

import numpy as np

from . import receiver_cfo_restore_object as restore
from .receiver_frame_planes_composed import check_regression
from .receiver_spectral_vectors_trial import REFERENCE_SHA, measure
from leo.analysis.starlink.templates import qin_edge_pilot_frame
from tools.pipeline_eval.qualification.two_carrier_injections import mix, unit_wave
from tools.pipeline_eval.variants.experimental.receiver_benchmark import digest


CANDIDATE_SHA = "b63cf5b0b70e142a246fefd40b7ceb8ba2a24ecf0b4e8d0a05c6901cdef5dd94"
GROUPS = ("zero-ties", "one-count", "equal-strength-overlap")


def frontdoor_inputs():
    groups = defaultdict(list)
    rng = np.random.default_rng(53117)
    zeros = np.zeros((200_000, 2, 2), dtype="<i2")
    tiny = zeros.copy()
    tiny[::511, 0, 0] = 1
    tiny[211::517, 0, 1] = -1
    tiny[49::631, 1, 0] = -1
    tiny[307::601, 1, 1] = 1
    for index, edge in enumerate(("lower", "upper")):
        frame = qin_edge_pilot_frame(30_000_000, edge)
        overlaps = rng.integers(-75, 76, size=zeros.shape, dtype=np.int16)
        for lane in (0, 1):
            sign = 1 if lane == index else -1
            a, _ = unit_wave(frame, 39997, sign * 289_062.5, 72 + lane, False)
            b, _ = unit_wave(frame, 20000, -sign * 289_062.5, 93 + lane, False)
            overlaps, clipped = mix(overlaps, lane, [(a, 6), (b, 6)])
            if clipped:
                raise ValueError("Equal-amplitude synthetic pilots unexpectedly clipped")
        for label, samples in zip(GROUPS, (zeros, tiny, overlaps), strict=True):
            authority = digest(samples.tobytes())
            for center in (0., -50_000. if edge == "lower" else 50_000.):
                key = f"{edge}:{center:g}"
                for lane in (0, 1):
                    meta = dict(receiver_id=lane, channel=index + 1, actual_rf_hz=center,
                                valid_start_counter=0)
                    groups[label].append((key, key, edge, center, authority, meta, samples))
    return groups


def generated(reference, candidate, assets):
    restore.digest(reference, REFERENCE_SHA)
    restore.digest(candidate, CANDIDATE_SHA)
    results = measure(dict(reference=reference, packed=candidate), frontdoor_inputs(), assets)
    for name, batch in results["samples"].items():
        comparison = batch["paired"]["reference_to_packed"]["counts"]
        if comparison["lanes_changed"] or comparison["continuation_changed"]:
            raise ValueError(f"Generated real-front-door factors disagree on {name}")
    return dict(reference_sha256=REFERENCE_SHA, candidate_sha256=CANDIDATE_SHA, groups=results["samples"])


def regression(detector, bench, assets, pair, candidate, binding, bulk):
    return check_regression(detector, CANDIDATE_SHA, bench, assets, pair, candidate, binding, bulk)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for handler, fields in (
        (generated, ("reference", "candidate", "assets")),
        (regression, ("detector", "bench", "assets", "pair", "candidate", "binding", "bulk")),
    ):
        command = commands.add_parser(handler.__name__)
        command.set_defaults(handler=handler)
        for name in fields:
            command.add_argument(name, type=Path)
    args = vars(parser.parse_args())
    handler = args.pop("handler")
    args.pop("action")
    print(json.dumps(handler(**args), indent=2, allow_nan=False))
