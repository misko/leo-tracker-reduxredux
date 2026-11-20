"""Freeze and replay three-lag raw acquisition on real and planted pilot support."""

import argparse
import gzip
import os
import subprocess
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import center_union, iq_stream, multilag_search
from ..variants.differential_runtime_fft import FftScout
from . import differential_pilot_eval as fixtures
from . import hard_pilots_eval as original
from .center_union_gate import bind
from .full_v5_check import BULK, _load_case, _probe, _sha, compare_probes

REPORT = original.SCREEN / "pilot-influence/multilag-search"
WORK = Path("/var/tmp/leo-multilag-search-20261119")
FLAGS = ("-O3", "-ffp-contract=off", "-Wall", "-Wextra", "-Werror", "-fPIC", "-shared")
MODES = ("four", "five", "multilag")
SEGMENTS = (4, 9, 13)
SYNTHETIC = ("zero", "noise", "cw", "weak", "strong", "one-frame")


def build(work):
    work.mkdir(parents=True, exist_ok=True)
    src = work / "multilag-scout.c"
    lib = work / "libmultilag-scout.so"
    if lib.exists():
        raise FileExistsError("choose a new scratch directory for a new source build")
    src.write_text(multilag_search.overlay(multilag_search.SOURCE.read_text()))
    command = ["/usr/bin/gcc", *FLAGS, str(src), "-lfftw3f", "-lm", "-o", str(lib)]
    subprocess.run(command, check=True, env=dict(os.environ, TMPDIR=str(work)))
    versions = subprocess.check_output([command[0], "--version"], text=True).splitlines()[0]
    return dict(
        path=str(lib),
        sha256=_sha(lib),
        generated_source_sha256=_sha(src),
        compiler=versions,
        compiler_sha256=_sha(Path(command[0])),
        command=command,
    )


def rank(ident, segment, visit, rx):
    return sha256(f"multilag-hold-v1:{ident}:{segment}:{visit}:{rx}".encode()).hexdigest()


def candidate_holdout(ident):
    case = _load_case(ident)
    docs, sources = original.resolve(ident, case)
    masks = {}
    for segment in SEGMENTS:
        if segment < len(case["recording"]["segments"]):
            note = dict(
                case,
                recording=dict(
                    case["recording"], segments=[case["recording"]["segments"][segment]]
                ),
            )
            masks.update(
                {v: dict(meta, segment=segment) for v, meta in original.prefix(note).items()}
            )
    modes = ("capture", "four", "five")
    roles = {role: {} for role in modes}
    for role in modes:
        if original.support(docs[role]) != original.support(docs["capture"]):
            raise ValueError(f"{ident} held sources do not have a common capture clock")
        for probe in docs[role]["source"]["probes"]:
            visit = probe["visit_index"]
            if visit in masks:
                roles[role].setdefault(visit, []).append(probe)
    wanted = ("miss",) if ident in original.HARD else ("retained", "negative")
    eligible = {key: [] for key in wanted}
    for visit, operators in roles["capture"].items():
        four, five = [roles[k][visit] for k in ("four", "five")]
        truth = masks[visit]
        if len(operators) != 2 or [p["receiver_id"] for p in operators] != [0, 1]:
            raise ValueError(f"{ident} held visit lacks both physical receivers")
        raw = dict(truth, visit=visit, edge=operators[0]["edge"])
        any_gate = False
        for rx, (a, b, c) in enumerate(zip(operators, four, five, strict=True)):
            if not original.metadata(a) == original.metadata(b) == original.metadata(c) or (
                a["valid_start_counter"] != truth["counter"]
            ):
                raise ValueError(f"{ident} held raw support differs from the archived factors")
            gate_candidates = [original.factor_cross.winner(p["candidates"]) for p in (a, b, c)]
            any_gate |= any(k is not None for k in gate_candidates)
            if gate_candidates[0] is None:
                continue
            target = a["candidates"][gate_candidates[0]]
            vs = [original.classify(target, p["candidates"]) for p in (b, c)]
            if "miss" in eligible and all(p["category"] != "physical_gated" for p in vs):
                eligible["miss"].append(dict(raw, rx=rx, target=target))
            if "retained" in eligible and all(p["actual_winner_matches"] for p in vs):
                eligible["retained"].append(dict(raw, rx=rx, target=target))
        if "negative" in eligible and not any_gate:
            eligible["negative"].append(dict(raw, rx=0, target=None))
    selected, attempted, seen = [], [], set()
    for kind, options in eligible.items():
        ordered = sorted(options, key=lambda p: rank(ident, p["segment"], p["visit"], p["rx"]))
        chosen = next((option for option in ordered if option["visit"] not in seen), None)
        attempted.append(
            dict(case=ident, kind=kind, eligible=len(options), available=chosen is not None)
        )
        if chosen:
            visit = chosen["visit"]
            selected.append(
                dict(
                    chosen,
                    case=ident,
                    cohort="held",
                    kind=kind,
                    archive={k: roles[k][visit] for k in modes},
                )
            )
            seen.add(visit)
    return dict(sources=sources, availability=attempted), selected


