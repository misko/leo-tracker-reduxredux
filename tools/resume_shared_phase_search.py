"""Replay an interrupted shared-phase search with verified cached scores."""

import argparse
import hashlib
import json
from pathlib import Path

import evaluate_shared_satellite_phase as experiment
from associate_merged_track_catalogue import write
from resume_merged_track_search import evaluate_frozen, replay_objective


def run(previous, recording, inputs, output):
    protocol_path, progress_path = previous / "protocol.json", previous / "progress.json"
    protocol = json.loads(protocol_path.read_text())
    if (previous / "fit.json").exists():
        raise ValueError("previous search already completed")
    for name, expected in protocol["source_sha256"].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected:
            raise ValueError("scientific source changed; cached objectives cannot be reused")
    receipt = json.loads((inputs / "receipt.json").read_text())
    if receipt != protocol["bank_receipt"]:
        raise ValueError("causal phase bank receipt changed")
    study = experiment.Experiment(
        recording, inputs, fitted_c=protocol["fitted_c"], phase_enabled=protocol["phase_enabled"]
    )
    experiment.protocol(study, output, "resume", protocol["final_generated_seed_budget"])
    progress = json.loads(progress_path.read_text())
    original = experiment.regional_search

    def replay(objective, **kwargs):
        return original(replay_objective(objective, progress), **kwargs)

    experiment.regional_search = replay
    try:
        result = experiment.search(study, output, protocol["final_generated_seed_budget"])
    finally:
        experiment.regional_search = original
    write(
        output / "resume-receipt.json",
        dict(
            previous=str(previous),
            previous_protocol_sha256=hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
            previous_progress_sha256=hashlib.sha256(progress_path.read_bytes()).hexdigest(),
            cached_discovery_evaluations=sum(not r["final"] for r in progress),
            original_search_path_and_budget_unchanged=True,
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        ),
    )
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--previous", type=Path, required=True)
    p.add_argument("--recording", type=Path, required=True)
    p.add_argument("--inputs", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--reference-latitude", type=float, required=True)
    p.add_argument("--reference-longitude", type=float, required=True)
    a = p.parse_args()
    q = Path("/mnt/qnap01")
    if a.output.resolve() == q or q in a.output.resolve().parents:
        p.error("QNAP is read-only")
    run(a.previous, a.recording, a.inputs, a.output)
    evaluation = evaluate_frozen(a.output, (a.reference_latitude, a.reference_longitude))
    print(json.dumps(evaluation), flush=True)
