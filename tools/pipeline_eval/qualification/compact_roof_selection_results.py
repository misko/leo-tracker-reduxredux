"""Publish scheduled and observed compact complement outcomes with frozen originals."""

import argparse
import gzip
import json
import re
from collections import Counter
from pathlib import Path

from .. import corpus
from ..__main__ import encoded, local_output, read_predictions, save_json, write
from ..scoring import ARMS, ROLES, distance_km, distribution
from ..variants.v5_lean import SOURCE_SHA256
from . import compact_roof_selection as trial
from .full_v5_check import _sha
from .prefix_figures import csv_file
from .v5_postfit import ARCHIVE

PREDICTIONS = "positions.jsonl.gz"


def match_original_roles(ref, item):
    ident = ref["id"]
    directory = ARCHIVE / f"{ident}-r0"
    endpoints, bindings = {}, {}
    for role in ROLES:
        arms = ref["reference"].get(role, {})
        if set(arms) != set(ARMS):
            raise ValueError(f"{ident} archived {role} lacks its two calibration arms")
        endpoint_status = {row["status"] for row in arms.values()}
        path = directory / f"{role}-execution.json"
        result = trial.secant.phase._read(path)
        archive_status = "fix" if result["status"] == "complete" else result["status"]
        packet_path = directory / role / "experimental-request.json"
        packet_present = packet_path.is_file()
        packet = trial.secant.phase._read(packet_path) if packet_present else None
        request_sha = "sha256:" + corpus._sha(encoded(packet))
        if (
            result["role"] != role
            or endpoint_status != {archive_status}
            or result["request_sha256"] != request_sha
        ):
            raise ValueError(f"{ident} original {role} receipt disagrees with its frozen outcome")
        if packet is None:
            if item.get("unavailable") != "no_native_run" or archive_status != "missing":
                raise ValueError("a missing original request lacks frozen unavailable authority")
        else:
            job = packet["job"]
            latest = max(
                (int(name.split("-")[0]), checksum.removeprefix("sha256:"))
                for name, checksum in packet["causal_snapshots"].items()
                if int(name.split("-")[0]) < item["cutoff_utc_ns"]
            )
            if (
                packet["role"] != role
                or packet["source"]["sha256"] != SOURCE_SHA256
                or job["identity"]["session_id"] != item["session_id"]
                or job["evaluation_reference"] is not None
                or job["native_input"]["sha256"] != "sha256:" + item["native"]["sha256"]
                or job["search_center"] != item["regions"][0]["center"]
                or latest != (item["catalog_timestamp_ns"], item["catalog"]["sha256"])
            ):
                raise ValueError(f"{ident} original {role} uses different scientific inputs")
        if archive_status == "fix":
            worker = result["worker"]
            if (
                worker["request_sha256"] != request_sha
                or worker["source_sha256"] != SOURCE_SHA256
                or any(
                    (
                        gap := distance_km(
                            arms[arm]["latlon"], worker["arms"][arm]["endpoint_latlon"]
                        )
                    )
                    is None
                    or gap > 1e-6
                    for arm in ARMS
                )
            ):
                raise ValueError(
                    f"{ident} original {role} endpoints differ from the frozen outcome"
                )
        endpoints[role] = arms
        bindings[role] = dict(
            execution_sha256=_sha(path),
            request_sha256=request_sha,
            archive_status=result["status"],
            request_present=packet_present,
        )
    return endpoints, bindings


