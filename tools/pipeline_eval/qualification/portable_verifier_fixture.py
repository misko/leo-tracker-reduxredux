"""Freeze installed raw-IQ verification on physical, gate-adjacent and tied visits."""

import argparse
import math
import os
import subprocess
from collections import defaultdict, deque
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from struct import Struct
from time import process_time_ns
from unittest.mock import patch

import numpy as np

from .. import whole_iq
from ..__main__ import ROOT, THREAD_ENV, local_output, save_json
from ..variants import prepared_hotpath_peaks
from ..variants.original_kernel import PersistentGrid
from . import capture_exact_trial as exact
from . import original_kernel_trial as original
from . import parallel_acquisition_source as archives
from . import prepared_hotpath_trial as prepared
from .full_v5_check import _load_case, _sha
from .portable_fine_fixture import parent_lock

REPORT = ROOT / "reports/2026_11_19_receiver_screening/coarse-and-navigation/portable-verifier"
VISITS = {
    "DS26-0237": {1561: "closest recorded above gate", 3235: "closest recorded below gate"},
    "DS29-0082": {141: "dual positive", 152: "no pass", 5855: "closest recorded above gate"},
    "DS29-0519": {153: "equivalent candidate tie"},
}
HEADER = Struct("<8sI")
VISIT_HEADER = Struct("<II")
GROUP_HEADER = Struct("<IIddd")
SEED = Struct("<IIdd")


def oracle(acquisition, detector, window, policy):
    acquire = detector.acquire_symbolwise
    fft, peak = acquisition._normalized_frame_scores_fft, acquisition._quadratic_peak
    conditioned, refine = acquisition._conditioned_frame_scores, detector.refine_glrt64_epochs
    groups = []

    def observe_acquire(values, rate, calibration, *, edge, config):
        seeds = []

        def observe_fft(values, template, rate, epoch, grid, symbols, *, transform_size):
            if transform_size != 20_000 or not 2 <= len(grid) <= 321:
                raise ValueError("fixture left the supported original fine geometry")
            scores = fft(values, template, rate, epoch, grid, symbols, transform_size=20_000)
            seeds.append(
                dict(
                    epoch=int(epoch),
                    bins=len(grid),
                    absolute=grid[0],
                    fine_score_sha256=sha256(np.asarray(scores, dtype="<f8")).hexdigest(),
                )
            )
            return scores

        def observe_peak(grid, scores, index):
            value = peak(grid, scores, index)
            seeds[-1].update(residual=grid[0], fine_winner=index, fine_peak=value)
            return value

        def observe_conditioned(values, template, rate, epoch, grid):
            scores = conditioned(values, template, rate, epoch, grid)
            residual = acquisition._bounded_grid(
                max(config.residual_cfo_min_hz, seeds[-1]["fine_peak"] - 2_000),
                min(config.residual_cfo_max_hz, seeds[-1]["fine_peak"] + 2_000),
                100,
            )
            if tuple(calibration.center_hz + f for f in residual) != grid:
                raise ValueError("original candidate used a different conditioned grid")
            winner = max(
                range(len(grid)), key=lambda i: (scores[i], -abs(residual[i]), -residual[i])
            )
            seeds[-1].update(
                conditioned_grid=grid,
                conditioned_scores=scores,
                conditioned_winner=winner,
                acquired=grid[winner],
            )
            return scores

        start = process_time_ns()
        with (
            patch.object(acquisition, "_normalized_frame_scores_fft", observe_fft),
            patch.object(acquisition, "_quadratic_peak", observe_peak),
            patch.object(acquisition, "_conditioned_frame_scores", observe_conditioned),
        ):
            result = acquire(values, rate, calibration, edge=edge, config=config)
        if not seeds or len(seeds) != len(result.candidates):
            raise ValueError("a fine candidate departed from the retained coarse seed ledger")
        groups.append(
            dict(
                lane=int(calibration.receiver_id),
                center=calibration.center_hz,
                minimum=config.residual_cfo_min_hz,
                maximum=config.residual_cfo_max_hz,
                seeds=seeds,
                ranked=[asdict(c) for c in result.candidates],
                acquire_cpu_ns=process_time_ns() - start,
            )
        )
        return result

    def observe_refinement(values, rate, **kwargs):
        start = process_time_ns()
        stages = refine(values, rate, **kwargs)
        group = groups[-1]
        candidates = defaultdict(deque)
        for i, seed in enumerate(group["seeds"]):
            candidates[(seed["epoch"], seed["acquired"])].append(i)
        group["by_rank"] = []
        for obj, entry, integer in zip(
            group["ranked"], stages, kwargs["expected_integer_scores"], strict=True
        ):
            key = (obj["refined_epoch_sample"], obj["absolute_cfo_hz"])
            index = candidates[key].popleft()
            group["by_rank"].append(index)
            group["seeds"][index].update(
                ranked=obj, integer=asdict(integer), fractional=asdict(entry)
            )
        group["fractional_cpu_ns"] = process_time_ns() - start
        return stages

    with (
        patch.object(detector, "acquire_symbolwise", observe_acquire),
        patch.object(detector, "refine_glrt64_epochs", observe_refinement),
    ):
        packet, _ = prepared.sample(window, policy)
    if (
        not groups
        or {g["lane"] for g in groups} != {0, 1}
        or not all("by_rank" in g for g in groups)
    ):
        raise ValueError("original detector did not verify both physical receiver lanes")
    for group in groups:
        del group["ranked"]
    return packet, groups


