"""Audit capture winner support and try a representative-half fifth-center detector."""

import argparse
import gzip
import json
import os
from collections import Counter
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import ROOT, encoded, save_json, write
from ..variants import center_union, hard_pilots, iq_stream
from ..variants.differential_runtime_fft import FftScout
from . import differential_pilot_eval, factor_cross, ordinary_front_eval
from . import fifth_completion as completion
from .center_union_gate import bind
from .full_v5_check import ALIAS_HZ, BULK, _from_native, _load_case, _probe, _sha, compare_probes

SCREEN = completion.SCREEN
REPORT = SCREEN / "receiver-choice/hard-pilots"
HARD = ("DS26-0122", "DS26-0162", "DS26-0197", "DS26-0241", "DS29-0082", "DS29-0357")
CONTROLS = ("DS26-0014", "DS29-0519")
ROLES = ("four", "five", "halves")
CFO, GATE = factor_cross.CFO, factor_cross.GATE
MAX_PREFIX = 48 * iq_stream.MIB
FRAME = 13_333
TOLERANCE = 1_000
CPU = 6


def authorized(folder, name, seal="prediction-lock.json"):
    receipt = SCREEN / folder / seal
    digest = whole_iq.read(receipt)["files"][name]
    return whole_iq.checked(SCREEN / folder / name, digest), dict(
        receipt=str(receipt.relative_to(ROOT)), receipt_sha256=_sha(receipt), sha256=digest
    )


def resolve(ident, case):
    source = "latency-and-support/fifth-completion"
    parents = {
        "DS26-0197": ("support-preserving/whole-center-union", "native/candidate"),
        "DS29-0082": ("support-preserving/fifth-crossover", "native"),
    }
    folder, stem = parents.get(ident, (source, "native/candidate"))
    options = {
        "DS26-0014": ("acquisition-support/scout-full", "native/control", "prediction-lock.json"),
        "DS26-0197": (folder, "native/control", "prediction-lock.json"),
        **{key: (source, "native/stock", "figure-lock.json") for key in ("DS26-0241", "DS29-0357")},
    }
    stock, stock_stem, seal = options.get(
        ident, ("receiver-core/full-stride", "native/control", "prediction-lock.json")
    )
    paths = {
        "capture": whole_iq.checked(BULK / case["native"]["path"], case["native"]["sha256"]),
    }
    bindings = {"capture": dict(sha256=case["native"]["sha256"], path=str(paths["capture"]))}
    paths["four"], bindings["four"] = authorized(stock, f"{stock_stem}/{ident}.json.gz", seal)
    paths["five"], bindings["five"] = authorized(folder, f"{stem}/{ident}.json.gz")
    docs = {}
    for key, file in paths.items():
        raw = file.read_bytes()
        raw = gzip.decompress(raw) if file.suffix == ".gz" else raw
        docs[key] = json.loads(raw)
        bindings[key].update(path=str(file), native_sha256=sha256(raw).hexdigest())
    return docs, bindings


def support(doc):
    return dict(
        delivery=[doc[k] for k in ("clock_anchor", "delivery_clocks", "last_sample_counter")],
        science={
            k: v
            for k, v in doc["source"].items()
            if k not in ("analysis_manifest_sha256", "probes")
        },
        provenance={
            k: v
            for k, v in doc["provenance"].items()
            if k not in ("run_id", "detector_sha256", "scope")
        },
    )


def metadata(probe):
    return {k: v for k, v in probe.items() if k != "candidates"}


def epoch(p):
    return p["integer_epoch_sample"] + p["fractional_epoch_offset_samples"]


def near_epoch(point, target):
    return abs(factor_cross.wrapped(epoch(point) - epoch(target), FRAME)) <= 2


