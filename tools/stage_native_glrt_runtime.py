"""Stage the exactly tested native GLRT composition after full qualification."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

REPORT = "reports/2026_11_03_algo07_runtime_iteration010"
PROTOTYPE = "reports/2026_11_03_algo07_runtime_iteration005/prototype-build.json"
KIND = "native-glrt-qualified-runtime-v1"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_files(root, files):
    if not files:
        raise ValueError("Empty native runtime")
    for name, expected in files.items():
        relative, path = Path(name), root / name
        if (relative.is_absolute() or ".." in relative.parts or path.is_symlink()
                or not path.resolve().is_relative_to(root.resolve()) or digest(path) != expected):
            raise ValueError("Native runtime member differs: " + name)


def verify(root, pin):
    root = root.resolve(strict=True)
    path = root / "runtime-manifest.json"
    if (root / ".incomplete").exists() or digest(path) != pin:
        raise ValueError("Incomplete or unpinned native runtime")
    manifest = json.loads(path.read_text())
    if manifest["kind"] != KIND:
        raise ValueError("Unexpected native runtime kind")
    verify_files(root, manifest["files_sha256"])
    return manifest


def qualification(native, downstream, fixture, policy):
    if not (native["exact"] and native["mismatch_count"] == 0
            and native["windows"] == 6772 and native["receiver_results"] == 13534
            and native["all_candidates"] == 108272
            and native["matched_timing_configuration"] and native["wall_speedup"] > 1
            and native["frozen_verification"]["verified"]):
        raise ValueError("Matched complete native replay is not qualified")
    if not (downstream["exact"] and downstream["tolerance"] == 0
            and downstream["files"] == 6 and downstream["difference_count"] == 0
            and downstream["both_calibration_arms_required"]
            and downstream["frozen_inputs_verified"] and downstream["read_audit"]["verified"]):
        raise ValueError("Downstream paired localization is not qualified")
    if not (fixture["passed"] and fixture["unique_windows"] == 80
            and fixture["receiver_outputs"] == 160 and policy["passed"]
            and policy["cases"] == 175):
        raise ValueError("Frozen cohort qualification is incomplete")


def stage(repo, revision, base, candidate, *, execute=False):
    if not re.fullmatch("[0-9a-f]{40}", revision):
        raise ValueError("Exact committed revision required")
    repo, base, candidate = (p.resolve(strict=True) for p in (repo, base, candidate))

    def committed(name):
        return subprocess.check_output(["git", "-C", str(repo), "show", f"{revision}:{name}"])

    names = [REPORT + "/receipts/full-native-matched-parity.json",
             REPORT + "/receipts/downstream-parity.json",
             "reports/2026_11_03_algo07_runtime_iteration005/results.json",
             "reports/2026_11_03_algo07_runtime_iteration005/policy-parity.json"]
    proofs = {name: committed(name) for name in names}
    qualification(*(json.loads(proofs[name]) for name in names))
    build_bytes = committed(PROTOTYPE)
    build = json.loads(build_bytes)
    verify_files(base, build["original_sha256"])
    verify_files(candidate, build["candidate_sha256"])
    if set(build["original_sha256"]) != set(build["candidate_sha256"]):
        raise ValueError("Prototype changed the native file inventory")
    changes = {name for name, sha in build["original_sha256"].items()
               if sha != build["candidate_sha256"][name]}
    prefix = "src/leo/analysis/starlink/"
    expected = {prefix + name for name in (
        "acquisition.py", "_native_acquisition.c", "_native_acquisition_grid.inc",
        "_native_acquisition.cpython-312-x86_64-linux-gnu.so")}
    if changes != expected or changes != set(build["changes"]):
        raise ValueError("Unexpected native changes")
    native = json.loads(proofs[names[0]])
    if Path(native["candidate"]["runtime"]).resolve() != candidate:
        raise ValueError("Qualification belongs to another candidate")
    target = Path("/opt/leo-native-glrt-runtime") / revision
    if target.exists():
        raise FileExistsError(target)
    plan = dict(kind=KIND, revision=revision, release=str(target), base=str(base),
        tested_candidate=str(candidate), numerical_changes=sorted(changes),
        python="/opt/leo-fast-auto/20261010-r1/venv/bin/python",
        service_mutation=False, IQ_or_database_mutation=False,
        qualification_sha256={name: hashlib.sha256(data).hexdigest()
                              for name, data in proofs.items()})
    if not execute:
        return plan
    if os.geteuid() != 0:
        raise PermissionError("Root stages immutable native runtimes")
    target.mkdir(parents=True)
    (target / ".incomplete").touch()
    for name in build["candidate_sha256"]:
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(candidate / name, destination)
    verify_files(target, build["candidate_sha256"])
    files = dict(build["candidate_sha256"])
    extras = {"prototype-build.json": build_bytes,
              "tools/stage_native_glrt_runtime.py": committed("tools/stage_native_glrt_runtime.py")}
    extras.update({"qualification/" + str(i) + "-" + Path(name).name: data
                   for i, (name, data) in enumerate(proofs.items())})
    for name, data in extras.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        files[name] = hashlib.sha256(data).hexdigest()
    manifest = dict(plan, files_sha256=files)
    (target / "runtime-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    for path in target.rglob("*"):
        path.chmod(0o755 if path.is_dir() else 0o644)
    target.chmod(0o755)
    (target / ".incomplete").unlink()
    pin = digest(target / "runtime-manifest.json")
    verify(target, pin)
    return dict(plan, manifest_sha256=pin, files=len(files))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("verify")
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--pin", required=True)
    p = commands.add_parser("stage")
    for name in ("repo", "base", "candidate"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--revision", required=True)
    p.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.command == "verify":
        result = verify(args.root, args.pin)
        print(json.dumps(dict(verified=True, files=len(result["files_sha256"]))))
    else:
        print(json.dumps(stage(args.repo, args.revision, args.base, args.candidate,
                               execute=args.execute)))


if __name__ == "__main__":
    main()
