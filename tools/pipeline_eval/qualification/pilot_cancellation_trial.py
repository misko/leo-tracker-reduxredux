"""Replay a training-only two-pilot cancellation trial on saved stereo CI16."""

import argparse
import gzip
import json
import os
import subprocess
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from hashlib import sha256
from itertools import combinations
from pathlib import Path
from time import perf_counter_ns, process_time_ns

import numpy as np

from .. import whole_iq
from ..__main__ import ROOT, THREAD_ENV, encoded, local_output, save_json, write
from ..variants import frame_coherence
from ..variants import pilot_cancellation as pilot
from ..variants.selective_capture import visit_pairs
from . import capture_detector_lineage as lineage
from . import capture_release
from .capture_detector_replay import scan_capture_window
from .full_v5_check import _load_case, _sha
from .original_kernel_trial import PYTHON, decode

REPORT = ROOT / "reports/2026_11_19_receiver_screening/native-receiver/pilot-cancellation"
CASES = {"DS26-0237": 12, "DS29-0082": 13, "DS29-0519": 12}
STAGES = ("original", "primary", "raw_retry", "wider", "cancelled")
REPEATS = 5
EARLY_LIMIT = 768
ARCHIVE_GATE = "passed_fractional_margin_gate"
SALT = "qin-pilot-subtraction-roster-v1"


def location(row):
    return (
        row["integer_epoch_sample"] + row["fractional_epoch_offset_samples"],
        row["fractional_tracking_cfo_hz"],
    )


def separate_roles(pair):
    roles = set()
    for probe in pair:
        positive = [location(row) for row in probe["candidates"] if row[ARCHIVE_GATE]]
        kinds = set()
        for left, right in combinations(positive, 2):
            relation = pilot.relationship(*left, *right)
            kinds.add(relation)
            if relation == "distinct":
                diff, _, _ = pilot.difference(*left, *right)
                roles.add("close" if abs(diff) <= 2200 else "separate")
        if "alias" in kinds and "distinct" not in kinds:
            roles.add("alias")
    return roles


def select(ident, archive):
    provenance = archive["provenance"]
    rejected = {row["visit"] for row in provenance["excluded_windows"]}
    valid = dict(visit_pairs(archive["source"]["probes"]))
    if set(valid) & rejected or set(valid) | rejected != set(range(provenance["window_count"])):
        raise ValueError("original control misses scheduled physical visits")
    strata = defaultdict(list)
    strata["invalid"].extend(rejected)
    collision = defaultdict(list)
    for visit, pair in valid.items():
        if not 32 <= visit < EARLY_LIMIT:
            continue
        gate = tuple(any(row[ARCHIVE_GATE] for row in p["candidates"]) for p in pair)
        names = {
            (False, False): "neither",
            (True, False): "rx0",
            (False, True): "rx1",
            (True, True): "both",
        }
        strata[names[gate]].append(visit)
        for role in separate_roles(pair):
            collision[role].append(visit)

    chosen = {}

    def take(cohort, role, count, pool):
        def key(visit):
            return sha256(encoded([SALT, ident, cohort, role, visit])).digest()

        for visit in sorted(set(pool) - chosen.keys(), key=key)[:count]:
            chosen[visit] = dict(visit=visit, cohort=cohort, stratum=role)

    for role in ("invalid", "neither", "rx0", "rx1", "both"):
        take("systematic", role, 2, strata[role])
    for role, count in (("close", 2), ("separate", 1), ("alias", 1)):
        take("targeted", role, count, collision[role])
    return list(chosen.values()), dict(
        systematic={key: len(items) for key, items in strata.items()},
        targeted={key: len(items) for key, items in collision.items()},
    )


def source_files():
    paths = (
        Path(__file__),
        Path(pilot.__file__),
        Path(frame_coherence.__file__),
        REPORT / "PROTOCOL.md",
        ROOT / "tools/pipeline_eval/frozen/provenance.json",
        ROOT / "tools/pipeline_eval/variants/iq_stream.py",
        ROOT / "tools/pipeline_eval/qualification/original_kernel_trial.py",
        ROOT / "tools/pipeline_eval/qualification/capture_detector_replay.py",
    )
    return {str(path.relative_to(ROOT)): _sha(path) for path in paths}


