"""Run bound Cortex-A9 emulation and compare to the frozen host stride panel."""

import argparse
import csv
import gzip
import json
import os
import subprocess
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import numpy as np

from ..__main__ import ROOT, encoded, write
from ..variants import iq_stream
from . import ordinary_front_build, ordinary_front_eval, scout_stride_arm_build, scout_stride_eval
from .conditioned_cfo_eval import _test_signal
from .full_v5_check import PRODUCERS, _from_native, _load_case, _probe, _sha, compare_probes
from .ordinary_glrt_profile import C_SOURCE
from .pilot_kernel_eval import _digest, _windows
from .scout_budget_results import unpack
from .wide_regional_eval import synthetic, templates, validate

REPORT = ROOT / "reports/2026_11_19_receiver_screening/receiver-core/stride-arm"
HOST = scout_stride_eval.REPORT
MODES = scout_stride_arm_build.MODES
RATE = 10_000_000
SEQUENCES = (8, 15, 22, 27)
CONTROL_SEEDS = dict(odd=59491, edge=59493, noise=59498, empty=59499)
CONTROL_SEEDS.update({"faint-odd": 59494, "same-epoch-160khz": 59496, "symbol-alias": 59497})


def host_receipt(name):
    signed = json.loads((HOST / "prediction-lock.json").read_bytes())["files"]
    path = HOST / name
    if _sha(path) != signed[name]:
        raise ValueError("Frozen host comparator changed")
    return unpack(path)


def sources():
    paths = (
        Path(__file__),
        Path(scout_stride_arm_build.__file__),
        Path(ordinary_front_eval.__file__),
        Path(iq_stream.__file__),
        C_SOURCE,
        REPORT / "PROTOCOL.md",
        HOST / "prediction-lock.json",
    )
    return {p.name: _sha(p) for p in paths}


def load_arm(work):
    bank = json.loads((work / "release.json").read_bytes())
    for m, d in bank["builds"].items():
        folder = work / f"arm-{m}"
        if _sha(folder / scout_stride_arm_build.CLI) != d["cli_sha256"]:
            raise ValueError("ARM CLI differs from cross-build receipt")
        if _sha(folder / scout_stride_arm_build.LIBRARY) != d["library_sha256"]:
            raise ValueError("ARM library differs from cross-build receipt")
    return bank


def command(work, bank, edge, label):
    folder = work / f"{label}-local"
    folder.mkdir(exist_ok=False)
    exact, control, iq, rss = (folder / f for f in ("exact.c128", "ctrl.c128", "visit.ci16", "rss"))
    for path, arr in zip((exact, control), templates(RATE, edge), strict=True):
        arr.tofile(path)
    qemu = ["qemu-arm", "-cpu", "cortex-a9", "-L", bank["sysroot"]]

    def call(samples, mode):
        samples.tofile(iq)
        binary = work / f"arm-{mode}" / scout_stride_arm_build.CLI
        commands = [
            *qemu,
            str(binary),
            "--rate-hz",
            str(RATE),
            "--fractional-epoch",
            "--exact-template",
            str(exact),
            "--control-template",
            str(control),
            "--input-ci16",
            str(iq),
        ]
        start = perf_counter()
        run = subprocess.run(
            ["/usr/bin/time", "-f", "%M", "-o", str(rss), *commands],
            check=True,
            capture_output=True,
            timeout=18,
        )
        wall = perf_counter() - start
        result = json.loads(run.stdout)
        validate(ordinary_front_eval._payload(result), 800_000)
        return result, dict(external_wall_s=wall, emulator_peak_kib=int(rss.read_text()))

    return call, qemu, (exact, control, iq, rss)


def profile(work, qemu, paths, samples):
    base = work / "arm-control"
    receipt = json.loads((base / "build-receipt.json").read_bytes())
    runner = work / "warm-profile-arm"
    if not runner.is_file():
        subprocess.run(
            [
                receipt["compiler"],
                "-std=c11",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-mcpu=cortex-a9",
                "-mfpu=neon",
                "-mfloat-abi=hard",
                "-I",
                str(ordinary_front_build.SOURCE),
                str(C_SOURCE),
                "-L",
                str(base),
                "-lleo-adaptive-detector",
                "-o",
                str(runner),
            ],
            env={**os.environ, "TMPDIR": str(work / "compiler-temp")},
            check=True,
        )
    exact, control, iq, rss = paths
    samples.tofile(iq)
    costs = {}
    for mode in MODES:
        path = iq.parent / "libleo-adaptive-detector.so.1"
        path.symlink_to(work / f"arm-{mode}" / scout_stride_arm_build.LIBRARY)
        cmd = [
            *qemu,
            "-E",
            f"LD_LIBRARY_PATH={iq.parent}",
            str(runner),
            str(iq),
            str(exact),
            str(control),
        ]
        start = perf_counter()
        result = subprocess.run(
            ["/usr/bin/time", "-f", "%M", "-o", str(rss), *cmd],
            capture_output=True,
            text=True,
            check=True,
            timeout=18,
        )
        wall = perf_counter() - start
        path.unlink()
        init, *lines = result.stdout.splitlines()
        costs[mode] = dict(
            init_wall_ms=float(init),
            external_wall_s=wall,
            emulator_peak_kib=int(rss.read_text()),
            calls=[{k: float(v) for k, v in d.items()} for d in csv.DictReader(lines)],
        )
    return costs


