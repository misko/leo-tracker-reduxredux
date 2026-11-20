"""Fit the fixed 22 complete stock captures with a second antenna dispatched on a miss."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..scoring import ARMS
from ..variants import one_lane_schedule
from ..variants.selective_capture import visit_pairs
from . import complete_detector_roster as fixed
from . import one_lane_roster as one
from . import support_cross_trial as service
from .bracketed_position import check_release
from .fractional_runtime_whole import verify_request
from .fresh_replay_results import sealed
from .full_v5_check import _sha
from .phase_support_results import pack

REPORT = one.REPORT.with_name("second-on-miss-roster")
METHOD = "second_on_miss_roster"
CPUS = (16, 17, 18, 19)
DIRECT = ("DS26-0014", "DS29-0082")
SINGLE_PIN = "355665d05245ff43d2a33cfb3af2ee7a294715312c97a6709755f7cb60fb328b"
BOUNDARY = "Stored stock antenna factors through actual phase-release compact position"


def sources():
    from ..variants import second_on_miss

    members = (
        Path(__file__),
        Path(second_on_miss.__file__),
        Path(one_lane_schedule.__file__),
        Path(one.__file__),
        Path(service.__file__),
        Path(service.margin_admission_trial.__file__),
        REPORT / "PROTOCOL.md",
    )
    return {str(p.relative_to(ROOT)): _sha(p) for p in members}


def gated(probe):
    return sum(c["passed_fractional_margin_gate"] is True for c in probe["candidates"])


def audit(stock, projected, actual_dispatch, rf_centers):
    """Verify the strict pass, output bytes, invocation count and no lost positive visits."""
    physical = {"source", "provenance"}
    if {k: v for k, v in stock.items() if k not in physical} != {
        k: v for k, v in projected.items() if k not in physical
    }:
        raise ValueError("projection changed persisted sample counters or capture clocks")
    fields = {"probes", "analysis_manifest_sha256"}
    if {k: v for k, v in stock["source"].items() if k not in fields} != {
        k: v for k, v in projected["source"].items() if k not in fields
    } or stock["provenance"]["excluded_windows"] != projected["provenance"]["excluded_windows"]:
        raise ValueError("projection changed capture lineage or original invalid acquisitions")
    ledger = one_lane_schedule.dispatch(stock, rf_centers)
    probes = [visit_pairs(doc["source"]["probes"]) for doc in (stock, projected)]
    counts = dict.fromkeys(
        (
            "valid_visits",
            "invalid_visits",
            "primary_only_visits",
            "partner_calls",
            "positive_visits",
            "partner_rescued_visits",
            "stock_positive_probes",
            "positive_probes",
            "stock_candidates",
            "retained_candidates",
            "stock_non_gated_candidates",
            "retained_non_gated_candidates",
        ),
        0,
    )
    counts["invalid_visits"] = len(stock["provenance"]["excluded_windows"])
    for (i, original), (j, result), expected, measured in zip(
        *probes, ledger, actual_dispatch, strict=True
    ):
        primary = expected["selected_receiver"]
        partner = 1 - primary
        gated_counts = [gated(r) for r in original]
        call_partner = gated_counts[primary] == 0
        wanted = dict(
            visit=i,
            rf_center_hz=expected["rf_center_hz"],
            primary_receiver=primary,
            partner_required=call_partner,
        )
        other = original[partner] if call_partner else dict(original[partner], candidates=[])
        if (
            i != j
            or encoded(measured) != encoded(wanted)
            or encoded(result[primary]) != encoded(original[primary])
            or encoded(result[partner]) != encoded(other)
        ):
            raise ValueError(f"projection changed the strict per-lane dispatch at visit {i}")
        after = [gated(r) for r in result]
        if any(gated_counts) != any(after):
            raise ValueError(f"projection removed a stock positive visit at {i}")
        counts["valid_visits"] += 1
        counts["primary_only_visits"] += not call_partner
        counts["partner_calls"] += call_partner
        counts["positive_visits"] += any(after)
        counts["partner_rescued_visits"] += call_partner and bool(after[partner])
        counts["stock_positive_probes"] += sum(bool(n) for n in gated_counts)
        counts["positive_probes"] += sum(bool(n) for n in after)
        for name, rows, positives in (
            ("stock", original, gated_counts),
            ("retained", result, after),
        ):
            size = sum(len(r["candidates"]) for r in rows)
            counts[f"{name}_candidates"] += size
            counts[f"{name}_non_gated_candidates"] += size - sum(positives)
    counts["receiver_calls"] = counts["valid_visits"] + counts["partner_calls"]
    return counts


def prepare(work, row, parent, extensions, release, cpu):
    from ..variants.second_on_miss import project

    ident = row["id"]
    case, original = one.bind(ident, extensions)
    bindings = (
        case["native"]["sha256"],
        case["request"]["sha256"],
        case["catalog"]["sha256"],
        case["regions"][0],
    )
    if bindings != tuple(row[k] for k in fixed.BINDINGS):
        raise ValueError(f"{ident} differs from the previously sealed scientific request")
    stock = one.stock_document(parent["native_archive"])
    authority = stock["source"]["input_manifest_sha256"]
    if (
        row["stock_native_sha256"] != parent["native_archive"]["native_sha256"]
        or authority != parent["clock_authority"]
        or stock["source"]["session_id"] != case["session_id"]
        or stock["provenance"]["detector_sha256"] != "sha256:" + one.STOCK_SHA
        or stock["provenance"]["window_count"] != case["recording"]["window_count"]
    ):
        raise ValueError(f"{ident} lost complete original stock input authority")
    rf = {(r["channel"], r["edge"]): r["rf_center_hz"] for r in parent["rf_mapping"]}
    projected, dispatch = project(stock, rf)
    counts = audit(stock, projected, dispatch, rf)
    folder = work / ident / METHOD
    native, request = folder / "recording/native.json", folder / "recording/request.json"
    write(native, encoded(projected) + b"\n")
    identity = whole_iq.recording.bind_request(case, native, request)["native_sha256"]
    verify_request(whole_iq.read(request), original, native_path=native, native_sha256=identity)
    save_json(folder / "plan.json", dict(receiver=release["receiver"]))
    save_json(folder / "raw.json", dict(native_sha256=identity, request_sha256=_sha(request)))
    prediction = dict(
        id=ident,
        method=METHOD,
        condition=METHOD,
        mode="matched-tile",
        cpu=cpu,
        native_sha256=_sha(native),
        prepared_request_sha256=_sha(request),
        stock_native_sha256=row["stock_native_sha256"],
        one_lane_native_sha256=row["native_sha256"],
        **{k: row[k] for k in fixed.BINDINGS},
        **counts,
    )
    evidence = dict(
        stock_native=parent["native_archive"],
        clock_authority=authority,
        rf_mapping=parent["rf_mapping"],
        dispatch_sha256=sha256(encoded(dispatch)).hexdigest(),
        native_sha256=prediction["native_sha256"],
        **counts,
    )
    return prediction, evidence


def freeze(work):
    from ..variants.second_on_miss import POLICY

    if (REPORT / "plan.json").exists():
        raise FileExistsError("the second-on-miss roster is already frozen")
    prior = sealed(one.REPORT, "prediction-lock.json", SINGLE_PIN)
    old = whole_iq.read(fixed.member(one.REPORT, prior, "plan.json"))
    inputs = whole_iq.read(fixed.member(one.REPORT, prior, "packet-audit.json"))
    groups, _, _, extensions, release = one.inventory()
    if groups != old["groups"] or prior["cases"] != groups["all"]:
        raise ValueError("the preceding frozen complete comparator roster changed")
    checked_sources = sources()
    work.mkdir(exist_ok=False)
    groups["direct"] = list(DIRECT)
    parent = {r["id"]: r for r in old["jobs"]}
    order = list(dict.fromkeys([*groups["difficult"], *groups["fresh"], *DIRECT, *groups["all"]]))
    jobs, receipts, errors = [], {}, {}
    for i, ident in enumerate(order):
        cpu = CPUS[i % len(CPUS)]
        row = parent[ident]
        try:
            job, certificate = prepare(work, row, inputs[ident], extensions, release, cpu)
        except (OSError, ValueError, KeyError, StopIteration) as error:
            errors[ident] = str(error)
            job = dict(
                id=ident,
                condition=METHOD,
                method=METHOD,
                cpu=cpu,
                mode="matched-tile",
                native_sha256=None,
                **{k: row[k] for k in fixed.BINDINGS},
            )
        else:
            receipts[ident] = certificate
        jobs.append(job)
    if sources() != checked_sources:
        raise ValueError("a prospective method or adapter changed during input preparation")
    save_json(REPORT / "packet-audit.json", receipts)
    save_json(
        REPORT / "plan.json",
        dict(
            groups=groups,
            jobs=jobs,
            errors=errors,
            sources=checked_sources,
            policy=POLICY,
            cpus=CPUS,
            limit_s=service.LIMIT,
            memory_bytes=whole_iq.MEMORY,
            swap_bytes=0,
            packet_audit_sha256=_sha(REPORT / "packet-audit.json"),
            one_lane_prediction_sha256=SINGLE_PIN,
            **release,
        ),
    )
    save_json(work / "launch-lock.json", dict(plan_sha256=_sha(REPORT / "plan.json")))
    print("frozen", len(jobs), "physical inputs", len(receipts), "errors", errors, flush=True)


def run(work):
    path = whole_iq.checked(
        REPORT / "plan.json", whole_iq.read(work / "launch-lock.json")["plan_sha256"]
    )
    plan = whole_iq.read(path)
    whole_iq.checked(REPORT / "packet-audit.json", plan["packet_audit_sha256"])
    if plan["sources"] != sources():
        raise ValueError("scientific method or input preparation changed after its freeze")
    check_release(plan)

    def lane(cpu):
        attempts = []
        for row in plan["jobs"]:
            if row["cpu"] != cpu:
                continue
            if row["id"] in plan["errors"]:
                result = dict(
                    status="unavailable",
                    reason=plan["errors"][row["id"]],
                    boundary=BOUNDARY,
                    arms={a: dict(latlon=None) for a in ARMS},
                    metrics={},
                )
                attempts.append(dict(row, terminal="not-launched", result=result))
            else:
                attempts.append(service.service(work, row))
        return attempts

    with ThreadPoolExecutor(max_workers=len(CPUS)) as pool:
        rows = [r for outcome in pool.map(lane, CPUS) for r in outcome]
    pack(REPORT / "positions.jsonl.gz", sorted(rows, key=lambda r: r["id"]))
    names = ("plan.json", "packet-audit.json", "PROTOCOL.md", "positions.jsonl.gz")
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=plan["groups"]["all"],
            files={name: _sha(REPORT / name) for name in names},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "run"))
    parser.add_argument("work", type=local_output)
    args = parser.parse_args()
    {"freeze": freeze, "run": run}[args.action](args.work)
