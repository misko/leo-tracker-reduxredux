"""Seal the reviewed recovery delta over the effective immutable B7 worker tree.

Run as root after committing the exact source. This changes no service selector.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path("/opt/leo-b7/88e231eb1-r1")
BASE_COMMIT = "173a3956313234e04a7e28f72c89453570bf46cc"
ADDED = (
    "src/leo/analysis/hard60_reduced_newton.py",
    "src/leo/analysis/hard60_qualification.py",
    "src/leo/application/hard60_retained_calibration.py",
)
REPLACEMENTS = (
    *ADDED,
    "src/leo/application/hard60_b7.py",
    "src/leo/cli/regional_position.py",
)


def digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def git(repository, *args):
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={repository}", "-C", str(repository), *args]
    )


def main(repository):
    if os.geteuid() != 0:
        raise PermissionError("immutable stage requires root")
    repository = Path(repository).resolve(strict=True)
    revision = git(repository, "rev-parse", "HEAD").decode().strip()
    if git(repository, "status", "--porcelain"):
        raise ValueError("stage requires a clean committed source checkout")
    if git(repository, "merge-base", BASE_COMMIT, revision).decode().strip() != BASE_COMMIT:
        raise ValueError("source does not descend from the reviewed B7 base")
    destination = BASE.parent / f"{revision[:9]}-retained-r1"
    temporary = BASE.parent / f".{revision[:9]}-retained-r1-staging"
    if destination.exists() or temporary.exists():
        raise FileExistsError("immutable stage name already used")
    source = BASE / "worker/src"
    base_receipt = json.loads((BASE / "stage.json").read_text())
    if base_receipt["revision"] != "88e231eb1fd0ae52d9e043b08d643d27b711629c":
        raise ValueError("unexpected inherited worker tree")
    actual = {
        str(path.relative_to(source))
        for path in source.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    if actual != set(base_receipt["roles"]["worker"]["files"]):
        raise ValueError("inherited worker inventory changed")
    for name, expected in base_receipt["roles"]["worker"]["files"].items():
        path = source / name
        if path.is_symlink() or not path.is_file() or digest(path.read_bytes()) != expected:
            raise ValueError(f"inherited source changed: {name}")
    for name in REPLACEMENTS:
        if name in ADDED:
            continue
        previous = git(repository, "show", f"{BASE_COMMIT}:{name}")
        if (source / name.removeprefix("src/")).read_bytes() != previous:
            raise ValueError(f"effective source differs from reviewed base: {name}")
    for name in ADDED:
        if (source / name.removeprefix("src/")).exists():
            raise ValueError(f"new module already present in inherited tree: {name}")
    try:
        shutil.copytree(
            source, temporary / "worker/src", ignore=shutil.ignore_patterns("__pycache__")
        )
        target = temporary / "worker/src"
        for name in REPLACEMENTS:
            content = git(repository, "show", f"{revision}:{name}")
            committed = (repository / name).read_bytes()
            if committed != content:
                raise ValueError(f"working source differs from committed object: {name}")
            path = target / name.removeprefix("src/")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(committed)
        files = {
            str(path.relative_to(target)): digest(path.read_bytes())
            for path in sorted(target.rglob("*"))
            if path.is_file()
        }
        receipt = dict(
            revision=revision,
            inherited=str(source),
            inherited_revision=base_receipt["revision"],
            base_commit=BASE_COMMIT,
            replacements=list(REPLACEMENTS),
            files=files,
        )
        (temporary / "stage.json").write_text(json.dumps(receipt, indent=2) + "\n")
        for path in sorted(temporary.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if path.is_file():
                path.chmod(0o555 if path.suffix == ".so" else 0o444)
            elif path.is_dir():
                path.chmod(0o555)
        temporary.chmod(0o555)
        temporary.rename(destination)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    print(json.dumps(dict(stage=str(destination), revision=revision, files=len(files))))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: stage.py ABSOLUTE_SOURCE_CHECKOUT")
    main(sys.argv[1])
