#!/usr/bin/env python3
"""Build the authenticated 21-bin stock and adjacent-batch wide detector offline."""

import argparse
import hashlib
import json
import os
import runpy
import shutil
import subprocess
import sys
import tempfile
from io import BytesIO
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

CAPSULE = Path(__file__).with_name("wide_runtime_source.zip")
CAPSULE_SHA256 = "b8ad02aad7699f4f4cd88505c30aa376b341198ff11bc566b39e71066ddf58f7"
VARIANTS = ("stock", "adjacent")
OUTPUTS = ("libleo-adaptive-detector.so", "leo-native-glrt-short-window")
LEAF = Path("kernel/private/native_presence/presence.c")


def sha256(path):
    with path.open("rb") as stream:
        value = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
        return value.hexdigest()


def unpack(capsule, destination):
    # Check an open snapshot before interpreting or executing any member.
    with capsule.open("rb") as stream:
        payload = stream.read(128 * 1024 + 1)
    if hashlib.sha256(payload).hexdigest() != CAPSULE_SHA256:
        raise ValueError("wide detector source capsule SHA-256 differs from its release pin")
    with ZipFile(BytesIO(payload)) as bundle:
        manifest_bytes = bundle.read("manifest.json")
        manifest = json.loads(manifest_bytes)
        members = bundle.namelist()
        files = manifest["files"]
        if set(members) != {"manifest.json", *files} or len(members) != len(files) + 1:
            raise ValueError("wide detector source closure differs from its manifest")
        for name, expected in files.items():
            path = PurePosixPath(name)
            if (
                path.parts[0] not in ("source", "overlay")
                or ".." in path.parts
                or path.as_posix() != name
            ):
                raise ValueError("invalid member name in the wide detector capsule")
            body = bundle.read(name)
            if hashlib.sha256(body).hexdigest() != expected:
                raise ValueError(f"wide detector source member failed SHA-256: {name}")
            out = destination / path
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(body)
    (destination / "manifest.json").write_bytes(manifest_bytes)
    return manifest


def dependency_paths(prefix, compiler):
    triplet = subprocess.check_output([compiler, "-print-multiarch"], text=True).strip()
    header = prefix / "include/fftw3.h"
    for path in (prefix / "lib" / triplet, prefix / "lib", prefix / "lib64"):
        static, shared = path / "libfftw3f.a", path / "libfftw3.so"
        if header.is_file() and static.is_file() and shared.is_file():
            return header, static, shared
    raise ValueError(
        f"FFTW development files missing under {prefix}. Need include/fftw3.h, "
        "libfftw3f.a and libfftw3.so from libfftw3-dev or a local FFTW prefix."
    )


def stage_dependencies(paths, scratch, compiler):
    header, static, shared = paths
    prefix = scratch / "fftw"
    (prefix / "include").mkdir(parents=True)
    (prefix / "lib").mkdir()
    (prefix / "include" / header.name).symlink_to(header)
    (prefix / "lib" / static.name).symlink_to(static)
    tmp = scratch / "compiler-temp"
    tmp.mkdir()
    env = dict(os.environ, TMPDIR=str(tmp), LIBRARY_PATH=str(shared.parent))
    selected = subprocess.check_output(
        [compiler, "-print-file-name=libfftw3.so"], text=True, env=env
    ).strip()
    if Path(selected).resolve() != shared.resolve():
        raise ValueError("GCC did not select the requested prefix's shared double FFTW library")
    return prefix, env


