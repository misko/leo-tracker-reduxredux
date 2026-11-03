"""Stage an immutable ALGO02 package from committed exact numerical qualification."""

import argparse
import hashlib
import json
import os
import re
import shutil
import statistics
import subprocess
from pathlib import Path

from build_algo02_runtime_prototype import BASELINE_PIN, HELPER, REPLACEMENTS, digest

REPORT = "reports/2026_11_03_algo07_runtime_iteration011/receipts/"
KIND = "algo02-qualified-hierarchical-runtime-v1"
STORE = "src/leo/storage/fast_graph_position.py"
DISCOVERY_REPORT = "reports/2026_11_03_algo07_runtime_iteration012/receipts/"


def verify_files(root, files):
    if not files:
        raise ValueError("Empty ALGO02 runtime")
    for name, expected in files.items():
        relative, path = Path(name), root / name
        if (relative.is_absolute() or ".." in relative.parts or path.is_symlink()
                or not path.resolve().is_relative_to(root.resolve()) or digest(path) != expected):
            raise ValueError("ALGO02 runtime member changed: " + name)


def verify(root, pin):
    root = root.resolve(strict=True)
    path = root / "release-manifest.json"
    if (root / ".incomplete").exists() or digest(path) != pin:
        raise ValueError("Incomplete or unpinned ALGO02 runtime")
    manifest = json.loads(path.read_text())
    if manifest["kind"] != KIND:
        raise ValueError("Unexpected ALGO02 runtime kind")
    verify_files(root, manifest["files_sha256"])
    return manifest


def qualification(pair, build, policy):
    if not (pair["exact"] and pair["matched_timing_configuration"]
            and not pair["cprofile_enabled"] and pair["wall_speedup"] > 1):
        raise ValueError("Matched unprofiled improvement required")
    for row in [pair["parity"], *pair["reference_audits"]]:
        if not (row["exact"] and row["files"] == 6 and row["tolerance"] == 0
                and row["difference_count"] == 0 and row["both_calibration_arms_required"]):
            raise ValueError("Complete exact paired scientific outputs required")
    if len(pair["reference_audits"]) != 2:
        raise ValueError("Both trials must pass the public reference")
    for row, key in zip(pair["reference_audits"],
                        ("source_manifest_sha256", "candidate_manifest_sha256"), strict=True):
        if not (row["frozen_inputs_verified"] and row["read_audit"]["verified"]
                and row["runtime_manifest_sha256"] == build[key]):
            raise ValueError("Qualified replay belongs to another runtime")
    if not (policy["passed"] and policy["cases"] == 175 and policy["paired_arms"] == 350
            and policy["reference_after"]["verified"]):
        raise ValueError("Frozen saved-policy audit required")


def stage(repo, revision, source, candidate, *, execute=False):
    if not re.fullmatch("[0-9a-f]{40}", revision):
        raise ValueError("Exact committed revision required")
    repo, source, candidate = (p.resolve(strict=True) for p in (repo, source, candidate))

    def committed(name):
        return subprocess.check_output(["git", "-C", str(repo), "show", f"{revision}:{name}"])

    names = ("package-source-qualification.json", "prototype-build.json",
             "saved-policy-parity.json")
    proofs = {name: committed(REPORT + name) for name in names}
    pair, build, policy = (json.loads(proofs[n]) for n in names)
    qualification(pair, build, policy)
    if (digest(source / "release-manifest.json") != BASELINE_PIN
            or build["source_manifest_sha256"] != BASELINE_PIN
            or digest(candidate / "release-manifest.json") != build["candidate_manifest_sha256"]):
        raise ValueError("Tested implementation manifests changed")
    original = json.loads((source / "release-manifest.json").read_text())
    prototype = json.loads((candidate / "release-manifest.json").read_text())
    a, b = original["files_sha256"], prototype["files_sha256"]
    verify_files(source, a)
    verify_files(candidate, b)
    changes = set((*REPLACEMENTS, HELPER))
    if (a.keys() != b.keys() or {n for n in a if a[n] != b[n]} != changes
            or set(build["changed_files"]) != changes
            or any(build["original_sha256"][n] != a[n]
                   or build["candidate_sha256"][n] != b[n] for n in changes)):
        raise ValueError("Unexpected runtime composition")
    target = Path("/opt/leo-fast-graph-runtime-algo02") / revision
    if target.exists():
        raise FileExistsError(target)
    plan = dict(kind=KIND, revision=revision, release=str(target), base=str(source),
                tested_candidate=str(candidate), numerical_changes=sorted(changes),
                python=str(source / "venv/bin/python"), service_mutation=False)
    if not execute:
        return plan
    if os.geteuid() != 0:
        raise PermissionError("Root stages immutable runtimes")
    extras = {"qualification/" + name: data for name, data in proofs.items()}
    extras.update({name: committed(name) for name in
                   ("tools/stage_algo02_runtime.py", "tools/build_algo02_runtime_prototype.py")})
    extras["release-revision.txt"] = (revision + "\n").encode()
    return install(plan, candidate, b, extras, dict(source_manifest_sha256=BASELINE_PIN,
                   tested_manifest_sha256=build["candidate_manifest_sha256"]))