def unmeasured(binding, claimed):
    offered = binding["eligible"]
    if not offered:
        reason = binding["frozen_unavailable"] or binding["input_issues"].get(
            "request", "missing input authority"
        )
    elif claimed:
        reason = "queue claim has no completed numerical worker receipt"
    else:
        reason = "scheduled without an available full-budget worker slot"
    return dict(
        **{
            k: binding[k]
            for k in (
                "id",
                "input_sha256",
                "native_sha256",
                "catalog_sha256",
                "frozen_request_sha256",
                "tile",
            )
        },
        method=trial.METHOD,
        mode="matched-tile",
        attempted=None if claimed else False,
        worker_returned=False,
        worker_wall_s=None,
        source="unavailable_input"
        if not offered
        else "unconfirmed_claim"
        if claimed
        else "not_launched",
        result=dict(
            status="missing" if offered else "unavailable",
            reason=reason,
            boundary="Complete native factors through the original-budget compact secant v5 cavity",
            metrics=dict(position_attempted=False),
            arms={arm: dict(latlon=None) for arm in ARMS},
        ),
    )


def normalize_attempt(row):
    result = row["result"]
    reported = result["status"]
    reason = result.get("reason") or ""
    row["launcher_returned"] = row["worker_returned"]
    if reported == "unavailable":
        if reason.startswith("Frozen v5 inference exceeded"):
            result["status"] = "timed_out"
        elif reason.startswith("Frozen v5 worker exited") or re.match(
            r"^[A-Za-z][A-Za-z0-9]*(?:Error|Exception)(?:: |$)", reason
        ):
            result["status"] = "failed"
    if result["status"] != reported:
        row["reported_worker_status"] = reported
    row["worker_returned"] = row["launcher_returned"] and result["status"] in ("ok", "withheld")
    return row


def seal(work, output):
    plan = trial.secant.phase._read(work / "plan.json")
    published = trial.secant.phase._read(output / "roster.json")
    canonical, order, files = trial.roster()
    if (
        plan != published
        or plan["cases"] != canonical
        or plan["order"] != order
        or plan["frozen_panels_sha256"] != files["panels.json"]
        or plan["frozen_inputs_sha256"] != files["inputs.jsonl"]
        or plan["compact_sources"] != trial.secant.frozen_sources()
        or plan["cli_digest"] != trial.secant._cli_digest()
    ):
        raise ValueError("published inputs or unchanged five-round source failed its seal")
    rows, claims = [], {}
    for ident in canonical:
        binding = plan["bindings"][ident]
        outcome = work / "runs" / f"{ident}.json"
        launch = work / "claims" / f"{ident}.json"
        if launch.is_file():
            claims[ident] = trial.secant.phase._read(launch)
        if outcome.is_file():
            row = trial.secant.phase._read(outcome)
            trial.audit_result(row, plan)
            if (
                ident not in claims
                or not row["attempted"]
                or claims[ident]["cpu"] != row["cpu"]
                or row["deadline_s"] != trial.CAP
            ):
                raise ValueError(
                    "candidate receipt does not have its preregistered journal identity"
                )
            row = normalize_attempt(row)
        else:
            row = unmeasured(binding, ident in claims)
        rows.append(row)
    path = output / PREDICTIONS
    write(path, gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0))
    clock = trial.secant.phase._read(work / "clock.json")
    save_json(
        output / "run-receipt.json",
        dict(
            scheduled=len(canonical),
            eligible=sum(x["eligible"] for x in plan["bindings"].values()),
            claimed=len(claims),
            attempted=sum(r["attempted"] is True for r in rows),
            worker_returned=sum(r["worker_returned"] for r in rows),
            attempted_order=sorted(claims, key=lambda i: claims[i]["claimed_monotonic_s"]),
            cpus=sorted({x["cpu"] for x in claims.values()}),
            claims=claims,
            status_counts=dict(Counter(r["result"]["status"] for r in rows)),
            sources=dict(Counter(r["source"] for r in rows)),
            clock=clock,
        ),
    )
    save_json(
        output / "prediction-lock.json",
        dict(
            cases=canonical,
            files={
                name: _sha(output / name)
                for name in (PREDICTIONS, "roster.json", "run-receipt.json")
            },
        ),
    )


