"""Observe split-frame spectra and retrospectively compare sealed 20 ms factors."""

import argparse
from collections import Counter
from contextlib import ExitStack
import ctypes as ct
import gzip
from hashlib import sha256
from itertools import combinations
import json
from math import inf, remainder, sqrt
from pathlib import Path
from statistics import median
from time import thread_time_ns

import numpy as np

from tools.pipeline_eval.variants.experimental.receiver_benchmark import read_archive
from tools.pipeline_eval.variants.experimental.receiver_brackets import read_physical

from .fractional_reject_ceiling import ShortTrace, checked
from .mixed_aperture_receiver import NativePath, PILOT_SHA, StereoSchedule
from .scout_readout_trial import check_machine, factor_bytes
from .sparse_cold_input import BINDING, BINDING_SHA, RELEASE
from .split_spectrum_build import PRODUCTION_SHORT

HERE = Path(__file__).resolve().parent
MEASURED = HERE / "measurements"
PROTOCOL = HERE / "split-spectrum-protocol.md"
PINS = {
    "scout-readout": "5d1998cee0e16165f2c355059d28b4b96f2486cc9297e7c55d760d4784f34431",
}
WEAK_ARCHIVE = "0f025d0f5c80f5425a3c6fa90bc77a0e5628eb8cf7bc7ac7dab7fdd6c1d2e9d9"
FFT_SIZE = 512
BIN_HZ = 10e6 / (44 * FFT_SIZE)
PERIOD_HZ = FFT_SIZE * BIN_HZ
REPEATS = 3


class Spectra(ct.Structure):
    _fields_ = [
        *((key, ct.c_uint) for key in ("seen", "flags", "frames", "templates")),
        ("power", ((ct.c_double * FFT_SIZE) * 2) * 2),
    ]


