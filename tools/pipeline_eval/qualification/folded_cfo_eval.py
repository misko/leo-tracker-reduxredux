"""Replay a new authenticated panel through folded-phase and all-bin hinted GLRT."""

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
from ..variants import differential_pilot as dp
from ..variants import folded_cfo as band
from ..variants import iq_stream
from . import differential_pilot_eval as timing
from . import hinted_glrt_trial, oracle_start
from .folded_cfo_build import WORK
from .full_v5_check import _from_native, _load_case, _probe, _sha
from .ordinary_front_eval import _payload
from .pilot_kernel_eval import _digest
from .scout_stage_figures import verify

REPORT = timing.SCREEN / "acquisition-frontier/folded-cfo"
MODES = ("hinted", "off", "phase", "sham")


def sources():
    return {
        str(p.relative_to(ROOT)): _sha(p)
        for p in (
            Path(__file__),
            Path(band.__file__),
            band.HEADER,
            Path(dp.__file__),
            Path(timing.__file__),
            Path(oracle_start.__file__),
            Path(hinted_glrt_trial.__file__),
            REPORT / "PROTOCOL.md",
        )
    }


def choose(after, available):
    later = [r for r in available if r["visit"] > after]
    visits, selected = set(), []
    for kind, group in (
        ("miss", "weak"),
        ("miss", "middle"),
        ("miss", "strong"),
        ("matched", None),
    ):
        match = next(
            (
                r
                for r in later
                if r["visit"] not in visits
                and r["kind"] == kind
                and (group is None or r["stratum"] == group)
            ),
            None,
        )
        if match is not None:
            selected.append(match)
            visits.add(match["visit"])
    return sorted(selected, key=lambda row: row["visit"])


def freeze(work):
    verify(timing.REPORT, "prediction-lock.json")
    original = timing.REPORT / "confirmation-lock.json"
    boundary = json.loads(original.read_bytes())["cases"]
    previous = {case: max(row["visit"] for row in selected) for case, selected in boundary.items()}
    control = oracle_start.EXISTING / "prediction-lock.json"
    library = json.loads(oracle_start.ABI.read_bytes())
    authority = json.loads(control.read_bytes())
    chosen = {}
    for case, after in previous.items():
        metadata = _load_case(case)
        era, wide = oracle_start.read_inputs(metadata, authority["files"], library)
        with patch.object(oracle_start, "choose", partial(choose, after)):
            selected = oracle_start.select(metadata, era, wide)["selected"]
        chosen[case] = selected
    path = work / "plan.json"
    save_json(
        path,
        dict(
            cases=chosen,
            starts_after=previous,
            sources=sources(),
            original_confirmation_sha256=_sha(original),
            wide_authority_sha256=_sha(control),
            build_lock_sha256=_sha(work / "build-lock.json"),
        ),
    )
    write(REPORT / "input-lock.json.gz", gzip.compress(path.read_bytes(), mtime=0))


def bind(work):
    data = (work / "plan.json").read_bytes()
    if data != gzip.decompress((REPORT / "input-lock.json.gz").read_bytes()):
        raise ValueError("Raw input plan differs from its sealed roster")
    document = json.loads(data)
    path = work / "build-lock.json"
    if document["sources"] != sources() or document["build_lock_sha256"] != _sha(path):
        raise ValueError("As-run code or local overlay changed")
    library = json.loads(path.read_bytes())
    if _sha(Path(library["library"])) != library["library_sha256"]:
        raise ValueError("Folded CFO overlay changed")
    original = json.loads(oracle_start.ABI.read_bytes())
    if any(_sha(Path(p)) != original["library_sha256"][k] for k, p in original["paths"].items()):
        raise ValueError("Pinned original detector changed")
    return document, original["paths"] | {"band": library["library"]}


def ports(stack, paths, edge):
    from leo.analysis.starlink.native_short_window import NativeShortWindow

    from .wide_regional_eval import templates

    stock, hinted = hinted_glrt_trial.bound(stack, paths, edge)
    mask = stack.enter_context(
        NativeShortWindow(
            paths["band"], *templates(dp.RATE, edge), sample_rate_hz=dp.RATE, fractional_epoch=True
        )
    )
    return stock, hinted, band.BandCall(mask)


