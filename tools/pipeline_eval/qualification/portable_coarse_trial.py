"""Join native coarse acquisition and the frozen verifier on raw-only fixtures."""

import argparse
import gzip
import json
import os
import subprocess
from hashlib import sha256
from pathlib import Path
from struct import Struct
from time import perf_counter_ns, process_time_ns

import numpy as np

from ..__main__ import ROOT, local_output, save_json, write
from ..variants import portable_coarse, prepared_hotpath_peaks
from ..variants.original_kernel import PersistentGrid
from . import capture_exact_trial as exact
from . import original_kernel_trial as original
from . import portable_verifier_fixture as prior
from . import sliding_pilot_trial as sliding
from .capture_runtime import checked, read
from .coarse_basis_eval import captures, compare_map
from .full_v5_check import _load_case, _sha

REPORT = ROOT / "reports/2026_11_19_receiver_screening/original-schedule/portable-coarse"
CLI = Path(__file__).with_name("portable_coarse_cli.c")
PARENT = "481a79c7581330d68dfd1ed5dd35e4fe27bac4bc77c1a3996d4907e782a6b9ec"
SLIDING_SHA = "0ff64cdba8002e3093e26fa593a73014ab827dadae16d097b0bc6ec99e7f8758"
HEADER = Struct("<8sI")
RAW_HEADER = Struct("<5I4d")
VISIT = Struct("<2I")
GROUP = Struct("<3I4Q")
SEED = Struct("<2I2dId")
TARGETS = ("x86", "aarch64", "cortex-a9")
CPUS = dict(x86=4, aarch64=5, **{"cortex-a9": 5})
TEMPLATE_BYTES = 13_333 * 16
IQ_BYTES = 200_000 * 8
RESULT_BYTES = 896


def source_paths():
    return (
        Path(__file__),
        CLI,
        portable_coarse.SOURCE,
        portable_coarse.HEADER,
        portable_coarse.QIN,
        Path(portable_coarse.__file__),
        REPORT / "PROTOCOL.md",
    )


def build(work, target):
    from . import portable_verifier_run as verifier

    cc, arch, _, _ = verifier.TARGETS[target]
    arch = ("-march=x86-64-v3",) if target == "x86" else arch
    folder = work / target
    folder.mkdir(exist_ok=True)
    binary = folder / "portable-coarse"
    command = [
        cc,
        *verifier.BUILD_FLAGS,
        *arch,
        "-I",
        str(verifier.KERNEL / "native_presence"),
        CLI,
        portable_coarse.SOURCE,
        *verifier.SOURCES[1:],
        "-lm",
        "-o",
        binary,
    ]
    env = os.environ | {"TMPDIR": str(folder)}
    subprocess.run(command, cwd=folder, env=env, check=True, timeout=35)
    if subprocess.check_output(["readelf", "-l", binary]).find(b"INTERP") >= 0:
        raise ValueError("standalone ELF requests a dynamic interpreter")
    return dict(
        command=[str(a) for a in command],
        sha256=_sha(binary),
        bytes=binary.stat().st_size,
        tool=subprocess.check_output([cc, "--version"], text=True).splitlines()[0],
    )


def raw_visits(golden, capture):
    if sha256(capture).hexdigest() != golden["binary_sha256"]:
        raise ValueError("uncompressed parent fixture changed")
    cursor = HEADER.size + 2 * TEMPLATE_BYTES
    for visit in golden["visits"]:
        ident, groups = prior.VISIT_HEADER.unpack_from(capture, cursor)
        if (ident, groups) != (visit["visit"], len(visit["groups"])):
            raise ValueError("original visit boundary changed")
        cursor += VISIT.size
        raw = capture[cursor : cursor + IQ_BYTES]
        cursor += IQ_BYTES
        if "sha256:" + sha256(raw).hexdigest() != visit["iq_sha256"]:
            raise ValueError("raw-only projection changed original receiver samples")
        centers, limits = {}, set()
        for group in visit["groups"]:
            lane, count, center, first, last = prior.GROUP_HEADER.unpack_from(capture, cursor)
            if (lane, count, center, first, last) != (
                group["lane"],
                len(group["seeds"]),
                group["center"],
                group["minimum"],
                group["maximum"],
            ):
                raise ValueError("original public geometry changed")
            cursor += prior.GROUP_HEADER.size + count * prior.SEED.size
            centers[lane] = center
            limits.add((first, last))
        if set(centers) != {0, 1} or len(limits) != 1:
            raise ValueError("archived visit geometry cannot be represented by one dual header")
        lower, upper = limits.pop()
        yield (
            visit,
            RAW_HEADER.pack(
                ident,
                200_000,
                ("lower", "upper").index(golden["edge"]),
                3,
                1,
                centers[0],
                centers[1],
                lower,
                upper,
            )
            + raw,
        )
    if cursor != len(capture):
        raise ValueError("original fixture has leftover payload")


