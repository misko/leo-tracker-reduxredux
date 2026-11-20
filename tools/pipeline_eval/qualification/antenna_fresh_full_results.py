"""Publish the independently measured dual-four and partner-on-hit whole-QAM outcomes."""

import argparse
import gzip
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from ..variants import partner_on_hit, second_on_miss
from ..variants.selective_capture import same_support, visit_pairs
from . import acquisition_index, screening_figures
from . import antenna_fresh_full as trial
from . import antenna_fresh_full_hit as hit
from . import fresh_replay_results as paired
from . import frontier_whole_replay_results as traces
from . import whole_band_results as measured
from . import whole_center_union_results as union
from .exact_wide_iq_results import detector_rows, timing_rows
from .full_held_scores import held_references
from .full_v5_check import _sha
from .new_waveforms_results import original_audit
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

METHODS = {"control": trial.STOCK, "candidate": trial.METHOD}


def audit(stock, candidate, schedule, actual):
    expected, counts = partner_on_hit.project(stock, schedule)
    same_support(stock, candidate)
    for row, (visit, lanes), (found, primary, used) in zip(
        schedule, visit_pairs(stock["source"]["probes"]), actual, strict=True
    ):
        if (
            (found, primary) != (visit, row["selected_receiver"])
            or type(used) is not bool
            or used == second_on_miss.needs_partner(lanes[primary])
        ):
            raise ValueError("actual partner calls differ from the independently projected visit")
    calls = sum(allowed is True for _, _, allowed in actual)
    if calls != counts.get("primary_hits", 0):
        raise ValueError("actual partner calls differ from independent stock gate projection")
    projected_sha = sha256((whole_iq.recording.encoded(expected) + "\n").encode()).hexdigest()
    return dict(
        full_projection_matches=expected == candidate,
        projected_native_sha256=projected_sha,
        actual_primary_calls=len(actual),
        actual_partner_calls=calls,
        actual_physical_receiver_calls=len(actual) + calls,
        dual_physical_receiver_calls=2 * len(actual),
        **counts,
    )


def seal(work, out):
    if (out / "prediction-lock.json").exists():
        raise FileExistsError("the paired predictions are already sealed")
    source = trial.whole.source(work)
    plan = dict(
        source,
        detectors=dict(
            control=source["detectors"]["control"], candidate=source["detectors"]["control"]
        ),
    )
    rows, visits, assets, resources, parity = [], [], [], {}, {}
    for ident in source["cases"]:
        receipts, waveforms = {}, {}
        resources[ident] = receipts
        for role, method in METHODS.items():
            folder = work / ident / role
            row, receipt, native = measured.attempt(work, ident, role, plan, method=method)
            incident = folder.parent / f"{role}-failure.json"
            if incident.is_file() and whole_iq.read(incident).get("status") == "unavailable":
                row["result"]["status"] = "unavailable"
            rows.append(row)
            receipts[role] = receipt
            if native is not None:
                waveforms[role] = whole_iq.read(native)
                file = f"native/{role}/{ident}.json.gz"
                write(out / file, gzip.compress(native.read_bytes(), mtime=0))
                assets.append(file)
                visits.extend(traces.trace_rows(ident, role, detector_rows(folder)))
            log = folder / "service.log"
            if log.is_file():
                file = f"{ident}-{role}.service.log"
                write(
                    out / file, whole_iq.checked(log, receipt["service"]["log_sha256"]).read_bytes()
                )
                assets.append(file)
        case = parity[ident] = dict(raw_complete={role: role in waveforms for role in METHODS})
        if set(waveforms) == set(METHODS):
            measured.pair_geometry(receipts["control"], receipts["candidate"])
            candidate = hit.source(work, ident)["cases"][ident]
            schedule_path = hit.roots(work, ident)[1] / "dispatch.json"
            schedule = whole_iq.read(
                whole_iq.checked(schedule_path, candidate["dispatch"]["sha256"])
            )
            active = work / ident / "candidate" / "actual-dispatch.json"
            case.update(
                audit(waveforms["control"], waveforms["candidate"], schedule, whole_iq.read(active))
            )
            case["measured_native_sha256"] = rows[-1]["native_sha256"]
            case["same_native_bytes"] = (
                case["measured_native_sha256"] == case["projected_native_sha256"]
            )
            active_name = f"dispatch/{ident}/actual-dispatch.json"
            write(out / active_name, active.read_bytes())
            assets.append(active_name)
    traces.protect_resources(resources)
    pack(out / "positions.jsonl.gz", rows)
    pack(out / "visits.jsonl.gz", visits)
    save_json(out / "resources.json", resources)
    save_json(out / "parity.json", parity)
    assets.extend(
        (
            "positions.jsonl.gz",
            "visits.jsonl.gz",
            "resources.json",
            "parity.json",
            "source-lock.json",
            "selection.json",
            "PROTOCOL.md",
        )
    )
    assets.extend(str(f.relative_to(out)) for f in (out / "dispatch").glob("*/source-lock.json"))
    assets.extend(str(f.relative_to(out)) for f in (out / "dispatch").glob("*/dispatch.json"))
    save_json(
        out / "prediction-lock.json",
        dict(
            cases=list(source["cases"]),
            files={a: _sha(out / a) for a in assets},
            publisher_sha256=_sha(Path(__file__)),
        ),
    )