def classify(target, candidates):
    same = [p for p in candidates if near_epoch(p, target)]
    physical = [p for p in same if abs(p[CFO] - target[CFO]) <= TOLERANCE]
    alias = [
        p for p in same if abs(factor_cross.wrapped(p[CFO] - target[CFO], ALIAS_HZ)) <= TOLERANCE
    ]
    winning = factor_cross.winner(candidates)
    best = candidates[winning] if winning is not None else None
    if any(p[GATE] for p in physical):
        status = "physical_gated"
    elif physical:
        status = "physical_below_gate"
    elif alias:
        status = "alias_only"
    elif same:
        status = "other_cfo"
    else:
        status = "absent_phase"
    return dict(
        category=status,
        actual_winner_matches=best in physical,
        actual_winner_alias=best in alias,
        any_gate=best is not None,
        any_alias_gate=any(p[GATE] for p in alias),
        nearest_cfo_delta_hz=min((p[CFO] - target[CFO] for p in same), key=abs, default=None),
        nearest_epoch_delta_samples=min(
            (factor_cross.wrapped(epoch(p) - epoch(target), FRAME) for p in candidates),
            key=abs,
            default=None,
        ),
    )


def prefix(case):
    locator = case["recording"]["segments"][0]
    archive = BULK / locator["path"]
    raw = iq_stream._read_prefix(archive, 65_537)
    if len(raw) > 65_536 or sha256(raw).hexdigest() != locator["sha256"]:
        raise ValueError("segment-zero manifest differs from source archive")
    manifest = json.loads(raw)
    bounded = {}
    for chunk in manifest["chunks"]:
        if chunk["first_sequence"] >= 128:
            break
        p = archive.parent / chunk["index_relative_path"]
        rows = iq_stream._read_prefix(p, chunk["index_bytes"] + 1)
        if len(rows) != chunk["index_bytes"] or iq_stream._digest(rows) != chunk["index_sha256"]:
            raise ValueError("raw index differs from capture authority")
        for row in map(json.loads, rows.splitlines()):
            n = row["payload_offset_bytes"] + row["payload_bytes"]
            if row["sequence"] < 128 and row["sample_count"] == 200_000 and n <= MAX_PREFIX:
                bounded[row["acquisition"]["global_visit"]] = dict(
                    sequence=row["sequence"],
                    iq_sha256=row["iq_sha256"],
                    counter=row["acquisition"]["sample_start"],
                    index_sha256=chunk["index_sha256"],
                    prefix_bytes=n,
                )
    return bounded


def choose(ident, documents, allowed):
    original, four, five = (documents[k] for k in ("capture", "four", "five"))
    if support(original) != support(four) or support(original) != support(five):
        raise ValueError(f"{ident} clock, validity or physical metadata changed")
    tally, eligible = Counter(), []
    probes = [d["source"]["probes"] for d in (original, four, five)]
    for a, b, c in zip(*probes, strict=True):
        if metadata(a) != metadata(b) or metadata(a) != metadata(c):
            raise ValueError(f"{ident} probe metadata or order changed")
        winner = factor_cross.winner(a["candidates"])
        if winner is None:
            continue
        value = a["candidates"][winner]
        decisions = [classify(value, p["candidates"]) for p in (b, c)]
        x, y = (p["category"] for p in decisions)
        tally.update(["winners", f"four:{x}", f"five:{y}", f"joint:{x}:{y}"])
        for role, decision in zip(("four", "five"), decisions, strict=True):
            for status in (
                "actual_winner_matches",
                "any_gate",
                "actual_winner_alias",
                "any_alias_gate",
            ):
                tally[f"{role}:{status}"] += decision[status]
        if x != "physical_gated" and y != "physical_gated":
            tally["missing_both"] += 1
            tally["both_phases_absent"] += x == y == "absent_phase"
            tally["negative_cfo_of_missing_both"] += value[CFO] < 0
        missing = x != "physical_gated" and y != "physical_gated"
        retained = all(d["actual_winner_matches"] for d in decisions)
        visit, rx = a["visit_index"], a["receiver_id"]
        if visit in allowed and (missing if ident in HARD else retained):
            if a["valid_start_counter"] != allowed[visit]["counter"]:
                raise ValueError("original winner and raw acquisition clocks differ")
            rank = sha256(f"hard-pilots-v1:{ident}:{visit}:{rx}".encode()).hexdigest()
            eligible.append(
                dict(
                    rank=rank,
                    visit=visit,
                    rx=rx,
                    edge=a["edge"],
                    target=value,
                    known=decisions,
                    **allowed[visit],
                )
            )
    result = {}
    for p in sorted(eligible, key=lambda p: p["rank"]):
        result.setdefault(p["visit"], p)
        if len(result) == (2 if ident in HARD else 1):
            break
    included = {p["visit"] for p in result.values()}
    expected = {
        label: {v: [row for row in records if row["visit_index"] == v] for v in included}
        for label, records in zip(("capture", "four", "five"), probes, strict=True)
    }
    return (
        dict(tally),
        list(result.values()),
        expected,
        len(eligible),
        sha256(encoded(support(original))).hexdigest(),
    )