def freeze(work):
    from . import portable_verifier_run as verifier

    work.mkdir()
    seal = checked(prior.REPORT / "manifest.json", PARENT)
    parent = read(seal)
    source = (
        verifier.SOURCES[1:],
        (
            verifier.VARIANTS / "portable_verifier.h",
            verifier.VARIANTS / "portable_fine.h",
            verifier.KERNEL / "native_presence/fft.h",
        ),
    )
    for path in (*source[0], *source[1]):
        checked(path, parent["sources"][f"source/{path.name}.gz"])
    cases = {}
    for case, old in parent["cases"].items():
        current = work / case
        current.mkdir()
        golden, _, capture = [
            gzip.decompress(checked(prior.REPORT / name, parent["files"][name]).read_bytes())
            for name in (old["golden"], old["targets"]["x86"]["scores"], old["input"])
        ]
        rows = list(raw_visits(json.loads(golden), capture))
        names = []
        for visit, indexes in (("all", range(len(rows))), ("short", (0,))):
            packet = [rows[index] for index in indexes]
            raw = HEADER.pack(b"LEOCOA01", len(packet)) + b"".join(r[1] for r in packet)
            write(current / f"{visit}.ci16", raw)
            names.append(f"{visit}.ci16")
        write(current / "golden.json", golden)
        cases[case] = {name: _sha(current / name) for name in ("golden.json", *names)}
    compiled = {target: build(work, target) for target in TARGETS}
    save_json(
        work / "input-lock.json",
        dict(
            cases=cases,
            builds=compiled,
            parent_manifest_sha256=PARENT,
            sources={str(path): _sha(path) for path in (*source_paths(), *source[0], *source[1])},
        ),
    )


def decode_output(golden, data):
    if HEADER.unpack_from(data) != (b"LEOCOUT1", len(golden["visits"])):
        raise ValueError("unexpected raw detector output header")
    cursor, results, clocks = HEADER.size, [], []
    attempts, seeds = 0, 0
    for visit in golden["visits"]:
        number, groups = VISIT.unpack_from(data, cursor)
        cursor += VISIT.size
        if (number, groups) != (visit["visit"], len(visit["groups"])):
            raise ValueError("raw detector changed conditional retry inventory")
        seen = set()
        for g in visit["groups"]:
            lane, count, total, coarse_cpu, coarse_wall, verify_cpu, verify_wall = (
                GROUP.unpack_from(data, cursor)
            )
            cursor += GROUP.size
            if (lane, total, count) != (g["lane"], len(g["seeds"]), 22 if lane in seen else 12):
                raise ValueError("raw detector changed physical group or anchor masks")
            seen.add(lane)
            attempts += count == 22
            seeds += total
            for seed in g["seeds"]:
                emitted = SEED.unpack_from(data, cursor)
                cursor += SEED.size
                if emitted[:4] != tuple(seed[k] for k in ("epoch", "bins", "absolute", "residual")):
                    raise ValueError(
                        f"{golden['case']} visit {number} physical lane {lane} changed ordered "
                        f"coarse-to-fine seed: {emitted[:4]}"
                    )
            end = cursor + total * RESULT_BYTES
            results.append(data[cursor:end])
            cursor = end
            clocks.append(
                dict(
                    visit=number,
                    lane=lane,
                    anchors=count,
                    candidates=total,
                    coarse_cpu_ns=coarse_cpu,
                    coarse_wall_ns=coarse_wall,
                    verify_cpu_ns=verify_cpu,
                    verify_wall_ns=verify_wall,
                )
            )
    if cursor != len(data):
        raise ValueError("raw detector output contains extra records")
    return b"".join(results), clocks, dict(seeds=seeds, retries=attempts)


