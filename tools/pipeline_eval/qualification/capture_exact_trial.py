"""Qualify the batched coarse FFT and compiled capture stages on held IQ."""

import argparse
import gzip
import importlib.util
import os
import subprocess
from contextlib import ExitStack, contextmanager
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import numpy as np

from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import capture_batched_fft, capture_fft, conditioned_cfo_bank, refine_bank
from . import capture_detector_lineage as lineage
from . import capture_fft_trial as stages
from . import capture_runtime as prior
from . import capture_starts as starts
from .conditioned_cfo_eval import _test_signal
from .full_v5_check import _load_case, _sha

REPORT = ROOT / "reports/2026_11_19_receiver_screening/antenna-confirmation/capture-exact"
WORK = prior.WORK.with_name("capture-exact-v2")
CASES = dict(zip(prior.CASES, ((2, 19), (7, 72), (3, 13), (12, 157)), strict=True))
CONTROLS = frozenset(("DS26-0237", "DS29-0082"))
MODES = ("installed", "fft64", "batched32", "combined")
CPUS = dict(zip(CASES, (0, 0, 1, 1), strict=True))


def sources(work):
    batched, command = capture_batched_fft.build(work)
    libraries = dict(
        fft64=capture_fft.build(work / "capture_fft64.so"),
        batched32=batched,
        cfo=work / "conditioned.so",
        fused=work / "fused.so",
    )
    conditioned_cfo_bank.compile_bank(libraries["cfo"])
    refine_bank.compile_bank(libraries["fused"])
    paths = (
        Path(__file__),
        Path(stages.__file__),
        Path(starts.__file__),
        Path(capture_batched_fft.__file__),
        Path(capture_fft.__file__),
        capture_fft.SOURCE,
        capture_fft.SOURCE.with_name("folded_bank.c"),
        Path(conditioned_cfo_bank.__file__),
        conditioned_cfo_bank.SOURCE,
        Path(refine_bank.__file__),
        refine_bank.SOURCE,
        work / "folded_bank.c",
        REPORT / "PROTOCOL.md",
        Path("/usr/lib/x86_64-linux-gnu/libfftw3.so.3"),
        Path("/usr/lib/x86_64-linux-gnu/libfftw3f.so.3"),
    )
    return dict(
        libraries={k: dict(path=str(p), sha256=_sha(p)) for k, p in libraries.items()},
        batched_build=command,
        sources={str(p): _sha(p) for p in paths},
    )


def freeze(work):
    work.mkdir()
    releases = sources(work)
    lock = prior.read(prior.checked(starts.REPORT / "result-lock.json", prior.PRIOR_PIN))["files"]
    upstream = prior.read(prior.checked(starts.REPORT / "input-lock.json", lock["input-lock.json"]))
    for p, h in upstream["sources"].items():
        prior.checked(Path(p), h)
    oracle = prior.read(starts.ORACLE / "input-lock.json")["cases"]
    cases = {}
    for name, numbers in CASES.items():
        filename = f"{name}-capture.json.gz"
        old = prior.decompress(prior.checked(starts.REPORT / filename, lock[filename]))
        refs = {r["visit"]: r["capture"]["probes"] for r in old["capture"]}
        rows = {r["visit"]: r for r in oracle[name]["selected"]}
        selected = [dict(rows[n], sealed_probes=refs[n]) for n in numbers]
        if sorted(r["kind"] for r in selected) != ["matched", "miss"]:
            raise ValueError("prospective held roster changed")
        runtime = Path(old["producer"]["python"])
        cases[name] = dict(
            rows=selected,
            root=upstream["cases"][name],
            cpu=CPUS[name],
            python=str(runtime),
            python_sha256=_sha(runtime),
            controls=name in CONTROLS,
        )
    save_json(
        work / "source-lock.json", dict(cases=cases, **releases, previous_lock=prior.PRIOR_PIN)
    )


@contextmanager
def refiners(bind):
    from leo.analysis.starlink import acquisition, fast_scan_scores
    from leo.scanner import fast_scan_detector

    cfo = conditioned_cfo_bank.ConditionedBank(bind["cfo"], acquisition)
    fused = refine_bank.RefinementBank(bind["fused"], fast_scan_scores)
    if not fused.compatible:
        raise ValueError("installed runtime did not pass the fused arithmetic sentinel")
    with ExitStack() as scope:
        for module, name, function in (
            (acquisition, "_conditioned_frame_scores", cfo.score),
            (
                fast_scan_detector,
                "acquire_symbolwise",
                cfo.guarded_acquisition(fast_scan_detector.acquire_symbolwise),
            ),
            (fast_scan_detector, "conditioned_glrt64_scores", fused.integer),
            (fast_scan_scores, "conditioned_glrt64_scores", fused.integer),
            (fast_scan_scores, "conditioned_glrt64_score", fused.fractional),
        ):
            scope.enter_context(patch.object(module, name, function))
        yield


def trial(window, policy, mode, libs):
    with ExitStack() as scoped:
        grid = None
        if mode != "installed":
            grid = capture_fft.FullGrid(libs["batched32" if mode == "combined" else mode])
        if mode == "combined":
            scoped.enter_context(refiners(libs))
        return stages.detector(window, policy, grid)


