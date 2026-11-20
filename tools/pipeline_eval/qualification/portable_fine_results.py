"""Cross-build the offline fine scorer and seal target output against frozen PocketFFT."""

import argparse
import gzip
import os
import platform
import subprocess
from collections import Counter
from hashlib import sha256
from pathlib import Path
from struct import Struct

import numpy as np

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from ..variants import fine_search, portable_fine
from . import portable_fine_fixture as fixture
from . import portable_fine_host as host
from .full_v5_check import _sha
from .projector_arm import DEFAULT_CC

ENGINE = Path(portable_fine.__file__).with_suffix(".c")
DRIVER = Path(__file__).with_name("portable_fine_cli.c")
FLAGS = (
    "-std=c11",
    "-O3",
    "-Wall",
    "-Wextra",
    "-Werror",
    "-ffp-contract=off",
    "-fopenmp-simd",
    "-static",
    "-fstack-usage",
)
TARGETS = {
    "x86": ("cc", ("-march=x86-64",), (), 62),
    "cortex-a9": (
        str(DEFAULT_CC),
        ("-mcpu=cortex-a9", "-mfpu=neon", "-mfloat-abi=hard"),
        ("qemu-arm", "-cpu", "cortex-a9"),
        40,
    ),
    "aarch64": ("aarch64-linux-gnu-gcc", ("-march=armv8-a",), ("qemu-aarch64",), 183),
}
PEAK = Struct("<4I3d")
SCORE_TOL = 5e-13
HZ_TOL = 1e-6
TEMPLATE_BYTES = 13_333 * 16
STEREO_IQ_BYTES = 200_000 * 8


def build(work):
    folder = work / "build"
    folder.mkdir()
    for target, (cc, platform_flags, _, _) in TARGETS.items():
        subprocess.run(
            [cc, *FLAGS, *platform_flags, DRIVER, ENGINE, fine_search.SOURCE, "-lm", "-o", target],
            check=True,
            cwd=folder,
            env=os.environ | {"TMPDIR": str(folder)},
            timeout=20,
        )


def execute(work, cpu):
    for target, (_, _, prefix, _) in TARGETS.items():
        launcher = ["taskset", "-c", str(cpu), *prefix, work / "build" / target]
        subprocess.run([*launcher, "--self-test"], check=True, timeout=10)
        for ident in fixture.parent_lock()["cases"]:
            directory = work / ident
            reference = whole_iq.read(directory / "reference-lock.json")
            for name, digest in reference["files"].items():
                whole_iq.checked(directory / name, digest)
            with (
                (directory / f"{target}-scores.bin").open("xb") as out,
                (directory / f"{target}-resources.json").open("xb") as timing,
            ):
                subprocess.run(
                    [*launcher, directory / "captured.iq"],
                    stdout=out,
                    stderr=timing,
                    check=True,
                    timeout=40,
                )


def audit(reference, expected, actual, host_output):
    stats = Counter()
    max_score_delta = max_hz_delta = max_host_delta = 0.0
    score_offset = output_offset = 0
    for visit in reference["visits"]:
        for row in visit["rows"]:
            bins = row["bins"]
            oracle = expected[score_offset : score_offset + bins]
            if sha256(oracle).hexdigest() != row["scores_sha256"]:
                raise ValueError("PocketFFT score vector changed after independent freeze")
            score_offset += bins
            vector = np.frombuffer(actual, dtype="<f8", offset=output_offset, count=bins)
            host_scores = np.frombuffer(host_output, dtype="<f8", offset=output_offset, count=bins)
            output_offset += bins * 8
            winner, runner, guard, frames, interpolated, gap, _ = PEAK.unpack_from(
                actual, output_offset
            )
            output_offset += PEAK.size
            expected_frames = sum(
                row["epoch"] + (i * 40000 + 1) // 3 + 301 * 44 <= 200_000 for i in range(15)
            )
            err = float(np.max(np.abs(vector - oracle)))
            delta = abs(interpolated - row["interpolated"])
            if (
                not err <= SCORE_TOL
                or not delta <= HZ_TOL
                or not abs(gap - row["gap"]) <= 2 * SCORE_TOL
                or (winner, runner) != (row["winner"], row["runner"])
                or frames != expected_frames
            ):
                raise ValueError(f"captured fine score or peak changed at visit {visit['visit']}")
            stats.update(
                calls=1,
                frequencies=bins,
                guarded=bool(guard),
                lower_grid_edge=winner == 0,
                upper_grid_edge=winner == bins - 1,
                bitwise_vectors=np.array_equal(vector, oracle),
            )
            stats[f"frames_{frames}"] += 1
            stats[f"bins_{bins}"] += 1
            max_score_delta = max(max_score_delta, err)
            max_hz_delta = max(max_hz_delta, delta)
            max_host_delta = max(max_host_delta, float(np.max(np.abs(vector - host_scores))))
    if score_offset != len(expected) or output_offset != len(actual):
        raise ValueError("the full score reference or target file has trailing output")
    return dict(
        counts=dict(stats),
        max_absolute_score_delta=max_score_delta,
        max_absolute_score_delta_vs_host=max_host_delta,
        max_absolute_interpolated_hz_delta=max_hz_delta,
    )