def freeze(work):
    seal = original.REPORT / "evidence-lock.json"
    parent = whole_iq.checked(
        original.REPORT / "source-lock.json", whole_iq.read(seal)["files"]["source-lock.json"]
    )
    lock = whole_iq.read(parent)
    paths = (
        Path(__file__),
        Path(multilag_search.__file__),
        multilag_search.SOURCE,
        Path(original.__file__),
        Path(fixtures.__file__),
        REPORT / "PROTOCOL.md",
        seal,
        parent,
    )
    raster, sources = [], {}
    for case, info in lock["cases"].items():
        raster.extend(
            dict(
                p,
                segment=0,
                cohort="primary",
                case=case,
                kind="miss" if case in original.HARD else "retained",
                archive={
                    role: records[str(p["visit"])] for role, records in info["archived"].items()
                },
            )
            for p in info["selected"]
        )
    for ident in (*original.HARD, *original.CONTROLS):
        sources[ident], panels = candidate_holdout(ident)
        raster.extend(panels)
    if len(raster) != len({(r["case"], r["visit"]) for r in raster}):
        raise ValueError("duplicate waveform between locked sets")
    print(
        [(r["cohort"], r["case"], r["segment"], r["visit"], r["kind"]) for r in raster], flush=True
    )
    return dict(
        windows=raster,
        held=sources,
        detectors=lock["detectors"],
        multilag=build(work),
        files={str(p.relative_to(ROOT)): _sha(p) for p in paths},
    )


def measured(sample, calls, index, repeats):
    payloads, details = {}, {}
    times = {role: [] for role in MODES}
    for rep in range(repeats):
        slot = (index + rep) % len(MODES)
        for mode in MODES[slot:] + MODES[:slot]:
            wall, cpu = perf_counter_ns(), process_time_ns()
            data, info, scout_ns = calls[mode](sample)
            times[mode].append(
                dict(
                    wall_ms=(perf_counter_ns() - wall) / 1e6,
                    cpu_ms=(process_time_ns() - cpu) / 1e6,
                    scout_cpu_ms=scout_ns / 1e6,
                )
            )
            if encoded(data) != encoded(
                payloads.setdefault(mode, data)
            ) or info != details.setdefault(mode, info):
                raise ValueError("repeat changed native output or timing regions")
    for a, b in zip(details["five"]["lanes"], details["multilag"]["lanes"], strict=True):
        if a["ordinary"] != b["ordinary"] or a["stock_peak_keys"] != b["stock_peak_keys"]:
            raise ValueError("new admission changed original stock centers or pre-top-eight keys")
    return payloads, details, times


def runner(stack, paths, edge):
    native = bind(
        stack, dict(stock=paths["control"], hinted=paths["control"], union=paths["candidate"]), edge
    )
    union = center_union.UnionCall(native["union"])
    released = stack.enter_context(FftScout(paths["scout"], edge))
    multi = stack.enter_context(multilag_search.MultilagScout(paths["multilag"], edge))

    def timed_hint(scout):
        def call(sample):
            start = process_time_ns()
            hints = tuple(r[0] if r else None for r, _ in scout(sample, edge))
            scout_time = process_time_ns() - start
            payload, trace = union(sample, hints)
            return payload, dict(hints=hints, lanes=trace), scout_time

        return call

    return dict(
        four=lambda sample: (native["stock"].analyze(sample), {}, 0),
        five=timed_hint(released),
        multilag=timed_hint(multi),
    )


