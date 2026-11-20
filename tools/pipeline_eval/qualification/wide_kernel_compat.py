"""Exercise the released wide detector with AVX2 unavailable under x86 emulation."""

import argparse
import subprocess

import numpy as np

from ..__main__ import encoded, local_output, save_json
from . import ordinary_front_eval, scout_stride_build
from . import wide_kernel_eval as run
from .full_v5_check import _sha
from .pilot_kernel_eval import _digest
from .wide_regional_eval import RATE, templates

CLI = "leo-native-glrt-short-window"


def compare(work):
    build = run.release(work)
    programs = {}
    for role in run.MODES:
        folder = local_output(build[role]["path"]).parent
        receipt = run.load(folder / "build-receipt.json")
        if _sha(folder / CLI) != receipt["outputs"][CLI]:
            raise ValueError("native short-window CLI differs from its build receipt")
        programs[role] = folder / CLI
    local = work / "qemu"
    local.mkdir(exist_ok=True)
    result = {}
    for ident, edge in zip(run.PANEL, ("lower", "upper"), strict=True):
        file = scout_stride_build.ROOT / f"{ident}-held/visit.ci16"
        digest = _digest(file.read_bytes())
        visit = next(row for row in run.held_roster(ident) if row["iq_sha256"] == digest)
        pair = templates(RATE, edge)
        names = [local / f"{ident}-{role}.c128" for role in ("exact", "control")]
        for destination, values in zip(names, pair, strict=True):
            np.asarray(values, dtype="<c16").tofile(destination)
        argv = [
            "--rate-hz",
            str(RATE),
            "--input-ci16",
            str(file),
            "--exact-template",
            str(names[0]),
            "--control-template",
            str(names[1]),
            "--fractional-epoch",
        ]
        votes = {}
        for role, program in programs.items():
            path = local / f"{ident}-{role}.json"
            with path.open("w") as stream:
                subprocess.run(
                    ["qemu-x86_64", "-cpu", "Nehalem-v1", str(program), *argv],
                    check=True,
                    stdout=stream,
                    timeout=30,
                )
            votes[role] = ordinary_front_eval._payload(run.load(path))
        comparison = {role: _digest(encoded(d)) for role, d in votes.items()}
        if len(set(comparison.values())) != 1:
            raise ValueError("non-AVX2 stock and candidate detector payloads differ")
        result[ident] = dict(visit, edge=edge, detector_payload_sha256=comparison)
    qemu_version = subprocess.check_output(["qemu-x86_64", "--version"], text=True)
    return dict(
        environment="qemu-x86_64 Nehalem-v1 without AVX2; no device timing",
        qemu_version=qemu_version.splitlines()[0],
        executable_sha256={name: _sha(path) for name, path in programs.items()},
        cases=result,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=local_output, default=run.WORK)
    save_json(run.REPORT / "scalar-fallback.json", compare(parser.parse_args().work))