def audit_input(reference, actual):
    if fixture.HEADER.unpack_from(actual) != (b"LEOFINE1", len(reference["visits"])):
        raise ValueError("standalone fixture lost its physical visit count")
    offset = fixture.HEADER.size
    if sha256(actual[offset : offset + TEMPLATE_BYTES]).hexdigest() != reference["template_sha256"]:
        raise ValueError("standalone fixture lost its original pilot template")
    offset += TEMPLATE_BYTES
    for visit in reference["visits"]:
        rows = visit["rows"]
        if fixture.VISIT.unpack_from(actual, offset) != (visit["visit"], len(rows)):
            raise ValueError("standalone fixture changed physical visit order or score calls")
        offset += fixture.VISIT.size
        digest = sha256(actual[offset : offset + STEREO_IQ_BYTES]).hexdigest()
        if "sha256:" + digest != visit["raw_sha256"]:
            raise ValueError("standalone fixture changed the authenticated stereo IQ bytes")
        offset += STEREO_IQ_BYTES
        for row in rows:
            receipt = tuple(row[k] for k in ("lane", "epoch", "bins", "absolute", "residual"))
            if fixture.CALL.unpack_from(actual, offset) != receipt:
                raise ValueError("standalone fixture changed a frozen fine CFO call")
            offset += fixture.CALL.size
    if offset != len(actual):
        raise ValueError("standalone fixture has trailing input")


def target_details(work, target):
    cc, variant, emulation, machine = TARGETS[target]
    binary = work / "build" / target
    elf = binary.read_bytes()[:20]
    if elf[:4] != b"\x7fELF" or elf[5] != 1 or int.from_bytes(elf[18:20], "little") != machine:
        raise ValueError(f"unexpected ELF target identity: {target}")
    if b"INTERP" in subprocess.check_output(["readelf", "-l", binary]):
        raise ValueError("standalone target has a dynamic interpreter")
    stack = []
    for report in sorted((work / "build").glob(f"{target}-*.su")):
        stack.extend(line.split("\t") for line in report.read_text().splitlines())
    return dict(
        architecture=machine,
        compiler=subprocess.check_output([cc, "--version"], text=True).splitlines()[0],
        flags=[*FLAGS, *variant],
        emulation=emulation,
        emulator_version=(
            subprocess.check_output([emulation[0], "--version"], text=True).splitlines()[0]
            if emulation
            else None
        ),
        executable_sha256=_sha(binary),
        executable_bytes=binary.stat().st_size,
        compiler_reported_stack=stack,
        physical_target_speed_measured=not emulation,
    )


def publish(work, report, cpu):
    report.mkdir(parents=True, exist_ok=True)
    if (report / "manifest.json").exists():
        raise FileExistsError("sealed portable fine evidence already exists")
    files = ["PROTOCOL.md"]

    def pack(path, subdirectory=Path(), compress=False):
        name = subdirectory / (path.name + (".gz" if compress else ""))
        contents = path.read_bytes()
        if compress:
            contents = gzip.compress(contents, compresslevel=6, mtime=0)
        write(report / name, contents)
        files.append(str(name))
        return str(name)

    targets = {}
    for target in TARGETS:
        targets[target] = target_details(work, target) | {
            "archive": pack(work / "build" / target, Path("target"), compress=True)
        }
    cases = {}
    for ident in fixture.parent_lock()["cases"]:
        folder, out = work / ident, Path(ident)
        reference = whole_iq.read(folder / "reference-lock.json")
        capture = whole_iq.checked(folder / "captured.iq", reference["files"]["captured.iq"])
        audit_input(reference, memoryview(capture.read_bytes()))
        reference_scores = np.fromfile(
            whole_iq.checked(
                folder / "pocketfft-scores.bin", reference["files"]["pocketfft-scores.bin"]
            ),
            dtype="<f8",
        )
        data = dict(
            reference=pack(folder / "reference-lock.json", out),
            captured_iq=pack(folder / "captured.iq", out, compress=True),
            reference_scores=pack(folder / "pocketfft-scores.bin", out, compress=True),
            targets={},
        )
        native = None
        for target in TARGETS:
            scorefile = folder / f"{target}-scores.bin"
            timing = folder / f"{target}-resources.json"
            actual = scorefile.read_bytes()
            if target == "x86":
                native = actual
            measured = audit(reference, reference_scores, actual, native)
            measured.update(
                numerically_bitwise_equal_to_host=(actual == native),
                scores=pack(scorefile, out, compress=True),
                resources=pack(timing, out),
                summary=whole_iq.read(timing),
            )
            data["targets"][target] = measured
        if (folder / "normal-detector.json").exists():
            data["normal_detector"] = pack(folder / "normal-detector.json", out)
        cases[ident] = data
    sources = {}
    for path in (
        ENGINE,
        ENGINE.with_suffix(".h"),
        DRIVER,
        fine_search.SOURCE,
        Path(fixture.__file__),
        Path(host.__file__),
        Path(portable_fine.__file__),
        Path(__file__),
    ):
        archive = pack(path, Path("source"), compress=True)
        sources[archive] = _sha(path)
    save_json(
        report / "manifest.json",
        dict(
            version=1,
            cpu=cpu,
            processor=platform.machine(),
            score_tolerance=SCORE_TOL,
            interpolation_tolerance_hz=HZ_TOL,
            targets=targets,
            cases=cases,
            sources=sources,
            files={name: _sha(report / name) for name in files},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "execute", "publish"))
    parser.add_argument("work", type=local_output)
    parser.add_argument("--cpu", type=int, default=12)
    parser.add_argument("--report", type=local_output, default=fixture.REPORT)
    args = parser.parse_args()
    if args.action == "build":
        build(args.work)
    elif args.action == "execute":
        execute(args.work, args.cpu)
    else:
        publish(args.work, args.report, args.cpu)
