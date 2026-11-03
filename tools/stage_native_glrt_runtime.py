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
FRACTIONAL_REPORT = "reports/2026_11_03_algo07_runtime_iteration014/receipts/"
FRACTIONAL_MEMBER = "src/leo/analysis/starlink/fast_scan_fractional.py"


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
    extras = {"prototype-build.json": build_bytes,
              "tools/stage_native_glrt_runtime.py": committed("tools/stage_native_glrt_runtime.py")}
    extras.update({"qualification/" + str(i) + "-" + Path(name).name: data
                   for i, (name, data) in enumerate(proofs.items())})
    return install(plan, candidate, build["candidate_sha256"], extras)


def install(plan, candidate, inventory, extras):
    target = Path(plan["release"])
    target.mkdir(parents=True)
    (target / ".incomplete").touch()
    for name in inventory:
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(candidate / name, destination)
    verify_files(target, inventory)
    files = dict(inventory)
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


def fractional_qualification(native, downstream, paired, policy):
    if not (native["exact"] and native["mismatch_count"] == 0
            and native["windows"] == 6772 and native["receiver_results"] == 13534
            and native["all_candidates"] == 108272
            and native["frozen_verification"]["verified"]
            and native["baseline_frozen_verification"]["verified"]):
        raise ValueError("Complete exact native parity required")
    if not (downstream["exact"] and downstream["tolerance"] == 0
            and downstream["files"] == 6 and downstream["difference_count"] == 0
            and downstream["both_calibration_arms_required"]
            and downstream["frozen_inputs_verified"] and downstream["read_audit"]["verified"]):
        raise ValueError("Exact downstream both-arm replay required")
    if len(paired) != 3:
        raise ValueError("All three paired cohort fixtures required")
    for comparison in paired:
        rows = comparison["rows"]
        totals = {side: sum(r[side]["seconds"] for r in rows)
                  for side in ("baseline", "candidate")}
        if not (comparison["all_receiver_outputs_exact"] and not comparison["cprofile"]
                and len(rows) == 16 and len({r["visit"] for r in rows}) == 16
                and all(r["exact"] for r in rows) and totals == comparison["totals"]
                and 0 < totals["candidate"] < totals["baseline"]):
            raise ValueError("Exact faster paired native fixtures required")
    if not (policy["passed"] and policy["cases"] == 175 and policy["paired_arms"] == 350
            and policy["reference_after"]["verified"]):
        raise ValueError("Frozen population policy audit required")


def stage_fractional(repo, revision, base, candidate, *, execute=False):
    if not re.fullmatch("[0-9a-f]{40}", revision):
        raise ValueError("Exact committed revision required")
    repo, base, candidate = (p.resolve(strict=True) for p in (repo, base, candidate))

    def committed(name):
        return subprocess.check_output(["git", "-C", str(repo), "show", f"{revision}:{name}"])

    cases = ["glrt-native-DS26-0046", "glrt-native-DS27-0004", "glrt-native-DS28-0002"]
    names = ["build.json", "full-parity.json", "downstream-parity.json", "policy.json"]
    names += [c + suffix for c in cases for suffix in (".json", "-verification.json")]
    proofs = {n: committed(FRACTIONAL_REPORT + n) for n in names}
    data = {n: json.loads(v) for n, v in proofs.items()}
    build, native = data["build.json"], data["full-parity.json"]
    fractional_qualification(native, data["downstream-parity.json"],
                             [data[c + ".json"] for c in cases], data["policy.json"])
    original = verify(base, build["base_pin"])["files_sha256"]
    inventory = build["files_sha256"]
    verify_files(candidate, inventory)
    if (Path(build["base"]).resolve() != base or Path(build["candidate"]).resolve() != candidate
            or Path(native["candidate"]["runtime"]).resolve() != candidate
            or set(original) != set(inventory)
            or [n for n in inventory if inventory[n] != original[n]] != [FRACTIONAL_MEMBER]
            or hashlib.sha256(committed(FRACTIONAL_MEMBER)).hexdigest()
                != inventory[FRACTIONAL_MEMBER]):
        raise ValueError("Fractional qualification belongs to different source bytes")
    # The reused full baseline must have exactly the deployed native source bytes.
    source_files = {n: v for n, v in original.items()
                    if n.startswith("src/") and Path(n).suffix in (".py", ".so")}
    verify_files(Path(native["baseline"]["runtime"]), source_files)
    for case in cases:
        receipt = data[case + "-verification.json"]
        if not (receipt["exit_code"] == 0 and receipt["source_bytes_verified"]
                and receipt["fixture_before"]["verified"] and receipt["fixture_after"]["verified"]
                and receipt["build_receipt_sha256"]
                    == hashlib.sha256(proofs["build.json"]).hexdigest()):
            raise ValueError("Paired fixture source qualification differs")
    target = Path("/opt/leo-native-glrt-runtime") / revision
    if target.exists():
        raise FileExistsError(target)
    plan = dict(kind=KIND, qualification="fractional-weight-reuse", revision=revision,
                release=str(target), base=str(base), tested_candidate=str(candidate),
                numerical_changes=[FRACTIONAL_MEMBER],
                python="/opt/leo-fast-auto/20261010-r1/venv/bin/python",
                service_mutation=False, IQ_or_database_mutation=False,
                qualification_sha256={n: hashlib.sha256(v).hexdigest() for n, v in proofs.items()})
    if not execute:
        return plan
    if os.geteuid() != 0:
        raise PermissionError("Root stages immutable native runtimes")
    composition = dict(original_sha256=original, candidate_sha256=inventory)
    extras = {"prototype-build.json": (json.dumps(composition, indent=2) + "\n").encode(),
              "tools/stage_native_glrt_runtime.py": committed("tools/stage_native_glrt_runtime.py")}
    extras.update({"qualification/fractional/" + n: v for n, v in proofs.items()})
    return install(plan, candidate, inventory, extras)


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
    p = commands.add_parser("stage-fractional")
    for name in ("repo", "base", "candidate"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--revision", required=True)
    p.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.command == "verify":
        result = verify(args.root, args.pin)
        print(json.dumps(dict(verified=True, files=len(result["files_sha256"]))))
    else:
        operation = stage if args.command == "stage" else stage_fractional
        print(json.dumps(operation(args.repo, args.revision, args.base, args.candidate,
                                   execute=args.execute)))


if __name__ == "__main__":
    main()
