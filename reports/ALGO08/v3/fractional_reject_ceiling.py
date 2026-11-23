"""Audit the final fractional verifier's actual negative work."""

import argparse
from contextlib import ExitStack
import ctypes as ct
import gzip
from hashlib import sha256
import json
from math import isfinite, remainder
from pathlib import Path
from statistics import median
from time import thread_time_ns

import numpy as np

from tools.pipeline_eval.variants.experimental.receiver_benchmark import read_archive
from .directed_verifier_trial import Timing
from .eight_ms_primary_trial import PRODUCTION_SHORT, WEAK_ARCHIVE, encoded
from .mixed_aperture_receiver import NativePath, PILOT_SHA
from .scout_readout_trial import check_machine, factor_bytes


HERE = Path(__file__).resolve().parent
PINS = {
    "scout-readout.json.gz": "5d1998cee0e16165f2c355059d28b4b96f2486cc9297e7c55d760d4784f34431",
    "eight-ms-primary.json.gz": "a6b67123abe0a740b2843f08cc1cde7f603e6f18dd890ad15cc3b3243fc317b3",
}
WRAPPER_SHA = "6f21e36a55caa489f5992a3fbae6006c2af549c30753b7053fae926d0cefb48e"
COMPLETE, PASSED = 4, 2


def checked(path, expected):
    data = path.read_bytes()
    if sha256(data).hexdigest() != expected:
        raise ValueError(f"Unexpected source {path}")
    return data


def ledger(name):
    return json.loads(gzip.decompress(checked(HERE / "measurements" / name, PINS[name])))


def prefix_bounds(exact_maximum, exact_denominator, exact_rest_max,
                  rolled_maximum, rolled_denominator, rolled_rest_max):
    """Real-arithmetic bounds; a compiled gate would also need FP padding."""
    values = (exact_maximum, exact_denominator, exact_rest_max,
              rolled_maximum, rolled_denominator, rolled_rest_max)
    if any(not isfinite(x) or x < 0 for x in values):
        raise ValueError("Scores and energy bounds must be finite and nonnegative")
    if exact_maximum > exact_denominator or rolled_maximum > rolled_denominator:
        raise ValueError("Known maxima exceed their triangle bound")
    total_exact = exact_denominator + exact_rest_max
    total_rolled = rolled_denominator + rolled_rest_max
    upper = (exact_maximum + exact_rest_max) / total_exact if total_exact else 0
    lower = max(1/64, rolled_maximum/total_rolled) if rolled_denominator else 0
    return upper, lower


def summarize(rows):
    counts = dict(lanes=len(rows), primaries=0, residuals=0, examined=0, fractional=0, rejected=0)
    total, rejected_cpu = 0, 0
    for row in rows:
        for idx, state in enumerate(row["stock"]):
            if not state["examined"]:
                continue
            counts["primaries" if idx == 0 else "residuals"] += 1
            counts["examined"] += 1
            if state["flags"] & COMPLETE:
                counts["fractional"] += 1
                if not state["flags"] & PASSED:
                    counts["rejected"] += 1
                    rejected_cpu += row["verification_cpu_ns"]
        total += row["verification_cpu_ns"]
    return dict(**counts, verifier_cpu_ns=total, generous_oracle_cpu_ns=rejected_cpu)


class VerifierResult(ct.Structure):
    _fields_ = [
        *((name, ct.c_uint) for name in ("seed_index", "fine_winner", "conditioned_winner", "conditioned_bins",
                                         "flags", "stage_frames")),
        *((name, ct.c_double) for name in (
            "fine_residual_hz", "acquired_hz", "acquired_residual_hz", "acquire", "verify", "verify_control",
            "conditioned", "integer_exact", "integer_control", "integer_residual_hz", "offset_samples", "curvature",
            "fractional_exact", "fractional_control", "fractional_residual_hz")),
        ("exact_grid", ct.c_double*5), ("control_grid", ct.c_double*5),
        ("conditioned_grid", ct.c_double*42), ("conditioned_scores", ct.c_double*42),
    ]


