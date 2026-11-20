"""Replay and time ranked fractional stop policies on sixteen sealed saved windows."""

import argparse
import gzip
import os
import subprocess
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import ROOT, THREAD_ENV, encoded, local_output, save_json, write
from ..variants import fine_search, first_gate, prepared_hotpath_peaks
from ..variants.original_kernel import PersistentGrid
from . import fine_search_trial as prior
from .full_v5_check import _load_case, _sha

REPORT = prior.REPORT.parents[1] / "retry-and-transfer/first-gate-raw"
PRIOR_SHA = "905317d53cb7b41a341bc6c121bc99bddf9caf4da1e666f1e3580111184c4895"
MODES = dict(full=None, first=1, second=2)
CPUS = {"DS26-0237": 6, "DS29-0082": 7, "DS29-0174": 6, "DS29-0519": 7}
REPEATS = 5


def freeze(work):
    previous = prior.REPORT / "qualification-lock.json"
    files = whole_iq.read(whole_iq.checked(previous, PRIOR_SHA))["files"]
    path = whole_iq.checked(previous.with_name("input-lock.json"), files["input-lock.json"])
    lock = whole_iq.read(path)
    if lock["libs"]["fine"]["sha256"] != (
        "4d0b38f6c10aedba4f585e006fda5683ac78eafbc45be96a3609acf786b0458a"
    ):
        raise ValueError("fine baseline library differs from qualification")
    for name, cfg in lock["cases"].items():
        if len(cfg["rows"]) != 4:
            raise ValueError("held window roster changed")
        for relative, digest in first_gate.PRODUCER_FILES.items():
            if cfg["sources"][str(Path(cfg["root"]) / relative)] != digest:
                raise ValueError("installed rank or GLRT seam differs from its qualified source")
        cfg["cpu"] = CPUS[name]
    lock["sources"].update(
        {
            str(p): _sha(p)
            for p in (Path(__file__), Path(first_gate.__file__), REPORT / "PROTOCOL.md")
        }
    )
    lock.update(modes=MODES, repeats=REPEATS, input_authority=files["input-lock.json"])
    work.mkdir()
    for target in (work / "input-lock.json", REPORT / "input-lock.json"):
        if target.exists():
            raise FileExistsError(target)
        save_json(target, lock)


def cutoff_projections(stock, passes):
    public, probes = stock
    if passes is None:
        return stock

    def pass_margin(row):
        margin = row["fractional_margin"]
        return margin is not None and margin >= first_gate.GATE

    return (
        public
        | {
            "receivers": [
                receiver
                | {
                    "candidates": list(
                        first_gate.prefix(receiver["candidates"], passes, pass_margin)
                    )
                }
                for receiver in public["receivers"]
            ]
        },
        [
            probe
            | {
                "candidates": list(
                    first_gate.prefix(
                        probe["candidates"],
                        passes,
                        lambda row: row["passed_fractional_margin_gate"],
                    )
                )
            }
            for probe in probes
        ],
    )


def compare_attempts(full, actual, passes):
    witness = []
    occurrence = set()
    for stock, observed in zip(full, actual, strict=True):
        receiver, probe, available, candidates = stock
        kept = (
            candidates
            if passes is None
            else tuple(first_gate.prefix(candidates, passes, first_gate.fractional_pass))
        )
        payload = encoded([asdict(r) for r in kept])
        if observed[:3] != stock[:3] or encoded([asdict(r) for r in observed[3]]) != payload:
            raise ValueError("actual physical attempt differs from the ranked cutoff")
        witness.append(
            dict(
                receiver=receiver,
                probe=probe,
                retry=(receiver, probe) in occurrence,
                available=available,
                scored=len(kept),
                passing_ranks=[r.candidate_rank for r in kept if first_gate.fractional_pass(r)],
                retained_ranks=[r.candidate_rank for r in kept],
                payload_sha256=sha256(payload).hexdigest(),
            )
        )
        occurrence.add((receiver, probe))
    return witness


