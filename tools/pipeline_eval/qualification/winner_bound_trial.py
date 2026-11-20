"""Audit fractional winner bounds on sealed original dual-receiver IQ visits."""

import argparse
import gzip
import os
import subprocess
from hashlib import sha256
from pathlib import Path
from time import process_time_ns
from unittest.mock import patch

import numpy as np

from .. import whole_iq
from ..__main__ import ROOT, THREAD_ENV, encoded, local_output, save_json, write
from ..variants import prepared_hotpath_peaks, winner_bound
from ..variants.original_kernel import PersistentGrid
from ..variants.refine_bank import FRAME_BASE, OFFSET, RATE, STOP, TAPS
from ..variants.selective_capture import visit_pairs
from . import first_gate_trial as prior
from .full_v5_check import BULK, _load_case, _sha

REPORT = prior.REPORT.parents[1] / "coarse-and-navigation/winner-bound"
RAW_PIN = "235eee88a9cb7e803e3b02b517c1210bda594cfd86acec1e98f1c4b964898651"
CPUS = {"DS26-0237": 10, "DS29-0082": 11}
POLICIES = ("integer", "exact_only", "parseval", "sparse_control")
SAMPLE = 5
previous = prior.prior.previous
read, checked = whole_iq.read, whole_iq.checked


def select(probes, manifest):
    eligible = [(visit, pair) for visit, pair in visit_pairs(probes) if visit < 256]

    def key(row):
        visit, _ = row
        return sha256(f"winner-bound-v1|{manifest}|{visit}".encode("ascii")).digest(), visit

    selected = []
    bands = set()
    for visit, pair in sorted(eligible, key=key):
        freq = pair[0]["actual_rf_hz"]
        if freq in bands:
            continue
        bands.add(freq)
        selected.append((visit, pair))
        if len(selected) == SAMPLE:
            break
    if len(selected) != SAMPLE:
        raise ValueError("five distinct physical RFs are required")
    return selected


def freeze(work, cpus):
    if (REPORT / "input-lock.json").exists():
        raise FileExistsError("choose a separate report for new enrollment")
    lock = read(checked(prior.REPORT / "qualification-lock.json", RAW_PIN))
    parent_path = checked(prior.REPORT / "input-lock.json", lock["files"]["input-lock.json"])
    parent = read(parent_path)
    cases = {}
    for (name, _), cpu in zip(CPUS.items(), cpus, strict=True):
        case = _load_case(name)
        archive = read(checked(BULK / case["native"]["path"], case["native"]["sha256"]))
        manifest = archive["source"]["input_manifest_sha256"]
        candidates = select(archive["source"]["probes"], manifest)
        fixtures = []
        for visit, pair in candidates:
            segment, digest, window = prior.prior.original.decode(case, visit)
            if any(p["valid_start_counter"] != window.acquisition["sample_start"] for p in pair):
                raise ValueError("saved IQ counters and original factor support differ")
            fixtures.append(
                dict(
                    visit=visit,
                    segment=segment,
                    manifest=digest,
                    iq_sha256=window.iq_sha256,
                    probes=pair,
                )
            )
        cases[name] = dict(parent["cases"][name], rows=fixtures, cpu=cpu, native=case["native"])
    paths = (Path(__file__), Path(winner_bound.__file__), REPORT / "PROTOCOL.md")
    source = dict(
        cases=cases,
        python_sha256=parent["python_sha256"],
        libs=parent["libs"],
        sources={str(p): _sha(p) for p in paths},
        parent_pin=RAW_PIN,
    )
    work.mkdir()
    save_json(work / "input-lock.json", source)
    save_json(REPORT / "input-lock.json", source)


