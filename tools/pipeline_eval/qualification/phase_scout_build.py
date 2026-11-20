"""Build a private phase-scout overlay on the pinned sixteen-center ABI-1 release."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from ..__main__ import local_output, save_json
from ..variants import phase_scout
from . import ordinary_front_build, scout_budget_build
from .full_v5_check import _sha

STOCK = scout_budget_build.ROOT
BIN = scout_budget_build.LIBRARY
PIN = "85a62f4867f9959b9cc51edee1acb6c688aaee437c9a82b298f9f538e1d9c682"


def build(work):
    control, source = STOCK / "scout16" / BIN, STOCK / "scout16-source"
    prior = control.with_name("build-receipt.json")
    receipt = json.loads(prior.read_bytes())
    if (
        _sha(control) != PIN
        or receipt["outputs"][BIN] != PIN
        or receipt["abi_version"] != 1
        or any(_sha(source / f) != value for f, value in receipt["sources"].items())
    ):
        raise ValueError("expected the frozen sixteen-center release and source")
    work.mkdir(exist_ok=False, parents=True)
    output, candidate_source = work / "out", work / "source"
    temp = work / "compiler"
    temp.mkdir()
    shutil.copytree(source, candidate_source, ignore=shutil.ignore_patterns("__pycache__"))
    phase_scout.apply(candidate_source)
    subprocess.run(
        [
            sys.executable,
            str(candidate_source / "build.py"),
            "--compiler",
            receipt["compiler"],
            "--archiver",
            receipt["archiver"],
            "--fftw-prefix",
            str(ordinary_front_build.HOST_FFTW),
            "--target",
            receipt["target"],
            "--output-dir",
            str(output),
            "--work-dir",
            str(work / "obj"),
        ],
        env={**os.environ, "TMPDIR": str(temp)},
        check=True,
    )
    candidate = output / BIN
    current_receipt = json.loads(candidate.with_name("build-receipt.json").read_bytes())
    assert current_receipt["abi_version"] == 1 and current_receipt["outputs"][BIN] == _sha(
        candidate
    )
    assert [
        subprocess.check_output(["nm", "-D", "--defined-only", str(p)], text=True).split()[2::3]
        for p in (control, candidate)
    ][0] == subprocess.check_output(
        ["nm", "-D", "--defined-only", str(candidate)], text=True
    ).split()[2::3]
    row = dict(
        abi_version=1,
        stock=str(control),
        candidate=str(candidate),
        stock_sha256=PIN,
        candidate_sha256=_sha(candidate),
        stock_receipt_sha256=_sha(prior),
        candidate_receipt_sha256=_sha(candidate.with_name("build-receipt.json")),
        implementation_sha256={
            p.name: _sha(p)
            for p in (Path(__file__), Path(phase_scout.__file__), phase_scout.HEADER)
        },
    )
    save_json(work / "build.json", row)
    return row


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    build(local_output(parser.parse_args().work))
