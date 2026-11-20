"""Seal cross-target verifier packets, discrete decisions and timing evidence."""

import argparse
import gzip
import math
import subprocess
from collections import Counter
from hashlib import sha256
from pathlib import Path
from struct import Struct

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from . import portable_verifier_fixture as fixture
from . import portable_verifier_run as run
from .full_v5_check import _sha

RESULT = Struct("<6I109d")
SCORE = 5e-12
CONDITIONED_SCREEN = 3e-10
FREQUENCY_HZ = 1e-6
FRACTIONAL_SAMPLE = 2e-9
GATE = 0.025
TEMPLATE_BYTES = 13_333 * 16
IQ_BYTES = 200_000 * 8


def check_input(golden, path):
    actual = memoryview(whole_iq.checked(path, golden["binary_sha256"]).read_bytes())
    if fixture.HEADER.unpack_from(actual) != (b"LEOVRF01", len(golden["visits"])):
        raise ValueError("fixture header changed")
    offset = fixture.HEADER.size
    for digest in golden["template_sha256"]:
        if sha256(actual[offset : offset + TEMPLATE_BYTES]).hexdigest() != digest:
            raise ValueError("exact or rolled template changed")
        offset += TEMPLATE_BYTES
    for visit in golden["visits"]:
        if fixture.VISIT_HEADER.unpack_from(actual, offset) != (
            visit["visit"],
            len(visit["groups"]),
        ):
            raise ValueError("physical visit order changed")
        offset += fixture.VISIT_HEADER.size
        if "sha256:" + sha256(actual[offset : offset + IQ_BYTES]).hexdigest() != visit["iq_sha256"]:
            raise ValueError("fixture lost its authenticated physical CI16")
        offset += IQ_BYTES
        for group in visit["groups"]:
            expected = (
                group["lane"],
                len(group["seeds"]),
                group["center"],
                group["minimum"],
                group["maximum"],
            )
            if fixture.GROUP_HEADER.unpack_from(actual, offset) != expected:
                raise ValueError("fixture changed a receiver group")
            offset += fixture.GROUP_HEADER.size
            for seed in group["seeds"]:
                expected = tuple(seed[k] for k in ("epoch", "bins", "absolute", "residual"))
                if fixture.SEED.unpack_from(actual, offset) != expected:
                    raise ValueError("fixture changed one retained epoch or CFO grid")
                offset += fixture.SEED.size
    if offset != len(actual):
        raise ValueError("fixture has trailing input")


