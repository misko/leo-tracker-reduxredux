"""Stage an immutable causal graph-position worker without changing services."""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile


def stage(source, revision, python_root, uv, *, execute=False):
    source, python_root, uv = map(lambda p: Path(p).resolve(), (source, python_root, uv))
    resolved = subprocess.check_output(["git", "-C", str(source), "rev-parse", revision], text=True).strip()
    if len(revision) != 40 or revision != resolved:
        raise ValueError("Exact committed full revision required")
    release = Path("/opt/leo-fast-graph") / revision
    if release.exists():
        raise FileExistsError(release)
    if not (python_root / "bin/python3.12").is_file() or not uv.is_file():
        raise ValueError("Explicit CPython 3.12 runtime and uv executable required")
    plan = dict(revision=revision, release=str(release), python_root=str(python_root),
                service_mutation=False, recording_or_database_mutation=False)
    if not execute:
        return plan
    if os.geteuid() != 0:
        raise PermissionError("Root stages immutable releases")
    release.mkdir(parents=True)
    (release / ".incomplete").touch()
    payload = subprocess.check_output(["git", "-C", str(source), "archive", revision, "src", "tools", "deploy"])
    with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
        archive.extractall(release, filter="data")
    shutil.copytree(python_root, release / "runtime", symlinks=True)
    shutil.copyfile(uv, release / "uv")
    (release / "uv").chmod(0o755)
    (release / "release-revision.txt").write_text(revision + "\n")
    env = dict(os.environ, UV_CACHE_DIR="/var/cache/leo-fast-graph-uv", PYTHONDONTWRITEBYTECODE="1")
    subprocess.run([str(release / "uv"), "venv", "--python", str(release / "runtime/bin/python3.12"),
                    str(release / "venv")], env=env, check=True)
    subprocess.run([str(release / "uv"), "pip", "sync", "--python", str(release / "venv/bin/python"),
                    "--require-hashes", str(release / "deploy/fast-graph-position.lock")], env=env, check=True)
    env.update(PYTHONPATH=os.pathsep.join((str(release / "src"), str(release / "tools"))),
               OPENBLAS_NUM_THREADS="1", MPLCONFIGDIR="/tmp/leo-fast-graph-stage-matplotlib")
    subprocess.run([str(release / "venv/bin/python"), "-B", "-c",
                    "import algo02_scan, fast_graph_engine; import leo.cli.fast_graph_position; "
                    "import numpy, scipy; print(numpy.__version__, scipy.__version__)"],
                   env=env, cwd=release, check=True)
    # Seal the entire source and dependency lock independently of mutable Git.
    hashes = {str(p.relative_to(release)): hashlib.sha256(p.read_bytes()).hexdigest()
              for prefix in ("src", "tools", "deploy") for p in sorted((release / prefix).rglob("*"))
              if p.is_file()}
    (release / "release-manifest.json").write_text(json.dumps(dict(plan, files_sha256=hashes), indent=2) + "\n")
    (release / ".incomplete").unlink()
    # Root owns all files; service receives read/execute access only.
    for current, directories, files in os.walk(release):
        Path(current).chmod(0o755)
        for name in files:
            p = Path(current) / name
            if not p.is_symlink():
                p.chmod(0o755 if p.stat().st_mode & 0o111 else 0o644)
    return plan


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--python-root", type=Path, required=True)
    parser.add_argument("--uv", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    print(json.dumps(stage(args.source, args.revision, args.python_root, args.uv, execute=args.execute)))