def compile_variant(capsule, result, scratch, variant, reference, compiler, archiver, prefix, env):
    sources = scratch / (variant + "-source")
    shutil.copytree(capsule / "source", sources)
    if variant == "adjacent":
        which = runpy.run_path(str(capsule / "overlay/wide_kernel.py"))
        leaf = sources / LEAF
        leaf.write_text(which["overlay"](leaf.read_text()))
        shutil.copyfile(which["HEADER"], leaf.with_name(which["HEADER"].name))
    if sha256(sources / LEAF) != reference["patched_presence_sha256"]:
        raise ValueError("constructed detector does not match the measured variant source")
    build = scratch / (variant + "-build")
    subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(sources / "build.py"),
            "--compiler",
            compiler,
            "--archiver",
            archiver,
            "--fftw-prefix",
            str(prefix),
            "--target",
            "host",
            "--output-dir",
            str(build),
            "--work-dir",
            str(scratch / (variant + "-objects")),
        ],
        check=True,
        cwd=sources,
        env=env,
    )
    recipe = json.loads((build / "build-receipt.json").read_bytes())
    if recipe["abi_version"] != 1 or recipe["algorithm_id"] != "wave8-gate314-source-v1":
        raise ValueError("detector recipe returned an unexpected ABI or algorithm")
    result.mkdir()
    outputs = {}
    for name in OUTPUTS:
        digest = sha256(build / name)
        if digest != recipe["outputs"][name]:
            raise ValueError(f"build receipt disagrees with detector output {name}")
        outputs[name] = dict(
            sha256=digest, reference_exact=digest == reference["output_sha256"][name]
        )
        shutil.copy2(build / name, result / name)
    shutil.copyfile(build / "build-receipt.json", result / "build-receipt.json")
    return dict(
        outputs=outputs,
        build_receipt_sha256=sha256(result / "build-receipt.json"),
        toolchain={key: recipe[key] for key in reference["toolchain"]},
        reference_toolchain_exact=all(recipe[k] == v for k, v in reference["toolchain"].items()),
    )


def build(output, fftw_prefix, compiler="gcc", archiver="gcc-ar", variants=VARIANTS):
    output = output.resolve()
    if output.exists() or output.is_relative_to(Path("/mnt/qnap01")):
        raise ValueError("choose a new output directory on local storage")
    gcc, ar = shutil.which(compiler), shutil.which(archiver)
    if gcc is None or ar is None:
        raise ValueError("install GCC and gcc-ar before building the wide detector")
    gcc, ar = (os.path.abspath(name) for name in (gcc, ar))
    paths = dependency_paths(fftw_prefix.resolve(), gcc)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".wide-runtime-", dir=output.parent) as location:
        scratch = Path(location)
        capsule = scratch / "capsule"
        manifest = unpack(CAPSULE, capsule)
        prefix, env = stage_dependencies(paths, scratch, gcc)
        result = scratch / "release"
        result.mkdir()
        receipts = {
            variant: compile_variant(
                capsule, result / variant, scratch, variant, manifest[variant], gcc, ar, prefix, env
            )
            for variant in variants
        }
        shutil.copyfile(capsule / "manifest.json", result / "capsule-manifest.json")
        shutil.copyfile(capsule / "source/SOURCE_LICENSE.md", result / "SOURCE_LICENSE.md")
        stamp = dict(
            schema="leo-wide-runtime-release/v1",
            source_capsule_sha256=CAPSULE_SHA256,
            fftw_prefix=str(fftw_prefix.resolve()),
            variants=receipts,
        )
        (result / "release.json").write_text(json.dumps(stamp, indent=2, sort_keys=True) + "\n")
        if output.exists():
            raise FileExistsError(f"another build published at {output}")
        result.rename(output)
    return stamp


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="new local output directory")
    parser.add_argument("--fftw-prefix", type=Path, default=Path("/usr"))
    parser.add_argument("--compiler", default="gcc")
    parser.add_argument("--archiver", default="gcc-ar")
    parser.add_argument("--variant", choices=("both", *VARIANTS), default="both")
    args = parser.parse_args()
    variants = VARIANTS if args.variant == "both" else (args.variant,)
    try:
        result = build(args.out, args.fftw_prefix, args.compiler, args.archiver, variants)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.error(str(error))
    for variant, receipt in result["variants"].items():
        library = receipt["outputs"][OUTPUTS[0]]
        print(f"{variant}  {library['sha256']}  {args.out / variant / OUTPUTS[0]}")


if __name__ == "__main__":
    main()
