"""Build the released standalone stored-GLRT position receiver at its run location."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .qualification.cavity_payload import digest, read_bundle

RELEASE = (
    Path(__file__).resolve().parents[2]
    / "reports/2026_11_19_receiver_screening/next/cavity-payload"
)


PROFILES = ("compact", "majority", "longitude", "phase-release", "interior")
INTERIOR_RULE = "tools/pipeline_eval/variants/compact_tile_interior.py"
INTERIOR_RULE_SHA256 = "38241e8bde0b9b44888869f1360de12dc7e158099fb996152eebc18217757a35"


def interior_rule():
    path = Path(__file__).with_name("variants") / Path(INTERIOR_RULE).name
    qualified = path.read_bytes()
    if digest(qualified) != INTERIOR_RULE_SHA256:
        raise ValueError("the qualified interior publication rule changed")
    return qualified.replace(
        b"from .v5_secant_fit import STOP_KM",
        b"from .compact_cavity_optimizer import STOP_KM",
        1,
    )


def interior_launcher(source):
    output = b"    verify_project_modules(root)\n    print(json.dumps(result, allow_nan=False))"
    if source.count(output) != 1:
        raise ValueError("unexpected standalone result publication path")
    decision = (
        b"    from tools.pipeline_eval.variants.compact_tile_interior import guard\n"
        b"\n"
        b'    result = guard(result, {"center": args.tile, "width_km": args.width_km})\n'
    )
    return source.replace(output, decision + output, 1)


def release_files(release, profile):
    if profile not in PROFILES:
        raise ValueError(f"unknown standalone receiver profile {profile!r}")
    if profile == "longitude":
        folder = release.with_name("longitude")
        source = folder / "receiver-source.tar.gz"
        authority = folder / "source-lock.json"
        pin = json.loads((folder / "prediction-lock.json").read_bytes())
        if digest(authority.read_bytes()) != pin[authority.name]:
            raise ValueError("longitude release ledger changed")
        ledger = json.loads(authority.read_bytes())
        if digest(source.read_bytes()) != ledger["archive_sha256"]:
            raise ValueError("longitude release archive changed")
        return read_bundle(source, ledger["files"])
    source = release / "receiver-source.tar.gz"
    manifest = release / "package.json"
    expected = json.loads((release / "prediction-lock.json").read_bytes())["files"]
    for path in (source, manifest):
        if digest(path.read_bytes()) != expected[path.name]:
            raise ValueError(f"receiver release digest mismatch for {path.name}")
    package = json.loads(manifest.read_bytes())
    files = read_bundle(source, package["files"])
    if profile == "majority":
        folder = release.with_name("standalone-majority")
        authority = folder / "source-lock.json"
        pin = json.loads((folder / "prediction-lock.json").read_bytes())["files"]
        if digest(authority.read_bytes()) != pin[authority.name]:
            raise ValueError("majority release ledger changed")
        files["tools/pipeline_eval/variants/v5_direct_cavity.py"] = (
            folder / "as-executed-v5-direct-cavity.py.txt"
        ).read_bytes()
        actual = {name: digest(data) for name, data in files.items()} | package["binaries"]
        if actual != json.loads(authority.read_bytes())["derived_files"]:
            raise ValueError("majority profile differs from the measured receiver")
    if profile in ("phase-release", "interior"):
        studies = release.parent.parent / "detector-origins"
        qualified = studies / "pressure"
        receipt = (qualified / "candidate-lock.json").read_bytes()
        whole = json.loads((studies / "whole-pressure/replay-source-lock.json").read_bytes())
        if digest(receipt) != whole["release_receipt_sha256"]:
            raise ValueError("phase release differs from the full-IQ trial")
        target = "leo/analysis/localization_v3/feasible.py"
        files[target] = (qualified / "as-executed-feasible.py.txt").read_bytes()
        checked = json.loads(receipt)
        measured = checked["files"] | checked["compiler_sources"]
        if any(digest(data) != measured.get(name) for name, data in files.items()):
            raise ValueError("phase release sources differ from the measured receiver")
    if profile == "interior":
        files[INTERIOR_RULE] = interior_rule()
    return files


def install(out, release=RELEASE, *, profile="compact"):
    out = Path(out).resolve()
    if out.is_relative_to("/mnt/qnap01"):
        raise ValueError("the receiver build requires a writable local directory")
    files = release_files(release, profile)
    out.mkdir(parents=True, exist_ok=False)
    try:
        for name, data in files.items():
            path = out / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        # An explicit package wins over an unrelated installed package named tools.
        (out / "tools/__init__.py").write_text(
            f'"""Private receiver modules."""\nPROFILE = {profile!r}\n'
        )
        launcher = Path(__file__).with_name("cavity_entry.py")
        if profile == "interior":
            (out / "__main__.py").write_bytes(interior_launcher(launcher.read_bytes()))
        else:
            shutil.copyfile(launcher, out / "__main__.py")
        command = (
            "import runpy;from pathlib import Path;"
            "runpy.run_path('__main__.py')['build'](Path.cwd())"
        )
        subprocess.run(
            [sys.executable, "-IB", "-c", command],
            cwd=out,
            check=True,
            timeout=60,
            env=dict(
                os.environ,
                **dict.fromkeys(
                    (
                        "OMP_NUM_THREADS",
                        "MKL_NUM_THREADS",
                        "BLIS_NUM_THREADS",
                        "OPENBLAS_NUM_THREADS",
                    ),
                    "1",
                ),
            ),
        )
    except BaseException:
        # The exclusive mkdir above makes this partial directory ours.
        shutil.rmtree(out)
        raise
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "out", type=Path, help="new directory on the device that will run the receiver"
    )
    parser.add_argument("--profile", choices=PROFILES, default="compact")
    args = parser.parse_args()
    print(install(args.out, profile=args.profile))