class ShortTrace:
    def __init__(self, native):
        self.native = native
        ctx = ct.cast(native.native.ctx, ct.POINTER(ct.c_void_p))
        self.scout, self.verify = ctx[0], ctx[1]
        lib = native.native.lib
        bindings = (
            ("timing_first_detect", (ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_double, ct.c_double, ct.POINTER(Timing))),
            ("portable_verifier_load", (ct.c_void_p, ct.c_void_p, ct.c_uint)),
            ("portable_verifier_factor", (ct.c_void_p, ct.c_uint, ct.POINTER(VerifierResult))),
        )
        for name, arguments in bindings:
            call = getattr(lib, name)
            call.restype, call.argtypes = ct.c_int, arguments
            setattr(self, name, call)

    def measure(self, samples, rx, center):
        scout = Timing()
        if self.timing_first_detect(self.scout, samples.ctypes.data, rx, center-800000, center+800000, ct.byref(scout)):
            raise ValueError("Original scout call failed")
        if not scout.confirmation:
            return (), dict(stock=[], verification_cpu_ns=0, confirmed=False)
        if self.portable_verifier_load(self.verify, samples.ctypes.data, rx):
            raise ValueError("Original sample loading failed")
        epoch = round(scout.epoch) % 13333
        result = VerifierResult(acquired_hz=scout.hz)
        started = thread_time_ns()
        status = self.portable_verifier_factor(self.verify, epoch, ct.byref(result))
        verifier_ns = thread_time_ns()-started
        if status:
            raise ValueError("Original fractional verifier failed")
        candidates = ()
        if (result.flags & PASSED and abs(remainder(epoch+result.offset_samples-scout.epoch, 13333)) <= 2
                and abs(result.fractional_residual_hz) <= 1000):
            candidates = ((0, epoch, result.offset_samples, scout.hz+result.fractional_residual_hz,
                           result.fractional_exact, result.fractional_control),)
        trace = dict(examined=1, flags=result.flags, exact=result.fractional_exact, control=result.fractional_control)
        return candidates, dict(stock=[trace], verification_cpu_ns=verifier_ns, confirmed=True)


def weak_short(binary, archive, assets, weak):
    checked(binary, PRODUCTION_SHORT)
    checked(archive, WEAK_ARCHIVE)
    visits = list(read_archive(archive, 18))
    repeats = []
    with ExitStack() as paths:
        engines = {}
        for edge, pin in PILOT_SHA.items():
            pilot = np.frombuffer(checked(assets / (edge+".f32"), pin), dtype="<f4")
            engine = NativePath(binary, pilot, "short_primary")
            paths.callback(engine.close)
            engines[edge] = ShortTrace(engine)
        for repeat in range(3):
            traces = []
            for (visit, iq), prior in zip(visits, zip(weak["records"][::2], weak["records"][1::2], strict=True),
                                          strict=True):
                native = engines[visit["edge"]]
                center = (visit["target"]["rf_center_hz"] - visit["target"]["lnb_lo_hz"]
                          - visit["acquisition"]["actual_if_center_hz"])
                for rx, row in enumerate(prior):
                    if (row["sample_sha256"], row["rx"], row["id"]) != (visit["sha256"], rx, visit["key"]):
                        raise ValueError("Weak archive had different signed inputs")
                    factor = row["factors"]["12ms"]
                    expected = encoded({"candidates": [factor] if factor else []})
                    control, _ = native.native.run(iq, rx, center)
                    projected, trace = native.measure(iq, rx, center)
                    if factor_bytes(expected) != factor_bytes(control) or factor_bytes(control) != factor_bytes(projected):
                        raise ValueError("Trace changed the archived short primary factors")
                    traces.append(dict(**trace, rx=rx, key=visit["key"], digest=visit["sha256"]))
            repeats.append(traces)
    return dict(repeats=repeats, summary=[summarize(rows) for rows in repeats],
                complete_metadata_cpu_ns=median(sum(row["verification_cpu_ns"] for row in xs) for xs in repeats))


def run(binary, wrapper, archive, assets, out):
    host = check_machine()
    checked(wrapper, WRAPPER_SHA)
    short = ledger("eight-ms-primary.json.gz")
    groups = ledger("scout-readout.json.gz")["groups"]
    stock = {key: summarize(x["rows"]) for key, x in groups.items()}
    dense = short["dense"]["by_slot"]["short_primary"]
    empty = dense["lanes"]-dense["stock_selected"]
    result = dict(machine=host, stock=stock, short_dense=dict(issued=dense["lanes"], empty_upper_bound=empty),
                  short_weak=weak_short(binary, archive, assets, short["weak"]), pins=PINS, wrapper_sha256=WRAPPER_SHA,
                  short_sha256=PRODUCTION_SHORT, archive_sha256=WEAK_ARCHIVE, pilot_sha256=PILOT_SHA)
    with out.open("x") as target:
        json.dump(result, target, sort_keys=True, indent=2, allow_nan=False)
        target.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("binary", "wrapper", "archive", "assets", "out"):
        parser.add_argument(name, type=Path)
    run(**vars(parser.parse_args()))
