"""Replay complementary full-anchor scoring against exact installed capture."""

import argparse
import gzip
import json
import os
from functools import partial
from hashlib import sha256
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from unittest.mock import patch

import numpy as np

from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import anchor_race, iq_stream
from . import (
    complete_epoch_proxy_eval,
    differential_runtime_eval,
    hinted_glrt_trial,
    oracle_start,
)
from . import thinned_capture_eval as parent
from .full_v5_check import BULK, _load_case, _sha, compare_probes

REPORT = ROOT / "reports/2026_11_19_receiver_screening/arrival-and-timing/anchor-race"
ADDITIONAL = ("DS26-0237", "DS29-0082")
MODES = ("capture", "race", "mean", "sham", "wide")


def source_lock():
    old = parent.REPORT / "source-lock.json"
    base = parent.source_lock()
    if json.loads(old.read_bytes()) != base:
        raise ValueError("the directly comparable earlier roster changed")
    inputs = (
        Path(__file__),
        Path(anchor_race.__file__),
        old,
        REPORT / "PROTOCOL.md",
        differential_runtime_eval.FIXTURES / "input-lock.json.gz",
        differential_runtime_eval.FIXTURES / "confirmation-lock.json",
    )
    visits = list(differential_runtime_eval.locked_visits())
    for ident in ADDITIONAL:
        held = [r for scope, key, r in visits if key == ident and scope == "confirmation"]
        matched = [
            r
            for scope, key, r in visits
            if key == ident and scope == "primary" and r["kind"] == "matched"
        ]
        select = min(
            matched, key=lambda r: sha256(f"anchor-race:{ident}:{r['visit']}".encode()).digest()
        )
        if len(held) != 2 or [r["kind"] for r in held] != ["miss", "miss"]:
            raise ValueError("the prespecified independent confirmation visits are missing")
        base["roster"][ident].extend(
            dict(r, status="processed", held=True) for r in (*held, select)
        )
    base["sources"].update({str(p): _sha(p) for p in inputs})
    return base


def coarse_checks(reference, trial):
    base, result = [d[:2] for d in (reference, trial)]
    out = []
    for prior, actual in zip(base, result, strict=True):
        if prior["rx"] != actual["rx"] or prior["anchors"] != actual["anchors"]:
            raise ValueError("primary RX order or acquisition geometry changed")
        ranks = {tuple(p): i for i, p in enumerate(actual["peaks"], 1)}
        steps = [r for r in actual["eligible_ranges"]]
        out.append(
            dict(
                stock_peaks=prior["peaks"],
                new_peaks=actual["peaks"],
                exact_ranks=[ranks.get(tuple(key)) for key in prior["peaks"]],
                eligible=[
                    any(start <= e < stop for start, stop in steps) for e, _ in prior["peaks"]
                ],
            )
        )
    return out


def paired(window, policy, context, repeats, tag, index):
    results = []
    for rep in range(repeats):
        modes, matrices = {}, {}
        offset = (index + rep) % len(MODES)
        for mode in MODES[offset:] + MODES[:offset]:
            if mode == "wide":
                modes[mode] = parent.wide_call(context, window)
                continue
            proposal = partial(anchor_race.propose, role=mode, visit=tag)
            with patch.object(parent.thinned_capture, "propose", proposal):
                modes[mode], matrices[mode] = parent.capture(window, policy, mode != "capture")
        bound = modes["capture"]["acquisitions"]
        coarse, cells = {}, {}
        for mode in ("race", "mean", "sham"):
            coarse[mode] = coarse_checks(bound, modes[mode]["acquisitions"])
            count = 0
            for slot in matrices[mode].keys() & matrices["capture"].keys():
                left, right = (
                    np.asarray(matrices["capture"][slot]),
                    np.asarray(matrices[mode][slot]),
                )
                finite = np.isfinite(right)
                if not np.array_equal(left[finite], right[finite]):
                    raise ValueError("rescoring changed exact original coarse values")
                count += int(np.count_nonzero(finite))
            cells[mode] = count
        for a, b in zip(
            modes["race"]["acquisitions"][:2], modes["sham"]["acquisitions"][:2], strict=True
        ):
            if (a["nominations"], a["rescored_cells"]) != (b["nominations"], b["rescored_cells"]):
                raise ValueError("sham primary scan has a different exact evaluation budget")
        results.append(dict(modes=modes, coarse=coarse, exact_rescored=cells))
    for m in MODES:
        if any(
            encoded(row["modes"][m]["probes"]) != encoded(results[0]["modes"][m]["probes"])
            for row in results[1:]
        ):
            raise ValueError("candidate payload changed between warm repetitions")
    first = results[0]["modes"]
    return dict(
        pairs=results,
        positives={
            m: [
                compare_probes(before, after, window.sample_rate_hz)
                for before, after in zip(
                    first["capture"]["probes"], first[m]["probes"], strict=True
                )
            ]
            for m in MODES
        },
    )


