"""Frozen bounded scan trials, with no reference labels supplied to the tracker."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "2026_09_30_arm_fast_tracks/server-baseline/output"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    plan = json.loads((HERE / "experiment.json").read_text())
    for label in ("server", "arm"):
        if sha(BASE / f"{label}-observations.tsv") != plan["inputs"][f"{label}_observations_sha256"]:
            raise ValueError("input changed after experiment freeze")
    rows = []
    for acceleration in (250, 0, 125, 500):
        for label in ("server", "arm"):
            name = f"{label}-a{acceleration}"
            output = args.output / f"{name}.tsv"
            started = time.perf_counter()
            with output.open("w") as stream:
                result = subprocess.run([str(args.binary.resolve()), str(BASE / f"{label}-observations.tsv"),
                                         "--acceleration", str(acceleration)], stdout=stream,
                                        stderr=subprocess.PIPE, text=True, timeout=60)
            whole = time.perf_counter()-started
            (args.output / f"{name}.stderr").write_text(result.stderr)
            if result.returncode:
                raise RuntimeError(f"{name} failed: {result.stderr}")
            reconstruction = next(float(line.split("\t")[2]) for line in result.stderr.splitlines()
                                  if line.startswith("TIMING\treconstruct_s\t"))
            command = [sys.executable, str(HERE / "evaluation/compare_membership.py"),
                       "--reference-observations", str(BASE / "server-observations.tsv"),
                       "--reference-tracks", str(BASE / "server-tracks.tsv"),
                       "--reference-source-map", str(BASE / "server-candidate-map.tsv"),
                       "--output-observations", str(BASE / f"{label}-observations.tsv"),
                       "--output-tracks", str(output),
                       "--output-source-map", str(BASE / f"{label}-candidate-map.tsv"),
                       "--report", str(args.output / f"{name}.comparison.json")]
            subprocess.run(command, check=True, timeout=60)
            comparison = json.loads((args.output / f"{name}.comparison.json").read_text())
            row = {"case":name, "reconstruct_s":reconstruction,"whole_process_s":whole,
                   "tracks":comparison["output"]["tracks"],
                   "complete_one_to_one":comparison["primary"]["complete_one_to_one_count"],
                   "input_limited_references":len(comparison["primary"]["input_unsupported_reference_indexes"]),
                   "supported_misses":len(comparison["primary"]["supported_unmatched_reference_indexes"]),
                   "unmatched_output_tracks":len(comparison["primary"]["unmatched_output_indexes"]),
                   "output_sha256":sha(output)}
            rows.append(row)
            receipt = {"status":"executed", "binary_sha256":sha(args.binary),
                       "experiment_sha256":sha(HERE / "experiment.json"), "cases":rows}
            (args.output / "summary.json").write_text(json.dumps(receipt,indent=2)+"\n")
            print(json.dumps(row),flush=True)


if __name__ == "__main__":
    main()
