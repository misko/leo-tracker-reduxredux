"""Qualify the compact verifier through the dual raw detector and stage guards."""

import argparse
import gzip
import json
import math
import random
import subprocess
from array import array
from collections import Counter
from pathlib import Path
from struct import Struct

from . import c_fine_memory_build as build

BASE = build.ROOT / "reports/2026_11_19_receiver_screening"
REPORT = BASE / "native-receiver/verifier-memory"
FROZEN = BASE / "coarse-and-navigation/portable-verifier"
HELD = BASE / "original-schedule/verifier-integration"
FROZEN_SHA = "481a79c7581330d68dfd1ed5dd35e4fe27bac4bc77c1a3996d4907e782a6b9ec"
HELD_SHA = "c20332eac653646adef761d6e9c6d150e623a0e8fad5fc22de7261476fdc1f53"
HEADER = Struct("<8sI")
VISIT = Struct("<2I")
RAW = Struct("<5I4d")
RANGE = Struct("<2I3d")
SEED = Struct("<2I2d")
GROUP = Struct("<3I4Q")
COARSE = Struct("<2I2dId")
RESULT = Struct("<6I109d")
TEMPLATE_BYTES = 13333 * 16
IQ_BYTES = 200000 * 8
ARMS = ("stock", "compact")


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def checked(path, sha):
    data = path.read_bytes()
    if build.digest(data) != sha.removeprefix("sha256:"):
        raise ValueError(f"Input hash changed for {path}")
    return data


