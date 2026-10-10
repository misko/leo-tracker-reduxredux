"""Receipt-only summaries; evaluation callbacks forbidden before both branches seal."""

import hashlib
import json
from pathlib import Path

BRANCHES = ("native", "fixed")
ARMS = ("zero-c", "fitted-c")
TERMINAL = {"complete", "failed", "budget-exhausted"}


def load_records(directory, protocol_digest):
    records, hashes = {}, {}
    for branch in BRANCHES:
        path = Path(directory) / branch / "result.json"
        if not path.exists():
            records[branch] = dict(status="missing")
            continue
        data = path.read_bytes()
        hashes[str(path)] = hashlib.sha256(data).hexdigest()
        row = json.loads(data)
        if row.get("protocol_sha256") != protocol_digest or row.get("branch") != branch:
            raise ValueError("foreign branch result")
        if row.get("status") not in TERMINAL or row.get("fallback_available") is not False:
            raise ValueError("invalid terminal/fallback contract")
        records[branch] = row
    return records, hashes


def region_summary(name, region):
    receipt = region.get("recovery", {})
    calibration = receipt.get("result") or {}
    finals = region.get("finals", [])
    return dict(
        name=name,
        calibration_status=calibration.get("status", "unavailable"),
        calibration_available=calibration.get("calibration") is not None,
        failure_reason=receipt.get("reason") or calibration.get("error"),
        association_available=bool((region.get("association") or {}).get("result")),
        finals={
            arm: dict(
                attempts=sum(r.get("arm") == arm for r in finals),
                qualified=sum(
                    r.get("arm") == arm and bool((r.get("fit") or {}).get("converged"))
                    for r in finals
                ),
            )
            for arm in ARMS
        },
    )


def summarize(records, *, evaluate=None):
    sealed = all(records.get(branch, {}).get("status") in TERMINAL for branch in BRANCHES)
    if evaluate is not None and not sealed:
        raise ValueError("reference evaluation requires both sealed terminal branches")
    result = dict(
        both_terminal=sealed,
        scope="single consumed conditional research comparison",
        comparison_complete=all(records.get(b, {}).get("status") == "complete" for b in BRANCHES),
        branches={},
    )
    for branch in BRANCHES:
        receipt = records.get(branch, dict(status="missing"))
        row = dict(
            status=receipt["status"],
            reason=receipt.get("reason"),
            elapsed_last_slice_s=receipt.get("elapsed_s"),
            regions=[
                region_summary(name, region) for name, region in receipt.get("regions", {}).items()
            ],
            arms={},
        )
        for arm in ARMS:
            operation = receipt.get("operational", {}).get(arm)
            if not operation:
                row["arms"][arm] = dict(status="no-selected-endpoint")
                continue
            fit = operation["fit"]
            item = dict(
                status="selected",
                qualified=bool(fit.get("converged")),
                frequency={
                    key: fit.get(key) for key in ("objective", "posterior_rms_hz", "signal_windows")
                },
                qualification={
                    key: fit.get(key) for key in ("stationarity", "stop_reason", "evaluations")
                },
                selection={
                    key: operation.get(key)
                    for key in ("region_source", "basin", "start", "accepted_stage")
                },
            )
            if evaluate is not None:
                item["position_evaluation"] = evaluate(branch, arm, operation)
            row["arms"][arm] = item
        result["branches"][branch] = row
    result["interpretation"] = (
        "Raw objectives across discovery policies or model banks are descriptive only; "
        "lower frequency likelihood does not establish position improvement. "
        "Final c arms share fitted-led discovery/support within each branch. "
        "Last-slice elapsed time is not total branch runtime. No fallback is imputed."
    )
    return result


def slice_summary(directory, protocol_digest):
    result = {}
    for branch in BRANCHES:
        folder = Path(directory) / branch / "slices"
        started = list(folder.glob("*.started.json"))
        done = list(folder.glob("*.done.json"))
        rows = [json.loads(path.read_text()) for path in done]
        if any(
            row.get("protocol_sha256") != protocol_digest or row.get("branch") != branch
            for row in rows
        ):
            raise ValueError("foreign slice receipt")
        result[branch] = dict(
            claimed=len(started),
            completed=len(done),
            known_elapsed_s=sum(row["elapsed_s"] for row in rows),
            unfinished_claims=len(started) - len(done),
            statuses=[row["status"] for row in rows],
        )
    return result
