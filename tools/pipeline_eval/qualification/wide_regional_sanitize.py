"""Run ASan/UBSan on the source-identical widened release with CI16 extremes."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

from ..__main__ import local_output, save_json
from . import ordinary_front_build, wide_regional_build, wide_regional_eval
from .conditioned_cfo_eval import _test_signal
from .full_v5_check import _sha
from .pilot_kernel_eval import _digest

COMPILER = Path(__file__).with_name("wide_regional_sanitize_cc.sh")


def run(work):
    base = work / "sanitizer"
    base.mkdir(exist_ok=False)
    target, source = base / "build", work / "wide-source"
    compiler = base / "cc"
    shutil.copyfile(COMPILER, compiler)
    compiler.chmod(0o755)
    stock = ordinary_front_build
    ready = json.loads((work / "wide" / "build-receipt.json").read_bytes())
    if any(_sha(source / f) != d for f, d in ready["sources"].items()):
        raise ValueError("Sanitizer input differs from the exact widened release source")
    env = {
        **os.environ,
        "TMPDIR": str(base),
        "ASAN_OPTIONS": "detect_leaks=1:halt_on_error=1",
        "UBSAN_OPTIONS": "halt_on_error=1:print_stacktrace=1",
    }
    subprocess.run(
        [
            sys.executable,
            str(source / "build.py"),
            "--compiler",
            str(compiler),
            "--archiver",
            ready["archiver"],
            "--fftw-prefix",
            str(stock.HOST_FFTW),
            "--target",
            "host",
            "--output-dir",
            str(target),
            "--work-dir",
            str(base / "objects"),
        ],
        env=env,
        check=True,
    )
    executable = target / "leo-native-glrt-short-window"
    results = []
    for rate in (2_500_000, 5_000_000, 7_500_000, 10_000_000):
        count = rate // 50
        for edge, sign in (("lower", 1), ("upper", -1)):
            pair = wide_regional_eval.templates(rate, edge)
            exact, control = (base / name for name in ("exact.c128", "control.c128"))
            for data, path in zip(pair, (exact, control), strict=True):
                data.tofile(path)
            window = wide_regional_eval.synthetic(rate, edge)
            f = 799_875 if rate == 10_000_000 else 399_875
            plant = _test_signal(window, ((735, f * sign, 640),), 80294)
            rng = np.random.default_rng(78421)
            rails = rng.choice(np.array([-32768, 32767], dtype="<i2"), (count, 2, 2))
            empty = np.zeros_like(rails)
            for label, values in (("boundary", plant.samples), ("rails", rails), ("empty", empty)):
                path = base / "window.ci16"
                values.tofile(path)
                argv = [
                    str(executable),
                    "--rate-hz",
                    str(rate),
                    "--fractional-epoch",
                    "--exact-template",
                    str(exact),
                    "--control-template",
                    str(control),
                    "--input-ci16",
                    str(path),
                ]
                out = subprocess.run(argv, env=env, check=True, capture_output=True, timeout=12)
                payload = json.loads(out.stdout)
                band = 800_000 if rate == 10_000_000 else 400_000
                wide_regional_eval.validate(payload, band)
                results.append(
                    dict(
                        rate=rate,
                        edge=edge,
                        case=label,
                        iq_bytes=values.nbytes,
                        iq_sha256=_digest(values.tobytes()),
                        candidate_counts=[r["candidate_count"] for r in payload["rows"]],
                        stderr=out.stderr.decode(),
                        exit_code=out.returncode,
                    )
                )
    save_json(
        wide_regional_eval.REPORT / "sanitizers.json",
        dict(
            address_and_undefined=True,
            frozen_wide_library_sha256=ready["outputs"]["libleo-adaptive-detector.so"],
            runner_sha256=_sha(Path(__file__)),
            wrapper_sha256=_sha(COMPILER),
            executable_sha256=_sha(executable),
            results=results,
        ),
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--work", type=Path, default=wide_regional_build.ROOT)
    run(local_output(cli.parse_args().work))