def nearest_bound(producer, samples, epoch, freq, edge, offset, grid_score, observed):
    shift = round(offset)
    nearest = epoch + shift
    if not 0 <= nearest < round(RATE / 750):
        return 1.0, "circular_epoch_seam"
    starts = epoch + FRAME_BASE
    left, right = producer.fractional_take_bounds(offset)
    valid = (starts + OFFSET + offset >= left) & (starts + STOP - 1 + offset < len(samples) - right)
    integer_valid = (starts + OFFSET + shift >= 0) & (starts + STOP + shift <= len(samples))
    if not np.array_equal(valid, integer_valid) or int(valid.sum()) != len(observed):
        return 1.0, "different_frame_support"
    centers = starts[valid, None] + OFFSET + shift + np.arange(observed.shape[1])[None, :] * TAPS
    reference = producer.qin_edge_pilot_frame(RATE, edge)[OFFSET:STOP].reshape(-1, TAPS)
    first, stop, delta = winner_bound.perturbation(reference, offset, freq)
    indexes = centers[..., None] + np.arange(first, stop)
    if not indexes.size or indexes.min() < 0 or indexes.max() >= len(samples):
        return 1.0, "incomplete_bound_support"
    integer = (
        producer._conditioned_correlation_workspace(
            samples,
            RATE,
            nearest,
            freq,
            selected_symbols=np.arange(2, 66),
            edge=producer.StarlinkEdge(edge),
        )
        .select(np.arange(2, 66))
        .values
    )
    envelope = winner_bound.integer_envelope(
        integer,
        grid_score,
        delta,
        np.linalg.norm(samples[indexes], axis=-1),
    )
    return envelope, "evaluated"


class Audit:
    def __init__(self, producer, original):
        self.producer = producer
        self.original = original
        self.attempts = []

    def refine(self, samples, rate, **geometry):
        producer = self.producer
        scorer = producer.conditioned_glrt64_score
        pairs = producer._glrt_pair
        observed = []

        def terminal(values, sample_rate, **args):
            seen = []

            def record(exact, control, **spectrum):
                onset = process_time_ns()
                scores = pairs(exact, control, **spectrum)
                seen.append((exact.values, control.values, process_time_ns() - onset))
                return scores

            with patch.object(producer, "_glrt_pair", record):
                score = scorer(values, sample_rate, **args)
            if len(seen) != 1 or sample_rate != RATE:
                raise ValueError("terminal scorer differs from one original uniform spectral pair")
            observed.append((args, score, *seen[0]))
            return score

        with patch.object(producer, "conditioned_glrt64_score", terminal):
            result = self.original(samples, rate, **geometry)
        calls = iter(observed)
        candidates = []
        incumbent = None
        edge = geometry["edge"]
        for rank, (epoch, freq, row) in enumerate(
            zip(geometry["integer_epoch_samples"], geometry["acquired_cfo_hz"], result, strict=True)
        ):
            offset = row.fractional_epoch_offset_samples
            evidence = dict(
                rank=rank,
                epoch=int(epoch),
                acquired_cfo_hz=float(freq),
                offset=offset,
                grid_exact=list(row.exact_score_grid),
                grid_control=list(row.control_score_grid),
                incumbent=incumbent,
            )
            candidates.append(evidence)
            if offset is None:
                continue
            args, score, exact, control, pair_ns = next(calls)
            if (
                args["epoch_sample"] != epoch
                or args["acquired_cfo_hz"] != freq
                or args["fractional_epoch_offset_samples"] != offset
            ):
                raise ValueError("bound trace lost terminal fractional rank order")
            onset = process_time_ns()
            integer, disposition = nearest_bound(
                producer,
                samples,
                epoch,
                freq,
                edge,
                offset,
                row.exact_score_grid[round(offset) + 2],
                exact,
            )
            integer_ns = process_time_ns() - onset
            onset = process_time_ns()
            late = winner_bound.margin_bounds(score.exact_score, control)
            late_ns = process_time_ns() - onset
            bounds = dict(zip(POLICIES, (integer, *late), strict=True))
            if any(score.margin > u + winner_bound.ROUNDING_ALLOWANCE for u in bounds.values()):
                raise ValueError(
                    f"measured original margin exceeded the audited allowance: {bounds}"
                )
            evidence.update(
                margin=score.margin,
                exact_score=score.exact_score,
                control_score=score.control_score,
                tracking_cfo_hz=score.tracking_cfo_hz,
                bounds=bounds,
                skip={k: winner_bound.can_skip(u, incumbent) for k, u in bounds.items()},
                valid_winner=incumbent is not None,
                integer_disposition=disposition,
                frames=len(exact),
                coherent_denominators=[winner_bound.ceiling(x) for x in (exact, control)],
                cpu_ns=dict(
                    integer_diagnostic=integer_ns, late_diagnostic=late_ns, paired_fft=pair_ns
                ),
            )
            if score.margin >= winner_bound.GATE and (
                incumbent is None or score.margin > incumbent
            ):
                incumbent = score.margin
        if next(calls, None) is not None:
            raise ValueError("a terminal fractional evaluation has no candidate rank")
        self.attempts.append(candidates)
        return result