def archive_probes(case):
    if case in archives.ORIGINAL:
        doc, _ = archives.original_reference(case)
        chosen = set(VISITS[case])
        probes = defaultdict(list)
        for row in doc["source"]["probes"]:
            if row["visit_index"] in chosen:
                probes[row["visit_index"]].append(row)
        return probes
    return {r["visit"]: r["probes"] for r in parent_lock()["cases"][case]["rows"]}


def freeze(folder, case, cpu):
    from leo.analysis.starlink import acquisition
    from leo.scanner import fast_scan_detector

    parent = parent_lock()
    cfg = parent["cases"][case]
    if not Path(acquisition.__file__).is_relative_to(cfg["root"]) or os.sched_getaffinity(0) != {
        cpu
    }:
        raise ValueError("golden scores require the authenticated producer and CPU")
    for filename, digest in (parent["sources"] | cfg["sources"]).items():
        whole_iq.checked(Path(filename), digest)
    library = parent["libs"]["prepared"]
    grid = PersistentGrid(whole_iq.checked(Path(library["path"]), library["sha256"]))
    entry = _load_case(case)
    _, policy, source = exact.lineage.source_lineage(entry)
    templates = tuple(
        np.asarray(
            acquisition.qin_edge_pilot_frame(10_000_000, cfg["edge"], symbol_roll=roll),
            dtype="<c16",
        )
        for roll in (0, acquisition.CONTROL_SYMBOL_ROLL)
    )
    expected = archive_probes(case)
    records = []
    folder.mkdir(parents=True)
    raw_path = folder / "capture.bin"
    try:
        with (
            raw_path.open("xb") as binary,
            grid.route(acquisition, exact.starts.screen_module()),
            patch.object(
                acquisition, "_retain_score_map_peaks", prepared_hotpath_peaks.retained_peaks
            ),
        ):
            binary.write(HEADER.pack(b"LEOVRF01", len(VISITS[case])))
            for template in templates:
                template.tofile(binary)
            for visit, kind in VISITS[case].items():
                segment, digest, window = original.decode(entry, visit)
                raw = np.ascontiguousarray(window.samples, dtype="<i2")
                if "sha256:" + sha256(raw).hexdigest() != window.iq_sha256:
                    raise ValueError("physical CI16 bytes differ from signed archive")
                packet, groups = oracle(acquisition, fast_scan_detector, window, policy)
                for fresh, signed in zip(packet[1], expected[visit], strict=True):
                    for left, right in zip(fresh["candidates"], signed["candidates"], strict=True):
                        if (
                            left["integer_epoch_sample"],
                            left["passed_fractional_margin_gate"],
                        ) != (
                            right["integer_epoch_sample"],
                            right["passed_fractional_margin_gate"],
                        ):
                            raise ValueError(
                                "stock verification disagrees with the archived discrete packet"
                            )
                        if left["fractional_margin"] is not None and not math.isclose(
                            left["fractional_margin"], right["fractional_margin"], abs_tol=1e-10
                        ):
                            raise ValueError(
                                "stock verification disagrees with the archived margin"
                            )
                binary.write(VISIT_HEADER.pack(visit, len(groups)))
                raw.tofile(binary)
                for group in groups:
                    binary.write(
                        GROUP_HEADER.pack(
                            group["lane"],
                            len(group["seeds"]),
                            group["center"],
                            group["minimum"],
                            group["maximum"],
                        )
                    )
                    for fields in group["seeds"]:
                        binary.write(
                            SEED.pack(
                                *(fields[k] for k in ("epoch", "bins", "absolute", "residual"))
                            )
                        )
                records.append(
                    dict(
                        visit=visit,
                        purpose=kind,
                        segment=segment,
                        manifest=digest,
                        iq_sha256=window.iq_sha256,
                        archived=expected[visit],
                        groups=groups,
                    )
                )
                print(case, visit, [len(g["seeds"]) for g in groups], flush=True)
    finally:
        grid.clear_cache()
    save_json(
        folder / "golden.json",
        dict(
            case=case,
            edge=cfg["edge"],
            producer=cfg["root"],
            capture_manifest=source["capture"]["input_manifest_sha256"],
            binary_sha256=_sha(raw_path),
            template_sha256=[sha256(t).hexdigest() for t in templates],
            visits=records,
        ),
    )


def run(work, cpu):
    for case, cfg in parent_lock()["cases"].items():
        if case in VISITS:
            subprocess.run(
                [
                    "taskset",
                    "-c",
                    str(cpu),
                    original.PYTHON,
                    "-B",
                    "-m",
                    __spec__.name,
                    work / case,
                    str(cpu),
                    case,
                ],
                env=os.environ | THREAD_ENV | {"PYTHONPATH": f"{cfg['root']}:{ROOT}"},
                timeout=180,
                check=True,
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=local_output)
    parser.add_argument("cpu", type=int)
    parser.add_argument("case", nargs="?", choices=VISITS)
    args = parser.parse_args()
    if args.case is None:
        run(args.folder, args.cpu)
    else:
        freeze(args.folder, args.case, args.cpu)
