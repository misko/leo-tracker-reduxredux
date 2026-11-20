"""Replay exact archived timing labels through the bounded fractional wide GLRT."""

import argparse
import gzip
import json
from collections import Counter
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import hinted_glrt, iq_stream
from . import factor_cross, hinted_glrt_trial
from .full_v5_check import ALIAS_HZ, BULK, _from_native, _load_case, _probe, _sha, compare_probes

SCREEN = ROOT / "reports/2026_11_19_receiver_screening"
REPORT = SCREEN / "track-recovery/oracle-start"
EXISTING = SCREEN / "receiver-core/full-stride"
ABI = SCREEN / "receiver-core/hinted-glrt/build-lock.json"
CASES = ("DS29-0082", "DS26-0237", "DS26-0162", "DS29-0519")
STRATA = ("weak", "middle", "strong")
FRAME = hinted_glrt.FRAME
MODES = {"stock": "stock", "off": "off", "causal": "oracle", "sham": "half_frame"}


def exact_epoch(point):
    return point["integer_epoch_sample"] + point["fractional_epoch_offset_samples"]


def distance(left, right, period=FRAME):
    return abs(factor_cross.wrapped(left - right, period))


def target_matches(point, target, *, exact_cfo=False):
    delta = point[factor_cross.CFO] - target[factor_cross.CFO]
    return (
        distance(exact_epoch(point), exact_epoch(target)) <= 2
        and (abs(delta) if exact_cfo else distance(delta, 0, ALIAS_HZ)) <= 1000
    )


def stratum(margin):
    return STRATA[0] if margin < 0.075 else STRATA[1] if margin < 0.20 else STRATA[2]


def choose(available):
    """Consume chronological lane rows without revisiting a selected waveform."""
    chosen, used = [], set()

    def next_matching(rows, condition):
        for row in rows:
            if row["visit"] not in used and condition(row):
                used.add(row["visit"])
                chosen.append(row)
                return row
        return None

    missed = [x for x in available if x["kind"] == "miss"]
    matched = [x for x in available if x["kind"] == "matched"]
    for group in STRATA:
        next_matching(missed, lambda row, band=group: row["stratum"] == band)
    while len(chosen) < 4 and next_matching(missed, lambda _row: True):
        pass
    for _ in range(2):
        seen = {r["receiver"] for r in chosen if r["kind"] == "matched"}
        next_matching(
            matched, lambda row, lanes=seen: row["receiver"] not in lanes
        ) or next_matching(matched, lambda _row: True)
    return sorted(chosen, key=lambda r: (r["visit"], r["receiver"]))


def read_inputs(case, bindings, library):
    cached = EXISTING / f"native/control/{case['id']}.json.gz"
    raw = cached.read_bytes()
    if _sha(cached) != bindings[str(cached.relative_to(EXISTING))]:
        raise ValueError("complete wide control does not match the sealed stream")
    wide = json.loads(gzip.decompress(raw))
    era = hinted_glrt_trial.checked_json(BULK / case["native"]["path"], case["native"]["sha256"])
    if (
        wide["provenance"]["detector_sha256"] != "sha256:" + library["library_sha256"]["stock"]
        or len(era["source"]["probes"]) != len(wide["source"]["probes"])
        or era["source"]["session_id"] != wide["source"]["session_id"]
        or era["source"]["session_id"] != case["session_id"]
        or era["source"]["sample_rate_hz"] != 10_000_000
    ):
        raise ValueError("recording or original detector identity does not agree")
    return era["source"]["probes"], wide["source"]["probes"]


