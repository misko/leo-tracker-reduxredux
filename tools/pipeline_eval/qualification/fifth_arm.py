"""Build and replay the complete offline ARMv7 fractional fifth-center detector."""

import argparse
import gzip
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
from time import perf_counter_ns

import numpy as np

from ..__main__ import ROOT, local_output, save_json, write
from ..variants import differential_pilot as reference
from . import (
    differential_arm,
    differential_pilot_eval,
    hinted_glrt_trial,
    ordinary_front_build,
    wide_regional_eval,
)
from .full_v5_check import _from_native, _load_case, _sha, compare_probes

HERE = ROOT / "reports/2026_11_19_receiver_screening/support-preserving"
REPORT = HERE / "fifth-arm"
UNION = HERE / "center-union"
UNION_SOURCE = Path("/var/tmp/leo-center-union-20261119/capsule/source")
ADAPTER = Path(__file__).with_suffix(".c")
FIXTURES = (
    ("DS26-0162", 19, "upper", "recovered"),
    ("DS29-0082", 2, "upper", "difficult"),
    ("DS26-0237", 72, "lower", "recovered"),
    ("DS26-0237", 198, "lower", "difficult"),
)
MODES = ("stock", "union")


def check(path, digest):
    if _sha(path) != digest.removeprefix("sha256:"):
        raise ValueError(f"sealed input bytes changed: {path}")
    return path


def tools(work, source):
    previous = json.loads(differential_arm.ARM_RELEASE.read_bytes())
    expected_path = UNION / "build-receipt.json"
    expected = json.loads(expected_path.read_bytes())
    libraries = {}
    for mode in ("arm", "host"):
        arm = mode == "arm"
        root = work / f"{mode}-library"
        receipt_path = root / "build-receipt.json"
        receipt = json.loads(receipt_path.read_bytes())
        if receipt["sources"] != expected["sources"]:
            raise ValueError(
                "cross-built scientific detector differs from the sealed union sources"
            )
        for name, digest in receipt["sources"].items():
            check(source / name, digest)
        cc = check(Path(receipt["compiler"]), receipt["compiler_sha256"])
        float_archive = ordinary_front_build.ARM_FFTW if arm else ordinary_front_build.HOST_FFTW
        header = check(float_archive / "include/fftw3.h", receipt["fftw_header_sha256"])
        kernels = check(float_archive / "lib/libfftw3f.a", receipt["fftw_float_archive_sha256"])
        double = check(Path(receipt["fftw_double_library"]), receipt["fftw_double_library_sha256"])
        if arm and any(
            receipt[name] != previous[name]
            for name in (
                "compiler_sha256",
                "fftw_header_sha256",
                "fftw_float_archive_sha256",
                "fftw_double_library_sha256",
            )
        ):
            raise ValueError("ARM runtime differs from the prior authenticated wide capsule")
        library = check(
            root / "libleo-adaptive-detector.a", receipt["outputs"]["libleo-adaptive-detector.a"]
        )
        if (
            not arm
            and receipt["outputs"]["libleo-adaptive-detector.so"]
            != expected["outputs"]["libleo-adaptive-detector.so"]
        ):
            raise ValueError(
                "the host builder did not reproduce the original union shared artifact"
            )
        binary = work / f"fifth-detector-{mode}"
        platform = ("-mcpu=cortex-a9", "-mfpu=neon", "-mfloat-abi=hard") if arm else ()
        argv = [
            str(cc),
            "-std=c11",
            "-O3",
            "-ffp-contract=off",
            "-Wall",
            "-Wextra",
            "-Werror",
            *platform,
            "-I",
            str(source),
            "-I",
            str(differential_arm.SOURCE.parent),
            "-I",
            str(header.parent),
            str(ADAPTER),
            str(library),
            str(kernels),
            str(double),
            "-lm",
            "-o",
            str(binary),
        ]
        subprocess.run(
            argv, check=True, timeout=28, env=os.environ | {"TMPDIR": str(work / "compiler-temp")}
        )
        command = differential_arm.command
        elf = command(("readelf", "-h", binary))
        flags = command(("readelf", "-A", binary))
        if arm and not ("ARM" in elf and "hard-float ABI" in elf and "NEONv1" in flags):
            raise ValueError("ARM witness lacks the documented target ABI")
        libraries[mode] = dict(
            sha256=_sha(binary),
            file=binary.name,
            invoked=argv,
            elf=elf,
            attributes=flags,
            needed=command(("readelf", "-d", binary)),
            detector_build_sha256=_sha(receipt_path),
            detector_archive_sha256=_sha(library),
            float_fftw_sha256=_sha(kernels),
            double_fftw_sha256=_sha(double),
            compiler_version=command((cc, "--version")).splitlines()[0],
            compiler_sha256=_sha(cc),
        )
        if arm:
            libraries[mode]["sysroot"] = command((cc, "--print-sysroot"))
    return libraries