def execute(work, target):
    from . import portable_verifier_results as oracle
    from . import portable_verifier_run as verifier

    lock = read(work / "input-lock.json")
    for path, digest in lock["sources"].items():
        checked(Path(path), digest)
    binary = checked(work / target / "portable-coarse", lock["builds"][target]["sha256"])
    _, _, emu, _ = verifier.TARGETS[target]
    launch = ["taskset", "-c", str(CPUS[target]), *emu, binary]
    parent = read(checked(prior.REPORT / "manifest.json", PARENT))
    names = tuple(lock["cases"]) if target == "x86" else ("DS26-0237", "DS29-0082")
    out = {}
    for case in names:
        directory = work / case
        roster = lock["cases"][case]
        golden = read(checked(directory / "golden.json", roster["golden.json"]))
        variant = "all" if target == "x86" else "short"
        source = checked(directory / f"{variant}.ci16", roster[f"{variant}.ci16"])
        if variant == "short":
            golden["visits"] = golden["visits"][:1]
        times, evidence = [], None
        old_name = parent["cases"][case]["targets"]["x86"]["scores"]
        old = gzip.decompress(
            checked(prior.REPORT / old_name, parent["files"][old_name]).read_bytes()
        )
        for _ in range(3 if target == "x86" else 1):
            run = subprocess.run([*launch, source], capture_output=True, check=True, timeout=100)
            results, clocks, counts = decode_output(golden, run.stdout)
            confidence = oracle.audit(golden, results, old[: len(results)])
            if evidence is not None and evidence != confidence:
                raise ValueError("repeated standalone source produced different numerical result")
            evidence = confidence
            times.append(dict(clocks=clocks, resources=json.loads(run.stderr)))
        out[case] = dict(verification=evidence, timing=times, **counts)
        print(target, case, counts, flush=True)
    save_json(work / f"{target}.json", out)


def development(work, name):
    from leo.analysis.starlink import acquisition

    lockpath = checked(sliding.REPORT / "qualification-lock.json", SLIDING_SHA)
    anchored = read(lockpath)["files"]["input-lock.json"]
    lock = read(checked(sliding.REPORT / "input-lock.json", anchored))
    case = lock["cases"][name]
    if not Path(acquisition.__file__).is_relative_to(case["root"]) or os.sched_getaffinity(0) != {
        4
    }:
        raise ValueError("development uses wrong producer or core")
    for path, digest in case["sources"].items():
        checked(Path(path), digest)
    item = case["rows"][0]
    entry = _load_case(name)
    _, policy, _ = exact.lineage.source_lineage(entry)
    segment, manifest, window = original.decode(entry, item["visit"])
    if (segment, manifest, window.iq_sha256) != (
        item["segment"],
        item["manifest"],
        item["iq_sha256"],
    ):
        raise ValueError("development CI16 differs from its seal")
    old, _, args = captures(window, policy)
    lib = lock["libs"]["prepared"]
    grid = PersistentGrid(checked(Path(lib["path"]), lib["sha256"]))
    portable, cmd = portable_coarse.build(work)
    observations = []
    try:
        with portable_coarse.Coarse(portable, case["edge"]) as coarse:
            template_errors = [
                float(
                    abs(
                        coarse.template(bool(roll))
                        - acquisition.qin_edge_pilot_frame(
                            10_000_000, case["edge"], symbol_roll=roll
                        )
                    ).max()
                )
                for roll in (0, 17)
            ]
            for lane, (params, ranks) in enumerate(args):
                cfo, residual = params[3], ranks[0]
                center = cfo[0] - residual[0]
                for symbols in (params[4], sliding.sliding_pilot.RETRY):
                    test = (*params[:4], symbols, params[-1])
                    before = np.asarray(grid.score_grid(acquisition, old, *test))
                    clocks = []
                    for _ in range(3):
                        wall, cpu = perf_counter_ns(), process_time_ns()
                        seeds, peaks = coarse.acquire(
                            window.samples,
                            lane,
                            len(symbols),
                            (center, center),
                            (residual[0], residual[-1]),
                        )
                        clocks.append(
                            dict(cpu_ns=process_time_ns() - cpu, wall_ns=perf_counter_ns() - wall)
                        )
                    current, support = coarse.grid()
                    comparison = compare_map(
                        before, current, prepared_hotpath_peaks.retained_peaks, ranks
                    )
                    seen = [(p["original_epoch"], p["residual_hz"]) for p in peaks]
                    if not comparison["ordered"] or seen != [
                        tuple(p[1:]) for p in comparison["baseline_peaks"]
                    ]:
                        raise ValueError("development portable peak order changed")
                    observations.append(
                        dict(
                            lane=lane,
                            anchors=len(symbols),
                            clocks=clocks,
                            seeds=seeds,
                            support=[int(support.min()), int(support.max())],
                            comparison=comparison,
                        )
                    )
    finally:
        grid.clear_cache()
    save_json(
        work / f"{name}-development.json",
        dict(
            case=name,
            edge=case["edge"],
            visit=item["visit"],
            rows=observations,
            template_max_errors=template_errors,
            portable_sha256=_sha(portable),
            build=cmd,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("freeze", "execute", "development"))
    parser.add_argument("work", type=local_output)
    parser.add_argument("name", nargs="?")
    args = parser.parse_args()
    if args.operation == "freeze":
        freeze(args.work)
    elif args.operation == "execute":
        execute(args.work, args.name)
    else:
        development(args.work, args.name)
