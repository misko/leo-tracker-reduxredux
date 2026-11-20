"""Test coherent pilot aliases and actual native pruning on held raw CI16."""

import argparse
import gzip
import json
from contextlib import ExitStack
from functools import partial
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

import numpy as np

from ..__main__ import ROOT, encoded, save_json, write
from ..variants import alias_rank as rank
from ..variants import differential_pilot, folded_cfo, iq_stream, pilot_carrier
from . import folded_cfo_build, folded_cfo_eval, hinted_glrt_trial, oracle_start
from .differential_pilot_eval import CASES, SCREEN, synthetic
from .full_v5_check import _from_native, _load_case, _probe, _sha
from .ordinary_front_eval import _payload
from .pilot_kernel_eval import _digest
from .scout_stage_figures import verify
from .wide_regional_eval import templates

REPORT = SCREEN / "support-preserving/alias-rank"
WORK = Path("/var/tmp/leo-alias-rank-20261119")
MODES = ("hinted", "off", "gated", "forced")


def bindings():
    sources = (
        Path(__file__),
        Path(rank.__file__),
        rank.HEADER,
        Path(folded_cfo.__file__),
        Path(pilot_carrier.__file__),
        Path(differential_pilot.__file__),
        Path(oracle_start.__file__),
        Path(hinted_glrt_trial.__file__),
        REPORT / "PROTOCOL.md",
    )
    return {str(f.relative_to(ROOT)): _sha(f) for f in sources}


def prepare(work):
    with patch.object(folded_cfo_build, "band", rank):
        folded_cfo_build.build(work)
    parent = folded_cfo_eval.REPORT
    verify(parent, "prediction-lock.json")
    old = json.loads(gzip.decompress((parent / "input-lock.json.gz").read_bytes()))
    binding = oracle_start.EXISTING / "prediction-lock.json"
    native = json.loads(oracle_start.ABI.read_bytes())
    authority = json.loads(binding.read_bytes())["files"]
    cases = {}
    for ident, previous in old["cases"].items():
        case = _load_case(ident)
        boundary = max(r["visit"] for r in previous)
        prod, wide = oracle_start.read_inputs(case, authority, native)
        with patch.object(oracle_start, "choose", partial(folded_cfo_eval.choose, boundary)):
            selected = oracle_start.select(case, prod, wide)["selected"]
        cases[ident] = dict(after=boundary, selected=selected)
    save_json(
        work / "plan.json",
        dict(
            cases=cases,
            sources=bindings(),
            build_sha256=_sha(work / "build-lock.json"),
            prior_sha256=_sha(parent / "prediction-lock.json"),
            wide_source_sha256=_sha(binding),
        ),
    )
    write(REPORT / "input-lock.json.gz", gzip.compress((work / "plan.json").read_bytes(), mtime=0))


def bind(work):
    raw = (work / "plan.json").read_bytes()
    if raw != gzip.decompress((REPORT / "input-lock.json.gz").read_bytes()):
        raise ValueError("Input plan changed")
    plan = json.loads(raw)
    built = work / "build-lock.json"
    if plan["sources"] != bindings() or plan["build_sha256"] != _sha(built):
        raise ValueError("Frozen scorer, rollout or source changed")
    candidate = json.loads(built.read_bytes())
    release = json.loads(oracle_start.ABI.read_bytes())
    if _sha(Path(candidate["library"])) != candidate["library_sha256"] or any(
        _sha(Path(f)) != release["library_sha256"][n] for n, f in release["paths"].items()
    ):
        raise ValueError("The pinned native release changed")
    return plan, release["paths"] | {"candidate": candidate["library"]}


def ports(stack, paths, edge):
    from leo.analysis.starlink.native_short_window import NativeShortWindow

    stock, hinted = hinted_glrt_trial.bound(stack, paths, edge)
    ctx = stack.enter_context(
        NativeShortWindow(
            paths["candidate"],
            *templates(differential_pilot.RATE, edge),
            sample_rate_hz=differential_pilot.RATE,
            fractional_epoch=True,
        )
    )
    return stock, hinted, rank.NativeMask(ctx)


def waveform(iq, edge, lane, data):
    proposals, _, phase = data
    if not proposals:
        return []
    start = process_time_ns()
    pair = pilot_carrier.products(iq, lane)
    setup_ns = process_time_ns() - start
    rows = []
    for i, e in enumerate(proposals[:4]):
        start = process_time_ns()
        simple = pilot_carrier.at_epoch(pair, edge, e)
        baseline_ns = process_time_ns() - start
        folded = phase if i == 0 else (simple["folded_hz"] if simple else None)
        samples, observed = [], None
        for _ in range(4 if i == 0 else 1):
            cpu, wall = process_time_ns(), perf_counter_ns()
            result = rank.assess(iq, lane, edge, e, folded)
            samples.append(dict(cpu_ns=process_time_ns() - cpu, wall_ns=perf_counter_ns() - wall))
            if observed is not None and observed != result:
                raise ValueError("Coherent alias scores changed on identical CI16")
            observed = result
        rows.append(
            dict(
                epoch=e,
                rank=i + 1,
                simple=simple,
                folded_hz=folded,
                coherent=observed,
                clocks=samples,
                baseline_setup_cpu_ns=setup_ns,
                baseline_cpu_ns=baseline_ns,
            )
        )
    return rows


