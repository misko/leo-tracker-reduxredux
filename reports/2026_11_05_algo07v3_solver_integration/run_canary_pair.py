"""Bounded sequential pre-optimization/integrated comparisons on native canaries.

External qualification, not a production worker. This expands scientific
coverage; one pair does not establish dataset or cumulative speed qualification.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "request", "bundle", "baseline-sources", "integration-check"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    check = json.loads(args.integration_check.read_bytes())
    assert check["exact_owned_science_and_artifacts"] and check["both_c_arms"]
    root = args.root.resolve()
    root.mkdir(exist_ok=False)
    request = json.loads(args.request.read_bytes())
    sources = args.baseline_sources.resolve()
    run_baseline = Path(__file__).with_name("run_baseline.sh").resolve()
    changed = ["hierarchical", "position", "discovery_likelihood"]
    commands = {}
    for side in ("baseline", "candidate"):
        attempt = root / side
        attempt.mkdir()
        output_request = root / f"{side}-request.json"
        write(output_request, dict(request, output_root=str(root / f"{side}-publication")))
        common = [str(args.bundle.resolve()), str(attempt), sys.executable, str(output_request)]
        commands[side] = (
            ["sh", str(run_baseline), str(sources), *common, "1200", "0,1,2"]
            if side == "baseline" else
            ["taskset", "-c", "0,1,2", "sh", "tools/qualify_algo07v3_cli.sh",
             *common, "run", "1200"]
        )
    paths = [Path(__file__), run_baseline, args.integration_check,
             args.bundle / "input-bindings.json", Path("tools/compare_algo07v3_runs.py"),
             Path("tools/qualify_algo07v3_cli.sh")]
    paths += [sources / f"baseline-{n}.py" for n in changed]
    paths += [Path("src/leo/analysis/localization_v3") / f"{n}.py" for n in changed]
    paths += [root / f"{side}-request.json" for side in commands]
    write(root / "plan.json", dict(
        sequence=list(commands), commands=commands,
        bindings={str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        changed_modules=["leo.analysis.localization_v3." + n for n in changed],
        cpus=[0, 1, 2], blas_threads=1, per_run_timeout_seconds=1200,
        dataset_wide_qualification=False, production_modified=False,
    ))
    for side, command in commands.items():
        write(root / f"{side}-resources-start.json", dict(
            load=os.getloadavg(), cpu_pressure=Path("/proc/pressure/cpu").read_text()))
        with (root / f"{side}.log").open("xb") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        write(root / f"{side}-resources-end.json", dict(
            load=os.getloadavg(), cpu_pressure=Path("/proc/pressure/cpu").read_text()))
    command = [sys.executable, "-B", "tools/compare_algo07v3_runs.py"]
    for side in commands:
        command += [f"--{side}-request", str(root / f"{side}-request.json"),
                    f"--{side}-timing", str(root / side / "attempt/supervisor.json")]
    for name in changed:
        command += ["--changed-module", "leo.analysis.localization_v3." + name]
    command += ["--output", str(root / "comparison.json")]
    with (root / "comparison.log").open("xb") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    print((root / "comparison.json").read_text(), flush=True)


if __name__ == "__main__":
    main()
