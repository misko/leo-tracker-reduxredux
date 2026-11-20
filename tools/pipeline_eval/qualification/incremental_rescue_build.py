"""Build the opt-in one-region rescue plus a two-/one-lane FFTW scout offline."""

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from .. import wide_runtime as release
from ..__main__ import local_output, save_json
from ..variants import differential_runtime_fft as fftw
from ..variants import incremental_rescue_graft as graft
from .center_union_build import STOCK
from .glrt_reuse_build import exports

WORK = Path("/var/tmp/leo-incremental-rescue-20261119")
SCOUT = "libincremental-scout.so"
FLAGS = ("-O3", "-ffp-contract=off", "-Wall", "-Wextra", "-Werror", "-fPIC", "-shared")


def build(work, stock, fftw_prefix):
    work.mkdir(parents=True, exist_ok=False)
    capsule = work / "capsule"
    manifest = release.unpack(release.CAPSULE, capsule)
    bare, baseline = release.OUTPUTS[0], manifest["stock"]
    if release.sha256(stock) != baseline["output_sha256"][bare]:
        raise ValueError("stock detector is not the frozen 21-bin wide artifact")
    compiler, archiver = "/usr/bin/gcc", "/usr/bin/gcc-ar"
    source = capsule / "source/native_glrt.c"
    source.write_text(graft.native(source.read_text()))
    shutil.copyfile(graft.HEADER, source.with_name(graft.HEADER.name))
    dependencies = release.dependency_paths(fftw_prefix, compiler)
    prefix, env = release.stage_dependencies(dependencies, work, compiler)
    result = work / "release"
    proof = release.compile_variant(
        capsule, result, work, "rescue", baseline, compiler, archiver, prefix, env
    )
    receipt = json.loads((result / "build-receipt.json").read_text())
    parent = {
        key.removeprefix("source/"): val
        for key, val in manifest["files"].items()
        if key.startswith("source/")
    }
    changed = {key for key, value in parent.items() if receipt["sources"][key] != value}
    if (
        changed != {source.name}
        or receipt["sources"].keys() - parent.keys() != {graft.HEADER.name}
        or exports(result / bare) != exports(stock) | {graft.ENTRY}
    ):
        raise ValueError("one-region release changed other source files or exported symbols")
    scout = work / "incremental_scout.c"
    scout.write_text(graft.scout(fftw.SOURCE.read_text()))
    # FFTW float is a declared system dependency. Match the measured scout flags.
    include_dirs = (fftw_prefix / "include",)
    lib_dirs = (fftw_prefix / "lib", fftw_prefix / "lib/x86_64-linux-gnu")
    subprocess.run(
        [
            compiler,
            *FLAGS,
            *(f"-I{p}" for p in include_dirs),
            str(scout),
            *(f"-L{p}" for p in lib_dirs),
            "-lfftw3f",
            "-lm",
            "-o",
            str(result / SCOUT),
        ],
        check=True,
        env=dict(os.environ, TMPDIR=str(work)),
    )
    actual = {
        name: str(path)
        for name, path in dict(stock=stock, detector=result / bare, scout=result / SCOUT).items()
    }
    save_json(
        work / "release.json",
        dict(
            paths=actual,
            sha256={name: release.sha256(Path(path)) for name, path in actual.items()},
            capsule_sha256=release.CAPSULE_SHA256,
            detector_entry=graft.ENTRY,
            scout_entry=graft.SCOUT_ENTRY,
            stock_public_abi=1,
            proof=proof,
            scout_build_flags=FLAGS,
            scout_source_sha256=release.sha256(scout),
            changed_sources={
                name: receipt["sources"][name] for name in (source.name, graft.HEADER.name)
            },
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=local_output, default=WORK)
    parser.add_argument("--stock", type=Path, default=STOCK)
    parser.add_argument("--fftw-prefix", type=Path, default=Path("/usr"))
    args = parser.parse_args()
    build(args.work, args.stock.resolve(), args.fftw_prefix.resolve())
