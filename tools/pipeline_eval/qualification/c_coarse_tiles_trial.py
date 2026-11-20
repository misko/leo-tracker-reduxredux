"""Freeze dual-radio inputs and compare complete standalone C detectors."""

import argparse
import gzip
import itertools
import json
import os
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from struct import Struct
from time import perf_counter_ns

import numpy as np

from ..__main__ import local_output, save_json
from ..variants.portable_coarse import Coarse
from . import (
    capture_detector_lineage,
    coarse_basis_eval,
    original_kernel_trial,
    sliding_pilot_trial,
)
from . import portable_coarse_trial as reference
from .capture_runtime import checked, read
from .full_v5_check import _load_case

METHODS = ("incumbent", "pairs", "tiles")
CASES = ("DS26-0237", "DS29-0082", "DS29-0519")
CPUS = (8, 9)
PROFILE_CPU = 12
AUDIT_CPU = 13
REF_SHA = "c8b3c5634ecd59b2a9a6e5acea6fadbac7c83b781d7a3b5e7e43fc2f0ce66fa0"
SEAL = "qualification-lock.json"
HEADER, RAW, VISIT, GROUP, SEED = (
    reference.HEADER,
    reference.RAW_HEADER,
    reference.VISIT,
    reference.GROUP,
    reference.SEED,
)
RESULT = Struct("<6I109d")


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def locks():
    ref_seal = read(checked(reference.REPORT / SEAL, REF_SHA))
    sliding = sliding_pilot_trial.REPORT
    dev_seal = read(checked(sliding / SEAL, reference.SLIDING_SHA))
    return (
        read(checked(reference.REPORT / "input-lock.json", ref_seal["files"]["input-lock.json"])),
        read(checked(sliding / "input-lock.json", dev_seal["files"]["input-lock.json"])),
    )


def input_packets(payload):
    signature, count = HEADER.unpack_from(payload)
    if signature != b"LEOCOA01" or not 1 <= count <= 64:
        raise ValueError("raw detector input header changed")
    cursor, items = HEADER.size, []
    for _ in range(count):
        fields = RAW.unpack_from(payload, cursor)
        length = RAW.size + 8 * fields[1]
        packet = bytes(payload[cursor : cursor + length])
        if len(packet) != length:
            raise ValueError("truncated raw packet")
        items.append((fields, packet))
        cursor += length
    if cursor != len(payload):
        raise ValueError("unexpected trailing input")
    return items


def stream(packets):
    return HEADER.pack(b"LEOCOA01", len(packets)) + b"".join(packets)


def held_packets(case):
    from . import portable_verifier_fixture

    parent = read(checked(portable_verifier_fixture.REPORT / "manifest.json", reference.PARENT))
    row = parent["cases"][case]
    golden, raw = (
        gzip.decompress(
            checked(portable_verifier_fixture.REPORT / item, parent["files"][item]).read_bytes()
        )
        for item in (row["golden"], row["input"])
    )
    rows = list(reference.raw_visits(json.loads(golden), raw))
    return golden, [payload for _, payload in rows]


def extra_visits(case, entry, development):
    manifest = entry["recording"]["segments"][0]["sha256"]
    # Read only physical-visit membership from the authenticated archive.
    path, lock_sha = capture_detector_lineage.locked_native(entry, "capture")
    archive = read(checked(path, lock_sha.removeprefix("sha256:")))
    visits = {int(row["visit_index"]) for row in archive["source"]["probes"]}
    eligible = [visit for visit in range(200, 450) if visit in visits and visit != development]
    if len(eligible) < 2:
        raise ValueError("insufficient physically eligible visits")
    candidates = sorted(
        eligible,
        key=lambda visit: sha256(f"{manifest}/c-coarse-tiles-v1/{case}/{visit}".encode()).digest(),
    )
    return candidates[:2], manifest


