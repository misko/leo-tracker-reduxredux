"""Run adjacent-symbol differential pilot timing on fixed authenticated raw visits."""

import argparse
import gzip
import json
import tracemalloc
from contextlib import ExitStack
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

import numpy as np

from ..__main__ import ROOT, encoded, save_json, write
from ..variants import differential_pilot as dp
from ..variants import frame_coherence, hinted_glrt, iq_stream
from . import frame_coherence_results, hinted_glrt_trial, oracle_start
from .frame_coherence_eval import CASES, sham
from .full_v5_check import _from_native, _load_case, _probe, _sha
from .pilot_kernel_eval import _digest

SCREEN = ROOT / "reports/2026_11_19_receiver_screening"
REPORT = SCREEN / "acquisition-frontier/differential-pilot"
PRIMARY = SCREEN / "track-recovery/frame-coherence"
WORK = Path("/var/tmp/leo-differential-pilot-20261119")
CONTROLS = ("zero", "noise", "cw", "strong", "weak", "one-frame", "alternate-sign")


def sources():
    from leo.analysis.starlink import templates

    paths = (
        Path(__file__),
        Path(dp.__file__),
        Path(frame_coherence.__file__),
        Path(frame_coherence_results.__file__),
        Path(templates.__file__),
        Path(hinted_glrt_trial.__file__),
        Path(hinted_glrt.__file__),
        hinted_glrt.HEADER,
        Path(iq_stream.__file__),
        REPORT / "PROTOCOL.md",
        oracle_start.ABI,
    )
    return {str(p.relative_to(ROOT)): _sha(p) for p in paths}


def freeze(work):
    name = "input-lock.json.gz"
    receipt = json.loads((PRIMARY / "prediction-lock.json").read_bytes())
    original = PRIMARY / name
    if _sha(original) != receipt["files"][name]:
        raise ValueError("Original 24-visit source changed")
    old = json.loads(gzip.decompress(original.read_bytes()))
    if set(old["cases"]) != set(CASES) or sum(map(len, old["cases"].values())) != 24:
        raise ValueError("Unexpected primary raw roster")
    work.mkdir(exist_ok=False)
    save_json(
        work / "plan.json",
        dict(
            cases=old["cases"],
            parent_sha256=_sha(original),
            sources=sources(),
        ),
    )
    write(REPORT / name, gzip.compress((work / "plan.json").read_bytes(), mtime=0))


def bind(work):
    raw = (work / "plan.json").read_bytes()
    if raw != gzip.decompress((REPORT / "input-lock.json.gz").read_bytes()):
        raise ValueError("The planned cohort changed")
    plan = json.loads(raw)
    if plan["sources"] != sources():
        raise ValueError("Detector code changed after cohort freeze")
    release = json.loads(oracle_start.ABI.read_bytes())
    if any(_sha(Path(p)) != release["library_sha256"][m] for m, p in release["paths"].items()):
        raise ValueError("Native hinted or wide release changed")
    return plan, release["paths"]


def measure(samples, edge, name, stock, hinted, order, receiver=None):
    times, seen = [], None
    for _ in range(4):
        cpu, wall = process_time_ns(), perf_counter_ns()
        result = dp.scout(samples, edge)
        times.append(dict(cpu_ns=process_time_ns() - cpu, wall_ns=perf_counter_ns() - wall))
        if seen is not None and seen != result:
            raise ValueError("Same raw input produced different differential ranks")
        seen = result
    centers = [p[0] for p in seen]
    null = [sham(c, f"{name}:{i}") for i, c in enumerate(centers)]
    hints = {
        key: [
            c[0] if c and (receiver is None or receiver == i) else None
            for i, c in enumerate(ranked)
        ]
        for key, ranked in (("causal", centers), ("sham", null))
    }
    native = hinted_glrt_trial.measure(samples, stock, hinted, hints, order, reps=1)
    return dict(
        centers=centers,
        scores=[p[1] for p in seen],
        sham_centers=null,
        scout_times=times,
        hint_options=hints,
        native=native,
    )


def synthetic(edge, name):
    hz, gain, sigma = {
        "zero": (0, 0, 0),
        "noise": (0, 0, 500),
        "cw": (688_125, 0, 0),
        "strong": (688_125, 640, 500),
        "weak": (193_450, 128, 500),
        "one-frame": (193_450, 640, 500),
        "alternate-sign": (688_125, 640, 500),
    }[name]
    hz = hz if edge == "lower" else -hz
    epoch = 735
    waves, _ = dp.phase_templates(edge)
    signal = np.zeros(dp.SAMPLES, dtype=np.complex128)
    for m, (residue, start) in enumerate(dp.STARTS[1:]):
        if name == "one-frame" and m != 7:
            continue
        begin = epoch + start
        n = min(dp.FRAME, dp.SAMPLES - begin)
        polarity = -1 if name == "alternate-sign" and m % 2 else 1
        signal[begin : begin + n] = waves[residue, :n] * (polarity * gain)
    if name == "cw":
        signal.fill(640)
    signal *= np.exp(2j * np.pi * hz * np.arange(dp.SAMPLES) / dp.RATE)
    seed = 53429 + CONTROLS.index(name) + (169 if edge == "upper" else 0)
    rng = np.random.default_rng(seed)
    signal = np.stack((signal.real, signal.imag), axis=-1)[:, None, :]
    iq = np.clip(np.rint(signal + rng.normal(0, sigma, (dp.SAMPLES, 2, 2))), -32768, 32767)
    return iq.astype("<i2"), dict(
        plant=bool(gain),
        epoch=epoch if gain else None,
        cfo_hz=hz,
        seed=seed,
        live_frames=(1 if name == "one-frame" else None),
    )


