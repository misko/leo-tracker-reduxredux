"""Score every scheduled staggered outcome and verify its two native controls."""

import argparse
import gzip

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from ..scoring import (
    ARMS,
    ROLES,
    arm_outcome,
    distance_km,
    distribution,
    thresholds,
    validate_result,
)
from . import complete_detector_roster as roster
from . import screening_figures
from . import staggered_reconstruction_trial as trial
from .full_held_scores import held_references
from .full_v5_check import _sha
from .portable_gate_trials import compressed_rows
from .prefix_figures import csv_file
from .rescue_attribution import sealed
from .whole_pressure_trial import rows_from

REPORT = trial.REPORT
METHODS = (roster.FOUR, roster.FIVE, trial.METHOD)
read = whole_iq.read


def references(lock, cases):
    names = roster.REFS
    for member in names.values():
        keep = roster.member(roster.REPORT, lock, member)
        write(REPORT / member, keep.read_bytes())
    fresh = read(REPORT / names["authority"])["cases"]
    chosen = [x["id"] for x in fresh]
    if len(chosen) != 2 or set(chosen) - set(cases):
        raise ValueError("extended roster must retain both sealed new DS29 roofs")
    recent = screening_figures.new_roof_references(
        REPORT,
        lock,
        names,
        chosen,
    )
    for row in rows_from(REPORT / names["predictions"]):
        ref = recent[row["id"]]["reference"][row["method"]]
        for arm in ARMS:
            endpoint = row["result"].get("arms", {}).get(arm, {})
            ref[arm].update(latlon=endpoint.get("latlon"), rf_rms_hz=endpoint.get("rf_rms_hz"))
    _, old = held_references(None, [i for i in cases if i not in recent])
    return {r["id"]: r for r in old} | recent


def verified(work, plan, controls):
    path = sealed(REPORT, "prediction-lock.json", "positions.jsonl.gz")
    if len(plan["roster"]) != 20:
        raise ValueError("reconstruction did not retain the scheduled twenty")
    scheduled = {row["id"]: row for row in plan["scheduled"]}
    data = rows_from(path)
    if sorted(r["id"] for r in data) != sorted(plan["roster"]):
        raise ValueError("each scheduled case must remain visible exactly once")
    rows, receipts = {}, []
    for row in data:
        ident = row["id"]
        expected = scheduled[ident]
        four, five = (r[ident] for r in controls)
        if any(row[key] != planned for key, planned in expected.items()):
            raise ValueError("terminal result differed from frozen scientific input")
        validate_result(row["result"])
        if row["id"] in plan["excluded"]:
            if row["result"]["status"] != "unavailable":
                raise ValueError("prelaunch exclusion published an endpoint")
            rows[ident] = row
            continue
        if row["stock_native_sha256"] != four["native_sha256"] or (
            row["fifth_native_sha256"] != five["native_sha256"]
        ):
            raise ValueError("reconstruction used the wrong complete parents")
        leaf = work / ident / trial.METHOD
        if read(leaf / "attempt.json") != row:
            raise ValueError("sealed position differs from the actual service receipt")
        whole_iq.checked(leaf / "recording/native.json", row["native_sha256"])
        log = whole_iq.checked(leaf / "service.log", row["log_sha256"])
        write(REPORT / "logs" / f"{ident}.log.gz", gzip.compress(log.read_bytes(), mtime=0))
        sample = row["position_resources"] or {}
        for edge in ("start", "end"):
            if sample and (
                sample[edge]["cpus"] != [row["cpu"]]
                or sample[edge]["memory.max"] != plan["memory_bytes"]
                or sample[edge]["memory.swap.max"]
                or sample[edge]["memory.swap.current"]
            ):
                raise ValueError("physical service left the specified core or resource boundary")
        if row["terminal"] == "success" and not sample:
            raise ValueError("successful result lacks the post-acquisition timing witness")
        metrics = row["result"]["metrics"]
        if "observations" in metrics and metrics["observations"] != row["positive_probes"]:
            raise ValueError("actual native preparation did not retain the reconstructed winners")
        receipts.append(
            dict(
                id=ident,
                pin=row["cpu"],
                terminal=row["terminal"],
                status=row["result"]["status"],
                detector_cpu_s=None,
                detector_wall_s=None,
                position_cpu_s=sample.get("cpu_s"),
                position_wall_s=sample.get("wall_s"),
                supervisor_wall_s=row.get("supervisor_wall_s"),
                peak_bytes=sample.get("peak_bytes"),
                swap_bytes=sample.get("end", {}).get("memory.swap.current"),
            )
        )
        rows[ident] = row
    if plan["excluded"]:
        receipts.extend(
            dict(
                id=ident,
                pin=scheduled[ident]["cpu"],
                terminal="not-launched",
                status="unavailable",
                detector_cpu_s=None,
                detector_wall_s=None,
                position_cpu_s=None,
                position_wall_s=None,
                supervisor_wall_s=None,
                peak_bytes=None,
                swap_bytes=None,
            )
            for ident in plan["excluded"]
        )
    return rows, sorted(receipts, key=lambda row: row["id"])