def prepare_case(folder, case):
    from leo.analysis.starlink import acquisition

    old, dev = locks()
    item = dev["cases"][case]
    if not Path(acquisition.__file__).is_relative_to(item["root"]):
        raise ValueError("physical geometry requires the authenticated producer on PYTHONPATH")
    for path, sha in item["sources"].items():
        checked(Path(path), sha)
    entry = _load_case(case)
    _, policy, source = capture_detector_lineage.source_lineage(entry)
    golden, held = held_packets(case)
    if sha256(stream(held)).hexdigest() != old["cases"][case]["all.ci16"]:
        raise ValueError("prior held raw projection differs from published standalone input")
    (folder / "golden.json").write_bytes(golden)
    (folder / "held.ci16").write_bytes(stream(held))
    first = item["rows"][0]
    extra, manifest = extra_visits(case, entry, first["visit"])
    historical = json.loads(golden)["visits"]
    if set(extra) & {row["visit"] for row in historical}:
        raise ValueError("hashed visits overlap historical qualification")
    fresh, provenance = {}, {}
    for visit in (first["visit"], *extra):
        segment, physical_manifest, window = original_kernel_trial.decode(entry, visit)
        if visit == first["visit"] and (segment, physical_manifest, window.iq_sha256) != (
            first["segment"],
            first["manifest"],
            first["iq_sha256"],
        ):
            raise ValueError("development IQ changed")
        raw = window.samples.astype("<i2", copy=False).tobytes()
        if "sha256:" + sha256(raw).hexdigest() != window.iq_sha256:
            raise ValueError("raw acquisition bytes do not match physical IQ hash")
        _, _, parameters = coarse_basis_eval.captures(window, policy)
        grids = tuple(
            (args[3][0] - rank[0][0], rank[0][0], rank[0][-1]) for args, rank in parameters
        )
        if len(grids) != 2 or grids[0][1:] != grids[1][1:]:
            raise ValueError("raw ABI requires common CFO limits")
        edge = ("lower", "upper").index(window.target["edge"])
        if window.target["edge"] != item["edge"]:
            raise ValueError("locked producer changed pilot edge")
        fresh[visit] = (
            RAW.pack(
                visit, len(window.samples), edge, 3, 1, grids[0][0], grids[1][0], *grids[0][1:]
            )
            + raw
        )
        provenance[visit] = dict(
            visit=visit,
            segment=segment,
            physical_manifest_sha256=physical_manifest,
            target=window.target_id,
            sample_start=window.acquisition["sample_start"],
            input=RAW.unpack_from(fresh[visit]),
            iq_sha256=window.iq_sha256,
        )
    paths = {
        "development": [fresh[first["visit"]]],
        "blind": [fresh[visit] for visit in extra],
        "timed": held + [fresh[visit] for visit in extra],
    }
    for name, packets in paths.items():
        (folder / f"{name}.ci16").write_bytes(stream(packets))
    save_json(
        folder / "inputs.json",
        dict(
            files={path.name: digest(path) for path in sorted(folder.iterdir())},
            producer=source["capture"],
            producer_sources=item["sources"],
            edge=item["edge"],
            development=first["visit"],
            blind_visits=extra,
            selection_manifest_sha256=manifest,
            fresh=provenance,
            held_visits=[row["visit"] for row in historical],
        ),
    )


def prepare(work):
    work.mkdir()
    _, dev = locks()
    for case in CASES:
        folder = work / case
        folder.mkdir()
        child = [sys.executable, "-m", __spec__.name, "prepare-case", folder, "--case", case]
        subprocess.run(
            child,
            env=os.environ
            | {
                "PYTHONPATH": dev["cases"][case]["root"],
                "OPENBLAS_NUM_THREADS": "1",
                "OMP_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
            },
            check=True,
            timeout=100,
        )
    # Real replay duplicates verify repeatability through the full C schedule.
    _, real = input_packets((work / CASES[0] / "development.ci16").read_bytes())[0]
    fields = RAW.unpack_from(real)
    edge_control = []
    for ident, count, mask, mode, center, low, high in (
        (7001, 200_000, 3, 1, 0, -800_000, 800_000),
        (7002, 26_620, 3, 2, 4_960_000, -40_000, 40_000),
        (7003, 26_621, 2, 2, 4_960_000, -40_000, 40_000),
        (7004, 26_622, 1, 2, -4_960_000, -40_000, 40_000),
    ):
        raw = bytes(count * 8) if ident == 7001 else real[RAW.size : RAW.size + count * 8]
        edge_control.append(
            RAW.pack(ident, count, fields[2], mask, mode, center, center, low, high) + raw
        )
    repeats = [RAW.pack(ident, *fields[1:]) + real[RAW.size :] for ident in (7005, 7006)]
    controls = work / "controls.ci16"
    controls.write_bytes(stream(edge_control + repeats))
    save_json(
        work / "input-lock.json",
        dict(
            cases={case: digest(work / case / "inputs.json") for case in CASES},
            controls={"file": controls.name, "sha256": digest(controls)},
            historical_parent_sha256=REF_SHA,
            development_parent_sha256=reference.SLIDING_SHA,
            selection="two smallest SHA256 of segment-0 physical-manifest digest, fixed "
            "domain separator, recording ID and visit; visits 200–449 "
            "with a valid archived physical receiver pair",
        ),
    )


