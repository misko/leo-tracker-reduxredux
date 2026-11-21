"""One raw pass per recording to re-measure the fast receivers' admitted Doppler."""

import ctypes as ct
import json
import math
import subprocess
from pathlib import Path
from time import perf_counter, process_time

import numpy as np

from . import recording_to_v5
from .blind_compact_score import strongest
from .compact_position_diagnosis import FAST, HZ, OUT, WORK, panel, receipt
from .full_v5_check import _sha
from .reverse_glrt_report import read
from .timing_first_position import raw_windows
from .two_carrier_roster import WORK as ASSETS

SOURCE = Path(__file__).with_name("local_pilot_cfo.c")
LIB = WORK / "local-pilot-cfo.so"


def build():
    from .blind_compact_roster import seal

    WORK.mkdir(exist_ok=True, parents=True)
    cmd = [
        "cc",
        "-std=c11",
        "-O3",
        "-fPIC",
        "-shared",
        "-fopenmp-simd",
        "-ffp-contract=off",
        "-fno-math-errno",
        str(SOURCE),
        "-lm",
        "-o",
        str(LIB),
    ]
    subprocess.run(cmd, check=True)
    seal(
        OUT / "local-build.json",
        dict(command=cmd, source_sha256=_sha(SOURCE), binary_sha256=_sha(LIB)),
    )


def refiner(path):
    fn = ct.CDLL(str(path)).local_pilot_cfo
    fn.argtypes = [
        ct.c_void_p,
        ct.c_void_p,
        ct.c_int,
        ct.c_int,
        ct.c_double,
        ct.POINTER(ct.c_double),
    ]
    fn.restype = ct.c_int

    def fit(iq, pilot, lane, epoch, seed):
        if (
            iq.dtype != np.dtype("<i2")
            or iq.shape != (200000, 2, 2)
            or not iq.flags.c_contiguous
            or pilot.dtype != np.dtype("<f4")
            or pilot.shape != (26666,)
            or not pilot.flags.c_contiguous
        ):
            raise ValueError("expected a complete stereo I/Q window and one complex pilot frame")
        frequency = ct.c_double()
        status = fn(iq.ctypes.data, pilot.ctypes.data, lane, epoch, seed, ct.byref(frequency))
        if status not in (0, 1) or not math.isfinite(frequency.value):
            raise ValueError("invalid local frequency result")
        return frequency.value, status

    return fit


def pilots():
    result = {}
    hashes = read(panel.OUT / "build.json")["assets"]
    for edge, digest in hashes.items():
        path = ASSETS / "embedded" / (edge + ".f32")
        if _sha(path) != digest:
            raise ValueError("pilot differs from the raw panel")
        result[edge] = np.fromfile(path, dtype="<f4")[:26666]
    return result


def planted():
    from leo.analysis.starlink.templates import qin_edge_pilot_frame

    from .reverse_glrt_report import write_csv
    from .two_carrier_injections import mix, unit_wave

    fit = refiner(LIB)
    assets = pilots()
    rows = []
    for i, hz in enumerate([-393817.3, 274213.8, -58206.7, 619514.3]):
        rng = np.random.default_rng(100 + i)
        lane = i % 2
        edge = ("lower", "upper", "upper", "lower")[i]
        wave, t = unit_wave(
            qin_edge_pilot_frame(30000000, edge), 6012 + i * 2463, hz, 237 + i, False
        )
        noise = np.rint(rng.normal(scale=140, size=(200000, 2, 2))).astype("<i2")
        iq, _ = mix(noise, lane, [(wave, -8)])
        for offset in (-363, -107, 149, 398):
            f, ok = fit(iq, assets[edge], lane, round(t["epoch"]), hz + offset)
            rows.append(
                dict(
                    edge=edge,
                    lane=lane,
                    true_hz=hz,
                    seed_error_hz=offset,
                    refined_error_hz=f - hz,
                    interior=ok,
                )
            )
    if not all(r["interior"] and abs(r["refined_error_hz"]) < 30 for r in rows):
        raise ValueError("planted signed-frequency check failed")
    write_csv(OUT / "planted-frequency-check.csv", rows)