def replay(lock):
    for path, digest in lock["files"].items():
        whole_iq.checked(ROOT / path, digest)
    paths = {
        k: str(whole_iq.checked(Path(v["path"]), v["sha256"]))
        for k, v in dict(lock["detectors"], multilag=lock["multilag"]).items()
    }
    rows = []
    for edge in ("lower", "upper"):
        with ExitStack() as stack:
            calls = runner(stack, paths, edge)
            for name in SYNTHETIC:
                sample, plant = fixtures.synthetic(edge, name)
                values, trace, time = measured(sample, calls, len(rows), 1)
                truth = (
                    dict(
                        integer_epoch_sample=plant["epoch"],
                        fractional_epoch_offset_samples=0.0,
                        **{original.CFO: plant["cfo_hz"]},
                    )
                    if plant["plant"]
                    else None
                )
                rows.append(
                    dict(
                        cohort="synthetic",
                        edge=edge,
                        kind=name,
                        case=None,
                        iq_sha256=iq_stream._digest(sample.tobytes()),
                        flags=counts(values),
                        time=time,
                        matches={
                            role: [original.classify(truth, p) for p in original.projections(v)]
                            for role, v in values.items()
                        }
                        if truth
                        else {},
                        trace=trace,
                    )
                )
            for selected in [r for r in lock["windows"] if r["edge"] == edge]:
                case = _load_case(selected["case"])
                loc = case["recording"]["segments"][selected["segment"]]
                public = {
                    k: selected[k]
                    for k in (
                        "case",
                        "edge",
                        "cohort",
                        "kind",
                        "visit",
                        "rx",
                        "iq_sha256",
                        "segment",
                    )
                }
                try:
                    with patch.object(iq_stream, "MAX_CHUNK_PREFIX", original.MAX_PREFIX):
                        (w,) = iq_stream.load_windows(
                            dict(
                                recording_path=str(BULK / loc["path"]),
                                recording_sha256="sha256:" + loc["sha256"],
                            ),
                            (selected["sequence"],),
                        )
                except iq_stream.IQReadError as error:
                    rows.append(dict(public, status="unavailable", detail=str(error)))
                    continue
                if (
                    w.iq_sha256,
                    w.acquisition["sample_start"],
                    w.acquisition["global_visit"],
                    w.target["edge"],
                ) != (selected["iq_sha256"], selected["counter"], selected["visit"], edge):
                    raise ValueError("authentic decoded waveform differs from frozen visits")
                values, trace, time = measured(w.samples, calls, len(rows), 3)
                probes = {
                    role: [_probe(w, i, p) for i, p in enumerate(original.projections(v))]
                    for role, v in values.items()
                }
                for mode in ("four", "five"):
                    if encoded(probes[mode]) != encoded(selected["archive"][mode]):
                        raise ValueError(
                            "installed control does not reproduce its own released factor bytes"
                        )
                target = selected["target"]
                rx = selected["rx"]
                matches = (
                    {k: [original.classify(target, v[rx]["candidates"])] for k, v in probes.items()}
                    if target
                    else {}
                )
                compared = {
                    m: [
                        compare_probes(a, b, w.sample_rate_hz)
                        for a, b in zip(probes[m], probes["multilag"], strict=True)
                    ]
                    for m in ("four", "five")
                }
                rows.append(
                    dict(
                        public,
                        status="processed",
                        flags=counts(values),
                        matches=matches,
                        trace=trace,
                        time=time,
                        compared=compared,
                        candidate_rows=probes,
                    )
                )
                print(
                    public["cohort"],
                    public["case"],
                    public["visit"],
                    {r: t[0]["category"] for r, t in matches.items()} or counts(values),
                    flush=True,
                )
    return dict(
        rows=rows,
        affinity=sorted(os.sched_getaffinity(0)),
        lock_sha256=_sha(REPORT / "source-lock.json"),
    )


def counts(values):
    return {
        m: [sum(p[original.GATE] for p in lane) for lane in original.projections(v)]
        for m, v in values.items()
    }


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("stage", choices=("freeze", "replay", "build"))
    cli.add_argument("--work", type=local_output, default=WORK)
    args = cli.parse_args()
    source = REPORT / "source-lock.json"
    if args.stage == "freeze":
        if source.exists():
            raise FileExistsError("multi-lag replay is already prospectively locked")
        save_json(source, freeze(args.work))
    elif args.stage == "replay":
        write(
            REPORT / "waveform.json.gz",
            gzip.compress(encoded(replay(whole_iq.read(source))), mtime=0),
        )
    else:
        save_json(args.work / "build-lock.json", build(args.work))
