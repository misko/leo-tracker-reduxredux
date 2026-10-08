"""Stage the reviewed Hard60 delta over the effective immutable analysis overlays.

No service selectors are changed. Run with the production Python interpreter.
Usage: stage_overlay.py REPOSITORY BASE_SHA DESTINATION WORKER_SOURCE API_SOURCE
"""

import hashlib
import json
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def main(repository, base, destination, worker_source, api_source):
    repository, destination = Path(repository), Path(destination)

    def git(*args):
        return subprocess.check_output(["git", "-C", str(repository), *args], text=True).strip()

    revision = git("rev-parse", "HEAD")
    if git("status", "--porcelain"):
        raise ValueError("stage requires a clean reviewed checkout")
    if destination.exists():
        raise ValueError("immutable stage already exists")
    changes = git("diff", "--name-only", base, revision, "--", "src").splitlines()
    receipt = {"revision": revision, "base": base, "roles": {}}
    for role, source in (("worker", Path(worker_source)), ("api", Path(api_source))):
        target = destination / role / "src"
        files = [
            name
            for name in changes
            if not ((role == "worker" and "/api/" in name) or (role == "api" and "/cli/" in name))
        ]
        # Check inherited implementations before creating the stage.
        for name in files:
            inherited = source / name.removeprefix("src/")
            if inherited.exists():
                original = subprocess.check_output(
                    ["git", "-C", str(repository), "show", f"{base}:{name}"]
                )
                if inherited.read_bytes() != original:
                    raise ValueError(f"unreviewed inherited difference: {role}:{name}")
        shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))
        for name in files:
            output = target / name.removeprefix("src/")
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(repository / name, output)
        # Build the one new extension for this interpreter; never build inside a worker.
        import numpy

        extension = (
            target / "leo/analysis" / ("_regional_orbits" + sysconfig.get_config_var("EXT_SUFFIX"))
        )
        subprocess.run(
            [
                "g++",
                "-shared",
                "-fPIC",
                "-O3",
                "-fno-fast-math",
                "-ffp-contract=off",
                "-I" + sysconfig.get_path("include"),
                "-I" + numpy.get_include(),
                str(target / "leo/analysis/_regional_orbits.cpp"),
                "-o",
                str(extension),
            ],
            check=True,
        )
        receipt["roles"][role] = {
            "inherited": str(source),
            "replacements": files,
            "files": {
                str(p.relative_to(target)): digest(p)
                for p in sorted(target.rglob("*"))
                if p.is_file()
            },
        }
    shutil.copytree(repository / "web/dist", destination / "web/dist")
    receipt["web"] = {
        str(p.relative_to(destination)): digest(p)
        for p in sorted((destination / "web/dist").rglob("*"))
        if p.is_file()
    }
    (destination / "stage.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"revision": revision, "destination": str(destination)}))


if __name__ == "__main__":
    main(*sys.argv[1:])