def freeze(folder):
    if (folder / "input-lock.json").exists():
        raise FileExistsError("use a fresh trial directory")
    cases = {}
    for ident, cpu in CASES.items():
        case = _load_case(ident)
        installed = capture_release.read_capture(case)
        producer = capture_release.producer(case, installed)
        path, digest = lineage.locked_native(case, "capture")
        archive = whole_iq.read(whole_iq.checked(path, digest))
        roster, pools = select(ident, archive)
        cases[ident] = dict(
            root=str(producer.root),
            installed=installed,
            cpu=cpu,
            archive=str(path),
            archive_sha256=digest,
            pools=pools,
            rows=roster,
        )
        print(ident, [(r["visit"], r["stratum"]) for r in roster], flush=True)
    save_json(
        folder / "input-lock.json",
        dict(cases=cases, source=source_files(), python_sha256=_sha(PYTHON), repeats=REPEATS),
    )


def save_receipt(path, value):
    write(path, gzip.compress(encoded(value), mtime=0))


def read_receipt(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def cfo_range(window):
    from leo.analysis.starlink.templates import edge_frequencies_hz

    target = window.target
    center = (
        target["rf_center_hz"] - target["lnb_lo_hz"] - window.acquisition["actual_if_center_hz"]
    )
    offsets = edge_frequencies_hz(target["edge"])
    half = window.sample_rate_hz / 2
    width = min(800_000, center + float(offsets.min()) + half, half - center - float(offsets.max()))
    nyquist = pilot.RATE / pilot.STRIDE / 2
    if width <= 0 or center - width < -nyquist or center + width >= nyquist:
        raise ValueError("capture band extends outside the trial literal CFO search")
    return center - width, center + width


def pilot_payload(value):
    data = asdict(value)
    amplitude = data.pop("amplitude")
    return dict(data, phase=value.phase, amplitude=[amplitude.real, amplitude.imag])


def record_evidence(value):
    return dict(asdict(value), coded=value.coded)


def measured_candidates(training, raw, edge, guesses):
    rows = []
    for guess in guesses:
        measured = pilot.evidence(raw, edge, guess)
        residual = measured if training is raw else pilot.evidence(training, edge, guess)
        admitted = measured.coded and residual.coded and residual.coherent_power >= 9
        rows.append(
            dict(
                pilot=pilot_payload(guess),
                raw=record_evidence(measured),
                search=record_evidence(residual),
                admitted=admitted,
            )
        )
    first = next((guess for guess, row in zip(guesses, rows, strict=True) if row["admitted"]), None)
    return first, rows


def subtraction(samples, edge, primary, mode):
    if mode == "raw_retry":
        return samples
    if mode == "time_shift":
        return samples - pilot.render(edge, primary, shift=17 * 44)
    if mode == "phase_shuffle":
        rotations = np.exp(2j * np.pi * np.random.default_rng(6139).permutation(17) / 17)
        return samples - pilot.render(edge, primary, frame_rotation=rotations)
    return samples - pilot.render(edge, primary)


def lane(samples, edge, limits, mode, *, diagnostics=False):
    start = process_time_ns()
    centers = pilot.scout(samples, edge)
    scout_ns = process_time_ns() - start
    start = process_time_ns()
    guesses = pilot.discover(samples, edge, centers[: pilot.BASE_CENTERS], *limits)
    primary, base = measured_candidates(samples, samples, edge, guesses)
    primary_ns = process_time_ns() - start
    start = process_time_ns()
    followup, retry, offered, retry_centers, removed = None, [], False, [], None
    if mode == "wider":
        offered = len(centers) > pilot.BASE_CENTERS
        extra = centers[pilot.BASE_CENTERS :]
        wider = pilot.discover(
            samples, edge, extra, *limits, rank_start=pilot.BASE_CENTERS, exclude=primary
        )
        followup, retry = measured_candidates(samples, samples, edge, wider)
        retry_centers = extra
    if primary is not None and mode in ("raw_retry", "cancelled", "phase_shuffle", "time_shift"):
        offered = True
        residual = subtraction(samples, edge, primary, mode)
        retry_centers = pilot.scout(residual, edge)[: pilot.BASE_CENTERS]
        second = pilot.discover(residual, edge, retry_centers, *limits, exclude=primary)
        followup, retry = measured_candidates(residual, samples, edge, second)
        old_power = pilot.evidence(samples, edge, primary).coherent_power
        new_power = pilot.evidence(residual, edge, primary).coherent_power
        removed = 1 - new_power / old_power if old_power > 0 else None
    retry_ns = process_time_ns() - start
    independent = {}
    if diagnostics and primary is not None:
        opposite = "upper" if edge == "lower" else "lower"
        opposite_pilot = replace(primary, cfo_hz=-primary.cfo_hz)
        independent.update(
            wrong_edge=record_evidence(pilot.evidence(samples, opposite, primary)),
            opposite_cfo=record_evidence(pilot.evidence(samples, edge, opposite_pilot)),
            zero_cfo=record_evidence(pilot.evidence(samples, edge, replace(primary, cfo_hz=0))),
        )
    return dict(
        primary=pilot_payload(primary) if primary else None,
        secondary=pilot_payload(followup) if followup else None,
        base=base,
        retry=retry,
        offered=offered,
        centers=centers,
        retry_centers=retry_centers,
        held_removal_coherent=removed,
        null_at_primary=independent,
        cpu_parts_ns=dict(scout=scout_ns, primary=primary_ns, retry=retry_ns),
    )


def candidate(window, policy, mode):
    from leo.contracts.fast_scan import FastScanReceiverV1
    from leo.scanner.fast_scan_analysis import analyze_window

    lanes = []

    def detect(window, receivers):
        limits = cfo_range(window)
        edge = window.target["edge"]
        lanes.extend(
            lane(x, edge, limits, mode, diagnostics=mode == "diagnostic")
            for x in pilot.lane_values(window.samples)
        )
        return tuple(FastScanReceiverV1(receiver_id=rx, candidates=()) for rx in receivers)

    status = analyze_window(window, window.receiver_ids, None, policy, detector=detect)
    return dict(status=status.status, reason=status.reason, lanes=lanes)


def controls(window, policy):
    return {
        mode: candidate(window, policy, mode)
        for mode in ("diagnostic", "time_shift", "phase_shuffle")
    }


def planted(edge, condition):
    sign = 1 if edge == "lower" else -1
    primary = pilot.Pilot(735, -1, sign * 193_453.2, 0, 0, 400 + 110j)
    weak = pilot.Pilot(2044, 1, -sign * 187_192.1, 0, 0, -80 + 35j)
    targets = {"two_pilots": (primary, weak), "one_pilot": (primary,), "noise": (), "zero": ()}[
        condition
    ]
    rng = np.random.default_rng(528 if edge == "lower" else 488)
    raw = np.zeros(pilot.SAMPLES, dtype=np.complex64)
    if condition != "zero":
        raw.real = rng.normal(0, 180, pilot.SAMPLES)
        raw.imag = rng.normal(0, 180, pilot.SAMPLES)
    for target in targets:
        raw += pilot.render(edge, target)
    samples = np.repeat(
        np.stack((np.rint(raw.real), np.rint(raw.imag)), axis=-1)[:, None], 2, axis=1
    ).astype("<i2")
    return samples, targets


def synthetic(folder):
    rows = []
    for edge in ("lower", "upper"):
        for condition in ("two_pilots", "one_pilot", "noise", "zero"):
            samples, targets = planted(edge, condition)
            raw = pilot.lane_values(samples)[0]
            modes = (
                "primary",
                "raw_retry",
                "wider",
                "cancelled",
                "time_shift",
                "phase_shuffle",
                "diagnostic",
            )
            outputs = {
                mode: lane(raw, edge, (-800_000, 800_000), mode, diagnostics=mode == "diagnostic")
                for mode in modes
            }
            rows.append(
                dict(
                    edge=edge,
                    condition=condition,
                    iq_sha256=sha256(samples.tobytes()).hexdigest(),
                    targets=[pilot_payload(target) for target in targets],
                    modes=outputs,
                )
            )
    save_receipt(folder / "controls.json.gz", rows)


def timed(call):
    start, wall = process_time_ns(), perf_counter_ns()
    data = call()
    return data, dict(cpu_ns=process_time_ns() - start, wall_ns=perf_counter_ns() - wall)


def stable(value):
    return dict(
        value,
        lanes=[{k: v for k, v in lane.items() if k != "cpu_parts_ns"} for lane in value["lanes"]],
    )


def measure(window, policy, index):
    timing, original, outputs = [], None, {}
    for repeat in range(-1, REPEATS):
        rotation = (repeat + index) % len(STAGES)
        for order, mode in enumerate(STAGES[rotation:] + STAGES[:rotation]):
            if mode == "original":

                def baseline():
                    result, probes = scan_capture_window(window, window.receiver_ids, policy)
                    return dict(public=result.model_dump(mode="json"), probes=probes)

                current, elapsed = timed(baseline)
                consistent = original is None or original == current
                original = current
            else:
                current, elapsed = timed(lambda mode=mode: candidate(window, policy, mode))
                consistent = mode not in outputs or stable(outputs[mode]) == stable(current)
                outputs[mode] = current
                elapsed["parts"] = [result["cpu_parts_ns"] for result in current["lanes"]]
            if repeat >= 0:
                timing.append(
                    dict(mode=mode, repeat=repeat, order=order, stable=consistent, **elapsed)
                )
    return dict(modes=outputs, timing=timing, original=original, controls=controls(window, policy))


def worker(folder, ident):
    lockfile = folder / "input-lock.json"
    lock = whole_iq.read(lockfile)
    cfg = lock["cases"][ident]
    if source_files() != lock["source"] or os.sched_getaffinity(0) != {cfg["cpu"]}:
        raise ValueError("replay requires the frozen sources and CPU")
    whole_iq.checked(PYTHON, lock["python_sha256"])
    case = _load_case(ident)
    capture, policy, producer = lineage.source_lineage(case)
    if capture != cfg["installed"] or producer["capture"]["root"] != cfg["root"]:
        raise ValueError("replay imported a different capture producer")
    rows = []
    for index, selected in enumerate(cfg["rows"]):
        visit = selected["visit"]
        try:
            segment, manifest, window = decode(case, visit)
            row = dict(
                selected,
                segment=segment,
                manifest_sha256=manifest,
                iq_sha256=window.iq_sha256,
                **measure(window, policy, index),
            )
        except (OSError, RuntimeError, ValueError) as error:
            row = dict(selected, failure=f"{type(error).__name__}: {error}")
        rows.append(row)
        print(
            ident,
            visit,
            selected["stratum"],
            row.get("failure", row.get("original", {}).get("public", {}).get("status")),
            flush=True,
        )
    save_receipt(
        folder / f"{ident}-predictions.json.gz",
        dict(
            case=ident,
            cpu=cfg["cpu"],
            producer=producer,
            input_lock_sha256=_sha(lockfile),
            rows=rows,
        ),
    )


def run(folder):
    lockfile = folder / "input-lock.json"
    lock = whole_iq.read(lockfile)
    for case in lock["cases"]:
        if (folder / f"{case}-predictions.json.gz").exists():
            raise FileExistsError("use a fresh trial directory")

    def group(cpu):
        for ident, cfg in lock["cases"].items():
            if cfg["cpu"] != cpu:
                continue
            env = os.environ | THREAD_ENV | {"PYTHONPATH": f"{cfg['root']}:{ROOT}"}
            command = [
                "taskset",
                "-c",
                str(cpu),
                str(PYTHON),
                "-u",
                "-m",
                __spec__.name,
                "worker",
                str(folder),
                ident,
            ]
            subprocess.run(command, cwd=ROOT, env=env, timeout=480, check=True)

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(group, sorted(set(CASES.values()))))
    synthetic(folder)
    names = [
        "input-lock.json",
        "controls.json.gz",
        *(f"{case}-predictions.json.gz" for case in lock["cases"]),
    ]
    save_json(
        folder / "prediction-lock.json", dict(files={name: _sha(folder / name) for name in names})
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "run", "worker"))
    parser.add_argument("folder", type=Path)
    parser.add_argument("case", nargs="?")
    args = parser.parse_args()
    folder = local_output(args.folder)
    if args.action == "worker":
        worker(folder, args.case)
    else:
        if os.sched_getaffinity(0) - set(CASES.values()):
            raise ValueError("pin the trial launcher to CPUs 12 and 13")
        {"freeze": freeze, "run": run}[args.action](folder)


if __name__ == "__main__":
    main()