def grid_samples(window, policy, libs):
    """Audit every actual primary grid cell, outside the complete detector clock."""
    from leo.analysis.starlink import acquisition

    base = acquisition._folded_anchor_score_grid
    grid = capture_fft.FullGrid(libs["batched32"])
    screen = starts.screen_module()
    outcomes = []

    def compare(args, exact):
        approximate = np.asarray(grid.score_grid(acquisition, base, *args))
        absolute = np.abs(approximate - exact)
        outcomes.append(
            dict(
                cells=absolute.size,
                max_abs=float(absolute.max()),
                rms=float(np.sqrt(np.mean(absolute**2))),
                exact_cells=int(np.count_nonzero(absolute == 0)),
                cfo_rows=absolute.shape[0],
                epochs=absolute.shape[1],
                anchors=len(args[4]),
                dispatch=grid.calls[-1],
            )
        )

    def dense(*args):
        exact = base(*args)
        compare(args, exact)
        return exact

    if screen is None:
        with patch.object(acquisition, "_folded_anchor_score_grid", dense):
            starts.coarse_prefix(window, policy)
    else:
        old = screen.acquire

        def screened(module, args, *params, **kwargs):
            compare(args, base(*args))
            return old(module, args, *params, **kwargs)

        with patch.object(screen, "acquire", screened):
            starts.coarse_prefix(window, policy)
    if len(outcomes) != 2:
        raise ValueError("independent grid audit did not cover two primary physical lanes")
    return outcomes


def worker(work, ident):
    lock = prior.read(work / "source-lock.json")
    for path, digest in lock["sources"].items():
        prior.checked(Path(path), digest)
    libs = {k: prior.checked(Path(v["path"]), v["sha256"]) for k, v in lock["libraries"].items()}
    cfg = lock["cases"][ident]
    if os.sched_getaffinity(0) != {cfg["cpu"]}:
        raise ValueError("installed replay launched off its declared CPU")
    case = _load_case(ident)
    capture, policy, producer = lineage.source_lineage(case)
    if producer["capture"]["root"] != cfg["root"]["producer"]:
        raise ValueError("original acquisition source differs")
    for f, h in cfg["root"]["sources"].items():
        prior.checked(Path(f), h)
    windows = [starts.hinted_glrt_trial.load_selected(case, r) for r in cfg["rows"]]
    fixture = [
        (str(r["visit"]), "held", w, r["sealed_probes"])
        for w, r in zip(windows, cfg["rows"], strict=True)
    ]
    if cfg["controls"]:
        sample = windows[0]
        samples = np.zeros_like(sample.samples)
        zero = replace(
            sample, samples=samples, iq_sha256="sha256:" + sha256(samples.tobytes()).hexdigest()
        )
        signed = 720_000 if capture["edge"] == "lower" else -720_000
        planted = _test_signal(zero, ((735, signed, 128),), 78201)
        fixture.extend((("zero", "control", zero, None), ("weak-signed", "control", planted, None)))
    out, grid_audit = [], []
    try:
        for repeat in range(2):
            for i, (label, kind, window, sealed) in enumerate(fixture):
                count = (list(CASES).index(ident) + i + repeat) % len(MODES)
                for offset, mode in enumerate(MODES[count:] + MODES[:count]):
                    result = trial(window, policy, mode, libs)
                    if mode == "installed" and sealed is not None and result["probes"] != sealed:
                        raise ValueError(
                            "unchanged installed detector differs from its archived rows"
                        )
                    out.append(
                        dict(
                            label=label,
                            kind=kind,
                            repeat=repeat,
                            order=offset,
                            mode=mode,
                            result=result,
                            iq_sha256=window.iq_sha256,
                        )
                    )
                print(ident, label, repeat, flush=True)
        grid_audit = grid_samples(windows[0], policy, libs)
    finally:
        write(
            work / f"{ident}.json.gz",
            gzip.compress(
                encoded(
                    dict(
                        rows=out,
                        producer=producer,
                        screen_available=importlib.util.find_spec(
                            "leo.analysis.starlink.coarse_screen"
                        )
                        is not None,
                        cpu=cfg["cpu"],
                        grid_audit=grid_audit,
                        source_lock_sha256=_sha(work / "source-lock.json"),
                    )
                ),
                mtime=0,
            ),
        )


def run(work, ids):
    lock = prior.read(work / "source-lock.json")
    for ident in ids:
        cfg = lock["cases"][ident]
        python = prior.checked(Path(cfg["python"]), cfg["python_sha256"])
        env = os.environ | {"PYTHONPATH": f"{cfg['root']['producer']}:{ROOT}"}
        for name in ("OMP", "OPENBLAS", "MKL", "VECLIB_MAXIMUM", "NUMEXPR", "BLIS"):
            env[name + "_NUM_THREADS"] = "1"
        cmd = [
            "taskset",
            "-c",
            str(cfg["cpu"]),
            str(python),
            "-u",
            "-m",
            __spec__.name,
            "worker",
            str(work),
            ident,
        ]
        subprocess.run(cmd, cwd=ROOT, env=env, check=True, timeout=100)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("freeze", "worker", "run"))
    p.add_argument("work", type=local_output, default=WORK, nargs="?")
    p.add_argument("cases", choices=tuple(CASES), nargs="*")
    a = p.parse_args()
    if a.action == "freeze":
        freeze(a.work)
    elif a.action == "run":
        run(a.work, a.cases)
    else:
        worker(a.work, a.cases[0])