def unpack_output(raw_packets, output):
    header = HEADER.unpack_from(output)
    if header != (b"LEOCOUT1", len(raw_packets)):
        raise ValueError("incomplete detector stream")
    cursor, visits = HEADER.size, []
    for fields, _ in raw_packets:
        ident, groups = VISIT.unpack_from(output, cursor)
        cursor += VISIT.size
        if ident != fields[0] or groups > 4:
            raise ValueError("physical visit or retry boundary changed")
        results = []
        for _ in range(groups):
            lane, anchors, count, coarse_cpu, coarse_wall, verify_cpu, verify_wall = (
                GROUP.unpack_from(output, cursor)
            )
            cursor += GROUP.size
            if lane not in (0, 1) or anchors not in (12, 22) or count > 8:
                raise ValueError("invalid acquisition packet inventory")
            seeds = [SEED.unpack_from(output, cursor + i * SEED.size) for i in range(count)]
            cursor += count * SEED.size
            packets = b""
            if fields[4] == 1:
                packets = output[cursor : cursor + count * RESULT.size]
                cursor += count * RESULT.size
            results.append(
                dict(
                    lane=lane,
                    anchors=anchors,
                    seeds=seeds,
                    verifier=packets,
                    coarse_cpu_ns=coarse_cpu,
                    coarse_wall_ns=coarse_wall,
                    verify_cpu_ns=verify_cpu,
                    verify_wall_ns=verify_wall,
                )
            )
        visits.append((ident, results))
    if cursor != len(output):
        raise ValueError("extra or truncated detector evidence")
    return visits


def run(work, method, target, cpu, source, *, profile=False):
    from .portable_verifier_run import TARGETS

    kind = "profile" if profile else target
    launch = ["taskset", "-c", str(cpu), *TARGETS[target][2], work / kind / method / "detector"]
    start = perf_counter_ns()
    result = subprocess.run(
        [*launch, source], cwd=work / kind / method, capture_output=True, check=True, timeout=120
    )
    return (
        unpack_output(input_packets(source.read_bytes()), result.stdout),
        json.loads(result.stderr) | {"process_elapsed_ns": perf_counter_ns() - start},
        result.stdout,
    )


def evidence(groups):
    counts = Counter(groups=len(groups), retries=sum(group["anchors"] == 22 for group in groups))
    records = []
    for group in groups:
        seeds = group["seeds"]
        counts["seeds"] += len(seeds)
        for rank, row in enumerate(RESULT.iter_unpack(group["verifier"])):
            seed, fine, conditioned, cells, mask, frames = row[:6]
            values = row[6:]
            counts.update(
                candidates=1,
                complete=bool(mask & 4),
                integer_pass=bool(mask & 1),
                fractional_pass=bool(mask & 2),
                fine_guard=bool(mask & 8),
                conditioned_ties=bool(mask & 16),
                glrt_bin_ties=bool(mask & 32),
                gate_guard=bool(mask & 64),
                equivalent_candidates=bool(mask & 128),
            )
            records.append(
                dict(
                    lane=group["lane"],
                    anchors=group["anchors"],
                    rank=rank,
                    seed=seed,
                    fine_bin=fine,
                    conditioned_bin=conditioned,
                    conditioned_cells=cells,
                    flags=mask,
                    frames=frames,
                    epoch=seeds[seed][0],
                    coarse_peak_epoch=seeds[seed][4],
                    coarse_score=seeds[seed][5],
                    coarse_cfo_low_hz=seeds[seed][3],
                    conditioned_absolute_hz=values[1],
                    integer_margin=values[7] - values[8],
                    fractional_margin=values[12] - values[13],
                    fractional_epoch_offset=values[10],
                    fractional_tracking_hz=values[1] + values[14],
                )
            )
    return dict(counts), records