def audit(golden, actual, native):
    counts, maxima = Counter(), Counter()
    rows = iter(RESULT.iter_unpack(actual))
    closest_above, closest_below = None, None
    for visit in golden["visits"]:
        final = {}
        for group in visit["groups"]:
            verified = []
            emitted_indices = set()
            counts["groups"] += 1
            for rank, index in enumerate(group["by_rank"]):
                row = next(rows)
                seed_index, fine_bin, conditioned_bin, cells, flags, frames = row[:6]
                v = row[6:]
                seed = group["seeds"][seed_index]
                ranked, integer, frac = (seed[k] for k in ("ranked", "integer", "fractional"))
                complete = frac["status"] == "complete"
                frac_margin = frac["fractional_margin"]
                expected_frames = sum(
                    seed["epoch"] + (i * 40000 + 1) // 3 + 13333 <= 200_000 for i in range(15)
                )
                if (
                    seed_index in emitted_indices
                    or fine_bin != seed["fine_winner"]
                    or cells != len(seed["conditioned_grid"])
                    or conditioned_bin != seed["conditioned_winner"]
                    or frames != expected_frames
                    or bool(flags & 1) != (integer["margin"] >= GATE)
                    or bool(flags & 2) != (frac_margin is not None and frac_margin >= GATE)
                    or bool(flags & 4) != complete
                ):
                    raise ValueError(
                        f"{golden['case']} {visit['visit']} discrete verifier changed: {row[:6]}"
                    )
                emitted_indices.add(seed_index)
                if seed_index != index:
                    other = group["seeds"][index]
                    other_margin = other["fractional"]["fractional_margin"]
                    if (
                        not flags & 128
                        or seed["epoch"] != other["epoch"]
                        or abs(seed["acquired"] - other["acquired"]) > 1e-9
                        or abs(integer["margin"] - other["integer"]["margin"]) > SCORE
                        or (frac_margin is None) != (other_margin is None)
                        or (
                            frac_margin is not None
                            and (
                                abs(frac_margin - other_margin) > SCORE
                                or (frac_margin >= GATE) != (other_margin >= GATE)
                            )
                        )
                    ):
                        raise ValueError(
                            "discrete rank changed between distinct physical candidates"
                        )
                    counts["equivalent_seed_reorders"] += 1

                def close(label, actual_value, reference, limit, visit_id=visit["visit"]):
                    delta = abs(actual_value - reference)
                    if not math.isfinite(delta) or delta > limit:
                        raise ValueError(f"{golden['case']} {visit_id} {label} error {delta:.4g}")
                    maxima[label] = max(maxima[label], delta)

                for key, a, b, limit in (
                    ("fine_interpolation_hz", v[0], seed["fine_peak"], FREQUENCY_HZ),
                    ("conditioned_cfo_hz", v[1], ranked["absolute_cfo_hz"], FREQUENCY_HZ),
                    ("conditioned_residual_hz", v[2], ranked["residual_cfo_hz"], FREQUENCY_HZ),
                    ("acquire_score", v[3], ranked["acquire_score"], SCORE),
                    ("verify_score", v[4], ranked["verify_score"], SCORE),
                    ("verify_control_score", v[5], ranked["conditioned_control_score"], SCORE),
                    ("conditioned_winning_score", v[6], ranked["conditioned_exact_score"], SCORE),
                    ("integer_exact", v[7], integer["exact_score"], SCORE),
                    ("integer_control", v[8], integer["control_score"], SCORE),
                    ("integer_margin", v[7] - v[8], integer["margin"], SCORE),
                    ("integer_residual_hz", v[9], integer["residual_cfo_hz"], FREQUENCY_HZ),
                ):
                    close(key, a, b, limit)
                if complete:
                    for key, a, b, limit in (
                        (
                            "fractional_epoch_offset_samples",
                            v[10],
                            frac["fractional_epoch_offset_samples"],
                            FRACTIONAL_SAMPLE,
                        ),
                        (
                            "fractional_log_curvature",
                            v[11],
                            frac["log_curvature"],
                            FRACTIONAL_SAMPLE,
                        ),
                        ("fractional_exact", v[12], frac["fractional_exact_score"], SCORE),
                        ("fractional_control", v[13], frac["fractional_control_score"], SCORE),
                        (
                            "fractional_residual_hz",
                            v[14],
                            frac["fractional_residual_cfo_hz"],
                            FREQUENCY_HZ,
                        ),
                        ("fractional_margin", v[12] - v[13], frac_margin, SCORE),
                    ):
                        close(key, a, b, limit)
                    distance = abs(frac_margin - GATE)
                    detail = dict(
                        visit=visit["visit"],
                        lane=group["lane"],
                        seed=index,
                        original_margin=frac_margin,
                        measured_margin=v[12] - v[13],
                        distance=distance,
                    )
                    if frac_margin >= GATE and (
                        closest_above is None or closest_above["distance"] > distance
                    ):
                        closest_above = detail
                    if frac_margin < GATE and (
                        closest_below is None or closest_below["distance"] > distance
                    ):
                        closest_below = detail
                for key, measured, expected, limit in (
                    ("fractional_exact_grid", v[15:20], frac["exact_score_grid"], SCORE),
                    ("fractional_control_grid", v[20:25], frac["control_score_grid"], SCORE),
                    (
                        "conditioned_grid_hz",
                        v[25 : 25 + cells],
                        seed["conditioned_grid"],
                        FREQUENCY_HZ,
                    ),
                    (
                        "conditioned_screen_scores",
                        v[67 : 67 + cells],
                        seed["conditioned_scores"],
                        CONDITIONED_SCREEN,
                    ),
                ):
                    for a, b in zip(measured, expected, strict=True):
                        close(key, a, b, limit)
                counts.update(
                    candidates=1,
                    conditioned_cells=cells,
                    timing_cells=5,
                    complete=complete,
                    integer_pass=bool(flags & 1),
                    fractional_pass=bool(flags & 2),
                    fine_guard=bool(flags & 8),
                    conditioned_ties=bool(flags & 16),
                    glrt_bin_ties=bool(flags & 32),
                    gate_guard=bool(flags & 64),
                    equivalent_candidates=bool(flags & 128),
                )
                if complete:
                    verified.append(
                        (rank, seed["epoch"], bool(flags & 2), v[12] - v[13], v[10], v[1] + v[14])
                    )
            final[group["lane"]] = verified
        for probe in visit["archived"]:
            for observed, signed in zip(
                final[probe["receiver_id"]], probe["candidates"], strict=True
            ):
                rank, epoch, passed, margin, offset, tracking = observed
                if (rank, epoch, passed) != (
                    signed["candidate_rank"],
                    signed["integer_epoch_sample"],
                    signed["passed_fractional_margin_gate"],
                ):
                    raise ValueError(
                        "final ranked gates differ from the independent acquisition archive"
                    )
                if (
                    abs(margin - signed["fractional_margin"]) > SCORE
                    or abs(offset - signed["fractional_epoch_offset_samples"]) > FRACTIONAL_SAMPLE
                    or abs(tracking - signed["fractional_tracking_cfo_hz"]) > FREQUENCY_HZ
                ):
                    raise ValueError(
                        "final numeric fields differ from the independent acquisition archive"
                    )
        counts["visits"] += 1
    if next(rows, None) is not None or len(actual) != len(native):
        raise ValueError("portable output has trailing candidate packets")
    native_max = max(
        abs(x - y)
        for a, b in zip(RESULT.iter_unpack(actual), RESULT.iter_unpack(native), strict=True)
        for x, y in zip(a[6:], b[6:], strict=True)
    )
    return dict(
        counts=dict(counts),
        maximum_errors=dict(maxima),
        closest_above_gate=closest_above,
        closest_below_gate=closest_below,
        max_absolute_output_delta_vs_x86=native_max,
        byte_equal_x86=actual == native,
    )