def dependencies(work, arm):
    origin = Path(arm["sysroot"])
    needed = set(re.findall(r"Shared library: \[([^\]]+)\]", arm["needed"]))
    pending = list(needed)
    copied = {}
    while pending:
        soname = pending.pop()
        if Path(soname).name != soname:
            raise ValueError("unexpected target SONAME")
        if soname in copied:
            continue
        candidates = [
            p for directory in ("lib", "usr/lib") if (p := origin / directory / soname).is_file()
        ]
        if not candidates:
            raise FileNotFoundError(f"cannot resolve packaged ARM runtime {soname}")
        src = candidates[0]
        dst = work / "runtime" / src.relative_to(origin)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        dst.chmod(0o755)
        copied[soname] = dict(
            file=str(dst.relative_to(work)), sha256=_sha(dst), original=str(src.resolve())
        )
        dynamic = differential_arm.command(("readelf", "-d", src))
        pending.extend(re.findall(r"Shared library: \[([^\]]+)\]", dynamic))
    if copied["libfftw3.so.3"]["sha256"] != arm["double_fftw_sha256"]:
        raise ValueError("packaged double FFTW differs from the actual linker input")
    return copied


def fixtures(work, cache):
    manifest = json.loads((UNION / "evidence-lock.json").read_bytes())["files"]
    cases = {
        edge: json.loads(
            gzip.decompress(
                check(UNION / f"{edge}.json.gz", manifest[f"{edge}.json.gz"]).read_bytes()
            )
        )
        for edge in ("lower", "upper")
    }
    input_files, template_files = {}, {}
    for case, visit, edge, kind in FIXTURES:
        original = next(
            r for r in cases[edge]["measured"] if r["case"] == case and r["visit"] == visit
        )
        cache_file = cache / case / f"visit-{visit}.ci16"
        raw = (
            cache_file.read_bytes()
            if cache_file.is_file()
            else hinted_glrt_trial.load_selected(_load_case(case), original).samples.tobytes()
        )
        name = f"{case}-{visit}"
        write(work / f"{name}.ci16", raw)
        check(work / f"{name}.ci16", original["iq_sha256"])
        input_files[name] = dict(
            edge=edge,
            kind=kind,
            file=f"{name}.ci16",
            sha256=_sha(work / f"{name}.ci16"),
            receiver=original["receiver"],
            target=original["target"],
            original=original["payloads"],
            rank_one=original["traces"]["union"]["rank_one"],
            original_targets=original["target_results"],
        )
    for edge in ("lower", "upper"):
        pq = reference.filters(edge)
        exact, control = wide_regional_eval.templates(10_000_000, edge)
        files = {
            "exact.c16": exact,
            "control.c16": control,
            "filters.c8": np.stack([a for a, _ in pq], dtype="<c8"),
            "energies.f64": np.stack([b for _, b in pq], dtype="<f8"),
        }
        template_files[edge] = {}
        for file, array in files.items():
            name = f"{edge}-{file}"
            write(work / name, array.tobytes())
            template_files[edge][name] = _sha(work / name)
        for case in ("strong", "noise"):
            inputs, plant = differential_pilot_eval.synthetic(edge, case)
            old = cases[edge]["controls"][case]
            name = f"{edge}-{case}"
            write(work / f"{name}.ci16", inputs.tobytes())
            check(work / f"{name}.ci16", old["iq_sha256"])
            input_files[name] = dict(
                edge=edge,
                kind=case,
                file=f"{name}.ci16",
                sha256=_sha(work / f"{name}.ci16"),
                synthetic=plant,
                original=old["payloads"],
                rank_one=old["traces"]["union"]["rank_one"],
            )
    return input_files, template_files


def seal(work, source, cache):
    libraries = tools(work, source)
    runtime = dependencies(work, libraries["arm"])
    inputs, templates = fixtures(work, cache)
    from leo.analysis.starlink import templates as qin

    paths = (
        Path(__file__),
        ADAPTER,
        differential_arm.ADAPTER,
        differential_arm.SOURCE,
        Path(differential_arm.__file__),
        Path(reference.__file__),
        Path(qin.__file__),
        Path(differential_pilot_eval.__file__),
        source / "native_glrt_cli.c",
        source / "center_union.h",
        UNION / "evidence-lock.json",
        UNION / "build-receipt.json",
        UNION / "release.json",
        REPORT / "PROTOCOL.md",
    )
    save_json(
        work / "source-lock.json",
        dict(
            input=inputs,
            templates=templates,
            libraries=libraries,
            runtime=runtime,
            sources={str(p): _sha(p) for p in paths},
            qemu_sha256=_sha(differential_arm.QEMU),
            qemu_version=differential_arm.command(
                (differential_arm.QEMU, "--version")
            ).splitlines()[0],
        ),
    )


def verified(work):
    lock = json.loads((work / "source-lock.json").read_bytes())
    for path, sha in lock["sources"].items():
        check(Path(path), sha)
    for arc in (*lock["libraries"].values(), *lock["runtime"].values(), *lock["input"].values()):
        check(work / arc["file"], arc["sha256"])
    for edge in lock["templates"].values():
        for path, sha in edge.items():
            check(work / path, sha)
    check(differential_arm.QEMU, lock["qemu_sha256"])
    return lock


