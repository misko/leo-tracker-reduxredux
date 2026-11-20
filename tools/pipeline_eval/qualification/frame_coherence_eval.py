"""Replay a metadata-frozen raw panel through the cross-frame scout and hinted ABI."""

import argparse
import gzip
import json
import tracemalloc
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns, process_time_ns

import numpy as np

from ..__main__ import ROOT, encoded, save_json, write
from ..variants import frame_coherence as fc
from ..variants import hinted_glrt, iq_stream
from . import hinted_glrt_trial, oracle_start
from .full_v5_check import _from_native, _load_case, _probe, _sha
from .pilot_kernel_eval import _digest

REPORT = ROOT / "reports/2026_11_19_receiver_screening/track-recovery/frame-coherence"
ORACLE = Path("/home/mouse9911/.cache/leo-oracle-start-20261119/input-lock.json")
WORK = Path("/var/tmp/leo-frame-coherence-20261119")
CASES = tuple(oracle_start.CASES)


def template_receipt():
    from leo.analysis.starlink import templates as t

    rows = {}
    waves = {}
    for edge in ("lower", "upper"):
        h = waves[edge] = t.qin_edge_pilot_frame(fc.RATE, edge)
        rolled = t.qin_edge_pilot_frame(fc.RATE, edge, symbol_roll=t.CONTROL_SYMBOL_ROLL)
        states = t.qin_edge_pilot_states(edge)
        assert h.shape == (fc.FRAME,) and states.shape == (300, 8)
        assert not np.array_equal(h, rolled)
        rows[edge] = dict(
            indices=t.qin_edge_pilot_indices(edge),
            states_sha256=_digest(states.tobytes()),
            template_sha256=t.template_sha256(h),
            rolled_sha256=t.template_sha256(rolled),
            active_nonzero=int(np.count_nonzero(h)),
        )
    a, b = waves.values()
    spacing = [fc.STARTS[k + 3] - fc.STARTS[k] for k in range(len(fc.STARTS) - 3)]
    assert all(s == fc.LAG for s in spacing) and t.FRAME_RATE_HZ == 750.0
    return dict(
        rate_hz=fc.RATE,
        lag=fc.LAG,
        first_frame_pair_starts=fc.STARTS,
        exact_three_frame_start_differences=spacing,
        rows=rows,
        lower_upper_same_phase_overlap=float(
            abs(np.vdot(a, b)) / (np.linalg.norm(a) * np.linalg.norm(b))
        ),
        source_sha256=_sha(Path(t.__file__)),
    )


def sources():
    paths = (
        Path(__file__),
        Path(fc.__file__),
        Path(hinted_glrt_trial.__file__),
        Path(hinted_glrt.__file__),
        hinted_glrt.HEADER,
        Path(iq_stream.__file__),
        REPORT / "PROTOCOL.md",
        oracle_start.ABI,
    )
    return {p.name: _sha(p) for p in paths}


def freeze(work):
    data = ORACLE.read_bytes()
    parent = json.loads(data)
    roster = {c: parent["cases"][c]["selected"] for c in CASES}
    if sum(map(len, roster.values())) > 24 or any(
        len(r) != len({a["visit"] for a in r}) for r in roster.values()
    ):
        raise ValueError("Inherited roster is outside its independent sample cap")
    for case, rows in roster.items():
        if any(r["archive_probe"]["edge"] != r["reference_wide_probe"]["edge"] for r in rows):
            raise ValueError(f"Compare raw IQ only on matched edge {case}")
    work.mkdir(exist_ok=False)
    receipt = template_receipt()
    save_json(REPORT / "templates.json", receipt)
    save_json(
        work / "plan.json",
        dict(
            cases=roster,
            oracle_sha256=sha256(data).hexdigest(),
            sources=sources(),
            template_receipt=receipt,
        ),
    )
    data = (work / "plan.json").read_bytes()
    write(REPORT / "input-lock.json.gz", gzip.compress(data, mtime=0))


def bind(work):
    plan = work / "plan.json"
    if plan.read_bytes() != gzip.decompress((REPORT / "input-lock.json.gz").read_bytes()):
        raise ValueError("Different scout work roster")
    locked = json.loads(plan.read_bytes())
    if locked["sources"] != sources() or encoded(locked["template_receipt"]) != encoded(
        template_receipt()
    ):
        raise ValueError("The frozen scout changed before numerical replay")
    release = json.loads(oracle_start.ABI.read_bytes())
    if any(_sha(Path(p)) != release["library_sha256"][m] for m, p in release["paths"].items()):
        raise ValueError("Existing native hint release changed")
    return locked, release


def sham(centers, identifier):
    seed = int.from_bytes(sha256(f"coherence-sham-v1:{identifier}".encode()).digest()[:8], "big")
    shift = fc.FRAME // 4 + seed % (fc.FRAME // 2)
    return [(x + shift) % fc.FRAME for x in centers]