def stress():
    from leo.analysis.starlink.templates import qin_edge_pilot_frame

    from .reverse_glrt_report import write_csv
    from .two_carrier_injections import mix, unit_wave

    fit, assets = refiner(LIB), pilots()
    rows = []
    for i in range(8):
        edge = ("upper", "lower")[i % 2]
        lane = (i // 2) % 2
        code = qin_edge_pilot_frame(30000000, edge)
        clock = 2583 + i * 3363
        target = (-1) ** i * (314682.5 + 14049.2 * i)
        rng = np.random.default_rng(5601 + i)
        noise = np.rint(rng.normal(scale=140, size=(200000, 2, 2))).astype("<i2")
        for short in (False, True):
            wave, truth = unit_wave(code, clock, target, 7100 + i, short)
            for snr in (-8, -15, -22):
                iq, _ = mix(noise, lane, [(wave, snr)])
                for offset in (-320, 320):
                    f, ok = fit(iq, assets[edge], lane, round(truth["epoch"]), target + offset)
                    rows.append(
                        dict(
                            seed=i,
                            edge=edge,
                            lane=lane,
                            short=short,
                            injected_snr_db=snr,
                            seed_error_hz=offset,
                            refined_error_hz=f - target,
                            interior=ok,
                        )
                    )
    write_csv(OUT / "planted-noise-check.csv", rows)


def measure(case):
    target = WORK / case["id"] / "local-measurements.json"
    if target.is_file():
        return
    lock = read(OUT / "local-build.json")
    if _sha(LIB) != lock["binary_sha256"]:
        raise ValueError("changed local estimator")
    samples, old_hashes = {}, {}
    authority = None
    for method in FAST:
        r, folder = receipt(case, method)
        old_hashes[method] = r["native_sha256"]
        if authority is not None and authority != r["raw_authority"]:
            raise ValueError("conflicting recording identity")
        authority = r["raw_authority"]
        doc = read(folder / "native.json")
        input_hash = doc["source"]["input_manifest_sha256"]
        for probe in doc["source"]["probes"]:
            f = strongest(probe)
            if f:
                by = samples.setdefault(probe["visit_index"], {})
                key = (probe["receiver_id"], f["integer_epoch_sample"], f[HZ])
                by.setdefault(key, []).append(method)
    fit = refiner(LIB)
    rows = {m: [] for m in FAST}
    assets = pilots()
    iq_hashes = []
    cpu = 0.0
    start = perf_counter()
    calls = 0
    for i, w in enumerate(raw_windows(case)):
        if i != w.acquisition["global_visit"] or w.sample_rate_hz != 10000000:
            raise ValueError("unexpected hardware visit")
        iq_hashes.append(w.iq_sha256)
        for (lane, epoch, seed), methods in samples.pop(i, {}).items():
            t = process_time()
            hz, ok = fit(w.samples, assets[w.target["edge"]], lane, epoch, seed)
            cpu += process_time() - t
            calls += 1
            for m in methods:
                rows[m].append([i, lane, epoch, seed, hz, ok])
    if (
        samples
        or recording_to_v5.digest([input_hash, iq_hashes]) != authority
        or len(iq_hashes) != case["recording"]["window_count"]
    ):
        raise ValueError("raw recording digest differs")
    target.parent.mkdir(parents=True, exist_ok=True)
    recording_to_v5.save(
        target,
        dict(
            rows=rows,
            raw_authority=authority,
            input_hashes=old_hashes,
            calls=calls,
            cpu_s=cpu,
            raw_wall_s=perf_counter() - start,
            binary_sha256=_sha(LIB),
        ),
    )
    print(case["id"], "candidate remeasurements", calls, flush=True)


def update(case, method, document):
    target = WORK / case["id"] / "local-measurements.json"
    measurements = json.loads(target.read_bytes())
    baseline, _ = receipt(case, method)
    if (
        measurements["input_hashes"][method] != baseline["native_sha256"]
        or measurements["binary_sha256"] != read(OUT / "local-build.json")["binary_sha256"]
        or measurements["raw_authority"] != document["source"]["raw_recording_authority_digest"]
    ):
        raise ValueError("local measurements do not bind to native input")
    by = {
        (visit, lane): (epoch, seed, hz, ok)
        for visit, lane, epoch, seed, hz, ok in measurements["rows"][method]
    }
    changed = 0
    for p in document["source"]["probes"]:
        f = strongest(p)
        if f:
            e, s, h, ok = by.pop((p["visit_index"], p["receiver_id"]))
            if (
                e != f["integer_epoch_sample"]
                or s != f[HZ]
                or abs(h - s) > 750
                or (not ok and h != s)
            ):
                raise ValueError("local estimate changed waveform or recording")
            f[HZ] = h
            changed += h != s
    if by:
        raise ValueError("unmatched local measurement")
    return document, changed, _sha(target)


if __name__ == "__main__":
    build()
    planted()
    stress()