def execute(work, lock, record, arch, mode):
    prefix = (
        (differential_arm.QEMU, "-cpu", "cortex-a9", "-L", work / "runtime")
        if arch == "arm"
        else ()
    )
    edge = record["edge"]
    names = ("exact.c16", "control.c16", "filters.c8", "energies.f64")
    argv = (
        *prefix,
        work / lock["libraries"][arch]["file"],
        mode,
        work / record["file"],
        *(work / f"{edge}-{f}" for f in names),
        "1",
    )
    usage = getrusage(RUSAGE_CHILDREN)
    begin = perf_counter_ns()
    result = subprocess.run(argv, capture_output=True, check=True, timeout=15)
    wall = perf_counter_ns() - begin
    end = getrusage(RUSAGE_CHILDREN)
    data = json.loads(result.stdout)
    data["process_ms"] = dict(
        wall=wall / 1e6,
        cpu=1e3 * ((end.ru_utime + end.ru_stime) - (usage.ru_utime + usage.ru_stime)),
    )
    return data


def science(rows):
    return [{key: value for key, value in row.items() if key != "timings_ms"} for row in rows]


def compare(left, right):
    a, b = left["rows"], right["rows"]
    results = []
    for host_row, arm_row in zip(a, b, strict=True):
        probes = [
            dict(
                candidates=[
                    x
                    for i, candidate in enumerate(k["candidates"])
                    if (x := _from_native(i, candidate)) is not None
                ]
            )
            for k in (host_row, arm_row)
        ]
        scores = compare_probes(*probes, 10_000_000)
        exact_rank = [(c["epoch"], c["coarse_bin"]) for c in host_row["candidates"]] == [
            (c["epoch"], c["coarse_bin"]) for c in arm_row["candidates"]
        ]
        results.append(dict(scores, ordered_integer_keys_match=exact_rank))
    return dict(
        lanes=results,
        exact_payload=science(a) == science(b),
        rank_one_matches=[
            x[:1] == y[:1] for x, y in zip(left["top16"], right["top16"], strict=True)
        ],
        full16_matches=[x == y for x, y in zip(left["top16"], right["top16"], strict=True)],
        support_trace_exact=left["trace"] == right["trace"],
    )


def run(work):
    lock = verified(work)
    affinity = sorted(os.sched_getaffinity(0))
    if len(affinity) != 1:
        raise ValueError("pin the complete comparison to one authorized host core")
    results = {}
    for i, (name, item) in enumerate(lock["input"].items()):
        data = {}
        for arch in ("host", "arm") if i % 2 == 0 else ("arm", "host"):
            modes = MODES if i % 2 == 0 else MODES[::-1]
            data[arch] = {m: execute(work, lock, item, arch, m) for m in modes}
            if name in ("lower-strong", "upper-strong"):
                off = execute(work, lock, item, arch, "off")
                data[arch]["off"] = off
                if science(off["rows"]) != science(data[arch]["stock"]["rows"]):
                    raise ValueError("absent hints changed the original detector output")
        previous = {
            m: science(data["host"][m]["rows"]) == science(item["original"][m]["rows"])
            for m in MODES
        }
        rank_one = [x[0] if x else None for x in data["host"]["union"]["top16"]]
        results[name] = dict(
            study=data,
            comparison={m: compare(data["host"][m], data["arm"][m]) for m in MODES},
            host_matches_previous=previous,
            host_rank_one_matches_previous=rank_one == item["rank_one"],
            edge=item["edge"],
            kind=item["kind"],
        )
        print(name, previous, results[name]["comparison"]["union"]["full16_matches"], flush=True)
        save_json(work / "in-progress.json", results)
    save_json(
        work / "measurements.json",
        dict(rows=results, affinity=affinity, source_lock_sha256=_sha(work / "source-lock.json")),
    )


def capsule(work):
    lock = verified(work)
    files = [
        lock["libraries"]["arm"]["file"],
        *(x["file"] for x in lock["runtime"].values()),
        *(p for edge in lock["templates"].values() for p in edge),
        "lower-strong.ci16",
    ]
    plain = io.BytesIO()
    with tarfile.open(fileobj=plain, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name in sorted(files):
            payload = (work / name).read_bytes()
            field = tarfile.TarInfo(name)
            field.size = len(payload)
            field.mode = 0o755 if name.startswith(("fifth-detector", "runtime/")) else 0o644
            archive.addfile(field, io.BytesIO(payload))
        checks = "".join(f"{_sha(work / name)}  {name}\n" for name in sorted(files)).encode()
        field = tarfile.TarInfo("SHA256SUMS")
        field.size = len(checks)
        archive.addfile(field, io.BytesIO(checks))
    write(work / "fifth-armv7.tar.gz", gzip.compress(plain.getvalue(), mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("seal", "run", "capsule"))
    parser.add_argument("work", type=Path)
    parser.add_argument("--source", type=Path, default=UNION_SOURCE)
    parser.add_argument(
        "--cache", type=Path, default=Path.home() / ".cache/leo-capture-starts-20261119"
    )
    args = parser.parse_args()
    work = local_output(args.work)
    if args.mode == "seal":
        seal(work, args.source, args.cache)
    elif args.mode == "run":
        run(work)
    else:
        capsule(work)