def full_visit(number, raw, edge, bounds, flags=1):
    return RAW.pack(number, len(raw) // 8, ("lower", "upper").index(edge), 3, flags, *bounds) + raw


def stage_fixtures(work):
    manifest = json.loads(checked(FROZEN / "manifest.json", FROZEN_SHA))
    locked, complete, bounds = {}, [], {}
    for case, item in manifest["cases"].items():
        golden_path, raw_path = item["golden"], item["input"]
        golden, capture = [
            gzip.decompress(checked(FROZEN / p, manifest["files"][p]))
            for p in (golden_path, raw_path)
        ]
        golden = json.loads(golden)
        if build.digest(capture) != golden["binary_sha256"]:
            raise ValueError(f"Decompressed retained seeds changed for {case}")
        template = capture[HEADER.size : HEADER.size + 2 * TEMPLATE_BYTES]
        cursor = HEADER.size + len(template)
        checks = []
        for visit in golden["visits"]:
            visit_start = cursor
            number, groups = VISIT.unpack_from(capture, cursor)
            cursor += VISIT.size
            raw = capture[cursor : cursor + IQ_BYTES]
            cursor += IQ_BYTES
            checked_raw = build.digest(raw)
            if (
                checked_raw != visit["iq_sha256"].removeprefix("sha256:")
                or number != visit["visit"]
            ):
                raise ValueError(f"Original CI16 differs for {case} {number}")
            centers, ranges = {}, set()
            for group in visit["groups"]:
                lane, count, center, low, high = RANGE.unpack_from(capture, cursor)
                if lane != group["lane"] or count != len(group["seeds"]):
                    raise ValueError("Retained seed route changed")
                centers[lane] = center
                ranges.add((low, high))
                cursor += RANGE.size + count * SEED.size
            if len(ranges) != 1 or set(centers) != {0, 1} or groups != len(visit["groups"]):
                raise ValueError("Retained routes have incompatible bounds")
            geometry = (centers[0], centers[1], *ranges.pop())
            if case in bounds and geometry != bounds[case]:
                raise ValueError("Recorded visits changed calibration geometry")
            bounds[case] = geometry
            checks.append(dict(visit=number, purpose=visit["purpose"], iq_sha256=checked_raw))
            complete.append(full_visit(number, raw, golden["edge"], geometry))
            if case == "DS26-0237" and number == 1561:
                (work / "arm-stage.bin").write_bytes(
                    HEADER.pack(b"LEOVRF01", 1) + template + capture[visit_start:cursor]
                )
        if cursor != len(capture):
            raise ValueError("Unexpected trailing retained-seed bytes")
        path = work / f"{case}-stage.bin"
        path.write_bytes(capture)
        locked[path.name] = dict(
            sha256=build.digest(capture),
            visits=checks,
            edge=golden["edge"],
            producer=golden["producer"],
            bounds=bounds[case],
        )
    return locked, complete, bounds


def held_fixtures(bounds):
    manifest = json.loads(checked(HELD / "manifest.json", HELD_SHA))
    plan = json.loads(checked(HELD / "input-lock.json", manifest["files"]["input-lock.json"]))
    complete, locked = [], []
    for case, cfg in plan["cases"].items():
        name = f"{case}/resident-lock.json"
        ledger = json.loads(checked(HELD / name, manifest["files"][name]))
        captured = {item["visit"]: item for item in ledger["staged"]}
        for choice in cfg["rows"]:
            visit = choice["visit"]
            item = captured[visit]
            name = f"{case}/capture/{visit}.ci16.gz"
            raw = gzip.decompress(checked(HELD / name, manifest["files"][name]))
            if len(raw) != IQ_BYTES or build.digest(raw) != item["iq_sha256"].removeprefix(
                "sha256:"
            ):
                raise ValueError(f"Held CI16 changed for {case} {visit}")
            complete.append(full_visit(visit, raw, cfg["edge"], bounds[case]))
            locked.append(
                dict(
                    case=case,
                    visit=visit,
                    purpose=choice["kind"],
                    edge=cfg["edge"],
                    producer=cfg["root"],
                    iq_sha256=item["iq_sha256"],
                    bounds=bounds[case],
                )
            )
    return complete, locked


def guard_fixtures(work):
    # A repeated otherwise-silent tap at a fixed inter-frame epoch makes all
    # fine magnitudes close-ranked and some conditioned frequencies tied.
    quiet = bytes(IQ_BYTES)
    impulse = array("h", [0]) * (IQ_BYTES // 2)
    for frame in range(15):
        for lane in range(2):
            index = ((frame * 40000 + 1) // 3 + 100) * 4 + 2 * lane
            impulse[index] = 1200
            impulse[index + 1] = -321
    rng = random.Random(194617)
    noise = array("h", (rng.randrange(-128, 129) for _ in range(IQ_BYTES // 2))).tobytes()
    stage = (work / "arm-stage.bin").read_bytes()
    templates = stage[HEADER.size : HEADER.size + 2 * TEMPLATE_BYTES]
    pattern = bytearray(HEADER.pack(b"LEOVRF01", 3) + templates)
    for visit, raw in enumerate((quiet, impulse.tobytes(), noise), 101):
        pattern.extend(VISIT.pack(visit, 2) + raw)
        pattern.extend(RANGE.pack(0, 3, 0, -5e6, 5e6))
        pattern.extend(SEED.pack(0, 2, -5e6, -5e6))
        pattern.extend(SEED.pack(0, 2, -5e6, -5e6))
        pattern.extend(SEED.pack(13332, 32, 5e6 - 15500, 5e6 - 15500))
        pattern.extend(RANGE.pack(1, 2, 0, -5e6, 5e6))
        pattern.extend(SEED.pack(1, 160, -40000, -40000))
        pattern.extend(SEED.pack(13332, 321, -80000, -80000))
    (work / "guard-stage.bin").write_bytes(pattern)
    bound = (0, 0, -800000, 800000)
    full = [
        full_visit(101, quiet, "lower", bound),
        full_visit(102, noise, "upper", bound),
        full_visit(103, noise[: 137 * 8], "upper", bound, flags=0),
    ]
    (work / "guard-full.bin").write_bytes(HEADER.pack(b"LEOCOA01", len(full)) + b"".join(full))
    (work / "truncated.bin").write_bytes(HEADER.pack(b"LEOCOA01", 1) + full[0][:-1])


def freeze(work):
    stage, development, bounds = stage_fixtures(work)
    held, held_lock = held_fixtures(bounds)
    for key, group in (("development", development), ("held", held), ("arm-full", held[::4][:2])):
        (work / f"{key}.bin").write_bytes(HEADER.pack(b"LEOCOA01", len(group)) + b"".join(group))
    guard_fixtures(work)
    return dict(
        retained=stage,
        held=held_lock,
        references={
            str(FROZEN.relative_to(build.ROOT)): FROZEN_SHA,
            str(HELD.relative_to(build.ROOT)): HELD_SHA,
        },
        streams={p.name: build.digest(p.read_bytes()) for p in work.glob("*.bin")},
    )


def full_result(data, verification=None):
    magic, visits = HEADER.unpack_from(data)
    if magic != b"LEOCOUT1":
        raise ValueError("Incorrect detector result signature")
    cursor, inventory, records = HEADER.size, [], []
    coarse_cpu = coarse_wall = verify_cpu = verify_wall = 0
    groups = 0
    for _ in range(visits):
        visit, count = VISIT.unpack_from(data, cursor)
        groups += count
        cursor += VISIT.size
        inventory.append((visit, count))
        for _ in range(count):
            lane, anchors, size, coarse, coarse_w, verify, verify_w = GROUP.unpack_from(
                data, cursor
            )
            coarse_cpu += coarse
            coarse_wall += coarse_w
            verify_cpu += verify
            verify_wall += verify_w
            cursor += GROUP.size
            seeds = tuple(COARSE.unpack_from(data, cursor + i * COARSE.size) for i in range(size))
            inventory.append((lane, anchors, seeds))
            cursor += size * COARSE.size
            if verification is None or visit in verification:
                for _ in range(size):
                    records.append(RESULT.unpack_from(data, cursor))
                    cursor += RESULT.size
    if cursor != len(data):
        raise ValueError("Detector result has extra bytes")
    return (
        inventory,
        records,
        dict(
            visits=visits,
            groups=groups,
            coarse_cpu_ns=coarse_cpu,
            coarse_wall_ns=coarse_wall,
            verify_cpu_ns=verify_cpu,
            verify_wall_ns=verify_wall,
        ),
    )


def errors(reference, candidate):
    if len(reference) != len(candidate):
        raise ValueError("Verifier changed candidate count")
    maxima = Counter()
    counts = Counter(candidates=len(reference))
    nearest = {"pass": None, "fail": None}
    for rank, (before, after) in enumerate(zip(reference, candidate, strict=True)):
        if before[:6] != after[:6]:
            raise ValueError(f"Verifier changed rank {rank}: {before[:6]} versus {after[:6]}")
        i, new = before[6:], after[6:]
        flags = before[4]
        counts["different_numeric_records"] += before != after
        for flag, label in (
            (1, "integer_pass"),
            (2, "fractional_pass"),
            (4, "fractional_complete"),
            (8, "fine_guard"),
            (16, "conditioned_tie"),
            (32, "glrt_bin_tie"),
            (64, "gate_guard"),
            (128, "equivalent_tie"),
        ):
            counts[label] += bool(flags & flag)
        counts["short_conditioned_frames"] += before[5] < 15
        for key, indices, ceiling in (
            ("fine_hz", (0,), 1e-6),
            ("acquired_hz", (1, 2), 1e-6),
            ("held_scores", range(3, 6), 5e-12),
            ("conditioned_scores", (6, *range(67, 109)), 3e-10),
            ("integer_scores", (7, 8, *range(15, 25)), 5e-12),
            ("glrt_hz", (9, 14), 1e-6),
            ("fractional_offset", (10,), 2e-9),
            ("curvature", (11,), 5e-12),
            ("fractional_scores", (12, 13), 5e-12),
            ("conditioned_grid_hz", range(25, 67), 1e-6),
        ):
            delta = max(abs(i[k] - new[k]) for k in indices)
            if not math.isfinite(delta) or delta > ceiling:
                raise ValueError(f"Verifier rank {rank} error {key}={delta} exceeds {ceiling}")
            maxima[key] = max(maxima[key], delta)
        for key, a, b in (("integer_margin", 7, 8), ("fractional_margin", 12, 13)):
            maxima[key] = max(maxima[key], abs((i[a] - i[b]) - (new[a] - new[b])))
        if flags & 4:
            margin = i[12] - i[13]
            key = "pass" if flags & 2 else "fail"
            if nearest[key] is None or abs(margin - 0.025) < abs(nearest[key] - 0.025):
                nearest[key] = margin
    return dict(
        counts=dict(counts), max_absolute_errors=dict(maxima), closest_fractional_margin=nearest
    )


def launch(binary, target, cpu, input_file, cwd=None):
    emulation = build.TARGETS[target][2]
    cmd = ["taskset", "-c", str(cpu), *emulation, binary, input_file]
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, timeout=105)


def profile_x86(work):
    results = {}
    for arm in ARMS:
        binary, compiled = build.build(work, "x86", arm, profile=True)
        launch(binary, "x86", 10, work / "held.bin", cwd=binary.parent)
        raw = subprocess.check_output(
            ["gprof", "-bp", binary, binary.parent / "gmon.out"], text=True, timeout=15
        )
        results[arm] = dict(
            executable_sha256=compiled["sha256"],
            sample_resolution=raw.splitlines()[2].strip(),
            flat_profile=raw.splitlines()[4:18],
        )
    return results


def measure(work, repeats, targets):
    ledger = freeze(work)
    builds, evidence = {}, {}
    proc = Path("/proc/cpuinfo").read_text()
    metadata = dict(
        host_model=next(
            line.split(":", 1)[1].strip()
            for line in proc.splitlines()
            if line.startswith("model name")
        ),
        load_start=Path("/proc/loadavg").read_text().strip(),
    )
    for target in targets:
        for arm in ARMS:
            for driver in ("full", "stage"):
                builds[target, arm, driver], details = build.build(work, target, arm, driver)
                evidence[f"{target}-{arm}-{driver}"] = details

    timings, checks = [], {}
    for target in targets:
        trial_sets = {
            "x86": ("held", "development", "guard-full"),
            "aarch64": ("arm-full",),
            "cortex-a9": (),
        }[target]
        for trial in trial_sets:
            compared = None
            for repeat in range(repeats if trial == "held" else 1):
                cpu = 10 + repeat % 2
                outcomes = {}
                order = ARMS if (repeat // 2 + repeat % 2) % 2 == 0 else ARMS[::-1]
                for arm in order:
                    path = work / f"{trial}.bin"
                    run = launch(builds[target, arm, "full"], target, cpu, path)
                    inventory, records, clocks = full_result(
                        run.stdout, {101, 102} if trial == "guard-full" else None
                    )
                    outcomes[arm] = (inventory, records)
                    resources = json.loads(run.stderr) | clocks
                    if target == "x86" and resources["vm_hwm_kib"] <= 0:
                        raise ValueError("Native detector RSS high-water reading unavailable")
                    timings.append(
                        dict(
                            target=target,
                            fixture=trial,
                            repeat=repeat,
                            arm=arm,
                            cpu=cpu,
                            candidates=len(records),
                            order=order.index(arm),
                            **resources,
                        )
                    )
                first, second = (outcomes[arm] for arm in ARMS)
                if first[0] != second[0]:
                    raise ValueError("Coarse seeds or conditional retry routing changed")
                compared = errors(first[1], second[1])
                if repeat == 0:
                    expected = outcomes
                elif outcomes != expected:
                    raise ValueError("Detector result changed across native repeats")
            checks[f"{target}-{trial}"] = compared
            print(
                f"{target} {trial}: {compared['counts']['candidates']} matched candidates",
                flush=True,
            )
        stages = (*ledger["retained"], "guard-stage.bin") if target == "x86" else ("arm-stage.bin",)
        for case in stages:
            results = []
            for arm in ARMS:
                run = launch(builds[target, arm, "stage"], target, 11, work / case)
                records = list(RESULT.iter_unpack(run.stdout))
                results.append(records)
                timings.append(
                    dict(
                        target=target,
                        fixture=case,
                        arm=arm,
                        cpu=11,
                        repeat=0,
                        **json.loads(run.stderr),
                    )
                )
            checks[f"{target}-{case}"] = errors(*results)
        for arm in ARMS:
            sentinel = launch(builds[target, arm, "stage"], target, 11, "--self-test")
            if sentinel.stdout != b"standalone verifier sentinels passed\n":
                raise ValueError(f"Verifier sentinels failed for {target}/{arm}")

    for arm in ARMS:
        bad = subprocess.run(
            ["taskset", "-c", "10", builds["x86", arm, "full"], work / "truncated.bin"],
            capture_output=True,
            timeout=15,
        )
        if (
            bad.returncode != 2
            or bad.stderr != b"truncated raw coarse stream\n"
            or bad.stdout != HEADER.pack(b"LEOCOUT1", 1)
        ):
            raise ValueError("Physically truncated raw capture failed open")
    guards = checks["x86-guard-stage.bin"]["counts"]
    if not all(
        guards[key]
        for key in ("fine_guard", "conditioned_tie", "equivalent_tie", "short_conditioned_frames")
    ):
        raise ValueError(
            "Tied, ambiguous, or frame-truncated stage control missed its intended path"
        )
    if checks["x86-guard-full"]["counts"]["fractional_pass"]:
        raise ValueError("Full-detector negative control admitted a fractional gate")
    metadata["load_end"] = Path("/proc/loadavg").read_text().strip()
    return dict(
        metadata=metadata,
        inputs=ledger,
        builds=evidence,
        timings=timings,
        checks=checks,
        x86_sampling_profile=profile_x86(work),
        truncated_raw_rejected=True,
        original_self_tests_passed=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("--repeats", type=int, default=8)
    parser.add_argument("--targets", nargs="+", choices=build.TARGETS, default=list(build.TARGETS))
    args = parser.parse_args()
    if args.repeats < 5:
        parser.error("Use at least five matched timing pairs")
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    write_json(work / "qualification.json", measure(work, args.repeats, args.targets))