def details(work, target):
    cc, _, emulator, machine = run.TARGETS[target]
    binary = work / "build" / target / "portable-verifier"
    elf = binary.read_bytes()[:20]
    if elf[:4] != b"\x7fELF" or elf[5] != 1 or int.from_bytes(elf[18:20], "little") != machine:
        raise ValueError(f"wrong ELF target: {target}")
    if b"INTERP" in subprocess.check_output(["readelf", "-l", binary]):
        raise ValueError("portable executable has a dynamic interpreter")
    sections = subprocess.check_output(["size", binary], text=True).splitlines()[1].split()
    return dict(
        binary_sha256=_sha(binary),
        executable_bytes=binary.stat().st_size,
        text_bytes=int(sections[0]),
        data_bytes=int(sections[1]),
        bss_bytes=int(sections[2]),
        compiler=subprocess.check_output([cc, "--version"], text=True).splitlines()[0],
        options=[str(a) for a in run.command(target)],
        launch=emulator,
        architecture=machine,
        native_timing=(target == "x86"),
        emulator_speed_is_target_speed=False,
    )


def publish(work, report, cpu):
    report.mkdir(parents=True, exist_ok=True)
    if (report / "manifest.json").exists():
        raise FileExistsError("portable verifier evidence already sealed")
    files = ["PROTOCOL.md"]

    def pack(path, directory=Path(), compress=False):
        name = directory / (path.name + (".gz" if compress else ""))
        data = path.read_bytes()
        write(report / name, gzip.compress(data, mtime=0, compresslevel=6) if compress else data)
        files.append(str(name))
        return str(name)

    cases, targets = {}, {}
    for target in run.TARGETS:
        binary = work / "build" / target / "portable-verifier"
        targets[target] = details(work, target) | {
            "archive": pack(binary, Path("target") / target, True)
        }
    for case in fixture.VISITS:
        folder = work / case
        out = Path(case)
        golden_path, capture = folder / "golden.json", folder / "capture.bin"
        golden = whole_iq.read(golden_path)
        check_input(golden, capture)
        data = dict(golden=pack(golden_path, out, True), input=pack(capture, out, True), targets={})
        native = (folder / "x86-scores.bin").read_bytes()
        for target in run.TARGETS:
            scores, timing = (
                folder / f"{target}-{name}" for name in ("scores.bin", "resources.json")
            )
            measured = audit(golden, scores.read_bytes(), native)
            data["targets"][target] = dict(
                measured,
                scores=pack(scores, out, True),
                resources=pack(timing, out),
                timing=whole_iq.read(timing),
            )
        cases[case] = data
    sources = {}
    bindings = (
        run.VARIANTS / "portable_verifier.h",
        run.VARIANTS / "portable_fine.h",
        run.KERNEL / "native_presence/fft.h",
        Path(run.__file__),
        Path(fixture.__file__),
        Path(__file__),
    )
    for path in (*run.SOURCES, *bindings):
        sources[pack(path, Path("source"), True)] = _sha(path)
    save_json(
        report / "manifest.json",
        dict(
            schema_version=1,
            cpu=cpu,
            candidates=112,
            scope="Retained refined epochs and authenticated raw IQ through fractional gates",
            tolerances=dict(
                score=SCORE,
                conditioned_screen=CONDITIONED_SCREEN,
                frequency_hz=FREQUENCY_HZ,
                fractional_samples=FRACTIONAL_SAMPLE,
            ),
            targets=targets,
            cases=cases,
            sources=sources,
            files={name: _sha(report / name) for name in files},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--report", type=local_output, default=fixture.REPORT)
    parser.add_argument("--cpu", type=int, default=17)
    args = parser.parse_args()
    publish(args.work, args.report, args.cpu)