def compare(baseline, proposed):
    if [(a["lane"], a["anchors"], len(a["seeds"])) for a in baseline] != [
        (a["lane"], a["anchors"], len(a["seeds"])) for a in proposed
    ]:
        return dict(inventory_equal=False, ordered_peaks_equal=False, verifier_bytes_equal=False)
    seed_keys, delta, products = True, [], True
    for a, b in zip(baseline, proposed, strict=True):
        seed_keys &= [r[:5] for r in a["seeds"]] == [r[:5] for r in b["seeds"]]
        delta.extend(abs(x[5] - y[5]) for x, y in zip(a["seeds"], b["seeds"], strict=True))
        products &= a["verifier"] == b["verifier"]
    return dict(
        inventory_equal=True,
        ordered_peaks_equal=seed_keys,
        verifier_bytes_equal=products,
        max_abs_peak_score=max(delta, default=0),
    )


def timed_rows(visits, case, cpu, replicate, order, method, resources):
    for ident, groups in visits:
        counts, _ = evidence(groups)
        clocks = {
            field: sum(group[field] for group in groups)
            for field in ("coarse_cpu_ns", "coarse_wall_ns", "verify_cpu_ns", "verify_wall_ns")
        }
        yield dict(
            case=case,
            visit=ident,
            cpu=cpu,
            replicate=replicate,
            order=order,
            method=method,
            **clocks,
            **resources,
            detector_cpu_ns=clocks["coarse_cpu_ns"] + clocks["verify_cpu_ns"],
            detector_wall_ns=clocks["coarse_wall_ns"] + clocks["verify_wall_ns"],
            retries=counts.get("retries", 0),
            groups=counts.get("groups", 0),
            seeds=counts.get("seeds", 0),
        )


def profile(work, panel, out):
    profiled = out / "profiles"
    profiled.mkdir()
    for case in CASES:
        for method in METHODS:
            source = panel / case / "timed.ci16"
            run(work, method, "x86", PROFILE_CPU, source, profile=True)
            gmon = work / "profile" / method
            dest = profiled / f"{case}-{method}.txt"
            with dest.open("x") as file:
                subprocess.run(
                    ["gprof", "-l", "-p", gmon / "detector", gmon / "gmon.out"],
                    stdout=file,
                    check=True,
                    timeout=30,
                )


def clock(work, panel, out):
    def core(core_index):
        cpu = CPUS[core_index]
        warm = panel / CASES[core_index] / "held.ci16"
        for method in METHODS:
            run(work, method, "x86", cpu, warm)
        permutations = (
            ((0, 1, 2), (1, 2, 0), (2, 0, 1))
            if core_index == 0
            else (
                (2, 1, 0),
                (1, 0, 2),
                (0, 2, 1),
            )
        )
        timing, checks = [], []
        for round_index, order in enumerate(permutations):
            for case in CASES[round_index:] + CASES[:round_index]:
                source = panel / case / "timed.ci16"
                products = {}
                for position, index in enumerate(order):
                    method = METHODS[index]
                    visits, resources, _ = run(work, method, "x86", cpu, source)
                    timing.extend(
                        timed_rows(visits, case, cpu, round_index, position, method, resources)
                    )
                    products[method] = visits
                for method in METHODS[1:]:
                    for (ident, baseline), (_, current) in zip(
                        products["incumbent"],
                        products[method],
                        strict=True,
                    ):
                        checks.append(
                            dict(
                                case=case,
                                visit=ident,
                                cpu=cpu,
                                replicate=round_index,
                                method=method,
                                **compare(baseline, current),
                            )
                        )
            print(f"CPU {cpu} finished matched round {round_index + 1}/3", flush=True)
        return timing, checks

    with ThreadPoolExecutor(max_workers=2) as futures:
        paired = list(futures.map(core, range(len(CPUS))))
    save_json(out / "timing.json", [row for data in paired for row in data[0]])
    save_json(out / "timed-parity.json", [row for data in paired for row in data[1]])


def development_grids(work, panel):
    result = []
    for case in CASES:
        [(f, p)] = input_packets((panel / case / "development.ci16").read_bytes())
        iq = np.frombuffer(p[RAW.size :], dtype="<i2").reshape(-1, 2, 2)
        edge = ("lower", "upper")[f[2]]
        for lane, anchors in itertools.product((0, 1), (12, 22)):
            grids = {}
            for name in METHODS:
                with Coarse(work / "grid" / name / "detector.so", edge) as bank:
                    seeds, peaks = bank.acquire(iq, lane, anchors, f[5:7], f[7:9])
                    grid, support = bank.grid()
                    grids[name] = (
                        seeds,
                        [tuple(p[k] for k in p if k != "score") for p in peaks],
                        grid,
                        support,
                    )
            a = grids["incumbent"]
            for name in METHODS[1:]:
                b = grids[name]
                delta = abs(a[2] - b[2])
                result.append(
                    dict(
                        case=case,
                        visit=f[0],
                        lane=lane,
                        anchors=anchors,
                        method=name,
                        cells=delta.size,
                        max_abs=float(delta.max()),
                        rms=float(np.sqrt(np.mean(delta * delta))),
                        support_equal=bool((a[3] == b[3]).all()),
                        ordered_peaks_equal=a[:2] == b[:2],
                    )
                )
    return result


