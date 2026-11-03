"""Build an isolated ALGO02 prototype from verified installed bytes; no deployment."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

BASELINE = "1b63f5908785fc940446086aa4ef5de1a1539003"
BASELINE_PIN = "4ac6389cdeb4e5ef4571dd7affa7e2791a28a2e8ecc6c507441ad6a6ba056263"
HELPER = "tools/probe_ds23_history_calibrated_phase.py"
REPLACEMENTS = ("tools/dsx01_hierarchical_bound.py", "tools/dsx01_joint_marginal.py")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def adapt_helper(source):
    """Keep the older ALGO02 API and all its scientific policies intact."""
    old = "result=JointMarginal.calculate(p,x)"
    if source.count(old) != 1 or "geometry_only" in source:
        raise ValueError("Expected one unoptimized ALGO02 geometry call")
    return source.replace(old, "result=JointMarginal.calculate(p,x,geometry_only=True)")


def build(args):
    source, checkout = args.source.resolve(strict=True), args.checkout.resolve(strict=True)
    target = args.output.resolve()
    if not target.is_relative_to("/srv/bulk/leo/research") or target.exists():
        raise ValueError("New private research destination required")
    if digest(source / "release-manifest.json") != BASELINE_PIN:
        raise ValueError("Installed ALGO02 manifest differs from the frozen reference")
    manifest = json.loads((source / "release-manifest.json").read_text())
    if manifest["revision"] != BASELINE:
        raise ValueError("Unexpected installed ALGO02 release")
    qualification = checkout / "reports/2026_11_03_algo07_runtime_iteration007/implementation.json"
    qualified = json.loads(qualification.read_text())
    files = manifest["files_sha256"]
    for name, expected in files.items():
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError("Unsafe runtime member")
        if digest(source / name) != expected:
            raise ValueError("Installed runtime changed: " + name)
    for name in REPLACEMENTS:
        if files[name] != qualified["baseline_files_sha256"][name]:
            raise ValueError("Unqualified baseline: " + name)
        if digest(checkout / name) != qualified["files_sha256"][name]:
            raise ValueError("Qualified optimization changed: " + name)
    adapted = adapt_helper((source / HELPER).read_text())
    target.mkdir(parents=True)
    for name in files:
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, destination)
    for name in REPLACEMENTS:
        shutil.copyfile(checkout / name, target / name)
    (target / HELPER).write_text(adapted)
    updated = {name: digest(target / name) for name in files}
    changed = sorted(name for name in files if files[name] != updated[name])
    if changed != sorted((*REPLACEMENTS, HELPER)):
        raise ValueError("Unexpected changed runtime inventory")
    manifest.update(release=str(target), files_sha256=updated,
                    runtime_prototype="algo02-exact-hierarchical-v1")
    (target / "release-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    receipt = dict(source=str(source), output=str(target), files=len(files),
                   changed_files=changed, production_modified=False,
                   source_manifest_sha256=digest(source / "release-manifest.json"),
                   candidate_manifest_sha256=digest(target / "release-manifest.json"),
                   qualification_sha256=digest(qualification),
                   original_sha256={n: files[n] for n in changed},
                   candidate_sha256={n: updated[n] for n in changed})
    (target / "prototype-build.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "checkout", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    build(parser.parse_args())