def freeze():
    source = completion.REPORT / "source-lock.json"
    detectors = whole_iq.read(source)["detectors"]
    for row in detectors.values():
        whole_iq.checked(Path(row["path"]), row["sha256"])
    roster = {}
    for ident in (*HARD, *CONTROLS):
        case = _load_case(ident)
        documents, refs = resolve(ident, case)
        counts, visits, archived, eligible, clock = choose(ident, documents, prefix(case))
        roster[ident] = dict(
            sources=refs,
            counts=counts,
            selected=visits,
            eligible=eligible,
            archived=archived,
            clock_sha256=clock,
        )
        print(
            ident,
            counts["winners"],
            counts.get("missing_both", 0),
            [r["visit"] for r in visits],
            flush=True,
        )
    files = (Path(__file__), Path(hard_pilots.__file__), REPORT / "PROTOCOL.md", source)
    return dict(
        detectors=detectors,
        cases=roster,
        source_sha256={str(p.relative_to(ROOT)): _sha(p) for p in files},
    )


def measure(samples, native, union, scout, halves, edge, index, repeats):
    payloads, hints, times = {}, {}, {k: [] for k in ROLES}
    for rep in range(repeats):
        n = (index + rep) % len(ROLES)
        for role in ROLES[n:] + ROLES[:n]:
            wall, cpu = perf_counter_ns(), process_time_ns()
            centers, sides, trace = None, None, None
            if role == "four":
                payload = native.analyze(samples)
            else:
                if role == "five":
                    centers = tuple(p[0] if p else None for p, _ in scout(samples, edge))
                else:
                    centers, sides = halves(samples)
                payload, trace = union(samples, centers)
            times[role].append(
                dict(
                    wall_ms=(perf_counter_ns() - wall) / 1e6, cpu_ms=(process_time_ns() - cpu) / 1e6
                )
            )
            payload = ordinary_front_eval._payload(payload)
            info = dict(centers=centers, sides=sides, trace=trace)
            if (
                encoded(payloads.setdefault(role, payload)) != encoded(payload)
                or hints.setdefault(role, info) != info
            ):
                raise ValueError("same-input detector changed between repeated calls")
    return payloads, hints, times


def projections(payload):
    return [
        [p for i, c in enumerate(row["candidates"]) if (p := _from_native(i, c)) is not None]
        for row in payload["rows"]
    ]