def evaluate(iq, edge, loaded, order, lane=None):
    stock, hinted, mask = loaded
    phase_times, data = [], None
    for _ in range(4):
        cpu, wall = process_time_ns(), perf_counter_ns()
        data = band.score_and_phase(iq, edge)
        phase_times.append(dict(cpu_ns=process_time_ns() - cpu, wall_ns=perf_counter_ns() - wall))
    if [(row[0], row[1]) for row in data] != dp.scout(iq, edge):
        raise ValueError("The phase adapter altered the frozen raw timing score/rank")
    hints, freq = [], []
    for i, (ranks, _, hz) in enumerate(data):
        active = (lane is None or i == lane) and bool(ranks)
        hints.append(ranks[0] if active else None)
        freq.append(hz if active else None)
    rotated = [None if f is None else (f % band.PERIOD) - band.PERIOD / 2 for f in freq]
    modes = dict(off=[None, None], phase=freq, sham=rotated)
    science = {"stock": _payload(stock.analyze(iq))}
    numbers, unmasked_trace = {}, None
    clocks = {mode: [] for mode in MODES}
    for rep in range(4):
        shift = (order + rep) % len(MODES)
        for mode in MODES[shift:] + MODES[:shift]:
            cpu, wall = process_time_ns(), perf_counter_ns()
            if mode == "hinted":
                native, trace = hinted(iq, hints, timings=True)
                unmasked_trace = trace
            else:
                native, counts = mask(iq, hints, modes[mode])
                if numbers.setdefault(mode, counts) != counts:
                    raise ValueError("Unstable native coarse counts on identical IQ")
            clocks[mode].append(
                dict(
                    cpu_ns=process_time_ns() - cpu,
                    wall_ns=perf_counter_ns() - wall,
                    coarse_ms=[r["timings_ms"]["coarse"] for r in native["rows"]],
                    detector_ms=native["detector_cpu_ms"],
                )
            )
            payload = _payload(native)
            if encoded(science.setdefault(mode, payload)) != encoded(payload):
                raise ValueError("Same-IQ native payload changed")
    if encoded(science["hinted"]) != encoded(science["off"]):
        raise ValueError("Disabling the phase mask changed all-bin hinted native output")
    if lane is not None and any(
        encoded(p["rows"][1 - lane]) != encoded(science["stock"]["rows"][1 - lane])
        for p in science.values()
    ):
        raise ValueError("The unhinted receiver changed")
    return dict(
        raw=data,
        hints=hints,
        phases=modes,
        phase_times=phase_times,
        payloads=science,
        counts=numbers,
        timings=clocks,
        unmasked_trace=unmasked_trace,
    )


def controls(work, paths):
    receipts = {}
    for edge in ("lower", "upper"):
        dp.filters(edge)
        with ExitStack() as stack:
            loaded = ports(stack, paths, edge)
            for i, label in enumerate(
                ("zero", "noise", "cw", "strong", "weak", "one-frame", "edge")
            ):
                iq, target = timing.synthetic(edge, "strong" if label == "edge" else label)
                if label == "edge":
                    hz = 790_000 if edge == "lower" else -790_000
                    rotation = np.exp(
                        2j * np.pi * (hz - target["cfo_hz"]) * np.arange(dp.SAMPLES) / dp.RATE
                    )
                    z = (iq[..., 0] + 1j * iq[..., 1]) * rotation[:, None]
                    iq = np.rint(np.stack((z.real, z.imag), axis=-1)).astype("<i2")
                    target["cfo_hz"] = hz
                name = f"{edge}-{label}"
                receipts[name] = dict(
                    target=target,
                    iq_sha256=_digest(iq.tobytes()),
                    result=evaluate(iq, edge, loaded, i),
                )
                print(name, flush=True)
    write(work / "controls.json.gz", gzip.compress(encoded(receipts), mtime=0))


def replay(case, roster, paths, work):
    metadata = _load_case(case)
    edge = roster[0]["archive_probe"]["edge"]
    records = []
    dp.filters(edge)
    with ExitStack() as stack:
        loaded = ports(stack, paths, edge)
        for i, row in enumerate(roster):
            try:
                window = hinted_glrt_trial.load_selected(metadata, row)
            except iq_stream.IQReadError as error:
                records.append(dict(row, status="unavailable", reason=str(error)))
                continue
            if window.target["edge"] != edge:
                raise ValueError("The evaluated IQ uses another physical edge")
            lane = row["receiver"]
            result = evaluate(window.samples, edge, loaded, i, lane)
            result["probes"] = {
                mode: [
                    _probe(window, rx, (_from_native(j, c) for j, c in enumerate(p["candidates"])))
                    for rx, p in zip(window.receiver_ids, doc["rows"], strict=True)
                ]
                for mode, doc in result["payloads"].items()
            }
            if encoded(result["probes"]["stock"]) != encoded(row["baseline"]):
                raise ValueError("Stock raw endpoint differs from frozen complete wide")
            views = {
                mode: oracle_start.endpoints(
                    row["target"],
                    result["probes"][mode][lane],
                    result["payloads"][mode]["rows"][lane],
                )
                for mode in ("stock", "hinted", "phase", "sham")
            }
            records.append(dict(row, status="processed", outcomes=views, result=result))
            print(
                case,
                row["visit"],
                lane,
                row["kind"],
                [p["passes"] for p in views.values()],
                result["counts"]["phase"][lane],
                flush=True,
            )
    write(work / f"{case}.json.gz", gzip.compress(encoded(records), mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "synthetic", "replay"))
    parser.add_argument("--case", choices=timing.CASES)
    parser.add_argument("--work", type=Path, default=WORK)
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.work)
    else:
        plan, library = bind(args.work)
        if args.action == "synthetic":
            controls(args.work, library)
        elif args.case:
            replay(args.case, plan["cases"][args.case], library, args.work)
        else:
            parser.error("replay requires a frozen case")
