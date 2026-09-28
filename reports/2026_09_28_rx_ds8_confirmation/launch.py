"""Run bounded DS8 confirmation stages with immutable input receipts."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PRIOR = ROOT / "reports/2026_09_28_rx_causal_refit"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    stage = sys.argv[1]
    evidence = PRIOR / "evidence-sha256.json"
    for name, expected in json.loads(evidence.read_text()).items():
        if digest(ROOT / name) != expected:
            raise ValueError(f"Prior evidence changed: {name}")
    # Verify the scientific dependencies recorded by the previous completed stages.
    for name in ("reports/2026_09_28_rx_causal_geometry/launch.json",
                 "reports/2026_09_28_rx_temporal_transfer/launch.json"):
        for source, expected in json.loads((ROOT / name).read_text())["sha256"].items():
            if digest(ROOT / source) != expected:
                raise ValueError(f"Scientific dependency changed: {source}")
    readiness = PRIOR / "ds8-readiness.json"
    training = ROOT / "reports/2026_09_28_rx_geometry_association/dataset.json"
    prepared = HERE / "prepared"
    inventory, manifest = prepared / "inventory.json", prepared / "manifest.json"
    opportunities = HERE / "opportunities/opportunities.jsonl"
    partitions, bank = HERE / "partitions.json", HERE / "candidate-bank.json"
    mapping, dataset = HERE / "alias-mapping.json", HERE / "dataset.json"
    if stage == "models":
        module, limit = "rx_causal_full_calibration", 180
        args = ["--dataset", str(training), "--output", str(HERE / "models.json")]
        inputs = [training]
    elif stage == "cache":
        module, limit = "rx_ds8_confirmation_cache", 120
        args = ["--readiness", str(readiness), "--output-dir", str(prepared)]
        inputs = [readiness]
    elif stage == "opportunities":
        module, limit = "rx_paired_opportunities", 180
        args = ["--inventory", str(inventory), "--output-dir", str(opportunities.parent)]
        inputs = [inventory]
    elif stage == "partitions":
        module, limit = "rx_grouped_partitions", 180
        args = ["--opportunities", str(opportunities), "--output", str(partitions),
                "--evaluation-only"]
        inputs = [opportunities]
    elif stage == "bank":
        module, limit = "rx_training_candidate_bank", 180
        args = ["--inventory", str(inventory), "--manifest", str(manifest),
                "--partitions", str(partitions), "--snapshot-authority",
                str(HERE / "snapshot-authority.json"), "--output", str(bank)]
        inputs = [inventory, manifest, partitions, HERE / "snapshot-authority.json"]
    elif stage == "mapping":
        module, limit = "rx_training_alias_mapping", 180
        args = ["--inventory", str(inventory), "--partitions", str(partitions),
                "--candidate-bank", str(bank), "--protocol", str(HERE / "PROTOCOL.md"),
                "--protocol-sha256", "sha256:" + digest(HERE / "PROTOCOL.md"),
                "--output", str(mapping)]
        inputs = [inventory, partitions, bank]
    elif stage == "dataset":
        module, limit = "rx_geometry_dataset", 180
        args = ["--bank", str(bank), "--mapping", str(mapping), "--partitions", str(partitions),
                "--opportunities", str(opportunities), "--output", str(dataset)]
        inputs = [bank, mapping, partitions, opportunities]
    elif stage == "score":
        module, limit = "rx_ds8_geometry_score", 180
        args = ["--model", str(HERE / "models.json"), "--training-dataset", str(training),
                "--dataset", str(dataset), "--readiness", str(readiness),
                "--output", str(HERE / "results.json")]
        inputs = [HERE / "models.json", training, dataset, readiness]
    else:
        raise ValueError(f"Unknown stage: {stage}")
    code = [ROOT / f"tools/{module}.py"]
    test = ROOT / f"tests/research/test_{module}.py"
    if test.exists():
        code.append(test)
    bound = [Path(__file__), HERE / "PROTOCOL.md", evidence, *code, *inputs]
    command = ["sudo", "-n", "/usr/bin/time", "-v", "-o", str(HERE / f"{stage}-resources.txt"),
               "timeout", "--kill-after=5s", f"{limit}s", "prlimit", "--as=4294967296",
               "nice", "-n", "19", "env", "OPENBLAS_NUM_THREADS=1", "OMP_NUM_THREADS=1",
               "MKL_NUM_THREADS=1", "/opt/leo-tracker/current-api/.venv/bin/python", "-m",
               f"tools.{module}", *args]
    with (HERE / f"{stage}-launch.json").open("x") as stream:
        json.dump({"command": command, "cwd": str(ROOT),
                   "sha256": {str(p.relative_to(ROOT)): digest(p) for p in bound}},
                  stream, indent=2)
    with (HERE / f"{stage}-terminal.log").open("x") as stream:
        result = subprocess.run(command, cwd=ROOT, stdout=stream,
                                stderr=subprocess.STDOUT, check=False)
    (HERE / f"{stage}-exit-code.txt").write_text(str(result.returncode) + "\n")
    print(stage, "exit:", result.returncode)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