def select(case, archive, wide):
    potential, proposals, counts, baseline = {}, {}, Counter(), {}
    for capture, stock in zip(archive, wide, strict=True):
        if {k: v for k, v in capture.items() if k != "candidates"} != {
            k: v for k, v in stock.items() if k != "candidates"
        }:
            raise ValueError("archived capture and wide probes disagree about same-lane support")
        key = capture["visit_index"], capture["receiver_id"]
        baseline[key] = stock
        index = factor_cross.winner(capture["candidates"])
        if index is None:
            continue
        point = capture["candidates"][index]
        old = stock["candidates"]
        match = any(c[factor_cross.GATE] and target_matches(c, point) for c in old)
        if match:
            kind = "matched"
        elif any(distance(exact_epoch(c), exact_epoch(point)) <= 3 for c in old):
            counts["nearby_wide_excluded"] += 1
            continue
        else:
            kind = "miss"
        center = round(exact_epoch(point)) % FRAME
        group = stratum(point[factor_cross.MARGIN])
        potential[key] = dict(
            kind=kind,
            stratum=group,
            receiver=key[1],
            target=point,
            archive_probe=capture,
            reference_wide_probe=stock,
            known_center=center,
        )
        proposals[key] = (capture["valid_start_counter"], capture["channel"], center)
        counts[f"candidate_{kind}_{group}"] += 1

    with patch.object(hinted_glrt_trial, "LIMIT", 20_000):
        raw, examined, index_bytes = hinted_glrt_trial.select(case, proposals)
    counts.update(x["disposition"] for x in examined)
    counts["eligible_metadata_visits"] = len(raw)
    for exclusion in examined:
        if exclusion["disposition"] == "selected":
            continue
        for receiver in exclusion["receiver_ids"]:
            matched = potential.get((exclusion["visit"], receiver))
            if matched is not None:
                counts[f"raw_excluded_{matched['kind']}_{matched['stratum']}"] += 1
    available = []
    for row in raw:
        visit = row["visit"]
        for rx, declared in zip(row["receiver_ids"], row["causal"], strict=True):
            if declared is None:
                continue
            target = potential[visit, rx]
            oracle = [declared if i == rx else None for i in row["receiver_ids"]]
            sham = [
                (declared + FRAME // 2) % FRAME if i == rx else None for i in row["receiver_ids"]
            ]
            available.append(
                dict(
                    row,
                    **target,
                    causal=oracle,
                    sham=sham,
                    baseline=[baseline[visit, i] for i in row["receiver_ids"]],
                )
            )
    return dict(
        selected=choose(available),
        full_support_counts=dict(counts),
        index_bytes=index_bytes,
        all_raw_exclusions=[row for row in examined if row["disposition"] != "selected"],
    )


def verified(work):
    source_path = work / "input-lock.json"
    plan = json.loads(source_path.read_bytes())
    changed = {path for path, digest in plan["sources"].items() if _sha(Path(path)) != digest}
    amendment = None
    if changed == {str(Path(__file__))} and (work / "execution-amendment.json").is_file():
        amendment = json.loads((work / "execution-amendment.json").read_bytes())
        initial = gzip.decompress((work / "first-worker-source.py.gz").read_bytes())
        if (
            _sha(source_path) != amendment["plan_sha256"]
            or _sha(Path(__file__)) != amendment["amended_worker_sha256"]
            or sha256(initial).hexdigest() != plan["sources"][str(Path(__file__))]
        ):
            raise ValueError("execution-boundary amendment differs from its seal")
    elif changed:
        raise ValueError("run-time code differs from the input seal")
    library = json.loads(ABI.read_bytes())
    for key, path in library["paths"].items():
        if _sha(Path(path)) != library["library_sha256"][key]:
            raise ValueError("hinted detector library changed")
    return plan, library["paths"], amendment


def freeze(work):
    parent = EXISTING / "prediction-lock.json"
    parents = json.loads(parent.read_bytes())
    lib = json.loads(ABI.read_bytes())
    cases = {}
    for ident in CASES:
        case = _load_case(ident)
        capture, wide = read_inputs(case, parents["files"], lib)
        cases[ident] = select(case, capture, wide)
    paths = (
        Path(__file__),
        Path(factor_cross.__file__),
        Path(hinted_glrt.__file__),
        hinted_glrt.HEADER,
        Path(hinted_glrt_trial.__file__),
        Path(iq_stream.__file__),
        Path(compare_probes.__code__.co_filename),
        ABI,
        parent,
        REPORT / "PROTOCOL.md",
    )
    save_json(work / "input-lock.json", dict(cases=cases, sources={str(p): _sha(p) for p in paths}))


def collect(work, ident):
    plan, paths, amendment = verified(work)
    case = _load_case(ident)
    output = []
    contexts = {}
    with ExitStack() as stack:
        for n, row in enumerate(plan["cases"][ident]["selected"]):
            if amendment and [ident, row["visit"]] == amendment["already_read_wrong_edge"]:
                output.append(dict(row, status="unavailable", reason=amendment["reason"]))
                continue
            try:
                window = hinted_glrt_trial.load_selected(case, row)
            except iq_stream.IQReadError as error:
                output.append(dict(row, status="unavailable", reason=str(error)))
                continue
            edge = row["archive_probe"]["edge"]
            if edge != window.target["edge"]:
                raise ValueError("raw and archived template edge disagree")
            if edge not in contexts:
                contexts[edge] = hinted_glrt_trial.bound(stack, paths, edge)
            stock, hinted = contexts[edge]
            outcome = hinted_glrt_trial.measure(window.samples, stock, hinted, row, n)
            probes = {
                MODES[m]: [
                    _probe(
                        window, rx, (_from_native(i, c) for i, c in enumerate(lane["candidates"]))
                    )
                    for rx, lane in zip(window.receiver_ids, payload["rows"], strict=True)
                ]
                for m, payload in outcome["payloads"].items()
            }
            if encoded(probes["stock"]) != encoded(row["baseline"]):
                raise ValueError(
                    f"{ident}/{row['visit']} does not replay the complete wide factors"
                )
            if any(
                encoded(v[1 - row["receiver"]]) != encoded(probes["stock"][1 - row["receiver"]])
                for v in probes.values()
            ):
                raise ValueError("untreated receiver factors changed")
            output.append(
                dict(
                    row,
                    status="processed",
                    result={
                        field: {MODES[m]: v for m, v in items.items()}
                        for field, items in outcome.items()
                    },
                    probes=probes,
                )
            )
            print(ident, row["visit"], row["kind"], row["stratum"], flush=True)
    write(work / f"{ident}.json.gz", gzip.compress(encoded(output), mtime=0))


def endpoints(point, probe, public):
    candidates = probe["candidates"]
    all_matches = [c for c in candidates if target_matches(c, point)]
    gated = [c for c in all_matches if c[factor_cross.GATE]]
    best = max(
        gated or all_matches,
        key=lambda c: (c[factor_cross.MARGIN], -c[factor_cross.RANK]),
        default=None,
    )
    best_i = factor_cross.winner(candidates)
    target_wins = best_i is not None and target_matches(candidates[best_i], point)
    if gated:
        status = "gated"
    elif all_matches:
        status = "below_gate"
    elif any(distance(exact_epoch(c), exact_epoch(point)) <= 2 for c in candidates):
        status = "cfo_mismatch"
    elif any(distance(c["epoch"], exact_epoch(point)) <= 2 for c in public["candidates"]):
        status = "incomplete_fractional"
    else:
        status = "no_near_epoch"
    return dict(
        status=status,
        available=bool(all_matches),
        passes=bool(gated),
        physical_available=any(target_matches(c, point, exact_cfo=True) for c in all_matches),
        physical_passes=any(target_matches(c, point, exact_cfo=True) for c in gated),
        winner=target_wins,
        physical_winner=target_wins and target_matches(candidates[best_i], point, exact_cfo=True),
        rank=best[factor_cross.RANK] if best else None,
        margin=best[factor_cross.MARGIN] if best else None,
        margin_delta=best[factor_cross.MARGIN] - point[factor_cross.MARGIN] if best else None,
        epoch_delta=factor_cross.wrapped(exact_epoch(best) - exact_epoch(point), FRAME)
        if best
        else None,
        cfo_delta_hz=best[factor_cross.CFO] - point[factor_cross.CFO] if best else None,
    )


def score_row(row):
    rx = row["receiver"]
    target = row["target"]
    if row["status"] != "processed":
        return dict(row, methods={})
    stock = row["probes"]["stock"]
    result = row["result"]
    modes = {}

    def without_target(probe):
        return dict(
            probe, candidates=[c for c in probe["candidates"] if not target_matches(c, target)]
        )

    baseline = endpoints(target, stock[rx], result["payloads"]["stock"]["rows"][rx])
    for mode, probes in row["probes"].items():
        if mode == "off":
            continue
        public = result["payloads"][mode]["rows"][rx]
        target_fit = endpoints(target, probes[rx], public)
        control = compare_probes(without_target(stock[rx]), without_target(probes[rx]), 10_000_000)
        trace = result["traces"][mode if mode != "stock" else "off"][rx]
        groups = result["timings"][mode]
        modes[mode] = dict(
            **target_fit,
            selected=trace["selected"],
            ordinary=trace["ordinary"],
            active_epochs=trace["active_epochs"],
            activated=trace["selected"] != trace["ordinary"],
            other_added=control["native_only"],
            stock_other_lost=control["production_only"],
            rank_delta_stock=(
                target_fit["rank"] - baseline["rank"]
                if target_fit["rank"] is not None and baseline["rank"] is not None
                else None
            ),
            timing=groups,
        )
    fields = (
        "visit",
        "case",
        "receiver",
        "kind",
        "stratum",
        "channel",
        "known_center",
        "target",
        "status",
    )
    return dict({k: row[k] for k in fields}, methods=modes)


def score(work):
    _, _, amendment = verified(work)
    files = {
        name: _sha(work / name) for name in ("input-lock.json", *(f"{c}.json.gz" for c in CASES))
    }
    if amendment:
        for name in ("execution-amendment.json", "first-worker-source.py.gz"):
            files[name] = _sha(work / name)
    save_json(work / "worker-lock.json", dict(files=files))
    result = {}
    for case in CASES:
        rows = json.loads(gzip.decompress((work / f"{case}.json.gz").read_bytes()))
        result[case] = [score_row(row) for row in rows]
    save_json(work / "summary.json", result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("freeze", "score", *CASES))
    parser.add_argument("work", type=Path)
    args = parser.parse_args()
    home = local_output(args.work)
    home.mkdir(exist_ok=True, parents=True)
    if args.mode == "freeze":
        if (home / "input-lock.json").exists():
            raise FileExistsError("sealed input roster already exists")
        freeze(home)
    elif args.mode == "score":
        score(home)
    else:
        collect(home, args.mode)