def scores(rows, refs):
    table = []
    for row in rows:
        ident, method = row["id"], row["method"]
        result = row["result"]
        metrics = result["metrics"]
        ref = refs[ident]
        for arm in ARMS:
            value = result.get("arms", {}).get(arm, {})
            point = value.get("latlon")
            error = distance_km(point, ref["truth"])
            latitude, longitude = point or (None, None)
            status, _ = arm_outcome(result, value)
            original = {k: ref["reference"][k][arm].get("error_km") for k in ROLES}
            base = original["baseline"]
            table.append(
                dict(
                    id=ident,
                    method=method,
                    arm=arm,
                    status="withheld" if status == "ok" and point is None else status,
                    latitude=latitude,
                    longitude=longitude,
                    error_km=error,
                    conditional_rms_hz=value.get("rf_rms_hz"),
                    frequency_objective=metrics.get(f"{arm}_frequency_score"),
                    observations=metrics.get("observations"),
                    tracks=metrics.get("tracks"),
                    initial_branches=metrics.get("initial_branches"),
                    cavity_offered=metrics.get("cavity_offered"),
                    within_5pct_original=error is not None
                    and base is not None
                    and error <= 1.05 * base,
                    within_10pct_original=error is not None
                    and base is not None
                    and error <= 1.10 * base,
                    **{f"v5_{key}_error_km": score for key, score in original.items()},
                )
            )
    return table


def original_rows(refs, controls):
    table = []
    for ident, source in sorted(refs.items()):
        for role in ROLES:
            for arm in ARMS:
                fit = source["reference"][role][arm]
                latitude, longitude = fit.get("latlon") or (None, None)
                table.append(
                    dict(
                        id=ident,
                        mode=role,
                        arm=arm,
                        status=fit["status"],
                        capture_era_native_sha256=controls[ident]["paired_capture_sha256"],
                        latitude=latitude,
                        longitude=longitude,
                        error_km=fit.get("error_km"),
                        conditional_rms_hz=fit.get("rf_rms_hz"),
                    )
                )
    return table


def summary(rows, refs):
    out = {}
    for name in (*METHODS, *ROLES):
        out[name] = {}
        for arm in ARMS:
            subset = [r for r in rows if r["arm"] == arm and r["method"] == name]
            if name in ROLES:
                errors = [v["reference"][name][arm].get("error_km") for v in refs.values()]
                rms = [v["reference"][name][arm].get("rf_rms_hz") for v in refs.values()]
            else:
                errors = [r["error_km"] for r in subset]
                rms = [r["conditional_rms_hz"] for r in subset]
            out[name][arm] = dict(
                scheduled=len(errors),
                published=sum(e is not None for e in errors),
                horizontal_error_km=distribution(errors),
                within_km=thresholds(errors),
                conditional_rms_hz=distribution(rms),
                within_5pct_original=sum(r["within_5pct_original"] for r in subset)
                if subset
                else None,
                within_10pct_original=sum(r["within_10pct_original"] for r in subset)
                if subset
                else None,
            )
    return out


def pair_effects(table, ids):
    lookup = {(r["id"], r["arm"], r["method"]): r for r in table}
    rows = []

    def change(control, candidate, field):
        old, new = control[field], candidate[field]
        return new - old if old is not None and new is not None else None

    for ident in ids:
        for arm in ARMS:
            a, b, c = (lookup[ident, arm, method] for method in METHODS)
            rows.append(
                dict(
                    id=ident,
                    arm=arm,
                    error_vs_stock_km=change(a, c, "error_km"),
                    error_vs_fifth_km=change(b, c, "error_km"),
                    conditional_rms_vs_stock_hz=change(a, c, "conditional_rms_hz"),
                    conditional_rms_vs_fifth_hz=change(b, c, "conditional_rms_hz"),
                )
            )
    return rows


