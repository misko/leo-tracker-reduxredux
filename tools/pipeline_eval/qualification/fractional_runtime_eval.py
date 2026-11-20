"""Measure ordinary GLRT ordered fractional interpolation on saved wave8 CI16."""

import argparse
import gzip
import json
import shutil
import subprocess
import sys
from contextlib import ExitStack
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from time import perf_counter_ns, process_time_ns

import numpy as np

from ..__main__ import ROOT, encoded, local_output, write
from ..variants import fractional_runtime_overlay as variant
from ..variants import iq_stream, ordinary_prepared
from . import ordinary_front_build, ordinary_front_eval, ordinary_prepared_eval
from .conditioned_cfo_eval import _test_signal
from .full_v5_check import NATIVE_LIBRARY, _sha
from .ordinary_prepared_position import TEMPLATES
from .pilot_kernel_eval import _digest

REPORT = ROOT / "reports/2026_11_19_receiver_screening/streamlined/fractional-runtime"
METHOD = "fractional_runtime"
CASES = ordinary_prepared_eval.CASES
MODES = ("control", METHOD)
RATE = 10_000_000
ARM_RECEIPT = ordinary_front_build.ARM_CONTROL / "build-receipt.json"


def unpack(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def build(work, arch, mode):
    stock = ordinary_front_build
    receipt = json.loads((stock.CONTROL_BUILD if arch == "host" else ARM_RECEIPT).read_bytes())
    if any(_sha(stock.SOURCE / name) != sha for name, sha in receipt["sources"].items()):
        raise ValueError("Frozen wave8 source differs from the measured original build")
    target = work / f"{arch}-{mode}"
    source = target.with_name(target.name + "-source")
    shutil.copytree(stock.SOURCE, source, ignore=shutil.ignore_patterns("__pycache__"))
    detector = source / "native_glrt.c"
    detector.write_text(ordinary_prepared.retain_short_window_preparation(detector.read_text()))
    if mode == METHOD:
        kernel = source / "kernel/private/native_presence/presence.c"
        kernel.write_text(variant.overlay(kernel.read_text()))
        shutil.copyfile(variant.HEADER, kernel.with_name(variant.HEADER.name))
    subprocess.run(
        [
            sys.executable,
            str(source / "build.py"),
            "--compiler",
            receipt["compiler"],
            "--archiver",
            receipt["archiver"],
            "--fftw-prefix",
            str(stock.HOST_FFTW if arch == "host" else stock.ARM_FFTW),
            "--target",
            receipt["target"],
            "--output-dir",
            str(target),
            "--work-dir",
            str(target.with_name(target.name + "-build")),
        ],
        check=True,
    )


def alias_control(case):
    """Two seeded pilots separated by one GLRT residual-bin alias."""
    edge = "lower" if case.startswith("DS26") else "upper"
    window = iq_stream.IQWindow(
        sequence=0,
        samples=np.empty((200_000, 2, 2), dtype="<i2"),
        receiver_ids=(0, 1),
        sample_rate_hz=RATE,
        acquisition={"actual_if_center_hz": 0},
        target_id="synthetic-glrt-alias",
        target={"edge": edge, "rf_center_hz": 0, "lnb_lo_hz": 0},
        iq_sha256="",
    )
    return _test_signal(window, ((731, -178_000, 144), (746, 1 / 4.4e-6 - 178_000, 114)), 319207)


def _prior(case, parent_work):
    known = ordinary_prepared_eval.REPORT
    path = known / f"{case}.json.gz"
    lock = json.loads((known / "prediction-lock.json").read_bytes())["files"]
    if _sha(path) != lock[path.name]:
        raise ValueError("prepared visit receipt differs from its published seal")
    previous = unpack(path)
    if previous["libraries"]["ordinary_prepared"] != _sha(
        parent_work / "host" / NATIVE_LIBRARY.name
    ):
        raise ValueError("prepared baseline library differs from its measured build")
    return previous, _sha(path)


def replay(case, arch, work, parent_work):
    from leo.analysis.starlink.native_short_window import NativeShortWindow

    previous, parent_sha = _prior(case, parent_work)
    iq_folder = parent_work / f"{case}-inputs"
    input_folder = work / f"{case}-{arch}-inputs"
    input_folder.mkdir(exist_ok=True)
    template_folder = TEMPLATES / f"{case}-arm-input"
    exact, control = (template_folder / f"{name}.c128" for name in ("exact", "control"))
    synthetic = alias_control(case)
    synthetic.samples.tofile(input_folder / "alias.ci16")
    host = arch == "host"
    suffix = NATIVE_LIBRARY.name if host else "leo-native-glrt-short-window"
    paths = {
        "control": (parent_work / "host" if host else work / "arm-control") / suffix,
        METHOD: work / f"{arch}-{METHOD}" / suffix,
    }
    with ExitStack() as stack:
        timings, contexts, setup = {}, {}, {}
        if host:
            for mode, path in paths.items():
                start = perf_counter_ns()
                context = stack.enter_context(
                    NativeShortWindow(
                        str(path),
                        np.fromfile(exact, dtype="<c16"),
                        np.fromfile(control, dtype="<c16"),
                        sample_rate_hz=RATE,
                        fractional_epoch=True,
                    )
                )
                setup[mode] = (perf_counter_ns() - start) / 1e6
                contexts[mode] = context
                timings[mode] = ordinary_prepared_eval._profile(context)
        else:
            arm = json.loads(ARM_RECEIPT.read_bytes())
            sysroot = Path(arm["fftw_double_library"]).parents[2]

        def call(path, mode, digest):
            samples, seen, read_wall, read_cpu = ordinary_prepared_eval.load_ci16(path, mapped=True)
            if seen != digest:
                raise ValueError("visit CI16 bytes differ from their frozen receipt")
            start, cpu = perf_counter_ns(), process_time_ns()
            if host:
                result = contexts[mode].analyze(samples, include_timings=True)
                profile = timings[mode]
                extra = dict(
                    host_cpu_ms=(process_time_ns() - cpu) / 1e6,
                    profile={name: getattr(profile, name) for name, _ in profile._fields_},
                )
            else:
                rss_path = input_folder / "rss.txt"
                run = subprocess.run(
                    [
                        "/usr/bin/time",
                        "-f",
                        "%M",
                        "-o",
                        str(rss_path),
                        "qemu-arm",
                        "-cpu",
                        "cortex-a9",
                        "-L",
                        str(sysroot),
                        str(paths[mode]),
                        "--rate-hz",
                        str(RATE),
                        "--fractional-epoch",
                        "--exact-template",
                        str(exact),
                        "--control-template",
                        str(control),
                        "--input-ci16",
                        str(path),
                    ],
                    capture_output=True,
                    check=True,
                    timeout=15,
                )
                result = json.loads(run.stdout)
                extra = dict(qemu_peak_kib=int(rss_path.read_text()))
            wall = (perf_counter_ns() - start) / 1e6
            return ordinary_front_eval._payload(result), dict(
                extra,
                read_wall_ms=read_wall,
                read_cpu_ms=read_cpu,
                wall_ms=wall,
                detector_cpu_ms=result.get(
                    "detector_cpu_ms", result.get("timings_ms", {}).get("detector_cpu")
                ),
                rows=[r["timings_ms"] for r in result["rows"]],
            )

        def measure(path, digest, index, repeats, expected=None):
            if host:
                for mode in MODES:
                    call(path, mode, digest)
            payloads, calls = {}, []
            for rep in range(repeats):
                order = MODES if (index + rep) % 2 == 0 else MODES[::-1]
                for mode in order:
                    payload, timing = call(path, mode, digest)
                    payloads.setdefault(mode, payload)
                    calls.append(
                        dict(
                            timing, mode=mode, repeat=rep, payload_sha256=_digest(encoded(payload))
                        )
                    )
            target = expected if host and expected else calls[0]["payload_sha256"]
            return dict(
                calls=calls,
                payloads=payloads,
                digest=target,
                positives={m: ordinary_front_eval.positive(p) for m, p in payloads.items()},
                exact=all(c["payload_sha256"] == target for c in calls),
            )

        rows = []
        for index, row in enumerate(previous["rows"]):
            entry = {k: row[k] for k in ("segment", "sequence", "visit", "status", "iq_sha256")}
            if row["status"] == "processed":
                path = iq_folder / f"{row['segment']}-{row['sequence']}.ci16"
                entry.update(
                    measure(
                        path,
                        row["iq_sha256"],
                        index,
                        5 if host else 1,
                        row["archive_payload_sha256"],
                    )
                )
            rows.append(entry)
        controls = {
            name: measure(
                iq_folder / f"{name}.ci16",
                row["archive_iq_sha256"],
                index,
                3 if host else 1,
                row["archive_payload_sha256"],
            )
            for index, (name, row) in enumerate(previous["controls"].items())
        }
        controls["alias"] = measure(
            input_folder / "alias.ci16", synthetic.iq_sha256, 3, 3 if host else 1
        )
    return dict(
        case=case,
        arch=arch,
        rows=rows,
        controls=controls,
        context_wall_ms=setup,
        parent_receipt_sha256=parent_sha,
        executable_sha256={m: _sha(p) for m, p in paths.items()},
        template_sha256={p.name: _sha(p) for p in (exact, control)},
        runner_peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss,
    )


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("task", choices=("build", *CASES))
    cli.add_argument("--arch", choices=("host", "arm"), required=True)
    cli.add_argument("--work", type=Path, required=True)
    cli.add_argument("--parent-work", type=Path, required=True)
    args = cli.parse_args()
    work, parent_work = local_output(args.work), local_output(args.parent_work)
    work.mkdir(parents=True, exist_ok=True)
    if args.task == "build":
        for mode in MODES if args.arch == "arm" else (METHOD,):
            build(work, args.arch, mode)
    else:
        result = replay(args.task, args.arch, work, parent_work)
        out = REPORT / f"{args.task}-{args.arch}.json.gz"
        write(out, gzip.compress(encoded(result), mtime=0))


if __name__ == "__main__":
    main()
