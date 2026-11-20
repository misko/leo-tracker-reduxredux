"""Seal finished attempts after the supervisor loses a terminal service receipt."""

import argparse
import gzip
from pathlib import Path
from unittest.mock import patch

from .. import iq_service, whole_iq
from ..__main__ import encoded, local_output, save_json, write
from ..scoring import validate_result
from . import sequential_fix_trial as trial
from . import short_compact
from .full_v5_check import _sha


def restore(folder, spec, job, checkpoint):
    request = whole_iq.read(folder / "request.json")
    source = request["compact"]
    whole_iq.checked(Path(source["native"]), spec["native_sha256"])
    if checkpoint != "full" or source["native_sha256"] != spec["native_sha256"]:
        raise ValueError("recovery is limited to the original complete native file")
    with patch.object(iq_service, "MODULE", trial.MODULE):
        service = iq_service.reconcile(folder)
    if service["systemd"]["Result"] != "timeout" or (folder / "worker-result.json").exists():
        raise ValueError("expected a terminal timeout with no compact endpoint")
    result = short_compact.no_fix("timed_out", "capped compact worker service result timeout")
    row = dict(
        **job,
        checkpoint=checkpoint,
        tile=spec["tile"],
        support=request["support"],
        result=result,
        recorded_native_sha256=spec["native_sha256"],
        input_native_sha256=source["native_sha256"],
        catalog_sha256=spec["catalog_sha256"],
        track_config_sha256=spec["config_sha256"],
        original_request_sha256=spec["original_request_sha256"],
        input_preparation_wall_s=None,
        service=service,
        resources={},
    )
    save_json(folder / "prediction.json", row)
    return row


def recover(base, report):
    plan = trial.verified_plan(base, report)
    if (report / "prediction-lock.json").exists():
        raise FileExistsError("cumulative predictions are already sealed")
    rows, decisions, recovered = [], [], []
    for job in plan["assignment"]:
        spec = plan["cases"][job["id"]]
        this_offer = []
        for checkpoint in trial.CHECKPOINTS:
            folder = base / job["id"] / job["offer"] / str(checkpoint)
            path = folder / "prediction.json"
            if not path.exists():
                if (job["id"], job["offer"], checkpoint) != ("DS29-0519", "original", "full"):
                    raise ValueError(
                        "the registered supervisor recovery is missing another attempt"
                    )
                row = restore(folder, spec, job, checkpoint)
                recovered.append(
                    dict(job, checkpoint=checkpoint, log_sha256=row["service"]["log_sha256"])
                )
            else:
                row = whole_iq.read(path)
            validate_result(row["result"])
            if any(row[k] != v for k, v in job.items()) or row["checkpoint"] != checkpoint:
                raise ValueError("receipt belongs to a different planned request")
            if (
                row["recorded_native_sha256"] != spec["native_sha256"]
                or row["catalog_sha256"] != spec["catalog_sha256"]
            ):
                raise ValueError("receipt has a different capture or catalogue")
            source = whole_iq.read(folder / "request.json")["compact"]
            whole_iq.checked(Path(source["native"]), row["input_native_sha256"])
            whole_iq.checked(folder / "service.log", row["service"]["log_sha256"])
            this_offer.append(row)
        sky = {
            r["result"]["metrics"].get("causal_audit", {}).get("selected_tle_sha256")
            for r in this_offer
        }
        if len(sky - {None}) > 1:
            raise ValueError("the candidate catalogue changed with prefix length")
        rows.extend(this_offer)
        decisions.append(
            dict(id=job["id"], offer=job["offer"], **trial.policy.release(*this_offer[:2]))
        )
    save_json(
        report / "supervisor-recovery.json",
        dict(
            recovered=recovered,
            source_sha256=_sha(Path(__file__)),
            reason=(
                "Systemd had stopped the worker after its cap, but the log lock remained busy "
                "during receipt collection."
            ),
            effect=(
                "Recovered the original systemd timeout and resource receipt. The supervisor "
                "did not persist separate input preparation wall for this attempt."
            ),
        ),
    )
    write(
        report / "checkpoint-predictions.jsonl.gz",
        gzip.compress(
            b"".join(encoded(r) + b"\n" for r in rows),
            mtime=0,
        ),
    )
    save_json(report / "release-decisions.json", decisions)
    files = (
        "checkpoint-predictions.jsonl.gz",
        "release-decisions.json",
        "source-lock.json",
        "supervisor-recovery.json",
    )
    save_json(
        report / "prediction-lock.json",
        dict(rows=len(rows), files={f: _sha(report / f) for f in files}),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=local_output)
    parser.add_argument("--report", type=local_output, default=trial.REPORT)
    args = parser.parse_args()
    recover(args.base, args.report)