def worker(work, ident):
    from leo.analysis.starlink import acquisition, fast_scan_scores
    from leo.scanner import fast_scan_detector

    path = checked(work / "input-lock.json", _sha(REPORT / "input-lock.json"))
    lock = read(path)
    cfg = lock["cases"][ident]
    assert os.sched_getaffinity(0) == {cfg["cpu"]}
    checked(prior.prior.original.PYTHON, lock["python_sha256"])
    for name, digest in (lock["sources"] | cfg["sources"]).items():
        checked(Path(name), digest)
    libs = {
        name: checked(Path(item["path"]), item["sha256"]) for name, item in lock["libs"].items()
    }
    case = _load_case(ident)
    _, policy, lineage = previous.exact.lineage.source_lineage(case)
    if lineage["capture"]["root"] != cfg["root"]:
        raise ValueError("installed original capture release changed")
    grid = PersistentGrid(libs["prepared"])
    records = []
    try:
        for fixture in cfg["rows"]:
            segment, digest, window = prior.prior.original.decode(case, fixture["visit"])
            if (segment, digest, window.iq_sha256) != (
                fixture["segment"],
                fixture["manifest"],
                fixture["iq_sha256"],
            ):
                raise ValueError("raw visit differs from the frozen outcome-independent holdout")
            baseline, baseline_time = previous.sample(window, policy)
            audit = Audit(fast_scan_scores, fast_scan_detector.refine_glrt64_epochs)
            with (
                previous.exact.refiners(libs),
                grid.route(acquisition, previous.exact.starts.screen_module()),
                patch.object(
                    acquisition, "_retain_score_map_peaks", prepared_hotpath_peaks.retained_peaks
                ),
                patch.object(fast_scan_detector, "refine_glrt64_epochs", audit.refine),
            ):
                replay, _ = previous.sample(window, policy)
            if encoded(baseline) != encoded(replay) or encoded(replay[1]) != encoded(
                fixture["probes"]
            ):
                raise ValueError("diagnostics changed authentic original public or native payload")
            records.append(
                dict(
                    visit=fixture["visit"],
                    iq_sha256=window.iq_sha256,
                    edge=window.target["edge"],
                    attempts=audit.attempts,
                    baseline=baseline_time,
                )
            )
            print(ident, fixture["visit"], len(audit.attempts), "physical attempts", flush=True)
            grid.calls.clear()
    finally:
        grid.clear_cache()
    write(work / f"{ident}.json.gz", gzip.compress(encoded(records), mtime=0))


def run(work):
    source = read(work / "input-lock.json")
    workers = []
    for ident, cfg in source["cases"].items():
        env = os.environ | THREAD_ENV | {"PYTHONPATH": f"{cfg['root']}:{ROOT}"}
        launch = [
            "taskset",
            "-c",
            str(cfg["cpu"]),
            str(prior.prior.original.PYTHON),
            "-Bu",
            "-m",
            __spec__.name,
            "worker",
            str(work),
            ident,
        ]
        workers.append(subprocess.Popen(launch, cwd=ROOT, env=env))
    failures = [worker.wait(timeout=150) for worker in workers]
    if any(failures):
        raise RuntimeError(f"original winner-bound worker failed: {failures}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "run", "worker"))
    parser.add_argument("work", type=local_output)
    parser.add_argument("ident", nargs="?")
    parser.add_argument("--cpus", type=int, nargs=2, default=list(CPUS.values()))
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.work, args.cpus)
    elif args.action == "run":
        run(args.work)
    else:
        worker(args.work, args.ident)


if __name__ == "__main__":
    main()
