"""Repeat an exact variance pair in reverse order with whole-process CPU accounting."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-pair", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    previous, root = args.source_pair.resolve(), args.root.resolve()
    comparison = read(previous / "comparison.json")
    assert comparison["exact_owned_science_and_artifacts"] and comparison["both_c_arms"]
    assert comparison["source_changes"] == ["leo.analysis.localization_v3.hierarchical"]
    bindings = dict(read(previous / "plan.json")["bindings"], **comparison["input_bindings"])
    for name, sha in bindings.items():
        assert digest(name) == sha, name
    assert Path("/usr/bin/time").is_file()
    root.mkdir(exist_ok=False)
    runner = Path("reports/2026_11_05_algo07v3_factor_reuse/run_kernel.sh").resolve()
    comparator = Path("tools/compare_algo07v3_runs.py").resolve()
    commands = {}
    for arm in ("baseline", "candidate"):
        request = read(previous / f"{arm}-request.json")
        output_request = root / f"{arm}-request.json"
        write(output_request, dict(request, output_root=str(root / f"{arm}-publication")))
        bindings[str(output_request)] = digest(output_request)
        (root / arm).mkdir()
        commands[arm] = [
            "/usr/bin/time", "-v", "-o", str(root / f"{arm}-process-time.txt"),
            "sh", str(runner), str(previous / f"{arm}-kernel.py"),
            str(Path(request["native_input"]["path"]).parent), str(root / arm),
            sys.executable, str(output_request), "1200", "0,1,2",
        ]
    bindings[str(Path(__file__).resolve())] = digest(__file__)
    write(root / "plan.json", dict(commands=commands, sequence=list(commands), bindings=bindings,
                                  source_pair=str(previous), cpus=[0, 1, 2], blas_threads=1,
                                  timeout_seconds=1200, cpu_accounting="GNU time -v",
                                  production_modified=False, qualified_speedup=None))
    for arm, command in commands.items():
        write(root / f"{arm}-resources-start.json", dict(
            load=os.getloadavg(), cpu_pressure=Path("/proc/pressure/cpu").read_text()))
        with (root / f"{arm}.log").open("xb") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        write(root / f"{arm}-resources-end.json", dict(
            load=os.getloadavg(), cpu_pressure=Path("/proc/pressure/cpu").read_text()))
    for name, sha in bindings.items():
        assert digest(name) == sha, name
    command = [sys.executable, "-B", str(comparator)]
    for arm in commands:
        command += [f"--{arm}-request", str(root / f"{arm}-request.json"),
                    f"--{arm}-timing", str(root / arm / "attempt/supervisor.json")]
    command += ["--output", str(root / "comparison.json")]
    with (root / "comparison.log").open("xb") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    print((root / "comparison.json").read_text(), flush=True)


if __name__ == "__main__":
    main()
