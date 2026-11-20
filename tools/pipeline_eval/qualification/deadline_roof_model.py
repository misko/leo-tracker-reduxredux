"""Replay the operational deadline router on sealed historical DS26 worker intervals."""

import argparse
import csv
import gzip
import io
import math
from collections import Counter
from pathlib import Path

from .. import corpus
from ..__main__ import encoded, local_output, read_predictions, save_json
from ..scoring import ARMS, ROLES, distance_km, distribution, thresholds, validate_result
from ..variants import deadline_receiver as receiver
from . import full_receiver_comparison as verify
from . import roof_selection_native as native
from .prefix_figures import csv_file

REPORT = verify.SCREEN / "deployment/deadline-roof"
COMPARISON = verify.SCREEN / "redesign/roof-selection/comparison"
NATIVE_REPORT = COMPARISON.with_name("native")
METHOD = "deadline_roof"
TOTALS = (30, 90, 180)
RESERVE = 15
COMPACT = "v5_secant_fit"
SMOOTH = native.METHOD
SHARED = ("native_sha256", "catalog_sha256", "tile")
SAMPLE = "reports/2026_11_18_v5_blind_comparison/sample-errors.csv"


class ReplayClock:
    def __init__(self):
        self.elapsed = 0.0

    def now(self):
        return self.elapsed


def archived_wall(row):
    timings = [
        row[key]
        for key in (
            "worker_wall_s",
            "prior_timing_worker_wall_s",
            "prior_confirmation_worker_wall_s",
        )
        if row.get(key) is not None
    ]
    if len(timings) != 1 or not math.isfinite(timings[0]) or timings[0] <= 0:
        raise ValueError(f"{row['id']} does not have one positive archived worker interval")
    return timings[0]


def archive_callback(row, clock, sources, name):
    outcome, observed = row["result"], archived_wall(row)
    status = outcome["status"]
    if status not in ("ok", "withheld", "failed", "timed_out"):
        raise ValueError(f"{row['id']} has an unsupported observed status {status}")
    # The hard cap precedes supervisor process-exit overhead on recorded timeouts.
    censor = min(observed, row.get("deadline_s") or observed) if status == "timed_out" else None

    def run(allowance):
        record = dict(
            method=name, archived_status=status, recorded_wall_s=observed, censor_s=censor
        )
        sources.append(record)
        if censor is not None and allowance > censor:
            clock.elapsed += censor
            record["event"] = "right-censored-before-model-cap"
            return dict(
                receiver.deadline_result(),
                status="missing",
                reason="archived timeout ended before modeled cutoff",
            )
        if observed > allowance or censor is not None:
            clock.elapsed += allowance
            record["event"] = "modeled-timeout"
            return receiver.deadline_result()
        clock.elapsed += observed
        record["event"] = "observed-terminal"
        return outcome

    return run


def replay(compact, smooth, budget, *, absent=False, reserve=RESERVE):
    if absent:
        return dict(
            result=smooth["result"],
            selected="none",
            calls=[],
            elapsed_s=None,
            elapsed_lower_bound_s=None,
            replay_events=[],
            endpoint_source=None,
        )
    clock, seen = ReplayClock(), []
    out = receiver.route(
        archive_callback(compact, clock, seen, "compact"),
        archive_callback(smooth, clock, seen, "smooth"),
        total_s=budget,
        reserve_s=reserve,
        now=clock.now,
    )
    exact = seen[-1]["event"] == "observed-terminal"
    if seen[-1]["event"] == "right-censored-before-model-cap":
        out["elapsed_lower_bound_s"] = out["elapsed_s"]
        out["elapsed_s"] = None
    else:
        out["elapsed_lower_bound_s"] = None
    return dict(out, replay_events=seen, endpoint_source=out["selected"] if exact else None)


def auth_archives():
    one, stock = "all159-one.jsonl.gz", "all159-stock.jsonl.gz"
    lock = verify.seal(COMPARISON, "all159-figure-lock.json", (one, stock, "source-audit.json"))
    audit = verify.read(COMPARISON / "source-audit.json")
    inputs, common, _, seals = native.roster()
    verify.roster_matches(lock["cases"], inputs, "integrated deadline input")
    if audit["frozen_fixture"] != seals or audit["original_role_receipts"]["ds26"] != 159 * 4:
        raise ValueError("integrated root loses its frozen all159 verification")
    verify.secant_full._verify_files(verify.SCREEN, audit["screening_seals"])
    compact, smooth = (read_predictions(COMPARISON / file) for file in (one, stock))
    for name, rows in ((COMPACT, compact), (SMOOTH, smooth)):
        verify.roster_matches(rows, inputs, name)
        for ident, row in rows.items():
            item = inputs[ident]
            (tile,) = item["regions"]
            verify.require_fields(row, dict(id=ident, method=name, tile=tile))
            if reason := item.get("unavailable"):
                verify.require_fields(
                    row, dict(native_sha256=None, catalog_sha256=None, input_sha256=None)
                )
                verify.require_fields(row["result"], dict(status="unavailable", reason=reason))
            else:
                verify.require_fields(
                    row,
                    dict(
                        native_sha256=item["native"]["sha256"],
                        catalog_sha256=item["catalog"]["sha256"],
                    ),
                )
                if not row.get("input_sha256") or row["result"]["status"] == "unavailable":
                    raise ValueError(f"{ident} was not measured against a bound solver input")
                if name == SMOOTH:
                    packet = native.bound_query(item)["packet"]
                    verify.require_fields(row, {"input_sha256": corpus._sha(encoded(packet))})
                archived_wall(row)
    return inputs, common, compact, smooth, audit


