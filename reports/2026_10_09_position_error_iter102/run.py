"""Two independent direct qualification attempts; no downstream position fit."""

import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

from qualification import qualify

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PREFIT = HERE.parent / "2026_10_09_position_error_iter93"
sys.path.insert(0, str(PREFIT))
import replay_prefit  # noqa: E402

SPEC = importlib.util.spec_from_file_location(
    "postfit97_for102", HERE.parent / "2026_10_09_position_error_iter97/run.py"
)
postfit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(postfit)


def main():
    protocol = HERE / "protocol.json"
    plan = json.loads(protocol.read_text())
    assert plan["maximum_attempts"] == 2
    assert plan["maximum_rounds"] == 2 and plan["maximum_evaluations_per_attempt"] == 100
    for name, digest in plan["source_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    assert not (HERE / "result.json").exists()
    receipt = dict(
        protocol_sha256=hashlib.sha256(protocol.read_bytes()).hexdigest(),
        session_id=plan["session_id"],
        attempts={},
    )
    for stage in ("calibration-prefit", "calibration-postfit"):
        begun = time.monotonic()
        try:
            if stage == "calibration-prefit":
                document = json.loads((PREFIT / "published-v3.json").read_text())["manifest"][
                    "document"
                ]
                checkpoint = json.loads((PREFIT / "verified-checkpoints.json").read_text())
                objective, seed, verification = replay_prefit.reconstruct(document, checkpoint)
                saved = verification["original_objective"]
            else:
                objective, seed, verification = postfit.reconstruct()
                saved = verification["saved_postfit_objective"]
            reconstruction_elapsed = time.monotonic() - begun
            attempt = qualify(
                objective,
                seed,
                saved,
                retained=True,
                stage=stage,
                independently_qualified=False,
                maximum_rounds=2,
                maximum_evaluations=100,
            )
            attempt["input_verification"] = verification
            attempt["reconstruction_elapsed_s"] = reconstruction_elapsed
        except Exception as error:
            attempt = dict(
                status="reconstruction-failed",
                qualified=False,
                error=repr(error),
                reconstruction_elapsed_s=time.monotonic() - begun,
            )
        receipt["attempts"][stage] = attempt
        replay_prefit.write(
            HERE / f"{stage}.json", dict(protocol_sha256=receipt["protocol_sha256"], **attempt)
        )
    receipt["status"] = "complete"
    replay_prefit.write(HERE / "result.json", receipt)
    print({stage: row["status"] for stage, row in receipt["attempts"].items()}, flush=True)


if __name__ == "__main__":
    main()