def controls(paths, work):
    results = {}
    for edge in ("lower", "upper"):
        dp.filters(edge)
        with ExitStack() as stack:
            stock, hinted = hinted_glrt_trial.bound(stack, paths, edge)
            for i, name in enumerate(CONTROLS):
                label = f"{edge}-{name}"
                iq, target = synthetic(edge, name)
                measurement = measure(iq, edge, label, stock, hinted, i)
                if name == "strong":
                    tracemalloc.start()
                    dp.scout(iq, edge)
                    _, peak = tracemalloc.get_traced_memory()
                    tracemalloc.stop()
                    measurement["allocator_peak_bytes"] = peak
                result = dict(
                    iq_sha256=_digest(iq.tobytes()), target=target, measurement=measurement
                )
                results[label] = result
                ranked = [list(z[:4]) for z in measurement["centers"]]
                print(label, ranked, flush=True)
    write(work / "controls.json.gz", gzip.compress(encoded(results), mtime=0))


def replay(case, planned, paths, work, suffix=""):
    outcome = []
    edge = planned[0]["archive_probe"]["edge"]
    dp.filters(edge)
    with ExitStack() as stack:
        stock, hinted = hinted_glrt_trial.bound(stack, paths, edge)
        for i, row in enumerate(planned):
            ident, visit, lane = row["case"], row["visit"], row["receiver"]
            try:
                window = hinted_glrt_trial.load_selected(case, row)
            except iq_stream.IQReadError as error:
                outcome.append(dict(row, status="unavailable", reason=str(error)))
                continue
            if window.target["edge"] != edge or row["archive_probe"]["edge"] != edge:
                raise ValueError("Templated edge differs from indexed capture edge")
            raw = measure(window.samples, edge, f"{ident}:{visit}", stock, hinted, i, lane)
            probes = {
                mode: [
                    _probe(
                        window,
                        receiver,
                        (_from_native(j, c) for j, c in enumerate(port["candidates"])),
                    )
                    for receiver, port in zip(window.receiver_ids, p["rows"], strict=True)
                ]
                for mode, p in raw["native"]["payloads"].items()
            }
            if encoded(probes["stock"]) != encoded(row["baseline"]):
                raise ValueError(f"{ident}/{visit} stock factors differ from the complete wide run")
            if any(
                encoded(p[1 - lane]) != encoded(probes["stock"][1 - lane]) for p in probes.values()
            ):
                raise ValueError(f"{ident}/{visit} unused physical lane changed")
            entry = dict(row, status="processed", measurement=raw, probes=probes)
            outcome.append(entry)
            scored = frame_coherence_results.score_real(entry)
            print(
                ident,
                visit,
                lane,
                row["kind"],
                scored["raw_4_2"],
                scored["raw_16_20"],
                scored["causal_physical_passes"],
                flush=True,
            )
    write(work / f"{case['id']}{suffix}.json.gz", gzip.compress(encoded(outcome), mtime=0))


def confirmation(work, plan, paths):
    members = {c: f"{c}.json.gz" for c in CASES}
    scores = [
        frame_coherence_results.score_real(row)
        for name in members.values()
        for row in frame_coherence_results.capture(work, name)
    ]
    retained = sum(r.get("causal_passes", False) for r in scores if r["kind"] == "matched")
    gained = sum(r.get("causal_passes", False) for r in scores if r["kind"] == "miss")
    if retained < 7 or gained < 2:
        raise ValueError("Primary panel did not meet the predeclared confirmation gate")

    def choose(available):
        available = [r for r in available if r["kind"] == "miss" and r["visit"] > after]
        if not available:
            return []
        first = available[0]
        later = [r for r in available[1:] if r["visit"] != first["visit"]]
        return (
            [first] + [next((r for r in later if r["stratum"] != first["stratum"]), later[0])]
            if later
            else [first]
        )

    confirmations = {}
    preexisting = oracle_start.EXISTING / "prediction-lock.json"
    authority = json.loads(preexisting.read_bytes())["files"]
    lib = json.loads(oracle_start.ABI.read_bytes())
    for ident in CASES:
        selected = plan["cases"][ident]
        after = max(r["visit"] for r in selected)
        case = _load_case(ident)
        archive, wide = oracle_start.read_inputs(case, authority, lib)
        with patch.object(oracle_start, "choose", choose):
            selected = oracle_start.select(case, archive, wide)["selected"]
        confirmations[ident] = selected
    name = "confirmation-lock.json"
    save_json(
        work / name,
        dict(
            cases=confirmations,
            authority_sha256=_sha(preexisting),
            primary={c: _sha(work / fn) for c, fn in members.items()},
        ),
    )
    for ident, selected in confirmations.items():
        if selected:
            replay(_load_case(ident), selected, paths, work, suffix="-confirmation")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "synthetic", "replay", "confirm"))
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--work", type=Path, default=WORK)
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.work)
    else:
        locked, libraries = bind(args.work)
        if args.action == "synthetic":
            controls(libraries, args.work)
        elif args.action == "confirm":
            confirmation(args.work, locked, libraries)
        elif args.case:
            replay(_load_case(args.case), locked["cases"][args.case], libraries, args.work)
        else:
            parser.error("replay requires a named frozen case")