def signed_bin(k):
    return (k + FFT_SIZE // 2) % FFT_SIZE - FFT_SIZE // 2


def spectral_peak(power):
    if power.shape != (FFT_SIZE,) or not np.all(np.isfinite(power)):
        raise ValueError("Malformed residual spectrum")
    k = int(np.argmax(power))
    strongest = float(power[k])
    if strongest <= 0 or np.ptp(power) <= 1e-12:
        return None
    current = np.arange(FFT_SIZE)
    left, right = np.roll(power, 1), np.roll(power, -1)
    separation = (current - k + FFT_SIZE // 2) % FFT_SIZE - FFT_SIZE // 2
    maxima = (power >= left) & (power >= right) & ((power > left) | (power > right))
    remote = power[maxima & (abs(separation) > 8)]
    distinct = float(remote.max()) if len(remote) else None
    offset = curvature = None
    if min(left[k], right[k]) > 0:
        a, b, c = np.log((left[k], strongest, right[k]))
        curvature = float(a - 2*b + c)
        if curvature < -np.finfo(float).eps:
            offset = float(np.clip(0.5*(a-c)/curvature, -0.5, 0.5))
    return dict(
        bin=signed_bin(k), score=strongest, curvature=curvature, sub_bin=offset,
        distinct_peak=distinct, ambiguous=distinct is not None and distinct >= .99*strongest,
    )


def disagreement(power):
    exact = [spectral_peak(v) for v in power[0]]
    control = [spectral_peak(v) for v in power[1]]
    result = dict(exact=exact, rolled=control, margins=[
        e["score"]-c["score"] if e is not None and c is not None else None
        for e, c in zip(exact, control, strict=True)
    ], bin_delta=None, signed_delta_hz=None, absolute_delta_hz=None, ambiguous=None)
    if all(p is not None for p in exact):
        even, odd = exact
        result["ambiguous"] = even["ambiguous"] or odd["ambiguous"]
        result["bin_delta"] = signed_bin(even["bin"]-odd["bin"])
        if even["sub_bin"] is not None and odd["sub_bin"] is not None:
            delta = remainder((result["bin_delta"] + even["sub_bin"]-odd["sub_bin"])
                              * BIN_HZ, PERIOD_HZ)
            result.update(signed_delta_hz=delta, absolute_delta_hz=abs(delta))
    return result


def resolution_control():
    """A 64-symbol rectangular aperture with the stock padded frequency grid."""
    result = {}
    for label, center in (("centered", 0), ("straddled", BIN_HZ/2)):
        freq = [center+35, center-35]
        waves = np.exp(2j*np.pi*np.outer(freq, np.arange(64))*44/10e6)
        spectra = abs(np.fft.fft(waves, n=FFT_SIZE))**2 / 64**2
        result[label] = disagreement(np.array([spectra, spectra]))
    return result


def bind_trace(lib):
    lib.split_spectrum_reset.argtypes = []
    lib.split_spectrum_reset.restype = None
    lib.split_spectrum_trace.argtypes = []
    lib.split_spectrum_trace.restype = ct.POINTER(Spectra)


def trace_lane(reference, traced, audit, iq, lane, center, visit):
    clocks = {}
    recorded = None
    for repeat in range(REPEATS):
        arms = (("stock", reference), ("trace", traced))
        for arm, engine in arms if (repeat+lane+visit) % 2 == 0 else arms[::-1]:
            if arm == "trace":
                started = thread_time_ns()
                traced.native.lib.split_spectrum_reset()
                reset_cpu = thread_time_ns() - started
            else:
                reset_cpu = 0
            values, (cpu, wall) = engine.run(iq, lane, center)
            clocks.setdefault(arm, []).append(dict(cpu_ns=cpu+reset_cpu, wall_ns=wall))
            if recorded is None:
                recorded = values
            if factor_bytes(values) != factor_bytes(recorded):
                raise ValueError("Split instrumentation changed a signed primary factor")
    measured, meta = audit.measure(iq, lane, center)
    if factor_bytes(measured) != factor_bytes(recorded):
        raise ValueError("Unmodified verifier flag entry differs from the primary route")
    evidence = traced.native.lib.split_spectrum_trace().contents
    flags = meta["stock"][0]["flags"] if meta["confirmed"] else None
    if ((evidence.flags if evidence.seen else None) != flags
            or evidence.templates != (2 if flags is not None and flags & 4 else 0)
            or evidence.frames != (8 if evidence.templates else 0)):
        raise ValueError("Fractional flags, template count or eight-origin geometry changed")
    metric, spent = None, 0
    if evidence.templates:
        started = thread_time_ns()
        metric = disagreement(np.ctypeslib.as_array(evidence.power))
        spent = thread_time_ns() - started
    return dict(factor=recorded[0] if recorded else None, flags=flags,
                frames=evidence.frames, metric=metric, rank_cpu_ns=spent, clocks=clocks)


def write(path, value):
    with path.open("xb") as target:
        target.write(gzip.compress((json.dumps(value, sort_keys=True, allow_nan=False)
                                    + "\n").encode(), mtime=0))


def observe(build, weak, output):
    machine = check_machine()
    record = json.loads(build.read_bytes())
    paths = {key: Path(record[key]) for key in ("control", "binary")}
    checked(paths["control"], PRODUCTION_SHORT)
    checked(paths["binary"], record["binary_sha256"])
    checked(BINDING, BINDING_SHA)
    checked(weak, WEAK_ARCHIVE)
    roster = dict(
        dense=list(read_physical(BINDING, Path("/srv/bulk"), 48)),
        weak=list(read_archive(weak, 18)),
    )
    if len(roster["dense"]) != 48 or len(roster["weak"]) != 18:
        raise ValueError("The bounded physical roster changed")
    data = {key: [] for key in roster}
    cadence = StereoSchedule(full_coverage=True)
    skipped = []
    with ExitStack() as close:
        engines = {}
        for edge, pin in PILOT_SHA.items():
            pilot = np.frombuffer(checked(RELEASE / "assets" / (edge+".f32"), pin), dtype="<f4")
            control, traced = [NativePath(p, pilot, "short_primary") for p in paths.values()]
            close.callback(control.close)
            close.callback(traced.close)
            bind_trace(traced.native.lib)
            engines[edge] = control, traced, ShortTrace(control)
        for cohort, visits in roster.items():
            for index, (row, iq) in enumerate(visits):
                acquisition, target, edge = row["acquisition"], row["target"], row["edge"]
                if cohort == "dense" and cadence.visit(edge, target, acquisition)[1] == "full":
                    skipped.append([row["key"], row["sha256"]])
                    continue
                center = target["rf_center_hz"] - target["lnb_lo_hz"] - acquisition["actual_if_center_hz"]
                for lane in (0, 1):
                    result = trace_lane(*engines[edge], iq, lane, center, index)
                    data[cohort].append(dict(
                        key=row["key"], visit=acquisition.get("global_visit", row.get("visit")),
                        start=acquisition["sample_start"], digest=row["sha256"], edge=edge,
                        lane=lane, center_hz=center, **result,
                    ))
    write(output, dict(
        data=data, skipped_dense_anchors=skipped, resolution=resolution_control(),
        build=record, machine=machine, protocol_sha256=sha256(PROTOCOL.read_bytes()).hexdigest(),
        dense_binding_sha256=BINDING_SHA, weak_archive_sha256=WEAK_ARCHIVE, repeats=REPEATS,
        observation_source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
    ))


def tau_b(xs, ys):
    pairs = list(zip(xs, ys, strict=True))
    numerator, nx, ny = 0, 0, 0
    for (a, b), (c, d) in combinations(pairs, 2):
        dx, dy = (a > c)-(a < c), (b > d)-(b < d)
        numerator += dx*dy
        nx += dx != 0
        ny += dy != 0
    return numerator/sqrt(nx*ny) if nx*ny else None


def qty(values):
    if not values:
        return dict(count=0)
    return dict(count=len(values), median=median(values), rms=sqrt(sum(x*x for x in values)/len(values)),
                maximum=max(values))


def quality(rows, metric):
    matches = [(x[metric], x["error_hz"]) for x in rows
               if x[metric] is not None and x["error_hz"] is not None]
    if not matches:
        return dict(count=0)
    cut = median(a for a, _ in matches)
    return dict(
        count=len(matches), median_metric=cut,
        tau_b=tau_b([a for a, _ in matches], [abs(b) for _, b in matches]),
        low=qty([b for a, b in matches if a <= cut]),
        high=qty([b for a, b in matches if a > cut]),
    )


def score(trace, pin, output):
    observed = json.loads(gzip.decompress(checked(trace, pin)))
    if sha256(PROTOCOL.read_bytes()).hexdigest() != observed["protocol_sha256"]:
        raise ValueError("Protocol changed after trace seal")
    prior = {key: json.loads(gzip.decompress(checked(MEASURED / (key+".json.gz"), digest)))
             for key, digest in PINS.items()}
    scored, stats = {}, {}
    for cohort, rows in observed["data"].items():
        released = {
            (row["key"], row["lane"], row["digest"]):
            next((f for f in row["released"] if f[0] == 0), None)
            for row in prior["scout-readout"]["groups"][cohort]["rows"]
        }
        cohort_rows = []
        by_state = Counter()
        for row in rows:
            control = released[row["key"], row["lane"], row["digest"]]
            short = row["factor"]
            state, timing, delta = "short_empty", None, None
            if short is not None:
                state = "full_rank_zero_absent"
                if control is not None:
                    timing = remainder(short[1]+short[2]-control[1]-control[2], 13333)
                    delta = short[3]-control[3]
                    state = "matched" if abs(timing) <= 2 and abs(delta) <= 250 else "different"
            metric = row["metric"] or {}
            margin = short[4]-short[5] if short else None
            by_state[state] += 1
            cohort_rows.append(dict(
                key=row["key"], lane=row["lane"], state=state, stock=control,
                timing_samples=timing, colocated_delta_hz=delta,
                error_hz=delta if state == "matched" else None,
                metric_hz=metric.get("absolute_delta_hz"),
                bin_delta=metric.get("bin_delta"), ambiguous=metric.get("ambiguous"),
                negative_margin=-margin if margin is not None else None,
            ))
        scored[cohort] = cohort_rows
        rankable = [r for r in cohort_rows if r["metric_hz"] is not None]
        stats[cohort] = dict(
            states=by_state, spectra=len(rankable),
            ambiguous=sum(bool(r["ambiguous"]) for r in rankable),
            same_integer_bin=sum(r["bin_delta"] == 0 for r in rankable),
            signed_cfo=qty([r["error_hz"] for r in cohort_rows if r["error_hz"] is not None]),
            absolute_cfo=qty([abs(r["error_hz"]) for r in cohort_rows if r["error_hz"] is not None]),
            metric=quality(cohort_rows, "metric_hz"), margin=quality(cohort_rows, "negative_margin"),
            cpu_per_lane_ns={arm: [sum(row["clocks"][arm][i]["cpu_ns"] for row in rows)/len(rows)
                                   for i in range(observed["repeats"])]
                             for arm in ("stock", "trace")},
            ranking_cpu_ns=qty([row["rank_cpu_ns"] for row in rows if row["rank_cpu_ns"]]),
        )
    write(output, dict(statistics=stats, rows=scored, trace_sha256=pin, outcome_archives=PINS))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    observed = modes.add_parser("observe")
    observed.add_argument("build", type=Path)
    observed.add_argument("weak", type=Path)
    observed.add_argument("output", type=Path)
    scored = modes.add_parser("score")
    scored.add_argument("trace", type=Path)
    scored.add_argument("pin")
    scored.add_argument("output", type=Path)
    args = vars(parser.parse_args())
    action = args.pop("mode")
    (observe if action == "observe" else score)(**args)