def verify_original_refs(inputs, common, audit):
    native_lock = verify.seal(NATIVE_REPORT, "all159-figure-lock.json", ("original-v5-audit.json",))
    receipts = verify.read(NATIVE_REPORT / "original-v5-audit.json")
    verify.roster_matches(native_lock["cases"], inputs, "original execution receipt authority")
    verify.roster_matches(receipts, inputs, "original execution receipts")
    sample_path = COMPARISON / "original-score-source.csv.gz"
    source = gzip.decompress(sample_path.read_bytes())
    expected = verify.read(corpus.FROZEN / "provenance.json")["sources"][SAMPLE]
    if (
        verify.sha(sample_path) != audit["original_score_archive_sha256"]
        or corpus._sha(source) != audit["original_score_sha256"]
        or audit["original_score_sha256"] != expected
    ):
        raise ValueError("original score bytes differ from the frozen published source")
    references = {row["id"]: row for row in corpus.references("ds26-all159")}
    entries = set()
    for row in csv.DictReader(io.StringIO(source.decode())):
        ident, role, arm = (row[name] for name in ("case", "method", "arm"))
        if ident not in inputs or row["query_id"] or role not in ROLES:
            continue
        fields = ident, role, arm
        if fields in entries:
            raise ValueError(f"duplicate frozen role {fields}")
        entries.add(fields)
        ref, receipt = references[ident]["reference"][role][arm], receipts[ident][role]
        coordinate = (
            [float(row[key]) for key in ("latitude_deg", "longitude_deg")]
            if row["latitude_deg"]
            else None
        )
        error = float(row["error_km"]) if row["error_km"] else None
        verify.require_fields(ref, dict(status=row["status"], latlon=coordinate, error_km=error))
        verify.require_fields(
            receipt, dict(status=row["worker_status"], request_sha256=row["worker_request_sha256"])
        )
        if (row["in_original_127"] == "1") != (ident in common) or len(
            receipt["execution_sha256"]
        ) != 64:
            raise ValueError(f"{ident}/{role} changed its receipt or common membership")
    if len(entries) != len(inputs) * len(ROLES) * len(ARMS):
        raise ValueError("original score authority does not cover the matched denominator")
    return references


def candidate_row(ident, compact, smooth, budget, absent):
    result = replay(compact, smooth, budget, absent=absent)
    source = {"compact": compact, "smooth": smooth}.get(result["selected"])
    return dict(
        result,
        id=ident,
        method=f"{METHOD}_{budget}s",
        total_s=budget,
        input_sha256=source["input_sha256"] if source else None,
        compact_input_sha256=compact["input_sha256"],
        smooth_input_sha256=smooth["input_sha256"],
        worker_attempted=bool(result["calls"]),
        **{key: smooth[key] for key in SHARED},
    )


def scores(records, references, common):
    for row in records:
        ref = references[row["id"]]
        for arm in ARMS:
            result, base = row["result"], ref["reference"]["baseline"][arm]
            endpoint = result["arms"][arm]
            error = distance_km(endpoint.get("latlon"), ref["truth"])
            yield dict(
                id=row["id"],
                method=row["method"],
                total_s=row.get("total_s"),
                arm=arm,
                cohort="common127" if row["id"] in common else "excluded32",
                status=result["status"],
                reason=result.get("reason"),
                selected=row["selected"],
                endpoint_source=row["endpoint_source"],
                latlon=endpoint.get("latlon"),
                error_km=error,
                forced_latlon=endpoint.get("forced_latlon"),
                forced_error_km=distance_km(endpoint.get("forced_latlon"), ref["truth"]),
                conditional_rf_rms_hz=endpoint.get("rf_rms_hz"),
                elapsed_s=row["elapsed_s"],
                elapsed_lower_bound_s=row.get("elapsed_lower_bound_s"),
                calls=row.get("calls"),
                worker_attempted=row["worker_attempted"],
                baseline_status=base["status"],
                baseline_error_km=base["error_km"],
                within_v5_10pct=verify.paired_threshold(error, base["error_km"], 1.10),
            )


