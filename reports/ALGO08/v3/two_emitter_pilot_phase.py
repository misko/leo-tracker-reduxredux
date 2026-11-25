"""Use the installed two-factor cancellation ABI on fixed synthetic stereo cases."""

from collections import Counter
from hashlib import sha256
from math import remainder
from pathlib import Path
from time import perf_counter_ns, process_time_ns
import ctypes as ct
import json
import sys


RATE = 10_000_000
PERIOD = 40_000 / 3
ALIAS = RATE / 44
HZ_LIMIT = 1_000
BASELINE_M = 18
LIGHT_M_S = 299_792_458
RF_HZ = 11_800_000_000
EDGE = "upper"
RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
RECEIVER = Path("/opt/leo-algo08/algo08v3/payload/receiver.so")
PILOT = RELEASE / "assets/upper.f32"
PINS = {
    RECEIVER: "2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5",
    PILOT: "eef7b89526adb80fc64cd0be61f35b7cc5edceb3eb293d72066378e751b4467c",
    RELEASE / "tools/pipeline_eval/qualification/full_v5_check.py":
        "90861af36b6e383d61cf2eb06ca27006110c62d01db9622cbea906b9429b775a",
    RELEASE / "tools/pipeline_eval/qualification/single_scan_trial.py":
        "022fae8bb43a4a11f039063df20a869dbff89017721cebc69e8ae2bdef3858cb",
    RELEASE / "tools/pipeline_eval/qualification/single_scan_position.py":
        "690f2a72163b7bedb082999d0ee221607ab02270aace0a74b8703c14df00d432",
    RELEASE / "tools/pipeline_eval/qualification/waveform_site_model.py":
        "13289981023ca968bb56a75e039924051b71e4b62b0a3671c0e9778d5f97e32e",
    RELEASE / "src/leo/analysis/starlink/templates.py":
        "7ea6575d681d28796d74ebbd912e423082f7fd792bfc5aa6c42b1bb194788b51",
}

SWAP = ((1500, 220), (220, 1500))
# Case name, gains by emitter, B minus A CFO, planted B/RX2 minus A/RX1 epoch.
# A null epoch separation makes the two synthesized pilot atoms identical.
CASES = (
    ("empty", ((0, 0), (0, 0)), -98_300, 67),
    ("one_radio", ((1500, 0), (0, 0)), -98_300, 67),
    ("same_single", ((1500, 1500), (0, 0)), -98_300, 67),
    ("same_with_decoy", ((1500, 1500), (220, 220)), -98_300, 67),
    ("different_coincident", SWAP, -98_300, 0),
    ("different_separated", SWAP, -98_300, 67),
    ("different_near_cfo_alias", SWAP, ALIAS + 1_800, 37),
    ("different_exact_cfo_alias", SWAP, ALIAS, 0),
    ("identical_pilot_atoms", SWAP, 0, None),
)


def matched_winner(rows):
    return max((r for r in rows if r["passed_fractional_margin_gate"] is True),
               key=lambda r: (r["fractional_margin"], -r["candidate_rank"]), default=None)


def identity(winner, lane, truth, isolated):
    if winner is None:
        return "missing"
    field = "fractional_tracking_cfo_hz"
    hz = winner[field]
    hits = [name for name, model in truth.items()
            if model["gains"][lane] and abs(hz - model["cfo_hz"]) <= HZ_LIMIT]
    if len(hits) != 1:
        return "ambiguous" if hits else "unsupported"
    name, = hits
    alone = matched_winner(isolated[name][lane])
    if alone is None or abs(alone[field] - truth[name]["cfo_hz"]) > HZ_LIMIT:
        return "unsupported"
    if any(abs(row[field] - hz) <= HZ_LIMIT
           for key, lanes in isolated.items() if key != name for row in lanes[lane]
           if row["passed_fractional_margin_gate"] is True):
        return "ambiguous"
    return name


def signed_phase_pair(winners):
    if any(row is None for row in winners):
        return None
    a, b = winners
    epoch = ((b["integer_epoch_sample"] - a["integer_epoch_sample"])
             + (b["fractional_epoch_offset_samples"] - a["fractional_epoch_offset_samples"]))
    return remainder(epoch, PERIOD)


def planted(gains, delta_hz, gap):
    base = 3280.3
    a_shift = BASELINE_M * (2 / 3) * RATE / LIGHT_M_S
    b_shift = BASELINE_M * (-1 / 3) * RATE / LIGHT_M_S
    b_epoch = (base, base + a_shift) if gap is None else (base + gap - b_shift, base + gap)
    return {
        "A": dict(gains=gains[0], cfo_hz=31_400, epochs=(base, base + a_shift), carrier_phase_cycles=.117),
        "B": dict(gains=gains[1], cfo_hz=31_400 + delta_hz, epochs=b_epoch, carrier_phase_cycles=.283),
    }


def digest(payload):
    return sha256(payload).hexdigest()


