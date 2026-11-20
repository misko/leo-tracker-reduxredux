"""Build statically linked x86 and ARMv7 differential scout witnesses and compare them."""

import argparse
import gzip
import io
import json
import os
import subprocess
import tarfile
from hashlib import sha256
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
from time import perf_counter_ns

import numpy as np

from ..__main__ import ROOT, local_output, save_json, write
from ..variants import differential_pilot as reference
from ..variants.differential_runtime_fft import SOURCE
from . import differential_pilot_eval as fixtures
from . import hinted_glrt_trial, oracle_start, ordinary_front_build, wide_regional_build
from .full_v5_check import _load_case, _sha

FRONTIER = ROOT / "reports/2026_11_19_receiver_screening/acquisition-frontier"
REPORT = FRONTIER / "differential-arm"
RUNTIME = FRONTIER / "differential-runtime"
ADAPTER = Path(__file__).with_suffix(".c")
ARM_RELEASE = wide_regional_build.ROOT / "arm-wide/build-receipt.json"
QEMU = Path("/usr/bin/qemu-arm")
REPETITIONS = 6
FIXTURES = (
    ("DS26-0162", 19, "recovered"),
    ("DS29-0082", 2, "difficult"),
    ("DS26-0237", 198, "lower-real"),
)
CONTROLS = ("strong", "one-frame", "noise", "zero")


def command(argv):
    return subprocess.check_output(list(map(str, argv)), text=True, timeout=15).strip()


def builds(work):
    known = json.loads(ARM_RELEASE.read_bytes())
    specs = {
        "host": (Path("/usr/bin/gcc"), ordinary_front_build.HOST_FFTW, ()),
        "arm": (
            Path(known["compiler"]),
            ordinary_front_build.ARM_FFTW,
            ("-mcpu=cortex-a9", "-mfpu=neon", "-mfloat-abi=hard"),
        ),
    }
    binaries = {}
    for mode, (cc, prefix, flags) in specs.items():
        archive = prefix / "lib/libfftw3f.a"
        header = prefix / "include/fftw3.h"
        if mode == "arm" and (
            _sha(archive) != known["fftw_float_archive_sha256"]
            or _sha(cc) != known["compiler_sha256"]
            or _sha(header) != known["fftw_header_sha256"]
        ):
            raise ValueError("ARM build inputs differ from previously qualified NEON FFTW")
        binary = work / f"differential-scout-{mode}"
        argv = [
            str(cc),
            "-std=c11",
            "-O3",
            "-ffp-contract=off",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-static",
            "-s",
            *flags,
            "-I",
            str(SOURCE.parent),
            "-I",
            str(header.parent),
            str(ADAPTER),
            str(archive),
            "-lm",
            "-o",
            str(binary),
        ]
        subprocess.run(argv, env=os.environ | {"TMPDIR": str(work)}, check=True, timeout=20)
        elf = command(("readelf", "-h", binary))
        attributes = command(("readelf", "-A", binary))
        dynamic = command(("readelf", "-d", binary))
        if "There is no dynamic section" not in dynamic or (
            mode == "arm"
            and not ("ARM" in elf and "hard-float ABI" in elf and "NEONv1" in attributes)
        ):
            raise ValueError("standalone executable has unexpected ABI or dynamic dependencies")
        binaries[mode] = dict(
            file=binary.name,
            sha256=_sha(binary),
            command=argv,
            bytes=binary.stat().st_size,
            compiler_version=command((cc, "--version")).splitlines()[0],
            compiler_sha256=_sha(cc),
            compiler_realpath=str(cc.resolve()),
            fftw_archive=str(archive),
            fftw_archive_sha256=_sha(archive),
            fftw_header=str(header),
            fftw_header_sha256=_sha(header),
            elf=elf,
            arm_attributes=attributes,
            elf_dynamic=dynamic,
        )
    return binaries