def install(plan, source, inventory, extras, metadata):
    target = Path(plan["release"])
    target.mkdir(parents=True)
    (target / ".incomplete").touch()
    files = dict(inventory)
    for name in files:
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, destination)
    for name, data in extras.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        files[name] = hashlib.sha256(data).hexdigest()
    manifest = dict(plan, files_sha256=files, **metadata)
    (target / "release-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    for path in target.rglob("*"):
        path.chmod(0o755 if path.is_dir() else 0o644)
    target.chmod(0o755)
    (target / ".incomplete").unlink()
    pin = digest(target / "release-manifest.json")
    verify(target, pin)
    return dict(plan, runtime_manifest_sha256=pin, files=len(files))


def discovery_qualification(result, fixture, policy):
    count = len(fixture["selected"])
    if not (result["exact"] and count > 0 and result["cases"] == count
            == fixture["public_inventory_count"] and len(result["cold"]) == 2
            and all(r["input_hash_calls"] == count for r in result["cold"])
            and not result["changed_states_hidden"] and not result["production_modified"]):
        raise ValueError("Complete exact discovery inventory required")
    groups = [[r for r in result["trials"] if r["variant"] == side]
              for side in ("baseline", "candidate")]
    if not (len(groups[0]) == len(groups[1]) >= 3
            and len(result["trials"]) == len(groups[0]) + len(groups[1])
            and [r["repeat"] for r in groups[0]] == [r["repeat"] for r in groups[1]]
            and all(r["input_hash_calls"] == count for r in groups[0])
            and all(r["input_hash_calls"] == 0 for r in groups[1])
            and statistics.median(r["wall_seconds"] for r in groups[0])
                > statistics.median(r["wall_seconds"] for r in groups[1])):
        raise ValueError("Matched repeated discovery improvement required")
    if not (policy["passed"] and policy["cases"] == 175 and policy["paired_arms"] == 350
            and policy["reference_after"]["verified"]):
        raise ValueError("Frozen policy audit required")


def stage_discovery(repo, revision, source, *, execute=False):
    if not re.fullmatch("[0-9a-f]{40}", revision):
        raise ValueError("Exact committed revision required")
    repo, source = repo.resolve(strict=True), source.resolve(strict=True)

    def committed(name):
        return subprocess.check_output(["git", "-C", str(repo), "show", f"{revision}:{name}"])

    proofs = {name: committed(DISCOVERY_REPORT + name) for name in
              ("full-inventory.json", "fixture.json", "saved-policy.json", "candidate_store.py")}
    result, fixture, policy = (json.loads(proofs[n]) for n in
                              ("full-inventory.json", "fixture.json", "saved-policy.json"))
    discovery_qualification(result, fixture, policy)
    base = verify(source, result["runtime_manifest_sha256"])
    candidate = proofs["candidate_store.py"]
    if (base["files_sha256"][STORE] != result["original_source_sha256"]
            or hashlib.sha256(candidate).hexdigest() != result["candidate_source_sha256"]
            or hashlib.sha256(proofs["fixture.json"]).hexdigest() != result["fixture_sha256"]
            or hashlib.sha256(committed(STORE)).hexdigest() != result["current_source_sha256"]):
        raise ValueError("Discovery source or fixture differs from qualified bytes")
    target = Path("/opt/leo-fast-graph-runtime-algo02") / revision
    if target.exists():
        raise FileExistsError(target)
    plan = dict(kind=KIND, revision=revision, release=str(target), base=str(source),
                qualification="discovery", discovery_cases=result["cases"],
                discovery_fixture_sha256=result["fixture_sha256"],
                discovery_store_sha256=result["candidate_source_sha256"],
                numerical_changes=[], python=base["python"], service_mutation=False)
    if not execute:
        return plan
    if os.geteuid() != 0:
        raise PermissionError("Root stages immutable runtimes")
    extras = {"qualification/discovery/" + name: data for name, data in proofs.items()}
    extras.update({STORE: candidate, "release-revision.txt": (revision + "\n").encode(),
                   "tools/stage_algo02_runtime.py": committed("tools/stage_algo02_runtime.py")})
    return install(plan, source, base["files_sha256"], extras,
                   dict(source_manifest_sha256=result["runtime_manifest_sha256"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("verify")
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--pin", required=True)
    p = commands.add_parser("stage")
    for name in ("repo", "source", "candidate"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--revision", required=True)
    p.add_argument("--execute", action="store_true")
    p = commands.add_parser("stage-discovery")
    for name in ("repo", "source"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--revision", required=True)
    p.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.command == "verify":
        result = verify(args.root, args.pin)
        print(json.dumps(dict(verified=True, files=len(result["files_sha256"]))))
    elif args.command == "stage":
        print(json.dumps(stage(args.repo, args.revision, args.source, args.candidate,
                               execute=args.execute)))
    else:
        print(json.dumps(stage_discovery(args.repo, args.revision, args.source,
                                         execute=args.execute)))
