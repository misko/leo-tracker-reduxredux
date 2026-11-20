"""Freeze and replay exact reuse of the ordinary fractional epoch center cell."""

import argparse
import gzip
import json
import shutil
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import glrt_center_cell as variant
from . import fractional_runtime_eval as base
from .full_v5_check import NATIVE_LIBRARY, _sha
from .pilot_kernel_eval import _digest

REPORT = ROOT / "reports/2026_11_19_receiver_screening/next/glrt-computation"
METHOD = "glrt_center_cell"
CASES = base.CASES
MODES = ("control", METHOD)
BASE_BUILD = "host-fractional_runtime"
HOLDOUT = {"DS26-0036": 4, "DS29-0082": 2}


def held_score(case, row):
    fields = (case, row["segment"], row["sequence"], row["iq_sha256"])
    material = "center-cell-holdout-v1:" + ":".join(map(str, fields))
    return sha256(material.encode()).hexdigest()


def roster(case, rows):
    ranks = sorted((held_score(case, r), r["visit"]) for r in rows if r["status"] == "processed")
    selected = {visit for _, visit in ranks[: HOLDOUT[case]]}
    return [
        dict(
            visit=r["visit"],
            score=held_score(case, r),
            cohort=(
                "excluded"
                if r["status"] != "processed"
                else "held"
                if r["visit"] in selected
                else "companion"
            ),
        )
        for r in rows
    ]


def sealed(path):
    lock = json.loads((path.parent / "prediction-lock.json").read_bytes())["files"]
    if _sha(path) != lock[path.name]:
        raise ValueError(f"prior evidence differs from the locked digest: {path}")
    return path


def bind_prior(case, ordered, prepared):
    path = sealed(base.REPORT / f"{case}-host.json.gz")
    calibrated = base.unpack(path)
    if calibrated["executable_sha256"][base.METHOD] != _sha(
        ordered / BASE_BUILD / NATIVE_LIBRARY.name
    ):
        raise ValueError("the ordered fractional parent differs from the measured library")
    original, original_sha = base._prior(case, prepared)
    rows = []
    for row, prior in zip(calibrated["rows"], original["rows"], strict=True):
        for key in ("segment", "sequence", "status", "visit", "iq_sha256"):
            if row[key] != prior[key]:
                raise ValueError("the ordered parent visit differs from the saved IQ inventory")
        if row["status"] == "processed" and (
            not row["exact"] or row["digest"] != prior["archive_payload_sha256"]
        ):
            raise ValueError("the measured parent lacks a verified candidate payload")
        rows.append(prior)
    return dict(original, rows=rows), _sha(path), original_sha


def plan(ordered, prepared):
    build_receipt = ordered / BASE_BUILD / "build-receipt.json"
    established = json.loads(sealed(base.REPORT / "source-lock.json").read_bytes())
    if _sha(build_receipt) != established["builds"][BASE_BUILD]:
        raise ValueError("the ordered parent build receipt differs from its qualification")
    sources = (
        Path(__file__),
        Path(variant.__file__),
        Path(base.__file__),
        Path(base.ordinary_prepared_eval.__file__),
        REPORT / "PROTOCOL.md",
    )
    cases = {}
    for case in CASES:
        data, parent_sha, saved_sha = bind_prior(case, ordered, prepared)
        cases[case] = dict(
            parent_receipt_sha256=parent_sha,
            prepared_input_sha256=saved_sha,
            visits=roster(case, data["rows"]),
        )
    return dict(
        cases=cases,
        sources={str(p): _sha(p) for p in sources},
        base_build_receipt_sha256=_sha(build_receipt),
    )


def build(work, ordered):
    stock = base.ordinary_front_build
    receipt = json.loads((ordered / BASE_BUILD / "build-receipt.json").read_bytes())
    prior = ordered / (BASE_BUILD + "-source")
    if any(_sha(prior / name) != sha for name, sha in receipt["sources"].items()):
        raise ValueError("the prepared-plus-fractional parent source differs from its build")
    target = work / f"host-{METHOD}"
    source = target.with_name(target.name + "-source")
    shutil.copytree(prior, source, ignore=shutil.ignore_patterns("__pycache__"))
    kernel = source / "kernel/private/full_search.c"
    kernel.write_text(variant.overlay(kernel.read_text()))
    subprocess.run(
        [
            sys.executable,
            str(source / "build.py"),
            "--compiler",
            receipt["compiler"],
            "--archiver",
            receipt["archiver"],
            "--fftw-prefix",
            str(stock.HOST_FFTW),
            "--target",
            receipt["target"],
            "--output-dir",
            str(target),
            "--work-dir",
            str(target.with_name(target.name + "-build")),
        ],
        check=True,
    )


def replay(case, work, ordered, prepared, frozen):
    data, parent_sha, _ = bind_prior(case, ordered, prepared)
    inputs = work / "replay-parent"
    inputs.mkdir(exist_ok=True)
    for name, target in (
        ("host", ordered / BASE_BUILD),
        (f"{case}-inputs", prepared / f"{case}-inputs"),
    ):
        link = inputs / name
        if not link.exists():
            link.symlink_to(target, target_is_directory=True)
        if link.resolve() != target.resolve():
            raise ValueError("the replay path differs from its locked parent")
    with patch.multiple(base, METHOD=METHOD, MODES=MODES, _prior=lambda *_: (data, parent_sha)):
        result = base.replay(case, "host", work, inputs)
    reference_controls = base.unpack(sealed(base.REPORT / f"{case}-host.json.gz"))["controls"]
    for key, observed in result["controls"].items():
        if observed["digest"] != reference_controls[key]["digest"]:
            raise ValueError(f"the sealed parent synthetic payload changed: {key}")
    result["cohort"] = frozen["cases"][case]["visits"]
    result["source_holdout_lock_sha256"] = _digest(encoded(frozen))
    return result


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("stage", choices=("freeze", "build", *CASES))
    cli.add_argument("--work", type=local_output, required=True)
    cli.add_argument("--ordered-work", type=local_output, required=True)
    cli.add_argument("--prepared-work", type=local_output, required=True)
    args = cli.parse_args()
    frozen = plan(args.ordered_work, args.prepared_work)
    lock = REPORT / "source-holdout-lock.json"
    if args.stage == "freeze":
        if lock.exists():
            raise ValueError("the source and holdout are already frozen")
        save_json(lock, frozen)
        return
    if json.loads(lock.read_bytes()) != frozen:
        raise ValueError("the fixed source or IQ roster changed after freeze")
    if args.stage == "build":
        build(args.work, args.ordered_work)
    else:
        result = replay(args.stage, args.work, args.ordered_work, args.prepared_work, frozen)
        write(REPORT / f"{args.stage}-host.json.gz", gzip.compress(encoded(result), mtime=0))


if __name__ == "__main__":
    main()