def extract_held(work, cache):
    proof = json.loads((RUNTIME / "prediction-lock.json").read_bytes())
    paired = RUNTIME / "paired.json.gz"
    if (
        _sha(paired) != proof["files"][paired.name]
        or _sha(SOURCE) != proof["sources"][str(SOURCE.relative_to(ROOT))]
    ):
        raise ValueError("frozen numerical kernel or original x86 evaluation changed")
    references = {
        (r["item"], r["edge"]): r for r in json.loads(gzip.decompress(paired.read_bytes()))
    }
    oracle_lock = json.loads((oracle_start.REPORT / "result-lock.json").read_bytes())
    oracle = oracle_start.REPORT / "input-lock.json"
    if _sha(oracle) != oracle_lock["files"][oracle.name]:
        raise ValueError("genuine sample source differs from the oracle-start seal")
    roster = json.loads(oracle.read_bytes())["cases"]
    panel = {}
    for ident, visit, kind in FIXTURES:
        key = f"{ident}:{visit}"
        row = next(r for r in roster[ident]["selected"] if r["visit"] == visit)
        selected = cache / ident / f"visit-{visit}.ci16"
        if selected.is_file():
            data = selected.read_bytes()
        else:
            data = hinted_glrt_trial.load_selected(_load_case(ident), row).samples.tobytes()
        edge = row["archive_probe"]["edge"]
        expected = references[key, edge]
        if (
            "sha256:" + sha256(data).hexdigest() != row["iq_sha256"]
            or expected["input_sha256"] != sha256(data).hexdigest()
            or edge != expected["edge"]
        ):
            raise ValueError("genuine selected input differs from both authorities")
        panel[key] = dict(
            edge=edge,
            role=kind,
            receiver=row["receiver"],
            visit=visit,
            target_epoch=row["known_center"],
            expected_centers=[r[0] for r in expected["fftw_proposals"]],
            file=f"{ident}-{visit}.ci16",
            sha256=expected["input_sha256"],
        )
        write(work / panel[key]["file"], data)

    for edge in ("lower", "upper"):
        for name in CONTROLS:
            samples, control = fixtures.synthetic(edge, name)
            key = f"{edge}-{name}"
            expected = references[name, edge]
            blob = samples.tobytes()
            if sha256(blob).hexdigest() != expected["input_sha256"]:
                raise ValueError("control generation differs from frozen paired FFTW study")
            panel[key] = dict(
                edge=edge,
                role=name,
                synthetic=control,
                expected_centers=[r[0] for r in expected["fftw_proposals"]],
                file=f"{key}.ci16",
                sha256=sha256(blob).hexdigest(),
            )
            write(work / panel[key]["file"], blob)
    return panel


def prepare(work, cache):
    from leo.analysis.starlink import templates

    work.mkdir(parents=True, exist_ok=False)
    libraries = builds(work)
    panel = extract_held(work, cache)
    banks = {}
    for edge in ("lower", "upper"):
        ports = reference.filters(edge)
        blobs = {
            f"{edge}-filters.c8": np.stack([k for k, _ in ports], dtype="<c8").tobytes(),
            f"{edge}-energies.f64": np.stack([e for _, e in ports], dtype="<f8").tobytes(),
        }
        for name, data in blobs.items():
            write(work / name, data)
        banks[edge] = {name: _sha(work / name) for name in blobs}
    files = (
        Path(__file__),
        ADAPTER,
        SOURCE,
        Path(reference.__file__),
        Path(reference.ranked_centers.__code__.co_filename),
        Path(fixtures.__file__),
        oracle_start.REPORT / "input-lock.json",
        RUNTIME / "prediction-lock.json",
        RUNTIME / "paired.json.gz",
        ARM_RELEASE,
        Path(templates.__file__),
        REPORT / "PROTOCOL.md",
    )
    save_json(
        work / "source-lock.json",
        dict(
            sources={str(path): _sha(path) for path in files},
            libraries=libraries,
            templates=banks,
            inputs=panel,
            qemu_version=command((QEMU, "--version")).splitlines()[0],
            qemu_sha256=_sha(QEMU),
            template_shapes={"filters": [2, 3, 32768], "energies": [2, 13333]},
            phase_residues=list(reference.PHASE_THIRDS),
            template_rate_hz=30_000_000,
            numpy=np.__version__,
            repetitions=REPETITIONS,
        ),
    )


def authenticated(work):
    p = work / "source-lock.json"
    lock = json.loads(p.read_bytes())
    bindings = dict(lock["sources"], **{str(QEMU): lock["qemu_sha256"]})
    for items in lock["templates"].values():
        bindings.update({str(work / name): digest for name, digest in items.items()})
    for member in lock["libraries"].values():
        bindings[str(work / member["file"])] = member["sha256"]
        for path, field in (
            (member["fftw_header"], "fftw_header_sha256"),
            (member["fftw_archive"], "fftw_archive_sha256"),
        ):
            bindings[path] = member[field]
    if any(_sha(Path(name)) != sha for name, sha in bindings.items()):
        raise ValueError("executable, template, or dependency bytes changed after sealing")
    return lock


