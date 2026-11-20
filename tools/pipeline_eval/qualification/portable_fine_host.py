"""Exercise the normal original capture detector with a guarded portable fine-CFO port."""

import argparse
import os
import subprocess
from collections import Counter
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import ROOT, THREAD_ENV, local_output, save_json
from ..variants import fine_search, portable_fine, prepared_hotpath_peaks
from ..variants.original_kernel import PersistentGrid
from . import capture_exact_trial as exact
from . import original_kernel_trial as original
from . import prepared_hotpath_trial as prepared
from .full_v5_check import _load_case, _sha
from .portable_fine_fixture import parent_lock

REPEATS = 3


def compare(reference, actual, maxima, field=""):
    if type(reference) is not type(actual):
        raise ValueError(f"type changed at {field}")
    if isinstance(reference, dict):
        if reference.keys() != actual.keys():
            raise ValueError(f"fields changed at {field}")
        for key in reference:
            compare(reference[key], actual[key], maxima, key)
    elif isinstance(reference, (tuple, list)):
        for old, new in zip(reference, actual, strict=True):
            compare(old, new, maxima, field)
    elif isinstance(reference, float) and actual != reference:
        limit = 1e-8 if field.endswith("_hz") else 1e-10
        delta = abs(actual - reference)
        if not delta <= limit:
            raise ValueError(f"{field} changed from {reference!r} to {actual!r}")
        maxima[field] = max(delta, maxima[field])
    elif reference != actual:
        raise ValueError(f"{field} changed from {reference!r} to {actual!r}")


def worker(work, ident, library, cpu):
    from leo.analysis.starlink import acquisition

    lock = parent_lock()
    cfg = lock["cases"][ident]
    if os.sched_getaffinity(0) != {cpu} or not Path(acquisition.__file__).is_relative_to(
        cfg["root"]
    ):
        raise ValueError(
            "normal-host measurement needs the pinned original capture producer and CPU"
        )
    for path, digest in (lock["sources"] | cfg["sources"]).items():
        whole_iq.checked(Path(path), digest)
    libraries = {
        name: whole_iq.checked(Path(info["path"]), info["sha256"])
        for name, info in lock["libs"].items()
    }
    case = _load_case(ident)
    _, policy, source = exact.lineage.source_lineage(case)
    if source["capture"]["input_manifest_sha256"] != cfg["input_manifest"]:
        raise ValueError("capture producer input differs from the frozen panel")
    grid = PersistentGrid(libraries["prepared"])
    fallback = fine_search.FineSearch(libraries["fine"], acquisition)
    if not fallback.compatible:
        raise ValueError("exact pruned fallback failed its runtime arithmetic sentinel")
    fine = portable_fine.PortableFine(library, acquisition, fallback.score)
    modes = dict(installed=nullcontext, pruned=fallback.route, portable=fine.route)
    maxima, rows = Counter(), []
    try:
        for offset, wanted in enumerate(cfg["rows"]):
            visit = wanted["visit"]
            segment, digest, window = original.decode(case, visit)
            if (segment, digest, window.iq_sha256) != (
                wanted["segment"],
                wanted["manifest"],
                wanted["iq_sha256"],
            ):
                raise ValueError("captured visit differs from the frozen original archive")
            with (
                exact.refiners(libraries),
                grid.route(acquisition, exact.starts.screen_module()),
                patch.object(
                    acquisition, "_retain_score_map_peaks", prepared_hotpath_peaks.retained_peaks
                ),
            ):
                reference, _ = prepared.sample(window, policy)
                if reference[1] != wanted["probes"]:
                    raise ValueError("installed numeric packet changed the fixed visit evidence")
                elapsed = []
                for repetition in range(REPEATS):
                    order = tuple(modes)
                    shift = (offset + repetition) % len(order)
                    for mode in order[shift:] + order[:shift]:
                        previous = (fine.calls, fine.guarded, fine.unsupported)
                        with modes[mode]():
                            packet, timing = prepared.sample(window, policy)
                        compare(reference, packet, maxima)
                        elapsed.append(
                            dict(
                                mode=mode,
                                repeat=repetition,
                                exact=packet == reference,
                                portable_calls=fine.calls - previous[0],
                                guard_fallbacks=fine.guarded - previous[1],
                                unsupported_fallbacks=fine.unsupported - previous[2],
                                **timing,
                            )
                        )
                if any(not row["portable_calls"] for row in elapsed if row["mode"] == "portable"):
                    raise ValueError("normal detector did not exercise the offered portable scorer")
                rows.append(dict(visit=visit, kind=wanted["kind"], timings=elapsed))
            print(ident, visit, len(elapsed), flush=True)
    finally:
        grid.clear_cache()
    save_json(
        work / ident / "normal-detector.json",
        dict(
            case=ident,
            cpu=cpu,
            rows=rows,
            library_sha256=_sha(library),
            max_absolute_float_delta_by_field=dict(maxima),
        ),
    )


def run(work, library, cpu):
    for ident, cfg in parent_lock()["cases"].items():
        env = os.environ | THREAD_ENV | {"PYTHONPATH": f"{cfg['root']}:{ROOT}"}
        subprocess.run(
            [
                "taskset",
                "-c",
                str(cpu),
                original.PYTHON,
                "-B",
                "-m",
                __spec__.name,
                str(work),
                str(library),
                str(cpu),
                ident,
            ],
            env=env,
            check=True,
            timeout=180,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("library", type=Path)
    parser.add_argument("cpu", type=int)
    parser.add_argument("case", nargs="?")
    args = parser.parse_args()
    if args.case is None:
        run(args.work, args.library, args.cpu)
    else:
        worker(args.work, args.case, args.library, args.cpu)
