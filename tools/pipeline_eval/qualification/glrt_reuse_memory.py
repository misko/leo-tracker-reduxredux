"""Measure fresh single-context RSS of the native C short-window programs."""

import argparse
import json
import subprocess

import numpy as np

from ..__main__ import encoded, local_output, save_json
from . import glrt_reuse_eval as run
from . import ordinary_front_eval, scout_stride_build
from .pilot_kernel_eval import _digest
from .wide_regional_eval import RATE, templates

CLI = "leo-native-glrt-short-window"


def compare(work):
    release = run.release(work)
    programs = {role: local_output(path).with_name(CLI) for role, path in release["paths"].items()}
    fixture = work / "rss"
    fixture.mkdir(exist_ok=True)
    results = {}
    for ident, edge in zip(run.wide.PANEL, ("lower", "upper"), strict=True):
        waveform = scout_stride_build.ROOT / f"{ident}-held/visit.ci16"
        digest = _digest(waveform.read_bytes())
        visit = next(item for item in run.wide.held_roster(ident) if item["iq_sha256"] == digest)
        paths = [fixture / f"{ident}-{role}.c128" for role in ("exact", "control")]
        for path, template in zip(paths, templates(RATE, edge), strict=True):
            np.asarray(template, dtype="<c16").tofile(path)
        argv = [
            "--rate-hz",
            str(RATE),
            "--input-ci16",
            str(waveform),
            "--exact-template",
            str(paths[0]),
            "--control-template",
            str(paths[1]),
            "--fractional-epoch",
        ]
        values = {role: [] for role in run.MODES}
        checksums = set()
        for repeat in range(3):
            modes = run.MODES if repeat % 2 == 0 else run.MODES[::-1]
            for mode in modes:
                rss = fixture / f"{ident}-{mode}.rss"
                response = subprocess.check_output(
                    ["/usr/bin/time", "-f", "%M", "-o", str(rss), str(programs[mode]), *argv],
                    timeout=30,
                )
                payload = ordinary_front_eval._payload(json.loads(response))
                checksums.add(_digest(encoded(payload)))
                values[mode].append(int(rss.read_text().strip()))
        if len(checksums) != 1:
            raise ValueError("fresh native process changed a public detector field")
        results[ident] = dict(visit, edge=edge, rss_kib=values, payload_sha256=checksums.pop())
    return dict(
        boundary="fresh single-context C process including template/IQ loading and JSON output",
        executable_sha256={role: run._sha(program) for role, program in programs.items()},
        cases=results,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work", type=local_output, default=run.WORK)
    save_json(run.REPORT / "memory.json", compare(p.parse_args().work))
