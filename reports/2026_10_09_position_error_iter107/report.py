"""Full-membership post-fit reporting; no optimization or operational selection."""

import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np

from leo.analysis.regional_position_score import coordinates
from leo.contracts.regional_position import RegionalPrior
from leo.storage.regional_position_v2 import Hard60Store
from leo.storage.regional_position_v3 import B7Store

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARMS = ("fitted-c", "zero-c")
TERMINAL = {"complete", "failed", "input-failed", "budget-exhausted"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def member_label(member):
    return member["member"].get("inventory_label", member["member"].get("dataset_label"))


def phase_receipts(directory, digest):
    records, hashes = {}, {}
    for phase in ("baseline", "candidate"):
        path = directory / (phase + ".json")
        if not path.exists():
            records[phase] = {"status": "missing"}
            continue
        hashes[str(path)] = sha(path)
        try:
            record = json.loads(path.read_text())
            assert record["protocol_sha256"] == digest
            assert record["status"] in TERMINAL
            assert record["phase"] == phase, "Phase receipt is swapped"
            if "label" not in record and record["status"] == "budget-exhausted":
                record["report_identity_limitation"] = (
                    "Budget-only engine receipt omits label; phase/protocol/hash and directory "
                    "bind this report row, with limited member identity"
                )
            else:
                assert record["label"] == directory.name, "Member receipt is swapped"
            records[phase] = record
        except (ValueError, KeyError, AssertionError) as error:
            records[phase] = dict(status="receipt-invalid", reason=repr(error))
    for phase, record in records.items():
        if not record.get("report_identity_limitation") or not record.get("operational"):
            continue
        if (
            phase != "candidate"
            or records["baseline"]["status"] != "complete"
            or (record["operational"] != records["baseline"].get("operational", {}))
        ):
            records[phase] = dict(
                status="receipt-invalid",
                reason="Unlabelled budget fallback is not the bound complete baseline",
            )
    if records["candidate"]["status"] == "missing" and records["baseline"]["status"] in (
        TERMINAL - {"complete"}
    ):
        records["candidate"] = dict(
            status="not-run-baseline-failed",
            report_only=True,
            reason="Controller stops after non-complete baseline; no candidate receipt invented",
        )
    return records, hashes


def paired_terminal(records):
    return records["baseline"]["status"] in TERMINAL and records["candidate"]["status"] in (
        TERMINAL | {"not-run-baseline-failed"}
    )


def evaluate_fit(operation, document):
    if not operation:
        return None
    fit = operation["fit"]
    prior = RegionalPrior(**document["configuration"]["prior"])
    latitude, longitude = coordinates(prior, np.asarray(fit["vector"])[:2])
    lat, lon, rlat, rlon = map(
        math.radians,
        (
            latitude,
            longitude,
            document["reference_latitude_deg"],
            document["reference_longitude_deg"],
        ),
    )
    haversine = math.sin((lat - rlat) / 2) ** 2
    haversine += math.cos(lat) * math.cos(rlat) * math.sin((lon - rlon) / 2) ** 2
    return dict(
        error_km=2 * 6371.0088 * math.asin(math.sqrt(min(1, max(0, haversine)))),
        **{
            key: fit.get(key)
            for key in (
                "objective",
                "posterior_rms_hz",
                "signal_windows",
                "converged",
                "stationarity",
                "evaluations",
                "elapsed_s",
                "stop_reason",
            )
        },
        selection={
            key: operation.get(key)
            for key in (
                "region_source",
                "basin",
                "accepted_stage",
                "start",
                "calibration_penalty",
            )
        },
    )


def evaluation_document(member):
    """Reference authority only for already terminal corresponding records."""
    if member.get("dataset") == "POST18-development":
        source = next((s for s in member["sources"] if s["name"] == "B7"), member["sources"][0])
        cls = B7Store if source["name"] == "B7" else Hard60Store
        manifest = cls(Path("/srv/bulk/leo")).status(member["member"]["session_id"]).manifest
        assert manifest is not None and manifest.document_sha256 == source["document_sha256"]
        return manifest.document.model_dump(mode="json")
    source = next(s for s in member["sources"] if s["name"] == "baseline")["source"]
    if "path" in source:
        path = ROOT / source["path"]
        assert sha(path) == source["sha256"]
        return json.loads(path.read_text())
    manifest = Hard60Store(Path(source["root"])).status(member["member"]["session_id"]).manifest
    assert manifest is not None and manifest.document_sha256 == source["document_sha256"]
    return manifest.document.model_dump(mode="json")


def recoveries(candidate):
    rows = []
    for name, region in candidate.get("regions", {}).items():
        if not name.startswith("direct107:"):
            continue
        receipt = region.get("recovery", {})
        result = receipt.get("result") or {}
        rows.append(
            dict(
                region=name,
                calibration_status=result.get("status", "not-qualified-or-not-reached"),
                calibration_qualified=result.get("calibration") is not None,
                failure_reason=receipt.get("reason") or result.get("error"),
                prefit_qualification=result.get("prefit_qualification"),
                postfit_qualification=result.get("qualification"),
                association_available=bool(region.get("association", {}).get("result")),
                final_qualified_counts={
                    arm: sum(
                        row.get("arm") == arm and bool(row.get("fit", {}).get("converged"))
                        for row in region.get("finals", [])
                        if row.get("fit")
                    )
                    for arm in ARMS
                },
            )
        )
    return rows


def slice_metrics(directory, digest):
    result = {}
    for phase in ("baseline", "candidate"):
        started = sorted((directory / "slices").glob(phase + "-*.started.json"))
        done = sorted((directory / "slices").glob(phase + "-*.done.json"))
        records = [json.loads(path.read_text()) for path in done]
        assert all(record["protocol_sha256"] == digest for record in records)
        for path in started:
            assert json.loads(path.read_text())["protocol_sha256"] == digest
        hits = Counter()
        for record in records:
            hits.update(record.get("source_port_metrics") or {})
        result[phase] = dict(
            claimed_slices=len(started),
            completed_slices=len(done),
            claimed_without_done=len(started) - len(done),
            known_elapsed_s=sum(record.get("elapsed_s", 0) for record in records),
            local_checkpoint_hits=sum(record.get("local_checkpoint_hits", 0) for record in records),
            source_port_metrics=dict(hits),
            cost_scope=(
                "Only persisted completed slices; unfinished duration unknown; "
                "no nested fit-cost sum"
            ),
        )
    return result


def describe_member(member, records, *, document_loader=evaluation_document, archive_loader=None):
    baseline, candidate = records["baseline"], records["candidate"]
    row = dict(
        label=member_label(member),
        dataset=member.get("dataset", member["member"].get("dataset")),
        session_id=member["member"]["session_id"],
        exposure=member["member"].get("exposure"),
        loader_kind=member.get("kind"),
        baseline_status=baseline["status"],
        candidate_status=candidate["status"],
        paired_terminal=paired_terminal(records),
        baseline_failure=baseline.get("reason"),
        candidate_failure=candidate.get("reason"),
        identity_limitations={
            phase: record.get("report_identity_limitation")
            for phase, record in records.items()
            if record.get("report_identity_limitation")
        },
        candidate_fallback=bool(candidate.get("fallback_available")),
        trigger_count=None
        if "inventory" not in candidate
        else len(candidate["inventory"]["candidates"]),
        trigger_failures=candidate.get("inventory", {}).get("failures"),
        recoveries=recoveries(candidate),
        stage_failures={"baseline": baseline.get("reasons"), "candidate": candidate.get("reasons")},
        arms={arm: {"baseline": None, "candidate": None} for arm in ARMS},
        evaluation_status="withheld-until-corresponding-member-terminal",
    )
    if not row["paired_terminal"]:
        return row
    if not any(record.get("operational") for record in (baseline, candidate)):
        row["evaluation_status"] = "no-operational-position"
        return row
    try:
        document = document_loader(member)
        archive = archive_loader(member) if archive_loader else None
        for arm in ARMS:
            value = row["arms"][arm]
            value["baseline"] = evaluate_fit(baseline.get("operational", {}).get(arm), document)
            value["candidate"] = evaluate_fit(candidate.get("operational", {}).get(arm), document)
            if value["baseline"] and value["candidate"]:
                value["error_delta_km"] = (
                    value["candidate"]["error_km"] - value["baseline"]["error_km"]
                )
                value["recovered_region_selected"] = str(
                    value["candidate"]["selection"].get("region_source", "")
                ).startswith("direct107:")
                same_stage = value["baseline"]["selection"].get("accepted_stage") == value[
                    "candidate"
                ]["selection"].get("accepted_stage")
                value["frequency_fit_stage_matched"] = same_stage
                value["frequency_fit_caveat"] = (
                    "Operational regions/associations/banks may differ even at the same stage; "
                    "score improvement is not evidence of better position accuracy"
                )
                value["objective_delta_same_stage_only"] = (
                    value["candidate"]["objective"] - value["baseline"]["objective"]
                    if same_stage
                    else None
                )
            if archive:
                old = archive["stages"]["B7"].get(arm)
                value["archived85_control"] = (
                    {
                        key: old.get(key)
                        for key in (
                            "error_km",
                            "objective",
                            "posterior_rms_hz",
                            "signal_windows",
                            "converged",
                            "stage",
                        )
                    }
                    if old
                    else None
                )
                if old and value["baseline"]:
                    current = baseline["operational"][arm]["fit"]
                    value["archive_to_current_baseline"] = dict(
                        error_delta_km=value["baseline"]["error_km"] - old["error_km"],
                        vector_exact=np.array_equal(current["vector"], old.get("vector")),
                        objective_delta=current["objective"] - old["objective"],
                        scope=(
                            "Archived85 control vs newly reproduced current B7; "
                            "not assumed identical"
                        ),
                    )
        row["evaluation_status"] = "post-fit-evaluation-only"
    except (AssertionError, ValueError, KeyError, FileNotFoundError) as error:
        row["evaluation_status"] = "evaluation-authority-failed"
        row["evaluation_failure"] = repr(error)
        row["arms"] = {arm: {"baseline": None, "candidate": None} for arm in ARMS}
    return row


def aggregate(rows, *, census_terminal=None):
    all_terminal = all(row["paired_terminal"] for row in rows)
    if census_terminal is not None:
        all_terminal = all_terminal and census_terminal
    output = dict(
        full_membership=len(rows),
        terminal_members=sum(r["paired_terminal"] for r in rows),
        full_census_position_metrics_withheld=not all_terminal,
        arms={},
    )
    for arm in ARMS:
        paired = [r for r in rows if r["arms"][arm]["baseline"] and r["arms"][arm]["candidate"]]
        item = dict(
            matched_position_count=len(paired), missing_or_failed_positions=len(rows) - len(paired)
        )
        full = all_terminal and len(paired) == len(rows)
        item["full_census_metrics_withheld"] = not full
        if full:
            for phase in ("baseline", "candidate"):
                errors = np.array([r["arms"][arm][phase]["error_km"] for r in paired])
                item[phase] = dict(
                    mean_km=float(errors.mean()),
                    median_km=float(np.median(errors)),
                    p95_km=float(np.quantile(errors, 0.95)),
                    worst_km=float(errors.max()),
                )
            item["paired_regressions"] = [
                dict(label=r["label"], delta_km=r["arms"][arm]["error_delta_km"])
                for r in paired
                if r["arms"][arm]["error_delta_km"] > 1e-9
            ]
        output["arms"][arm] = item
    output["full_census_position_metrics_withheld"] = not all_terminal or any(
        value["full_census_metrics_withheld"] for value in output["arms"].values()
    )
    return output


def archive_control(member):
    receipt = member.get("baseline_endpoint")
    if receipt is None:
        return None
    path = ROOT / receipt["path"]
    assert sha(path) == receipt["sha256"]
    return json.loads(path.read_text())


def main():
    protocol_path = HERE / "protocol.json"
    plan = json.loads(protocol_path.read_text())
    digest = sha(protocol_path)
    assert len(plan["members"]) == 193
    rows, source_hashes = [], {}
    for member in plan["members"]:
        directory = HERE / "results" / member_label(member)
        records, hashes = phase_receipts(directory, digest)
        row = describe_member(member, records, archive_loader=archive_control)
        row["runtime"] = slice_metrics(directory, digest)
        rows.append(row)
        source_hashes.update(hashes)
    census_terminal = all(row["paired_terminal"] for row in rows)
    datasets = {
        name: aggregate(
            [row for row in rows if row["dataset"] == name], census_terminal=census_terminal
        )
        for name in (
            "DS16",
            "DS17",
            "DS18",
            "POST18-development",
        )
    }
    result = dict(
        protocol_sha256=digest,
        scope=(
            "Full193 development census; no reserve/unseen claim; partial progress diagnostic only"
        ),
        members=rows,
        aggregate=aggregate(rows),
        datasets=datasets,
        phase_receipt_hashes=source_hashes,
        status_counts={
            phase: dict(Counter(row[phase + "_status"] for row in rows))
            for phase in ("baseline", "candidate")
        },
    )
    (HERE / "coverage-report.json").write_text(json.dumps(result, indent=2) + "\n")
    lines = [
        "# Generic recovery coverage",
        "",
        (
            "All193 members are accounted for. Partial progress is diagnostic; full-cohort "
            "position metrics remain withheld until full terminal and matched-position coverage."
        ),
        "",
        "| Dataset | Members | Terminal | Matched fitted-c positions | Matched c=0 positions |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, data in datasets.items():
        lines.append(
            f"|{name}|{data['full_membership']}|{data['terminal_members']}|{data['arms']['fitted-c']['matched_position_count']}|{data['arms']['zero-c']['matched_position_count']}|"
        )
    lines += [
        "",
        (
            "`coverage-report.json` records every member/status, recovery qualification, "
            "trigger/fallback, runtime/source metrics and matched arms. Archived85 controls "
            "are distinct from current B7 baselines; frequency-fit effects are separate "
            "from position accuracy."
        ),
        "",
        "```json",
        json.dumps(result["aggregate"], indent=2),
        "```",
    ]
    (HERE / "COVERAGE.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