def gates(result, targets):
    first = result["pairs"][0]["modes"]
    return {
        role: [
            oracle_start.endpoints(target, m["probes"][rx], {"candidates": []})
            for rx, target in targets
        ]
        for role, m in first.items()
    }


def archived(case, roster):
    path, digest = parent.lineage.locked_native(case, "capture")
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != digest:
        raise ValueError("stored capture probe receipt changed")
    doc = json.loads(raw)
    if doc["source"]["session_id"] != case["session_id"]:
        raise ValueError("capture reference belongs to another recording")
    visits = {r["visit"] for r in roster}
    mapping = {v: [] for v in visits}
    for p in doc["source"]["probes"]:
        if p["visit_index"] in visits:
            mapping[p["visit_index"]].append(p)
    return mapping, digest


def fixture_targets(name):
    k = {"weak": (735, 48_000), "high": (731, 720_000), "negative_high": (731, -720_000)}
    if name not in k:
        return []
    epoch, hz = k[name]
    return [
        (
            rx,
            dict(
                integer_epoch_sample=epoch,
                fractional_epoch_offset_samples=0.0,
                fractional_tracking_cfo_hz=float(hz),
                fractional_margin=0.0,
            ),
        )
        for rx in (0, 1)
    ]


def replay(ident, lock):
    from leo.analysis.starlink.native_short_window import NativeShortWindow
    from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame
    from leo.contracts.fast_scan import FastScanReceiverV1
    from leo.scanner.fast_scan_analysis import analyze_window

    case = _load_case(ident)
    meta, policy, provenance = parent.lineage.source_lineage(case)
    roster = lock["roster"][ident]
    reference, archive_sha256 = archived(case, roster)
    rate, edge = 10_000_000, meta["edge"]
    templates = [
        np.asarray(qin_edge_pilot_frame(rate, edge, symbol_roll=r), dtype="<c16")
        for r in (0, CONTROL_SYMBOL_ROLL)
    ]
    rows, controls = [], {}
    with NativeShortWindow(
        str(parent.WIDE), *templates, sample_rate_hz=rate, fractional_epoch=True
    ) as context:
        for index, key in enumerate(roster):
            if key.get("held"):
                window = hinted_glrt_trial.load_selected(case, key)
            else:
                locator = case["recording"]["segments"][key["segment"]]
                (window,) = iq_stream.load_windows(
                    dict(
                        recording_path=str(BULK / locator["path"]),
                        recording_sha256="sha256:" + locator["sha256"],
                    ),
                    (key["sequence"],),
                )
            if (window.iq_sha256, window.acquisition["global_visit"]) != (
                key["iq_sha256"],
                key["visit"],
            ):
                raise ValueError("saved IQ differs from the frozen roster")
            observed = analyze_window(
                window,
                window.receiver_ids,
                None,
                policy,
                detector=lambda _, ids: tuple(
                    FastScanReceiverV1(receiver_id=rx, candidates=()) for rx in ids
                ),
            ).status
            if observed != key["status"]:
                raise ValueError("capture validity changed")
            result = {}
            if observed == "processed":
                result = paired(window, policy, context, 2, f"{ident}:{key['visit']}", index)
                first = result["pairs"][0]["modes"]
                match = parent.lineage.compare_rows(
                    first["capture"]["probes"], reference[key["visit"]]
                )
                if match["exact"] != match["probes"]:
                    raise ValueError("installed original does not reproduce the archived output")
                if key.get("held"):
                    if encoded(first["wide"]["probes"]) != encoded(key["baseline"]):
                        raise ValueError(
                            "fresh ordinary wide factor differs from locked target roster"
                        )
                    result["physical"] = gates(result, [(key["receiver"], key["target"])])
                if not controls and ident in parent.CONTROLS:
                    for name, plant in complete_epoch_proxy_eval.signed_controls(window).items():
                        trial = paired(plant, policy, context, 1, f"{edge}:{name}", index)
                        controls[name] = dict(
                            iq_sha256=plant.iq_sha256,
                            physical=gates(trial, fixture_targets(name)),
                            **trial,
                        )
            rows.append(dict(key, **result))
            print(ident, key["visit"], observed, flush=True)
    return dict(
        id=ident,
        edge=edge,
        provenance=provenance,
        archive_sha256=archive_sha256,
        rows=rows,
        controls=controls,
        affinity=sorted(os.sched_getaffinity(0)),
        peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss,
        locked_sha256=parent._digest(encoded(lock)),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("freeze", *parent.CASES))
    args = parser.parse_args()
    lock = source_lock()
    target = REPORT / "source-lock.json"
    if args.stage == "freeze":
        if target.exists():
            raise ValueError("proposal and held roster are already frozen")
        save_json(target, lock)
    else:
        if json.loads(target.read_bytes()) != lock:
            raise ValueError("proposal or waveform roster changed after lock")
        data = replay(args.stage, lock)
        write(local_output(REPORT / f"{args.stage}.json.gz"), gzip.compress(encoded(data), mtime=0))