def measure(samples, edge, name, stock, hinted, order):
    times, rows = [], None
    for _ in range(4):
        cpu, wall = process_time_ns(), perf_counter_ns()
        now = fc.scout(samples, edge)
        elapsed = dict(cpu_ns=process_time_ns() - cpu, wall_ns=perf_counter_ns() - wall)
        if rows is not None and rows != now:
            raise ValueError("Same IQ produced unstable raw scout ranks")
        rows = now
        times.append(elapsed)
    original = [r[0] for r in rows]
    negative = [sham(r, f"{name}:{i}") for i, r in enumerate(original)]
    hints = {
        "causal": [p[0] if p else None for p in original],
        "sham": [p[0] if p else None for p in negative],
    }
    outputs = hinted_glrt_trial.measure(samples, stock, hinted, hints, order, reps=1)
    return dict(
        centers=original,
        scores=[r[1] for r in rows],
        sham_centers=negative,
        scout_times=times,
        hint_options=hints,
        native=outputs,
    )


def real(ident, locked, release, work):
    case = _load_case(ident)
    outputs = []
    rows = locked["cases"][ident]
    with ExitStack() as stack:
        edge = rows[0]["archive_probe"]["edge"]
        fc.filters(edge)
        stock, hinted = hinted_glrt_trial.bound(stack, release["paths"], edge)
        for k, row in enumerate(rows):
            visit = row["visit"]
            try:
                window = hinted_glrt_trial.load_selected(case, row)
            except iq_stream.IQReadError as error:
                outputs.append(dict(row, status="unavailable", reason=str(error)))
                continue
            if window.target["edge"] != edge or row["archive_probe"]["edge"] != edge:
                raise ValueError("Raw edge, archived edge and synthesized proposer differ")
            result = measure(window.samples, edge, f"{ident}:{visit}", stock, hinted, k)
            probes = {
                m: [
                    _probe(
                        window, rx, (_from_native(i, c) for i, c in enumerate(lane["candidates"]))
                    )
                    for rx, lane in zip(window.receiver_ids, p["rows"], strict=True)
                ]
                for m, p in result["native"]["payloads"].items()
            }
            if encoded(probes["stock"]) != encoded(row["baseline"]):
                raise ValueError(f"{ident}/{visit} stock replay differs from the wide raw endpoint")
            outputs.append(dict(row, status="processed", measurement=result, probes=probes))
            print(ident, visit, row["receiver"], row["kind"], flush=True)
    write(work / f"{ident}.json.gz", gzip.compress(encoded(outputs), mtime=0))


def synthetic(edge, name):
    from leo.analysis.starlink.templates import qin_edge_pilot_frame

    presets = {
        "zero": (0, 0, 0),
        "noise": (0, 0, 500),
        "cw": (688_125, 0, 0),
        "strong": (688_125, 640, 500),
        "weak": (193_450, 128, 500),
        "alternate-sign": (688_125, 640, 500),
        "no-pair": (193_450, 640, 500),
    }
    hz, amplitude, sigma = presets[name]
    hz = hz if edge == "lower" else -hz
    epoch = 735
    wave = qin_edge_pilot_frame(fc.RATE, edge)
    signal = np.zeros(fc.SAMPLES, dtype=np.complex128)
    for m in range(2 if name == "no-pair" else 15):
        begin = epoch + round(m * fc.LAG / 3)
        n = min(len(wave), len(signal) - begin)
        sign = -1 if name == "alternate-sign" and m % 2 else 1
        signal[begin : begin + n] = sign * amplitude * wave[:n]
    if name == "cw":
        signal.fill(640)
    signal *= np.exp(2j * np.pi * hz * np.arange(fc.SAMPLES) / fc.RATE)
    seed = 53429 + list(presets).index(name) + (169 if edge == "upper" else 0)
    rng = np.random.default_rng(seed)
    clean = np.stack((signal.real, signal.imag), axis=-1)[:, None, :]
    raw = np.clip(np.rint(clean + rng.normal(0, sigma, (fc.SAMPLES, 2, 2))), -32768, 32767).astype(
        "<i2"
    )
    return raw, dict(
        plant=bool(amplitude), epoch=epoch if amplitude else None, cfo_hz=hz, seed=seed
    )


def controls(release, work):
    receipts = {}
    for edge in ("lower", "upper"):
        fc.filters(edge)
        with ExitStack() as stack:
            stock, hinted = hinted_glrt_trial.bound(stack, release["paths"], edge)
            names = ("zero", "noise", "cw", "strong", "weak", "alternate-sign", "no-pair")
            for k, name in enumerate(names):
                label = f"{edge}-{name}"
                iq, target = synthetic(edge, name)
                data = measure(iq, edge, label, stock, hinted, k)
                if name == "strong":
                    tracemalloc.start()
                    fc.scout(iq, edge)
                    _, peak = tracemalloc.get_traced_memory()
                    tracemalloc.stop()
                    data["allocator_peak_bytes"] = peak
                receipts[label] = dict(
                    iq_sha256=_digest(iq.tobytes()), target=target, measurement=data
                )
                print(label, flush=True)
    write(work / "controls.json.gz", gzip.compress(encoded(receipts), mtime=0))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("freeze", "replay", "synthetic"))
    p.add_argument("--case", choices=CASES)
    p.add_argument("--work", type=Path, default=WORK)
    a = p.parse_args()
    if a.action == "freeze":
        freeze(a.work)
    else:
        plan, release = bind(a.work)
        if a.action == "synthetic":
            controls(release, a.work)
        elif a.case:
            real(a.case, plan, release, a.work)
        else:
            p.error("replay requires a frozen case")