def summary(rows):
    out = []
    for method in dict.fromkeys(row["method"] for row in rows):
        for arm in ARMS:
            for cohort in ("all159", "common127", "excluded32"):
                group = [
                    r
                    for r in rows
                    if r["method"] == method
                    and r["arm"] == arm
                    and cohort in ("all159", r["cohort"])
                ]
                errors = [r["error_km"] for r in group]
                out.append(
                    dict(
                        method=method,
                        arm=arm,
                        cohort=cohort,
                        scheduled=len(group),
                        statuses=Counter(r["status"] for r in group),
                        selected_last=Counter(r["selected"] for r in group),
                        published_by_solver=Counter(
                            r["endpoint_source"] for r in group if r["error_km"] is not None
                        ),
                        withheld_by_solver=Counter(
                            r["endpoint_source"] for r in group if r["status"] == "withheld"
                        ),
                        error_km=distribution(errors),
                        within_km=thresholds(errors),
                        elapsed_s=distribution(r["elapsed_s"] for r in group),
                        total_observed_elapsed_s=sum(
                            r["elapsed_s"] for r in group if r["elapsed_s"] is not None
                        ),
                        unresolved=sum(r["elapsed_lower_bound_s"] is not None for r in group),
                        paired_fixes=sum(
                            r["error_km"] is not None and r["baseline_error_km"] is not None
                            for r in group
                        ),
                        within_v5_10pct=sum(r["within_v5_10pct"] for r in group),
                        solver_rf_rms_hz={
                            name: distribution(
                                r["conditional_rf_rms_hz"]
                                for r in group
                                if r["endpoint_source"] == name
                            )
                            for name in ("compact", "smooth")
                        },
                    )
                )
    return out


def control_row(row, selected):
    present = row["result"]["status"] != "unavailable"
    return dict(
        row,
        selected=selected if present else "none",
        endpoint_source=selected if present else None,
        elapsed_s=archived_wall(row) if present else None,
        worker_attempted=present,
    )


def publish(output, inputs, positions):
    name = "positions.jsonl.gz"
    native.pack(output / name, positions)
    files = {
        key: verify.sha(output / key) for key in (name, "plan.json", "summary.json", "scores.csv")
    }
    seal = "prediction-lock.json"
    save_json(output / seal, dict(cases=list(inputs), files=files))
    charts = []
    for total in TOTALS:
        charts.append(
            dict(
                id=f"{METHOD}-{total}s",
                method=METHOD,
                scope="roof",
                cases="ds26-all159",
                title=f"Modeled DS26 deadline · {total} seconds",
                caption=(
                    "Historical post-capture worker intervals model the same operational router. "
                    "Compact keeps its first time slice. Smooth clock receives the remaining time "
                    "after a compact failure or timeout. Standalone controls retain archive caps."
                ),
                seal=seal,
                provenance=["plan.json", "summary.json", "scores.csv"],
                series=[
                    dict(key="one", label="Deadline router", value=f"{METHOD}_{total}s", file=name),
                    dict(
                        key="stock",
                        label="Archived compact",
                        value=COMPACT,
                        file=name,
                        match=["tile"],
                    ),
                    dict(
                        key="one_native_factors",
                        label="Archived smooth clock",
                        value=SMOOTH,
                        file=name,
                        match=["tile"],
                    ),
                ],
            )
        )
    save_json(output / "figures.json", dict(version=1, charts=charts))


def model(output):
    inputs, common, compact, smooth, audit = auth_archives()
    save_json(
        output / "plan.json",
        dict(
            total_s=list(TOTALS),
            reserve_s=RESERVE,
            cases=list(inputs),
            integrated_receipt_sha256=verify.sha(COMPARISON / "all159-figure-lock.json"),
            protocol_sha256=verify.sha(REPORT / "PROTOCOL.md"),
            router_source_sha256=verify.sha(Path(receiver.__file__)),
            model_source_sha256=verify.sha(Path(__file__)),
        ),
    )
    decisions = [
        candidate_row(ident, compact[ident], smooth[ident], total, bool(item.get("unavailable")))
        for total in TOTALS
        for ident, item in inputs.items()
    ]
    references = verify_original_refs(inputs, set(common), audit)
    controls = [
        control_row(row, key)
        for key, records in (("compact", compact), ("smooth", smooth))
        for row in records.values()
    ]
    positions = decisions + controls
    for row in positions:
        validate_result(row["result"])
    table = list(scores(positions, references, set(common)))
    csv_file(output / "scores.csv", table)
    save_json(
        output / "summary.json",
        dict(
            groups=summary(table),
            archived_original_role_receipts=159 * len(ROLES),
            boundary="Retrospective serial post-capture model of separately recorded host workers",
        ),
    )
    publish(output, inputs, positions)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=REPORT)
    model(local_output(parser.parse_args().out))


if __name__ == "__main__":
    main()
