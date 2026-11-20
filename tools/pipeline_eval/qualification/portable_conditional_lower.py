"""Replay one sealed lower-edge fixture using the same relocated portable application."""

import argparse
import subprocess

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from . import fresh_replay, portable_conditional_trial, staggered_benchmark
from .full_v5_check import _sha

CASE = "DS29-0491"
CPUS = (3, 2)
REPORT = portable_conditional_trial.REPORT


def run(work, bundle):
    work.mkdir()
    out = work / CASE
    out.mkdir()
    subprocess.run(["setfacl", "-m", "u:leo:rwx", str(out)], check=True)
    source = staggered_benchmark.FRESH / "source-lock.json"
    authority = whole_iq.read(whole_iq.checked(source, staggered_benchmark.FRESH_PIN))
    with fresh_replay.patched_case(authority):
        spec = portable_conditional_trial.manifest(CASE, authority["cases"][CASE])
    save_json(out / "input.json", spec)
    (out / "input.json").chmod(0o644)
    name = f"{CASE}-input.json"
    write(REPORT / name, (out / "input.json").read_bytes())
    save_json(
        REPORT / "lower-source-lock.json",
        dict(
            case=CASE,
            source_sha256=_sha(source),
            upper_study_sha256=_sha(REPORT / "source-lock.json"),
            selection="second DS29 capture in the earlier two-case genuine lower-edge cohort",
            cpus=CPUS,
            edge="lower",
            package_manifest_sha256=_sha(bundle / "files.json"),
            files={name: _sha(REPORT / name)},
        ),
    )
    portable_conditional_trial.launch(work, bundle, CASE, CPUS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("package", type=local_output)
    args = parser.parse_args()
    run(args.work, args.package)