def evaluate(iq, edge, loaded, order, lane=None):
    stock, hinted, mask = loaded
    tracker = []
    for _ in range(3):
        cpu, wall = process_time_ns(), perf_counter_ns()
        data = folded_cfo.score_and_phase(iq, edge)
        tracker.append(dict(cpu_ns=process_time_ns() - cpu, wall_ns=perf_counter_ns() - wall))
    estimates = [waveform(iq, edge, i, data[i]) if lane in (None, i) else [] for i in (0, 1)]
    hints = [p[0]["epoch"] if p else None for p in estimates]
    options = [p[0]["coherent"] if p else None for p in estimates]
    masks = dict(
        off=[None, None],
        gated=[rank.restrict(o) for o in options],
        forced=[rank.restrict(o, require_evidence=False) for o in options],
    )
    payloads = {"stock": _payload(stock.analyze(iq))}
    traces, native = {}, {m: [] for m in MODES}
    for rep in range(3):
        shift = (rep + order) % len(MODES)
        for mode in MODES[shift:] + MODES[:shift]:
            cpu, wall = process_time_ns(), perf_counter_ns()
            if mode == "hinted":
                result, trace = hinted(iq, hints, timings=True)
            else:
                result, trace = mask(iq, hints, masks[mode])
            timing = dict(
                cpu_ns=process_time_ns() - cpu,
                wall_ns=perf_counter_ns() - wall,
                coarse_ms=[r["timings_ms"]["coarse"] for r in result["rows"]],
            )
            native[mode].append(timing)
            payload = _payload(result)
            if encoded(payloads.setdefault(mode, payload)) != encoded(payload):
                raise ValueError("Paired native arm was not stable")
            if traces.setdefault(mode, trace) != trace:
                raise ValueError("Paired native cell counts were not stable")
    if encoded(payloads["hinted"]) != encoded(payloads["off"]):
        raise ValueError("Disabling alias masks changed the pinned unpruned hint")
    if lane is not None and any(
        encoded(d["rows"][1 - lane]) != encoded(payloads["stock"]["rows"][1 - lane])
        for d in payloads.values()
    ):
        raise ValueError("Unhinted native receiver differs from stock")
    return dict(
        payloads=payloads,
        traces=traces,
        timing=native,
        phase_times=tracker,
        estimates=estimates,
        masks=masks,
    )


def controls(work, libraries):
    output = {}
    for edge in ("lower", "upper"):
        differential_pilot.filters(edge)
        rank.reference(edge)
        with ExitStack() as stack:
            loaded = ports(stack, libraries, edge)
            for i, name in enumerate(
                ("zero", "noise", "cw", "strong", "weak", "one-frame", "edge")
            ):
                iq, target = synthetic(edge, "strong" if name == "edge" else name)
                if name == "edge":
                    hz = 790_000 if edge == "lower" else -790_000
                    twist = np.exp(
                        2j
                        * np.pi
                        * (hz - target["cfo_hz"])
                        * np.arange(rank.dp.SAMPLES)
                        / rank.dp.RATE
                    )
                    z = (iq[..., 0] + 1j * iq[..., 1]) * twist[:, None]
                    iq = np.rint(np.stack((z.real, z.imag), axis=-1)).astype("<i2")
                    target["cfo_hz"] = hz
                output[f"{edge}-{name}"] = dict(
                    iq_sha256=_digest(iq.tobytes()),
                    target=target,
                    result=evaluate(iq, edge, loaded, i),
                )
                print(edge, name, flush=True)
    write(work / "controls.json.gz", gzip.compress(encoded(output), mtime=0))


def replay(work, ident, planned, libraries):
    case = _load_case(ident)
    edge = planned[0]["archive_probe"]["edge"]
    differential_pilot.filters(edge)
    rank.reference(edge)
    output = []
    with ExitStack() as stack:
        loaded = ports(stack, libraries, edge)
        for i, row in enumerate(planned):
            try:
                window = hinted_glrt_trial.load_selected(case, row)
            except iq_stream.IQReadError as error:
                output.append(dict(row, status="unavailable", reason=str(error)))
                continue
            if window.target["edge"] != edge:
                raise ValueError("Wrong edge for the saved dual IQ")
            lane = row["receiver"]
            result = evaluate(window.samples, edge, loaded, i, lane)
            result["probes"] = {
                mode: [
                    _probe(window, rx, (_from_native(j, c) for j, c in enumerate(r["candidates"])))
                    for rx, r in zip(window.receiver_ids, d["rows"], strict=True)
                ]
                for mode, d in result["payloads"].items()
            }
            if encoded(result["probes"]["stock"]) != encoded(row["baseline"]):
                raise ValueError("Stock raw replay differs from the sealed wide factors")
            outcomes = {
                mode: oracle_start.endpoints(
                    row["target"], result["probes"][mode][lane], d["rows"][lane]
                )
                for mode, d in result["payloads"].items()
            }
            output.append(dict(row, status="processed", result=result, outcomes=outcomes))
            print(
                ident,
                row["visit"],
                lane,
                row["kind"],
                result["masks"]["gated"],
                [outcomes[m]["passes"] for m in ("stock", "hinted", "gated", "forced")],
                flush=True,
            )
    write(work / f"{ident}.json.gz", gzip.compress(encoded(output), mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "synthetic", "replay"))
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--work", type=Path, default=WORK)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.work)
    else:
        planned, libraries = bind(args.work)
        if args.action == "synthetic":
            controls(args.work, libraries)
        elif args.case:
            replay(args.work, args.case, planned["cases"][args.case]["selected"], libraries)
        else:
            parser.error("replay requires --case")
