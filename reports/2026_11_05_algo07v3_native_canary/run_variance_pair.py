"""Compare the bounded variance prototype through isolated native publication.

External experiment: kernels are mounted inside private namespaces. Production
and runtime source remain unchanged. Run from the repository root as root.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from probe_algo07v3_variance_groups import candidate_function

from leo.analysis.localization_v3 import hierarchical


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "request", "probe-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    probe_path = args.probe_root / "probe.json"
    probe = json.loads(probe_path.read_bytes())
    assert probe["complete"] and probe["exact"] and not probe["failures"]
    assert probe["calls"] == 6772
    _, original, candidate = candidate_function()
    assert hashlib.sha256(original.encode()).hexdigest() == probe["reference_sha256"]
    assert hashlib.sha256(candidate.encode()).hexdigest() == probe["candidate_sha256"]
    probe_tool = Path("tools/probe_algo07v3_variance_groups.py")
    assert digest(probe_tool) == probe["tool_sha256"]
    source = Path(hierarchical.__file__).read_text()
    assert source.count(original) == 1
    root = args.root.resolve()
    root.mkdir(exist_ok=False)
    request = json.loads(args.request.read_bytes())
    runner = Path("reports/2026_11_05_algo07v3_factor_reuse/run_kernel.sh")
    comparator = Path("tools/compare_algo07v3_runs.py")
    paths = [Path(__file__), probe_path, probe_tool, runner, comparator,
             Path("tools/qualify_algo07v3_cli.sh"), Path(hierarchical.__file__)]
    commands = {}
    # Reverse the previous solver pair's order to avoid always timing baseline first.
    for arm, kernel in (("candidate", source.replace(original, candidate)), ("baseline", source)):
        (root / f"{arm}-kernel.py").write_text(kernel)
        write(root / f"{arm}-request.json",
              dict(request, output_root=str(root / f"{arm}-publication")))
        (root / arm).mkdir()
        commands[arm] = [
            "sh", str(runner), str(root / f"{arm}-kernel.py"),
            str(Path(request["native_input"]["path"]).parent), str(root / arm),
            sys.executable, str(root / f"{arm}-request.json"), "1200", "0,1,2",
        ]
        paths += [root / f"{arm}-kernel.py", root / f"{arm}-request.json"]
    write(root / "plan.json", dict(
        commands=commands, sequence=list(commands), cpus=[0, 1, 2], blas_threads=1,
        timeout_seconds=1200, bindings={str(p.resolve()): digest(p) for p in paths},
        production_modified=False, enabled_in_runtime=False, qualified_speedup=None,
        base_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    ))
    for arm, command in commands.items():
        write(root / f"{arm}-resources-start.json", dict(
            load=os.getloadavg(), cpu_pressure=Path("/proc/pressure/cpu").read_text()))
        with (root / f"{arm}.log").open("xb") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        write(root / f"{arm}-resources-end.json", dict(
            load=os.getloadavg(), cpu_pressure=Path("/proc/pressure/cpu").read_text()))
    for path, sha in json.loads((root / "plan.json").read_bytes())["bindings"].items():
        assert digest(path) == sha, path
    command = [sys.executable, "-B", str(comparator)]
    for arm in ("baseline", "candidate"):
        command += [f"--{arm}-request", str(root / f"{arm}-request.json"),
                    f"--{arm}-timing", str(root / arm / "attempt/supervisor.json")]
    command += ["--output", str(root / "comparison.json")]
    with (root / "comparison.log").open("xb") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    print((root / "comparison.json").read_text(), flush=True)


if __name__ == "__main__":
    main()