def replay(lock):
    for path, digest in lock["source_sha256"].items():
        whole_iq.checked(ROOT / path, digest)
    resolved = {
        k: str(whole_iq.checked(Path(d["path"]), d["sha256"])) for k, d in lock["detectors"].items()
    }
    paths = dict(stock=resolved["control"], hinted=resolved["control"], union=resolved["candidate"])
    rows, controls = [], []
    for edge in ("lower", "upper"):
        with ExitStack() as stack:
            native = bind(stack, paths, edge)
            union = center_union.UnionCall(native["union"])
            scout = stack.enter_context(FftScout(resolved["scout"], edge))
            halves = hard_pilots.RepresentativeTime(scout)
            for name in ("zero", "noise", "weak", "strong", "one-frame"):
                samples, plant = differential_pilot_eval.synthetic(edge, name)
                payloads, hints, times = measure(
                    samples, native["stock"], union, scout, halves, edge, len(controls), 1
                )
                target = dict(
                    integer_epoch_sample=plant["epoch"],
                    fractional_epoch_offset_samples=0,
                    **{CFO: plant["cfo_hz"]},
                )
                controls.append(
                    dict(
                        edge=edge,
                        control=name,
                        plant=plant,
                        iq_sha256=iq_stream._digest(samples.tobytes()),
                        counts={
                            role: [sum(p[GATE] for p in g) for g in projections(output)]
                            for role, output in payloads.items()
                        },
                        target={
                            role: [classify(target, g) for g in projections(output)]
                            for role, output in payloads.items()
                        }
                        if plant["plant"]
                        else {},
                        hints=hints,
                        times=times,
                    )
                )
            for ident, item in lock["cases"].items():
                eligible = [p for p in item["selected"] if p["edge"] == edge]
                if not eligible:
                    continue
                case = _load_case(ident)
                locator = case["recording"]["segments"][0]
                for target in eligible:
                    row = dict(
                        id=ident, group="hard" if ident in HARD else "control", selection=target
                    )
                    try:
                        with patch.object(iq_stream, "MAX_CHUNK_PREFIX", MAX_PREFIX):
                            (w,) = iq_stream.load_windows(
                                dict(
                                    recording_path=str(BULK / locator["path"]),
                                    recording_sha256="sha256:" + locator["sha256"],
                                ),
                                (target["sequence"],),
                            )
                    except iq_stream.IQReadError as error:
                        rows.append(dict(row, status="unavailable", reason=str(error)))
                        continue
                    if (
                        w.iq_sha256,
                        w.acquisition["sample_start"],
                        w.acquisition["global_visit"],
                        w.target["edge"],
                    ) != (target["iq_sha256"], target["counter"], target["visit"], edge):
                        raise ValueError("raw waveform does not match frozen visit")
                    payloads, hints, times = measure(
                        w.samples, native["stock"], union, scout, halves, edge, len(rows), 3
                    )
                    candidate = {
                        role: [_probe(w, i, p) for i, p in enumerate(projections(out))]
                        for role, out in payloads.items()
                    }
                    for role in ("four", "five"):
                        expected = item["archived"][role][str(target["visit"])]
                        if encoded(candidate[role]) != encoded(expected):
                            raise ValueError(
                                f"{ident} {target['visit']} {role} differs from archived probes"
                            )
                    comparison = {
                        role: [
                            compare_probes(x, y, w.sample_rate_hz)
                            for x, y in zip(candidate[role], candidate["halves"], strict=True)
                        ]
                        for role in ("four", "five")
                    }
                    matched = {
                        role: classify(target["target"], probe[target["rx"]]["candidates"])
                        for role, probe in candidate.items()
                    }
                    rows.append(
                        dict(
                            row,
                            status="processed",
                            candidates=candidate,
                            matched=matched,
                            hints=hints,
                            times=times,
                            gate_delta=comparison,
                        )
                    )
                    print(
                        ident,
                        target["visit"],
                        {k: v["category"] for k, v in matched.items()},
                        flush=True,
                    )
    return dict(
        rows=rows,
        controls=controls,
        affinity=sorted(os.sched_getaffinity(0)),
        source_sha256=_sha(REPORT / "source-lock.json"),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("freeze", "replay"))
    args = p.parse_args()
    source = REPORT / "source-lock.json"
    if args.command == "freeze":
        if source.exists():
            raise FileExistsError("hard-pilot IQ sample already frozen")
        save_json(source, freeze())
    else:
        write(
            REPORT / "waveform.json.gz",
            gzip.compress(encoded(replay(whole_iq.read(source))), mtime=0),
        )
