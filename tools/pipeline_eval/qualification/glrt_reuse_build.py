"""Build the opt-in wide preparation path from the portable authenticated capsule."""

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from .. import wide_runtime as recipe
from ..variants import glrt_reuse

WORK = Path("/var/tmp/leo-glrt-reuse-20261119")


def exports(library):
    rows = subprocess.check_output(["nm", "-D", "--defined-only", str(library)], text=True)
    return {line.split()[-1] for line in rows.splitlines()}


def build(work, stock, fftw_prefix):
    if work.resolve().is_relative_to(Path("/mnt/qnap01")):
        raise ValueError("build requires local writable scratch")
    work.mkdir(parents=True, exist_ok=False)
    capsule = work / "capsule"
    manifest = recipe.unpack(recipe.CAPSULE, capsule)
    base = manifest["stock"]
    if recipe.sha256(stock) != base["output_sha256"][recipe.OUTPUTS[0]]:
        raise ValueError("candidate must be paired with the measured 21-bin stock artifact")
    source = capsule / "source/native_glrt.c"
    source.write_text(glrt_reuse.overlay(source.read_text()))
    shutil.copyfile(glrt_reuse.HEADER, source.with_name(glrt_reuse.HEADER.name))
    compiler, archiver = "/usr/bin/gcc", "/usr/bin/gcc-ar"
    paths = recipe.dependency_paths(fftw_prefix.resolve(), compiler)
    prefix, env = recipe.stage_dependencies(paths, work, compiler)
    candidate = work / "candidate"
    proof = recipe.compile_variant(
        capsule, candidate, work, "wide_pair", base, compiler, archiver, prefix, env
    )
    library = candidate / recipe.OUTPUTS[0]
    receipt = json.loads((candidate / "build-receipt.json").read_bytes())
    observed = {f"source/{f}": s for f, s in receipt["sources"].items()}
    parent = {f: s for f, s in manifest["files"].items() if f.startswith("source/")}
    changed = {f for f, s in parent.items() if observed[f] != s}
    added = observed.keys() - parent.keys()
    if (
        changed != {"source/native_glrt.c"}
        or added != {f"source/{glrt_reuse.HEADER.name}"}
        or exports(stock) != exports(library)
    ):
        raise ValueError("candidate changes sources or ABI outside wide preparation")
    result = dict(
        abi_version=1,
        capsule_sha256=recipe.CAPSULE_SHA256,
        paths={"control": str(stock), "candidate": str(library)},
        library_sha256={"control": recipe.sha256(stock), "candidate": recipe.sha256(library)},
        recipe=proof,
        modified_sources={f: observed[f] for f in changed | added},
    )
    (work / "release.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work", type=Path, default=WORK)
    p.add_argument("--stock", type=Path, required=True)
    p.add_argument("--fftw-prefix", type=Path, default=Path("/usr"))
    args = p.parse_args()
    build(args.work.resolve(), args.stock.resolve(), args.fftw_prefix)
