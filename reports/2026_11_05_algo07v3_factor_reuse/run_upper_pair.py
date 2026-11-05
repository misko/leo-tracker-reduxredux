"""Fresh reverse-order complete-path measurement of the exact upper-root probe.

Run from the repository root as root, with src:tools on PYTHONPATH. Kernels are
mounted only inside private namespaces. No runtime or production files change.
"""

import argparse
import hashlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from probe_algo07v3_factor_reuse import solve_factor
from probe_algo07v3_upper_root import candidate_function

from leo.analysis.localization_v3 import hierarchical


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--probe-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    probe = json.loads((args.probe_root / "probe.json").read_bytes())
    driver = json.loads((args.probe_root / "probe.driver.json").read_bytes())
    assert probe["complete"] and probe["exact"] and not probe["failures"]
    assert probe["calls"] == 6772
    for path, sha in driver["files"].items():
        assert digest(path) == sha
    _, original, candidate = candidate_function()
    assert hashlib.sha256(original.encode()).hexdigest() == probe["reference_sha256"]
    assert hashlib.sha256(candidate.encode()).hexdigest() == probe["candidate_sha256"]
    source = Path(hierarchical.__file__).read_text()
    assert source.count(original) == 1
    changed = source.replace(original, candidate)
    changed += "\n\nfrom scipy.linalg.lapack import dgetrf, dgetrs\n\n"
    changed += inspect.getsource(solve_factor)
    root.mkdir(exist_ok=False)
    kernels = dict(baseline=source, candidate=changed)
    request = json.loads(args.request.read_bytes())
    for arm in kernels:
        (root / f"{arm}-kernel.py").write_text(kernels[arm])
        write(root / f"{arm}-request.json", dict(request, output_root=str(root / f"{arm}-publication")))
    runner = Path("reports/2026_11_05_algo07v3_factor_reuse/run_kernel.sh")
    comparator = Path("tools/compare_algo07v3_runs.py")
    sequence = ["candidate", "baseline"]
    paths = [Path(__file__), runner, comparator, Path(hierarchical.__file__),
             args.probe_root / "probe.json", args.probe_root / "probe.driver.json"]
    paths += [root / f"{arm}-{kind}" for arm in kernels for kind in ("kernel.py", "request.json")]
    write(root / "plan.json", dict(
        sequence=sequence, cpus=[0, 1, 2], blas_threads=1, timeout_s=1200,
        bindings={str(p.resolve()): digest(p) for p in paths},
        scope="native GLRT ready through scientific storage and atomic publication",
        production_modified=False, enabled_in_runtime=False,
        base_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    ))

    def observe(arm, event, pid=None):
        value = dict(arm=arm, event=event, utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                     load=os.getloadavg(), cpu_pressure=Path("/proc/pressure/cpu").read_text(), pid=pid)
        with (root / "resources.jsonl").open("a") as stream:
            stream.write(json.dumps(value) + "\n")

    for arm in sequence:
        output = root / arm
        output.mkdir()
        observe(arm, "start")
        with (root / f"{arm}.log").open("xb") as log:
            process = subprocess.Popen([
                "sh", str(runner), str(root / f"{arm}-kernel.py"),
                str(Path(request["native_input"]["path"]).parent), str(output),
                sys.executable, str(root / f"{arm}-request.json"), "1200", "0,1,2",
            ], stdout=log, stderr=subprocess.STDOUT)
            while process.poll() is None:
                observe(arm, "running", process.pid)
                time.sleep(5)
            observe(arm, "end", process.pid)
            if process.returncode:
                raise SystemExit(f"{arm} failed with status {process.returncode}; retained evidence at {root}")
    command = [sys.executable, "-B", str(comparator)]
    for arm in ("baseline", "candidate"):
        command += [f"--{arm}-request", str(root / f"{arm}-request.json"),
                    f"--{arm}-timing", str(root / arm / "attempt/supervisor.json")]
    command += ["--output", str(root / "comparison.json")]
    with (root / "comparison.log").open("xb") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True,
                       env=dict(os.environ, OPENBLAS_NUM_THREADS="1"))
    print((root / "comparison.json").read_text(), flush=True)


if __name__ == "__main__":
    main()