def compare_host(arm, host, w=None):
    summary = {}
    for mode in MODES:
        old_rows, new_rows = (panel["payloads"][mode]["rows"] for panel in (host, arm))
        if len(old_rows) != len(new_rows) or len(old_rows) != 2:
            raise ValueError("Host and ARM have incompatible receiver row geometry")
        item = dict(exact_public_rows=sum(a == b for a, b in zip(old_rows, new_rows, strict=True)))
        if w is not None:
            pairs = []
            for rx, old, new in zip(w.receiver_ids, old_rows, new_rows, strict=True):
                left, right = (
                    _probe(w, rx, (_from_native(i, c) for i, c in enumerate(r["candidates"])))
                    for r in (old, new)
                )
                pairs.append(compare_probes(left, right, RATE))
            item["host_as_reference"] = pairs
        summary[mode] = item
    return summary


def real(case_id, work, bank):
    old = host_receipt(f"{case_id}-held.json.gz")
    case = _load_case(case_id)
    if old["archive"]["native_archive_sha256"] != case["native"]["sha256"]:
        raise ValueError("Capture-era reference changed")
    reference = {(r["visit"], r["receiver"]): r for r in old["archive"]["receivers"]}
    host_rows = {r["visit"]: r for r in old["rows"]}
    with patch.object(iq_stream, "MAX_CHUNK_PREFIX", 48 * iq_stream.MIB):
        windows = _windows(case, 3, SEQUENCES)
    call, qemu, paths = command(work, bank, windows[0].target["edge"], case_id)
    rows, first = [], None
    for i, w in enumerate(windows):
        visit = w.acquisition["global_visit"]
        prior = host_rows[visit]
        if w.iq_sha256 != prior["iq_sha256"] or w.samples.nbytes != prior["iq_bytes"]:
            raise ValueError("Replayed raw IQ differs from the preselected host visit")
        data = {}
        status = prior["status"]
        if status == "processed":
            with patch.object(ordinary_front_eval, "MODES", MODES):
                data = ordinary_front_eval.benchmark(w.samples, call, i, 1)
            data["host_comparison"] = compare_host(data, prior, w)
            fits = []
            for j, rx in enumerate(w.receiver_ids):
                archived = _probe(w, rx, reference[visit, rx]["archive_candidates"])
                comparison = {}
                for mode in MODES:
                    chosen = data["payloads"][mode]["rows"][j]["candidates"]
                    emitted = _probe(w, rx, (_from_native(k, c) for k, c in enumerate(chosen)))
                    comparison[mode] = compare_probes(archived, emitted, RATE)
                fits.append(dict(receiver=rx, fits=comparison))
            data["archive_comparison"] = fits
            first = (w, visit) if first is None else first
        rows.append(
            dict(data, visit=visit, sequence=w.sequence, status=status, iq_sha256=w.iq_sha256)
        )
    w, visit = first
    return dict(
        id=case_id,
        rows=rows,
        warm_visit=visit,
        warm_iq_sha256=w.iq_sha256,
        warm_profile=profile(work, qemu, paths, w.samples),
        build=bank["builds"],
    )


def controls(work, bank):
    old = host_receipt("smoke.json.gz")["results"]
    results = {}
    for edge in ("lower", "upper"):
        base = synthetic(RATE, edge)
        call, _, _ = command(work, bank, edge, f"control-{edge}")
        for i, (name, seed) in enumerate(CONTROL_SEEDS.items()):
            label = f"{edge}-{name}"
            prior = old[label]
            plants = prior["planted"]
            iq = (
                np.zeros_like(base.samples)
                if name == "empty"
                else _test_signal(base, plants, seed).samples
            )
            dig = _digest(iq.tobytes())
            if dig != prior["iq_sha256"]:
                raise ValueError("Emulated control IQ differs from frozen host control bytes")
            with patch.object(ordinary_front_eval, "MODES", MODES):
                row = ordinary_front_eval.benchmark(iq, call, i, 1)
            row["host_comparison"] = compare_host(row, prior)
            row["planted_matches"] = {
                m: [
                    [
                        sum(abs(x[1] - e) <= 2 and abs(x[2] - f) < 1000 for x in rx)
                        for rx in row["positives"][m]
                    ]
                    for e, f, _ in plants
                ]
                for m in MODES
            }
            row["host_planted_matches"] = {
                m: [
                    [
                        sum(abs(x[1] - e) <= 2 and abs(x[2] - f) < 1000 for x in rx)
                        for rx in prior["positives"][m]
                    ]
                    for e, f, _ in plants
                ]
                for m in MODES
            }
            results[label] = dict(row, planted=plants, iq_sha256=dig)
    return dict(results=results, build=bank["builds"])


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work", type=Path, default=scout_stride_arm_build.WORK)
    p.add_argument("--case", choices=PRODUCERS)
    a = p.parse_args()
    frozen = sources()
    if json.loads((REPORT / "source-lock.json").read_bytes()) != frozen:
        raise ValueError("ARM qualification sources differ from their pre-score lock")
    bank = load_arm(a.work)
    out = real(a.case, a.work, bank) if a.case else controls(a.work, bank)
    if sources() != frozen:
        raise ValueError("ARM qualification source changed during replay")
    name = f"{a.case}.json.gz" if a.case else "controls.json.gz"
    write(REPORT / name, gzip.compress(encoded(out), mtime=0))