def run():
    import numpy as np
    from tools.pipeline_eval.qualification import waveform_site_model as model
    from tools.pipeline_eval.qualification.blind_compact_run import Factor, Native, factor_candidate

    for path, pin in PINS.items():
        if digest(path.read_bytes()) != pin:
            raise ValueError(f"Installed input changed at {path}")
    modules = (model.make_scene, Native, Factor, factor_candidate, model.qin_edge_pilot_frame)
    for f in modules:
        source = Path(sys.modules[f.__module__].__file__).resolve()
        if source not in PINS:
            raise ValueError(f"Imported an unpinned implementation at {source}")
    if model.RATE != RATE or model.SAMPLES != RATE // 50:
        raise ValueError("Released waveform geometry changed")

    start = process_time_ns(), perf_counter_ns()
    frame = model.qin_edge_pilot_frame(RATE * model.OVER, EDGE).astype(np.complex64)
    asset = np.frombuffer(PILOT.read_bytes(), dtype="<f4")
    native = Native(RECEIVER, asset)
    call = native.lib.cancellation_factors
    call.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_double, ct.c_double, ct.POINTER(Factor)]
    call.restype = ct.c_int
    calls = clocks_cpu = clocks_wall = 0

    def detect(analog, noise):
        nonlocal calls, clocks_cpu, clocks_wall
        rounded = np.rint(np.stack((analog.real, analog.imag), axis=2) + noise)
        if np.max(np.abs(rounded)) >= 32767:
            raise ValueError("Unexpected synthetic ADC clipping")
        samples = np.ascontiguousarray(rounded, dtype="<i2")
        lanes = []
        for lane in (0, 1):
            vector = (Factor * 2)()
            begin = process_time_ns(), perf_counter_ns()
            count = call(native.ctx, samples.ctypes.data, lane, -800_000, 800_000, vector)
            clocks_cpu += process_time_ns() - begin[0]
            clocks_wall += perf_counter_ns() - begin[1]
            calls += 1
            if not 0 <= count <= 2 or calls > 54:
                raise ValueError("Unexpected native factor or work count")
            lanes.append([factor_candidate(f.rank, f.integer, status="complete", offset=f.offset, cfo=f.hz,
                                           exact=f.exact, control=f.control, margin=f.exact-f.control)
                          for f in vector[:count]])
        return dict(samples_sha256=digest(samples.tobytes()), lanes=lanes)

    results, counts = {}, Counter()
    time_s = model.INDEX / RATE
    try:
        for i, (name, gains, delta_hz, gap) in enumerate(CASES):
            truth = planted(gains, delta_hz, gap)
            noise = np.random.default_rng(3188 + i).normal(0, 265, (model.SAMPLES, 2, 2))
            signals = {}
            for key, tx in truth.items():
                if any(tx["gains"]):
                    carrier = np.exp(2j*np.pi*(time_s*tx["cfo_hz"]+tx["carrier_phase_cycles"]))
                    signals[key] = np.stack([
                        gain * model.pulse(frame, epoch, PERIOD) * carrier
                        for gain, epoch in zip(tx["gains"], tx["epochs"], strict=True)
                    ], axis=1)
            mixture = detect(sum(signals.values(), np.zeros((model.SAMPLES, 2), dtype=np.complex128)), noise)
            controls = {key: detect(signal, noise) for key, signal in signals.items()}
            isolation = {key: row["lanes"] for key, row in controls.items()}
            winners = [matched_winner(rows) for rows in mixture["lanes"]]
            identities = [identity(winner, lane, truth, isolation) for lane, winner in enumerate(winners)]
            order = [sorted(truth, key=lambda key: -truth[key]["gains"][lane]) for lane in (0, 1)]
            strongest = [a if truth[a]["gains"][lane] > truth[b]["gains"][lane] else None
                         for lane, (a, b) in enumerate(order)]
            phase = signed_phase_pair(winners)
            if phase is None:
                group = "one_winner" if any(winners) else "zero_winners"
            elif set(identities) <= truth.keys():
                group = "same_emitter" if len(set(identities)) == 1 else "different_emitters"
            else:
                group = "ambiguous_or_unsupported"
            counts[group] += 1
            agrees = None if phase is None else abs(phase) <= 2
            if agrees:
                counts[group + "_phase_agrees"] += 1
            results[name] = dict(noise_seed=3188+i, planted=truth, planted_strongest=strongest, mixed=mixture,
                                 isolated=controls, winner_ids=identities, group=group,
                                 wrapped_rx2_minus_rx1_samples=phase, phase_agrees=agrees)
    finally:
        native.close()
    return dict(schema="two-emitter-pilot-phase-v1", native_calls=calls, rf_hz=RF_HZ, edge=EDGE,
                sample_rate_hz=RATE, samples_per_visit=model.SAMPLES, baseline_m=BASELINE_M,
                library_and_source_sha256={str(k):v for k,v in PINS.items()},
                native_cpu_ns=clocks_cpu, native_wall_ns=clocks_wall, body_cpu_ns=process_time_ns()-start[0],
                body_wall_ns=perf_counter_ns()-start[1], counts=dict(counts), cases=results)


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, allow_nan=False))