def execute(work, arch, binary, row):
    name = work / row["file"]
    if _sha(name) != row["sha256"]:
        raise ValueError("bound CI16 changed before execution")
    edge = row["edge"]
    prefix = (QEMU, "-cpu", "cortex-a9") if arch == "arm" else ()
    argv = [
        *prefix,
        binary,
        name,
        work / f"{edge}-filters.c8",
        work / f"{edge}-energies.f64",
        str(REPETITIONS),
    ]
    start_usage = getrusage(RUSAGE_CHILDREN)
    started = perf_counter_ns()
    result = subprocess.run(argv, capture_output=True, check=True, timeout=15)
    wall = perf_counter_ns() - started
    usage = getrusage(RUSAGE_CHILDREN)
    data = json.loads(result.stderr)
    scores = np.frombuffer(result.stdout, dtype="<f8").reshape(2, reference.FRAME)
    if [reference.ranked_centers(grid) for grid in scores] != data["top_16"]:
        raise ValueError("standalone rank extraction differs from stock Python on its own grid")
    digest = sha256(result.stdout).hexdigest()
    write(work / f"{name.stem}-{arch}-scores.f64", result.stdout)
    data.update(
        full_grid_sha256=digest,
        external_wall_ns=wall,
        external_cpu_ns=round(
            1e9 * (usage.ru_utime + usage.ru_stime - start_usage.ru_utime - start_usage.ru_stime)
        ),
    )
    return data, scores


def replay(work):
    lock = authenticated(work)
    affinity = sorted(os.sched_getaffinity(0))
    if len(affinity) != 1:
        raise ValueError("use the same one effective host core for both architectures")
    outcomes = {}
    for i, (name, row) in enumerate(lock["inputs"].items()):
        records = {}
        for arch in ("host", "arm") if i % 2 == 0 else ("arm", "host"):
            records[arch] = execute(work, arch, work / lock["libraries"][arch]["file"], row)
        host, hg = records["host"]
        arm, ag = records["arm"]
        samples = np.fromfile(work / row["file"], dtype="<i2").reshape(200000, 2, 2)
        ref = reference.surface(samples, row["edge"])
        ref_ranks = [reference.ranked_centers(v) for v in ref]

        def relative(source, other):
            return (
                np.max(np.abs(source - other), axis=1)
                / np.maximum(np.max(np.abs(source), axis=1), 1)
            ).tolist()

        outcomes[name] = dict(
            input=row,
            host=host,
            arm=arm,
            rank_complete_parity=[
                a == b for a, b in zip(host["top_16"], arm["top_16"], strict=True)
            ],
            host_matches_previous=host["top_16"] == row["expected_centers"],
            arm_matches_python=[a == b for a, b in zip(arm["top_16"], ref_ranks, strict=True)],
            arm_vs_host_rel_linf=relative(hg, ag),
            arm_vs_numpy_rel_linf=relative(ref, ag),
        )
        print(
            name,
            outcomes[name]["rank_complete_parity"],
            outcomes[name]["arm_vs_host_rel_linf"],
            flush=True,
        )
    save_json(
        work / "measurements.json",
        dict(
            affinity=affinity, results=outcomes, source_lock_sha256=_sha(work / "source-lock.json")
        ),
    )


def capsule(work):
    lock = authenticated(work)
    if _sha(work / "lower-strong.ci16") != lock["inputs"]["lower-strong"]["sha256"]:
        raise ValueError("packaged synthetic CI16 differs from the sealed fixture")
    members = (
        lock["libraries"]["arm"]["file"],
        *(p for m in lock["templates"].values() for p in m),
        "lower-strong.ci16",
    )
    plain = io.BytesIO()
    with tarfile.open(fileobj=plain, mode="w", format=tarfile.USTAR_FORMAT) as save:
        for name in members:
            info = tarfile.TarInfo(name)
            raw = (work / name).read_bytes()
            info.size = len(raw)
            info.mode = 0o755 if name.startswith("differential-scout") else 0o644
            save.addfile(info, io.BytesIO(raw))
        checks = "".join(f"{_sha(work / name)}  {name}\n" for name in members).encode()
        info = tarfile.TarInfo("SHA256SUMS")
        info.size = len(checks)
        save.addfile(info, io.BytesIO(checks))
    write(work / "differential-armv7.tar.gz", gzip.compress(plain.getvalue(), mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "run", "capsule"))
    parser.add_argument("work", type=Path)
    parser.add_argument(
        "--cache", type=Path, default=Path.home() / ".cache/leo-capture-starts-20261119"
    )
    args = parser.parse_args()
    home = local_output(args.work)
    if args.mode == "prepare":
        prepare(home, args.cache)
    elif args.mode == "run":
        replay(home)
    else:
        capsule(home)
