"""Compose the two separately measured native changes without modifying either release."""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json
from . import dual_lane_build as lane
from . import fractional_cost_build as fractional
from .full_v5_check import _sha

REPORT = lane.REPORT.with_name("combined-native")
LANE = Path("/var/tmp/leo-dual-lane-De3lVUqp/build")
GROUPED = Path.home() / ".cache/leo-fractional-cost-20261119/build-v2"


def build(work):
    control_lock = whole_iq.read(lane.REPORT / "native-lock.json")["files"]
    control_file = whole_iq.checked(LANE / "build.json", control_lock["native-build.json"])
    control = whole_iq.read(control_file)
    previous_file = whole_iq.checked(
        LANE / "detector/build-receipt.json", control["detector_build_sha256"]
    )
    previous = whole_iq.read(previous_file)
    result_lock = whole_iq.read(fractional.REPORT / "result-lock.json")["files"]
    group_file = whole_iq.checked(GROUPED / "build.json", result_lock["build.json"])
    group = whole_iq.read(group_file)
    grouped_file = whole_iq.checked(
        GROUPED / "detector/build-receipt.json", group["candidate_receipt_sha256"]
    )
    grouped = whole_iq.read(grouped_file)
    for name, digest in previous["sources"].items():
        whole_iq.checked(LANE / "source" / name, digest)
    names = {
        fractional.PRESENCE,
        fractional.SEARCH,
        str(Path(fractional.PRESENCE).with_name(fractional.HEADER.name)),
    }
    source = work / "source"
    shutil.copytree(LANE / "source", source, ignore=shutil.ignore_patterns("__pycache__"))
    for name in names:
        shutil.copyfile(
            whole_iq.checked(GROUPED / "source" / name, grouped["sources"][name]), source / name
        )
    temporary = work / "tmp"
    temporary.mkdir()
    commands = [
        sys.executable,
        str(source / "build.py"),
        "--compiler",
        previous["compiler"],
        "--archiver",
        previous["archiver"],
        "--fftw-prefix",
        str(lane.hotpath.ordinary_front_build.HOST_FFTW),
        "--target",
        "host",
        "--output-dir",
        str(work / "detector"),
        "--work-dir",
        str(work / "objects"),
    ]
    whole_iq.checked(Path(previous["compiler"]), previous["compiler_sha256"])
    whole_iq.checked(Path(previous["archiver"]), previous["archiver_sha256"])
    subprocess.run(commands, env=os.environ | {"TMPDIR": str(temporary)}, timeout=60, check=True)
    receipt = work / "detector/build-receipt.json"
    got = whole_iq.read(receipt)
    if got["sources"] != previous["sources"] | {k: grouped["sources"][k] for k in names}:
        raise ValueError("combined build exceeds the two sealed source overlays")
    control_detector = whole_iq.checked(
        LANE / lane.hotpath.DETECTOR, control["files"][lane.hotpath.DETECTOR]
    )
    detector = work / "detector/libleo-adaptive-detector.so"
    if (
        lane.exports(detector) != lane.exports(control_detector)
        or got["abi_version"] != previous["abi_version"]
    ):
        raise ValueError("combined library changed the qualified dual-lane ABI")
    shutil.copyfile(
        whole_iq.checked(LANE / lane.LIBRARY, control["files"][lane.LIBRARY]), work / lane.LIBRARY
    )
    shutil.copyfile(detector, work / lane.hotpath.DETECTOR)
    for path in (work, work / lane.LIBRARY, work / lane.hotpath.DETECTOR):
        path.chmod(0o755 if path.is_dir() else 0o644)
    save_json(
        work / "build.json",
        dict(
            sources={
                str(p): _sha(p)
                for p in (Path(__file__), control_file, group_file, previous_file, grouped_file)
            },
            detector_build_sha256=_sha(receipt),
            files={n: _sha(work / n) for n in (lane.LIBRARY, lane.hotpath.DETECTOR)},
            command=commands,
            api=control["api"],
            changed={n: got["sources"][n] for n in sorted(names)},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    build(parser.parse_args().work)
