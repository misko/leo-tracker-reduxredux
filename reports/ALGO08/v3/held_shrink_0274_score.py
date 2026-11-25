"""Verify a future ordinary saved replay against the authenticated raw 0274."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from held_shrink_0019_score import verify_publication  # noqa: E402
from held_shrink_0274 import BLOCK, EXPERIMENT, NATIVE, WITNESS, archived, trial  # noqa: E402
from sparse8_cfo_epoch_trial import scientific_grid  # noqa: E402


def reference():
    _, _, original, raw, witness = archived()
    receipt = raw["evidence"]["receipt"]
    offer = witness["evidence"]["detail"]["region"]
    terminal, evidence, numerical = verify_publication(original, receipt, WITNESS, "sha256:"+NATIVE, offer)
    if terminal["decision"] != "ok":
        raise ValueError("The original signed charted comparison must be complete")
    return original, terminal, evidence, numerical, witness["source_sha256"]


def require_parity(ordinary, raw):
    if ordinary != raw:
        raise ValueError("Ordinary saved science differs from the signed raw incumbent")


def check_control():
    trial.start_runtime().load_runtime()
    _, terminal, evidence, numerical, _ = reference()
    print(json.dumps(dict(arms=list(terminal["arms"]), owners={k:len(v) for k,v in evidence["owner_rows"].items()},
                          grid_points=numerical["grid_points"], pngs=len(evidence["images"]))))


def score(pin):
    root = BLOCK/"ordinary-capsule/output"
    seal = trial.document(root/"prediction-seal.json", pin)
    clock = trial.document(root/"clock.json", seal["clock"])
    plan = trial.document(root/"plan.json", seal["plan_sha256"])
    run = trial.document(root/"receipt.json", seal["receipt"])
    if (clock["exit_code"] or run["input"] != "sha256:"+NATIVE or run["handoffs"] != 1 or run["waveform_reads"]
            or plan["cell"] != "ordinary" or seal["protocol"] != trial.protocol(EXPERIMENT)):
        raise ValueError("Expected an exit-zero ordinary saved control on the exact original detector")
    trial.start_runtime().load_runtime()
    original, raw, raw_evidence, _, sources = reference()
    output = root/"substituted"
    terminal, evidence, verified = verify_publication(output, run["receipt"], run["witness"],
                                                     "sha256:"+NATIVE, raw["region"])
    witness = trial.document(output/"exact-named-raw-witness.json", run["witness"])
    require_parity(
        dict(terminal=terminal, sources=witness["source_sha256"], owners=evidence["owner_rows"],
             path=evidence["sidecars"]["path"], figures=evidence["images"], grid=scientific_grid(output)),
        dict(terminal=raw, sources=sources, owners=raw_evidence["owner_rows"],
             path=raw_evidence["sidecars"]["path"], figures=raw_evidence["images"], grid=scientific_grid(original)),
    )
    print(trial.write(root/"ordinary-parity.json", dict(input=run["input"], original_witness=WITNESS,
          saved_prediction_sha256=pin, exact_ordinary_reproduction=True, verified=verified)))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--score")
    args = cli.parse_args()
    score(args.score) if args.score else check_control()