def timing(out, plan):
    resources = whole_iq.read(out / "resources.json")
    parity = whole_iq.read(out / "parity.json")
    raw = [r for r in rows_from(out / "visits.jsonl.gz") if r["status"] == "processed"]
    results = timing_rows(resources, raw)
    for row in results:
        ident, role = row["id"], row["role"]
        case = plan["cases"][ident]
        evidence = resources[ident][role]
        counts = evidence.get("counts", {})
        data = parity[ident]
        if role == "candidate":
            physical = data.get("actual_physical_receiver_calls")
        else:
            physical = 2 * row["calls"] if counts else None
        row.update(
            deadline_s=plan["limit_s"],
            cores=case["cpus"],
            native_receiver_calls=physical,
            recorded_clock_span_s=counts.get("window_delivery_span_s"),
            scheduled_visits=case["recording"]["window_count"],
            invalid_visits=counts.get("invalid_capture"),
            manager_wall_s=evidence["service"].get("service_wall_s"),
        )
    csv_file(out / "deadlines.csv", results)


def score(out):
    receipt = paired.sealed(out, "prediction-lock.json")
    original_audit(out)
    plan = whole_iq.read(out / "source-lock.json")
    ids = receipt["cases"]
    (ds26,) = [i for i in ids if i.startswith("DS26-")]
    (ds29,) = [i for i in ids if i.startswith("DS29-")]
    _, archived = held_references(None, [ds26])
    reference = {ds26: archived[0], ds29: paired.references(out, plan["cases"][ds29])}
    rows = rows_from(out / "positions.jsonl.gz")
    scores = paired.geographic(rows, reference)
    csv_file(out / "scores.csv", scores)
    groups = dict(all=ids, ds26=[ds26], ds29=[ds29])
    save_json(out / "summary.json", paired.distribution_rows(scores, groups))
    calibration, _ = union.paired_scores(scores)
    csv_file(out / "calibration.csv", calibration)
    timing(out, plan)
    evidence = (
        "prediction-lock.json",
        "reference-prediction-lock.json",
        "reference-binding-audit.json",
        *paired.ROOF_REFERENCES.values(),
        "scores.csv",
        "summary.json",
        "calibration.csv",
        "deadlines.csv",
        "parity.json",
    )
    charts = []
    for group, cases in groups.items():
        title = (
            "Antenna confirmation on new complete IQ recordings"
            if group == "all"
            else f"Partner on a measured primary hit on {cases[0]}"
        )
        card = paired.chart(out, group, title, cases, rows, evidence, group != "ds26")
        card.update(
            id=f"antenna-fresh-full-{group}",
            caption=(
                "Full recorded IQ and original clocks, causal requests and compact fit. "
                "Both policies search four timing regions. "
                "The partner runs only after a primary hit."
            ),
        )
        card["series"][0]["label"] = "Partner on primary hit"
        card["series"][1]["label"] = "Four regions on both antennas"
        for series in card["series"]:
            acquisition_index.endpoint_rows(out, card, series)
        charts.append(card)
    save_json(out / "figures.json", dict(version=2, charts=charts))
    screening_figures.generate(out / "charts", evidence=out)
    files = (*evidence, "figures.json", *(f"{g}-figure-lock.json" for g in groups))
    save_json(
        out / "score-lock.json", dict(cases=ids, files={name: _sha(out / name) for name in files})
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("seal", "score"))
    cli.add_argument("--work", default=trial.WORK, type=local_output)
    cli.add_argument("--out", default=trial.REPORT, type=local_output)
    args = cli.parse_args()
    with trial.context(), patch.object(paired, "METHODS", METHODS):
        if args.action == "seal":
            seal(args.work, args.out)
        else:
            score(args.out)