def worker(work, name):
    from leo.analysis.starlink import acquisition
    from leo.scanner import fast_scan_detector

    source = whole_iq.checked(work / "input-lock.json", _sha(REPORT / "input-lock.json"))
    lock = whole_iq.read(source)
    cfg = lock["cases"][name]
    if os.sched_getaffinity(0) != {cfg["cpu"]}:
        raise ValueError("wrong pinned CPU for the matched detector trial")
    whole_iq.checked(prior.original.PYTHON, lock["python_sha256"])
    for path, digest in (lock["sources"] | cfg["sources"]).items():
        whole_iq.checked(Path(path), digest)
    if Path(fast_scan_detector.__file__) != Path(cfg["root"]) / "leo/scanner/fast_scan_detector.py":
        raise ValueError("wrong installed evaluation binding")
    libs = {
        name: whole_iq.checked(Path(info["path"]), info["sha256"])
        for name, info in lock["libs"].items()
    }
    case = _load_case(name)
    exact = prior.previous.exact
    _, policy, lineage = exact.lineage.source_lineage(case)
    if (lineage["capture"]["root"], lineage["capture"]["input_manifest_sha256"]) != (
        cfg["root"],
        cfg["input_manifest"],
    ):
        raise ValueError("capture release changed")
    grid = PersistentGrid(libs["prepared"])
    fine = fine_search.FineSearch(libs["fine"], acquisition)
    if not fine.compatible:
        raise ValueError("qualified fine-search arithmetic compatibility failed")
    modes = {
        mode: first_gate.GateStop(fast_scan_detector, passes) for mode, passes in MODES.items()
    }

    def measure(mode, window):
        gate = modes[mode]
        grid.calls.clear()
        gate.attempts.clear()
        before = (fine.calls, fine.fallbacks)
        with gate.route():
            output, time = prior.previous.sample(window, policy)
        if not grid.calls or not all(r["applied"] for r in grid.calls):
            raise ValueError("original complete coarse transform was not applied")
        fine_counts = tuple(
            now - prev for now, prev in zip((fine.calls, fine.fallbacks), before, strict=True)
        )
        return (
            output,
            tuple(gate.attempts),
            time
            | dict(
                coarse_grids=len(grid.calls),
                fine_calls=fine_counts[0],
                fine_fallbacks=fine_counts[1],
            ),
        )

    rows = []
    try:
        for index, fixture in enumerate(cfg["rows"]):
            segment, manifest, window = prior.original.decode(case, fixture["visit"])
            if (segment, manifest, window.iq_sha256) != (
                fixture["segment"],
                fixture["manifest"],
                fixture["iq_sha256"],
            ):
                raise ValueError("decoded source differs from the sealed panel")
            archive_verified, _ = prior.previous.sample(window, policy)
            if archive_verified[1] != fixture["probes"]:
                raise ValueError("installed control differs from frozen archive factors")
            with (
                exact.refiners(libs),
                grid.route(acquisition, exact.starts.screen_module()),
                patch.object(
                    acquisition, "_retain_score_map_peaks", prepared_hotpath_peaks.retained_peaks
                ),
                fine.route(),
            ):
                stock, full_attempts, full_time = measure("full", window)
                if encoded(stock) != encoded(archive_verified):
                    raise ValueError("prepared control changed the original installed detector")

                def audit(
                    mode, output, actual, time, stock=stock, scope=full_time, full=full_attempts
                ):
                    if encoded(output) != encoded(cutoff_projections(stock, MODES[mode])):
                        raise ValueError(
                            "public or native probes differ from the numerical rank cutoff"
                        )
                    if any(
                        time[k] != scope[k]
                        for k in ("coarse_grids", "fine_calls", "fine_fallbacks")
                    ):
                        raise ValueError("scoring prefix changed acquisition scope")
                    return compare_attempts(full, actual, MODES[mode])

                witnesses = {"full": audit("full", stock, full_attempts, full_time)}
                for mode in ("first", "second"):
                    witnesses[mode] = audit(mode, *measure(mode, window))
                samples = []
                options = list(MODES)
                for rep in range(REPEATS):
                    start = (index + rep) % len(options)
                    order = options[start:] + options[:start]
                    if rep % 2:
                        order.reverse()
                    for ordinal, mode in enumerate(order):
                        output, attempts, time = measure(mode, window)
                        if audit(mode, output, attempts, time) != witnesses[mode]:
                            raise ValueError("attempt witness changed after warm-up")
                        samples.append(time | dict(mode=mode, rep=rep, ordinal=ordinal))
            rows.append(
                dict(
                    visit=fixture["visit"],
                    kind=fixture["kind"],
                    iq_sha256=window.iq_sha256,
                    attempts=witnesses,
                    samples=samples,
                )
            )
            print(name, fixture["visit"], fixture["kind"], flush=True)
    finally:
        grid.clear_cache()
    write(
        work / f"{name}.json.gz",
        gzip.compress(
            encoded(
                dict(
                    id=name,
                    cpu=cfg["cpu"],
                    input_lock_sha256=_sha(source),
                    rows=rows,
                )
            ),
            mtime=0,
        ),
    )


def run(work, names):
    lock = whole_iq.read(work / "input-lock.json")
    for name in names:
        cfg = lock["cases"][name]
        env = os.environ | THREAD_ENV | dict(PYTHONPATH=f"{cfg['root']}:{ROOT}")
        subprocess.run(
            [
                "taskset",
                "-c",
                str(cfg["cpu"]),
                str(prior.original.PYTHON),
                "-Bu",
                "-m",
                __spec__.name,
                "worker",
                str(work),
                name,
            ],
            cwd=ROOT,
            env=env,
            check=True,
            timeout=150,
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "worker", "run"))
    parser.add_argument("work", type=local_output)
    parser.add_argument("cases", nargs="*", choices=tuple(CPUS))
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.work)
    elif args.action == "worker":
        worker(args.work, args.cases[0])
    else:
        run(args.work, args.cases)


if __name__ == "__main__":
    main()
