"""Build the opt-in fifth-epoch-region detector from the portable wide capsule."""

import argparse
import json
import shutil
from pathlib import Path

from .. import wide_runtime as release
from ..__main__ import local_output, save_json
from ..variants import center_union
from .glrt_reuse_build import exports

WORK = Path("/var/tmp/leo-center-union-20261119")
STOCK = Path("/var/tmp/leo-frontier-whole-20261119/wide-stock.so")


def build(work, stock, fftw_prefix):
    work.mkdir(parents=True, exist_ok=False)
    capsule = work / "capsule"
    manifest = release.unpack(release.CAPSULE, capsule)
    baseline = manifest["stock"]
    bare = release.OUTPUTS[0]
    if release.sha256(stock) != baseline["output_sha256"][bare]:
        raise ValueError("stock library is not the frozen 21-bin wide artifact")
    source = capsule / "source"
    files = {
        "native_glrt.c": center_union.native,
        "kernel/private/full_search.c": center_union.full_search,
        str(release.LEAF): center_union.presence,
    }
    for name, transform in files.items():
        path = source / name
        path.write_text(transform(path.read_text()))
    shutil.copyfile(center_union.HEADER, source / center_union.HEADER.name)
    compiler, archiver = "/usr/bin/gcc", "/usr/bin/gcc-ar"
    dependencies = release.dependency_paths(fftw_prefix, compiler)
    prefix, environment = release.stage_dependencies(dependencies, work, compiler)
    candidate = work / "union"
    new_source = dict(baseline, patched_presence_sha256=release.sha256(source / release.LEAF))
    proof = release.compile_variant(
        capsule,
        candidate,
        work,
        "center_union",
        new_source,
        compiler,
        archiver,
        prefix,
        environment,
    )
    trial = candidate / bare
    receipt = json.loads((candidate / "build-receipt.json").read_text())
    parent = {
        key.removeprefix("source/"): val
        for key, val in manifest["files"].items()
        if key.startswith("source/")
    }
    changed = {key for key, value in parent.items() if receipt["sources"][key] != value}
    if (
        changed != files.keys()
        or receipt["sources"].keys() - parent.keys() != {center_union.HEADER.name}
        or exports(trial) != exports(stock) | {center_union.ENTRY}
    ):
        raise ValueError("center-union release differs outside its opt-in ABI and search support")
    save_json(
        work / "release.json",
        dict(
            paths={"stock": str(stock), "union": str(trial)},
            library_sha256={"stock": release.sha256(stock), "union": release.sha256(trial)},
            stock_public_abi=1,
            optional_entry=center_union.ENTRY,
            proof=proof,
            modified_sources={
                name: receipt["sources"][name] for name in (*files, center_union.HEADER.name)
            },
            capsule_sha256=release.CAPSULE_SHA256,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", default=WORK, type=local_output)
    parser.add_argument("--stock", default=STOCK, type=Path)
    parser.add_argument("--fftw-prefix", default=Path("/usr"), type=Path)
    args = parser.parse_args()
    build(args.work, args.stock.resolve(), args.fftw_prefix.resolve())