def paired_summary(rows):
    fields = (
        "error_vs_stock_km",
        "error_vs_fifth_km",
        "conditional_rms_vs_stock_hz",
        "conditional_rms_vs_fifth_hz",
    )
    summary = {}
    for arm in ARMS:
        changes = [row for row in rows if row["arm"] == arm]
        summary[arm] = {}
        for field in fields:
            values = [row[field] for row in changes if row[field] is not None]
            summary[arm][field] = dict(distribution(values), decreased=sum(x < 0 for x in values))
    return summary


def figure(cases):
    provenance = (
        "prediction-lock.json",
        "packet-audit.json",
        "scores.csv",
        "capture-era-v5.csv",
        "summary.json",
        "paired-effects.csv",
        "paired-summary.json",
        "raw-support.csv",
        "resources.csv",
        *roster.REFS.values(),
    )
    candidates, controls = "positions.jsonl.gz", "stock-fifth-positions.jsonl.gz"
    names = (candidates, controls, *provenance)
    save_json(
        REPORT / "figure-lock.json",
        dict(
            cases=cases,
            files={name: _sha(REPORT / name) for name in names},
        ),
    )
    matches = list(roster.BINDINGS)
    save_json(
        REPORT / "figures.json",
        dict(
            version=2,
            charts=[
                dict(
                    id="staggered-reconstructed-roof20",
                    method=trial.METHOD,
                    scope="roof",
                    cases="sealed",
                    seal="figure-lock.json",
                    roof_references=roster.REFS,
                    title="Alternating one fifth-region lane across the full roof roster",
                    caption=(
                        "Complete stored stock and fifth packets are selected per physical RF. "
                        "The candidate measures a new phase-release position fit. "
                        "Detector runtime is unavailable for this post-acquisition reconstruction."
                    ),
                    provenance=list(provenance),
                    series=[
                        dict(
                            file=file,
                            key=key,
                            value=method,
                            label=label,
                            native_field="paired_capture_sha256",
                            match=matches,
                        )
                        for file, key, method, label in (
                            (
                                candidates,
                                "one",
                                trial.METHOD,
                                "Alternating fifth region by RF and lane",
                            ),
                            (controls, "stock", roster.FOUR, "Complete four regions"),
                            (controls, "one_native_factors", roster.FIVE, "Complete fifth region"),
                        )
                    ],
                )
            ],
        ),
    )


def publish(work):
    plan = read(sealed(REPORT, "prediction-lock.json", "plan.json"))
    whole_iq.checked(roster.REPORT / "all-figure-lock.json", plan["parent_sha256"])
    lock, cases, four, five = trial.load_controls()
    reconstructed, timed = verified(work, plan, (four, five))
    refs = references(lock, cases)
    data = [r[k] for k in cases for r in (four, five, reconstructed)]
    records = scores(data, refs)
    write(
        REPORT / "stock-fifth-positions.jsonl.gz",
        compressed_rows(row for row in data if row["method"] != trial.METHOD),
    )
    audit = read(whole_iq.checked(REPORT / "packet-audit.json", plan["packet_audit_sha256"]))
    raw = []
    for ident in cases:
        details = audit.get(ident, {})
        raw.append(
            dict(
                id=ident,
                excluded_reason=plan["excluded"].get(ident),
                **{
                    key: details.get(key)
                    for key in (
                        "scheduled_visits",
                        "valid_visits",
                        "invalid_visits",
                        "stock_positive",
                        "fifth_positive",
                        "staggered_positive",
                        "staggered_receiver0_positive",
                        "staggered_receiver1_positive",
                        "new_positive_vs_stock",
                        "lost_positive_vs_stock",
                        "changed_winners_vs_stock",
                        "stock_candidate_rows",
                        "fifth_candidate_rows",
                        "staggered_candidate_rows",
                        "staggered_gated_candidates",
                    )
                },
            )
        )
    csv_file(REPORT / "scores.csv", records)
    csv_file(REPORT / "capture-era-v5.csv", original_rows(refs, four))
    csv_file(REPORT / "resources.csv", timed)
    differences = pair_effects(records, cases)
    csv_file(REPORT / "paired-effects.csv", differences)
    save_json(REPORT / "paired-summary.json", paired_summary(differences))
    csv_file(REPORT / "raw-support.csv", raw)
    save_json(REPORT / "summary.json", summary(records, refs))
    figure(cases)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    publish(parser.parse_args().work)