def qualify(work, panel, out, targets):
    from . import portable_verifier_fixture
    from . import portable_verifier_results as verifier

    archive = read(checked(portable_verifier_fixture.REPORT / "manifest.json", reference.PARENT))
    checks, candidate_rows, audits = [], [], []
    for target in targets:
        choices = [(case, "held") for case in CASES]
        if target == "x86":
            choices += [(case, "blind") for case in CASES] + [("synthetic", "controls")]
        for case, role in choices:
            source = panel / ("controls.ci16" if role == "controls" else f"{case}/{role}.ci16")
            runs = {name: run(work, name, target, AUDIT_CPU, source) for name in METHODS}
            if role == "held":
                golden = read(panel / case / "golden.json")
                prior = archive["cases"][case]["targets"]["x86"]["scores"]
                native = gzip.decompress(
                    checked(
                        portable_verifier_fixture.REPORT / prior, archive["files"][prior]
                    ).read_bytes()
                )
                for name, (_, resources, output) in runs.items():
                    binary, clocks, counts = reference.decode_output(golden, output)
                    audits.append(
                        dict(
                            case=case,
                            target=target,
                            method=name,
                            **counts,
                            verification=verifier.audit(golden, binary, native),
                            resources=resources,
                            clocks=clocks,
                        )
                    )
            for name, (visits, _, _) in runs.items():
                for (ident, groups), (_, baseline) in zip(
                    visits, runs["incumbent"][0], strict=True
                ):
                    counts, candidates = evidence(groups)
                    key = dict(target=target, case=case, role=role, method=name, visit=ident)
                    checks.append(dict(**key, **counts, **compare(baseline, groups)))
                    candidate_rows.extend(dict(**key, **candidate) for candidate in candidates)
            if role == "controls":
                for name, (visits, _, _) in runs.items():
                    if not all(not group["seeds"] for _, groups in visits[:2] for group in groups):
                        raise ValueError("zero or undersized input generated a seed")
                    equality = compare(visits[-2][1], visits[-1][1])
                    if (
                        not equality["inventory_equal"]
                        or not equality["ordered_peaks_equal"]
                        or not equality["verifier_bytes_equal"]
                        or equality["max_abs_peak_score"]
                    ):
                        raise ValueError(f"{name} changed evidence on an exact replay")
            print(target, case, role, flush=True)
    save_json(out / "qualification.json", checks)
    save_json(out / "candidates.json", candidate_rows)
    save_json(out / "archive-audits.json", audits)
    save_json(out / "development.json", development_grids(work, panel))


def verify_input(work, panel):
    inp = read(panel / "input-lock.json")
    for case in CASES:
        folder = panel / case
        for filename, sha in read(checked(folder / "inputs.json", inp["cases"][case]))[
            "files"
        ].items():
            checked(folder / filename, sha)
    checked(panel / inp["controls"]["file"], inp["controls"]["sha256"])
    for target, builds in read(work / "build-lock.json")["builds"].items():
        for name, info in builds.items():
            checked(
                work / target / name / ("detector.so" if target == "grid" else "detector"),
                info["sha256"],
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("prepare", "prepare-case", "profile", "clock", "qualify")
    )
    parser.add_argument("work", type=local_output)
    parser.add_argument("--panel", type=Path)
    parser.add_argument("--out", type=local_output)
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--targets", nargs="+", choices=reference.TARGETS, default=["x86"])
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.work)
    elif args.action == "prepare-case":
        prepare_case(args.work, args.case)
    else:
        verify_input(args.work, args.panel)
        args.out.mkdir(parents=True, exist_ok=True)
        if args.action == "qualify":
            qualify(args.work, args.panel, args.out, args.targets)
        else:
            {"profile": profile, "clock": clock}[args.action](args.work, args.panel, args.out)