def score(output):
    lock = json.loads((output / "prediction-lock.json").read_bytes())
    if any(_sha(output / name) != hash for name, hash in lock["files"].items()):
        raise ValueError("compact outcome or roster changed after sealing")
    records = read_predictions(output / PREDICTIONS)
    refs = {row["id"]: row for row in corpus.references("ds26-all159") if row["id"] in records}
    if list(records) != lock["cases"] or records.keys() != refs.keys():
        raise ValueError("candidate or reference rows differ from the complement roster")
    _, _, files = trial.roster()
    items = corpus._index(corpus._read_frozen("inputs.jsonl", files))
    scored, original, original_bindings = [], {}, {}
    for ident, row in records.items():
        ref = refs[ident]
        original[ident], original_bindings[ident] = match_original_roles(ref, items[ident])
        for arm in ARMS:
            result = row["result"]
            point = result["arms"][arm]
            scored.append(
                dict(
                    id=ident,
                    arm=arm,
                    method=trial.METHOD,
                    scope=row["source"],
                    status=result["status"],
                    reason=result.get("reason"),
                    attempted=row["attempted"],
                    worker_returned=row["worker_returned"],
                    position_error_km=distance_km(point["latlon"], ref["truth"]),
                    conditional_rms_hz=point.get("rf_rms_hz"),
                    archived_publication_rms_hz=None,
                    archived_matched_rms_hz=None,
                    worker_wall_s=row.get("worker_wall_s"),
                )
            )
            for role in ROLES:
                endpoint = original[ident][role][arm]
                scored.append(
                    dict(
                        id=ident,
                        arm=arm,
                        method=role,
                        scope="archived_capture_v5",
                        status=endpoint["status"],
                        reason=None,
                        attempted=None,
                        worker_returned=None,
                        position_error_km=endpoint["error_km"],
                        conditional_rms_hz=None,
                        archived_publication_rms_hz=endpoint["rf_rms_hz"],
                        archived_matched_rms_hz=endpoint["matched_rf_rms_hz"],
                        worker_wall_s=endpoint["wall_s"],
                    )
                )
    save_json(output / "original-roles.json", original)
    save_json(output / "original-role-bindings.json", original_bindings)
    csv_file(output / "scores.csv", scored)
    cohorts = {
        "scheduled": set(records),
        "attempted": {i for i, r in records.items() if r["attempted"] is True},
        "eligible": set(records)
        - {i for i, r in records.items() if r["source"] == "unavailable_input"},
    }
    summary = {}
    for name, ids in cohorts.items():
        table = {}
        for method in (trial.METHOD, *ROLES):
            table[method] = {}
            for arm in ARMS:
                group = [
                    r
                    for r in scored
                    if r["id"] in ids and r["method"] == method and r["arm"] == arm
                ]
                table[method][arm] = dict(
                    count=len(group),
                    statuses=dict(Counter(r["status"] for r in group)),
                    geographic_km=distribution(r["position_error_km"] for r in group),
                    conditional_rms_hz=distribution(r["conditional_rms_hz"] for r in group),
                    archived_publication_rms_hz=distribution(
                        r["archived_publication_rms_hz"] for r in group
                    ),
                )
        summary[name] = table
    save_json(output / "summary.json", summary)
    scored_files = (
        "original-roles.json",
        "original-role-bindings.json",
        "scores.csv",
        "summary.json",
    )
    save_json(
        output / "score-lock.json",
        dict(
            cases=lock["cases"],
            prediction_lock_sha256=_sha(output / "prediction-lock.json"),
            frozen_scores_sha256=files["scores.csv"],
            frozen_targets_sha256=files["targets.jsonl"],
            files={name: _sha(output / name) for name in scored_files},
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seal", "score"))
    parser.add_argument("--work", type=Path)
    parser.add_argument("--out", type=local_output, default=trial.REPORT)
    options = parser.parse_args()
    if options.action == "score":
        score(options.out)
    elif options.work is None:
        parser.error("sealing requires the original worker journal")
    else:
        seal(options.work, options.out)


if __name__ == "__main__":
    main()
