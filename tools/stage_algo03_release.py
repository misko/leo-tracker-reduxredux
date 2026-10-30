"""Stage a sealed ALGO03 release, including its frozen scientific inventory.

This separate stager does not select a service, write observations or touch the
v1 namespace. Only an exact committed revision can be packaged.
"""

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
from pathlib import Path, PurePosixPath

MANIFEST = "reports/ALGO03/releases/2026-10-30-r1/manifest.json"
MANIFEST_SHA256 = "6dd58bbbe5e7d1f881c820edf0bee0345952a365553afaf37f457dfcec189545"
MODEL_VERSION = "algo03-causal-predictive-v1"


def _git(source, *arguments):
    return subprocess.check_output(["git", "-C", str(source), *arguments])


def scientific_inventory(source, revision):
    """Check committed bytes, never mutable worktree copies, against frozen r1."""
    payload = _git(source, "show", f"{revision}:{MANIFEST}")
    if hashlib.sha256(payload).hexdigest() != MANIFEST_SHA256:
        raise ValueError("Committed ALGO03 scientific manifest differs from frozen r1")
    manifest = json.loads(payload)
    files = {MANIFEST: MANIFEST_SHA256, **manifest["sha256"]}
    for name, expected in files.items():
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise ValueError("Unsafe scientific inventory path")
        actual = hashlib.sha256(_git(source, "show", f"{revision}:{name}")).hexdigest()
        if actual != expected:
            raise ValueError("Frozen ALGO03 scientific source changed: " + name)
    return files


def stage(source, revision, python_root, uv, *, execute=False):
    source, python_root, uv = (Path(p).resolve() for p in (source, python_root, uv))
    resolved = _git(source, "rev-parse", revision).decode().strip()
    if not re.fullmatch(r"[0-9a-f]{40}", revision) or revision != resolved:
        raise ValueError("Exact committed full revision required")
    release = Path("/opt/leo-fast-graph") / revision
    if release.exists():
        raise FileExistsError(release)
    if not (python_root / "bin/python3.12").is_file() or not uv.is_file():
        raise ValueError("Explicit CPython 3.12 runtime and uv executable required")
    science = scientific_inventory(source, revision)
    roots = ("src", "tools", "deploy")
    extra = sorted(name for name in science if PurePosixPath(name).parts[0] not in roots)
    archive_paths = [*roots, *extra]
    plan = dict(
        revision=revision,
        release=str(release),
        model_version=MODEL_VERSION,
        python_root=str(python_root),
        frozen_science_manifest_sha256=MANIFEST_SHA256,
        scientific_files=len(science),
        archive_paths=archive_paths,
        service_mutation=False,
        recording_or_database_mutation=False,
    )
    if not execute:
        return plan
    if os.geteuid() != 0:
        raise PermissionError("Root stages immutable releases")
    release.mkdir(parents=True)
    (release / ".incomplete").touch()
    payload = _git(source, "archive", revision, *archive_paths)
    with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
        archive.extractall(release, filter="data")
    for name, expected in science.items():
        if hashlib.sha256((release / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Staged scientific source mismatch: " + name)
    shutil.copytree(python_root, release / "runtime", symlinks=True)
    shutil.copyfile(uv, release / "uv")
    (release / "uv").chmod(0o755)
    (release / "release-revision.txt").write_text(revision + "\n")
    environment = dict(
        os.environ, UV_CACHE_DIR="/var/cache/leo-fast-graph-uv", PYTHONDONTWRITEBYTECODE="1"
    )
    subprocess.run(
        [
            str(release / "uv"),
            "venv",
            "--python",
            str(release / "runtime/bin/python3.12"),
            str(release / "venv"),
        ],
        env=environment,
        check=True,
    )
    subprocess.run(
        [
            str(release / "uv"),
            "pip",
            "sync",
            "--python",
            str(release / "venv/bin/python"),
            "--require-hashes",
            str(release / "deploy/fast-graph-position.lock"),
        ],
        env=environment,
        check=True,
    )
    environment.update(
        PYTHONPATH=os.pathsep.join((str(release / "src"), str(release / "tools"))),
        OPENBLAS_NUM_THREADS="1",
        MPLCONFIGDIR="/tmp/leo-algo03-stage-matplotlib",
    )
    subprocess.run(
        [
            str(release / "venv/bin/python"),
            "-B",
            "-c",
            "import algo03_shadow_worker, run_algo03_shadow, algo03_production_worker; "
            "import leo.cli.fast_graph_position_v2; "
            "import leo.contracts.fast_graph_position_v2; import numpy, scipy",
        ],
        env=environment,
        cwd=release,
        check=True,
    )
    files = {
        str(p.relative_to(release)): hashlib.sha256(p.read_bytes()).hexdigest()
        for root in ("src", "tools", "deploy", "reports", "tests")
        for p in sorted((release / root).rglob("*"))
        if p.is_file()
    }
    (release / "release-manifest.json").write_text(
        json.dumps(dict(plan, files_sha256=files), indent=2) + "\n"
    )
    for current, _directories, names in os.walk(release):
        Path(current).chmod(0o755)
        for name in names:
            path = Path(current) / name
            if not path.is_symlink():
                path.chmod(0o755 if path.stat().st_mode & 0o111 else 0o644)
    (release / ".incomplete").unlink()
    return plan


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--python-root", type=Path, required=True)
    parser.add_argument("--uv", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            stage(args.source, args.revision, args.python_root, args.uv, execute=args.execute)
        )
    )
