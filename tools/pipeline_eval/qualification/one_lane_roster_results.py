"""Score the complete predeclared one-lane roster and publish standard position charts."""

import argparse
import gzip
from hashlib import sha256

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from ..scoring import ARMS, ROLES, distribution, validate_result
from . import complete_detector_roster as fixed
from . import one_lane_roster as trial
from . import screening_figures, staggered_benchmark
from .fresh_replay_results import sealed
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

REPORT = trial.REPORT
DIRECT = REPORT.with_name("one-lane-whole")


def released_stock(groups):
    prior = staggered_benchmark.prediction_rows(
        fixed.REPORT, "all-figure-lock.json", "all-positions.jsonl.gz", groups["reconstructed"]
    )
    fresh = staggered_benchmark.prediction_rows(
        trial.FRESH, "prediction-lock.json", "positions.jsonl.gz", groups["fresh"]
    )
    finite = fixed.select(prior, fixed.FOUR, groups["reconstructed"])
    new = fixed.select(fresh, "receiver_choice_four", groups["fresh"])
    return finite | {ident: dict(row, method=fixed.FOUR) for ident, row in new.items()}


def verify_rows(work, candidates, stock, plan):
    expected = {row["id"]: row for row in plan["jobs"]}
    if sorted(expected) != sorted(r["id"] for r in candidates) or set(expected) != set(stock):
        raise ValueError("position evidence must retain every scheduled 22-case attempt")
    timing = []
    for row in candidates:
        ident = row["id"]
        if any(row[key] != value for key, value in expected[ident].items()):
            raise ValueError(f"{ident} differs from its pre-scoring fit request")
        fixed.same_capture(row, stock[ident])
        result = row["result"]
        validate_result(result)
        stats = row.get("position_resources") or {}
        if ident not in plan["errors"]:
            directory = work / ident / trial.METHOD
            if (
                stock[ident]["native_sha256"] != row["stock_native_sha256"]
                or whole_iq.read(directory / "attempt.json") != row
            ):
                raise ValueError(f"{ident} terminal fit differs from its stock or worker receipt")
            whole_iq.checked(directory / "recording/native.json", row["native_sha256"])
            whole_iq.checked(directory / "recording/request.json", row["prepared_request_sha256"])
            log = whole_iq.checked(directory / "service.log", row["log_sha256"])
            write(REPORT / "logs" / f"{ident}.log.gz", gzip.compress(log.read_bytes(), mtime=0))
        if row["terminal"] == "success" and not stats:
            raise ValueError("successful worker lacks its true service measurements")
        for mark in (stats.get("start"), stats.get("end")):
            if mark and (
                mark["cpus"] != [row["cpu"]]
                or mark["memory.max"] != plan["memory_bytes"]
                or mark["memory.swap.max"]
                or mark["memory.swap.current"]
            ):
                raise ValueError("fit worker differs from the pinned no-swap limit")
        timing.append(
            dict(
                id=ident,
                dataset=ident[:4],
                cpu=row["cpu"],
                status=result["status"],
                terminal=row["terminal"],
                position_wall_s=stats.get("wall_s"),
                position_cpu_s=stats.get("cpu_s"),
                peak_bytes=stats.get("peak_bytes"),
                supervisor_wall_s=row.get("supervisor_wall_s"),
                gated_native_probes=row.get("positive_probes"),
                position_observations=result["metrics"].get("observations"),
                raw_detector_wall_s=None,
                raw_detector_cpu_s=None,
            )
        )
    return timing


def comparisons(rows, references):
    verdicts = fixed.scored(rows, references)
    lookup = {(r["id"], r["arm"]): r for r in verdicts if r["method"] == fixed.FOUR}
    for row in verdicts:
        error = row["error_km"]
        original = row["baseline_km"]
        stock = lookup[row["id"], row["arm"]]["error_km"]
        a, b = (
            100 * (error / reference - 1) if error is not None and reference else None
            for reference in (original, stock)
        )
        row.update(
            delta_pct_original=a,
            delta_pct_stock=b,
            within_symmetric_5pct_original=a is not None and abs(a) <= 5,
            within_symmetric_10pct_original=a is not None and abs(a) <= 10,
            at_most_5pct_above_stock=b is not None and b <= 5,
            at_most_10pct_above_stock=b is not None and b <= 10,
        )
    return verdicts


def group_metrics(verdicts, refs, groups):
    results = []
    for key, ids in groups.items():
        for arm in ARMS:
            rows = [r for r in verdicts if r["id"] in ids and r["arm"] == arm]
            for method in (trial.METHOD, fixed.FOUR, *ROLES):
                item = fixed.summary_row(rows, ids, key, arm, method)
                subset = [r for r in rows if r["method"] == method]
                rf = (
                    [r["rf_rms_hz"] for r in subset]
                    if subset
                    else [refs[ident]["reference"][method][arm].get("rf_rms_hz") for ident in ids]
                )
                dist = distribution(rf)
                results.append(
                    dict(
                        item,
                        rf_n=dist["n"],
                        rf_p50_hz=dist["p50"],
                        rf_p95_hz=dist["p95"],
                        within_symmetric_5pct_original=sum(
                            r["within_symmetric_5pct_original"] for r in subset
                        )
                        if subset
                        else None,
                        within_symmetric_10pct_original=sum(
                            r["within_symmetric_10pct_original"] for r in subset
                        )
                        if subset
                        else None,
                    )
                )
    return results


def figures(candidates, stock, generated_authority, generated_v5, groups):
    charts = []
    for key, title in (
        ("all", "One stock antenna on the complete 22-recording roof roster"),
        ("hard6", "One stock antenna on six earlier difficult recordings"),
        ("new2", "One stock antenna on two new lower-edge recordings"),
    ):
        ids = groups[key]
        name = f"{key}-matched-positions.jsonl.gz"
        pack(REPORT / name, [r for r in (*candidates, *stock.values()) if r["id"] in ids])
        references, _ = staggered_benchmark.export_references(
            REPORT, key, ids, generated_authority, generated_v5
        )
        files = (
            name,
            "prediction-lock.json",
            "scores.csv",
            "summary.csv",
            "resources.csv",
            "packet-audit.json",
            "projection-parity-lock.json",
            *references.values(),
        )
        receipt = f"{key}-figure-lock.json"
        save_json(REPORT / receipt, dict(cases=ids, files={p: _sha(REPORT / p) for p in files}))
        chart = dict(
            id=f"one-lane-roster-{key}",
            method=trial.METHOD,
            scope="roof",
            cases="sealed",
            title=title,
            seal=receipt,
            provenance=list(files[1:]),
            caption=(
                "One stored stock antenna per RF visit, both original physical probe slots, "
                "actual compact fits. Full stock was measured separately. Original v5 "
                "uses capture-era factors. All recordings are from one roof."
            ),
            series=[
                dict(
                    key="one",
                    file=name,
                    value=trial.METHOD,
                    native_field="paired_capture_sha256",
                    label="One stock antenna per valid visit",
                ),
                dict(
                    key="stock",
                    file=name,
                    value=fixed.FOUR,
                    native_field="paired_capture_sha256",
                    match=list(fixed.BINDINGS),
                    label="Both stock antennas",
                ),
            ],
        )
        if references:
            chart["roof_references"] = references
        charts.append(chart)
    save_json(REPORT / "figures.json", dict(version=2, charts=charts))
    screening_figures.generate(REPORT / "charts", evidence=REPORT)


def direct_parity(work, candidates):
    """Authenticate actual one-context native products against the frozen stock projection."""
    direct = sealed(DIRECT, "prediction-lock.json")
    parity = whole_iq.read(fixed.member(DIRECT, direct, "parity.json"))
    plan = whole_iq.read(fixed.member(DIRECT, direct, "source-lock.json"))
    raw = fixed.member(DIRECT, direct, "positions.jsonl.gz")
    actual = fixed.select(rows_from(raw), "one_lane_whole", direct["cases"])
    known = {r["id"]: r for r in candidates}
    findings = []
    for ident in direct["cases"]:
        row = known[ident]
        measured = actual[ident]
        fixed.same_capture(row, measured)
        own_native = whole_iq.checked(
            work / ident / trial.METHOD / "recording/native.json", row["native_sha256"]
        )
        proof = parity[ident]
        native = f"native/{ident}.json.gz"
        measured_blob = gzip.decompress(fixed.member(DIRECT, direct, native).read_bytes())
        digest = sha256(measured_blob).hexdigest()
        if (
            digest != proof["measured_native_sha256"].removeprefix("sha256:")
            or plan["cases"][ident]["control"]["native_sha256"] != row["stock_native_sha256"]
            or digest != measured["native_sha256"].removeprefix("sha256:")
        ):
            raise ValueError("direct IQ proof selected a different frozen stock authority")
        result, comparison = row["result"], measured["result"]
        arm_equal = {
            arm: all(
                result["arms"][arm].get(k) == comparison["arms"][arm].get(k)
                for k in ("latlon", "forced_latlon", "rf_rms_hz")
            )
            if result["status"] == comparison["status"] == "ok"
            else None
            for arm in ARMS
        }
        findings.append(
            dict(
                id=ident,
                direct_native_sha256=digest,
                projection_native_sha256=row["native_sha256"],
                source_stock_native_sha256=row["stock_native_sha256"],
                full_native_bytes_match=measured_blob == own_native.read_bytes(),
                valid_visits=row["valid_visits"],
                physical_probe_slots=2 * row["valid_visits"],
                direct_status=comparison["status"],
                projected_status=result["status"],
                matched_position_and_rf_by_arm=arm_equal,
            )
        )
    name = "direct-iq-parity.json"
    save_json(
        REPORT / name,
        dict(
            cases=findings,
            whole_prediction_sha256=_sha(DIRECT / "prediction-lock.json"),
            native_parity_sha256=_sha(DIRECT / "parity.json"),
            roster_prediction_sha256=_sha(REPORT / "prediction-lock.json"),
        ),
    )
    return name


def score(work):
    prediction = sealed(REPORT, "prediction-lock.json")
    plan = whole_iq.read(REPORT / "plan.json")
    projection = sealed(REPORT, "projection-parity-lock.json")
    original = plan["groups"]
    if prediction["cases"] != original["all"]:
        raise ValueError("sealed results differ from the complete scheduled roster")
    candidates = rows_from(REPORT / "positions.jsonl.gz")
    if any(
        projection["cases"][row["id"]]["native_sha256"] != row["native_sha256"]
        for row in candidates
        if row["id"] not in plan["errors"]
    ):
        raise ValueError("prepared worker document differs from the frozen projection check")
    stock = released_stock(original)
    timings = verify_rows(work, candidates, stock, plan)
    csv_file(REPORT / "resources.csv", timings)
    new_auth, new_pos = staggered_benchmark.fresh_references()
    new_keys = {r["id"] for r in new_auth}
    _, old = held_references(None, [i for i in original["all"] if i not in new_keys])
    _, fresh = staggered_benchmark.export_references(
        REPORT, "score", original["all"], new_auth, new_pos
    )
    for row in new_pos:
        for arm in ARMS:
            endpoint = row["result"]["arms"].get(arm, {})
            fresh[row["id"]]["reference"][row["method"]][arm]["rf_rms_hz"] = endpoint.get(
                "rf_rms_hz"
            )
    refs = {r["id"]: r for r in old} | fresh
    groups = dict(all=original["all"], hard6=original["difficult"], new2=original["fresh"])
    groups.update(
        {
            cohort: [i for i in original["all"] if i.startswith(cohort)]
            for cohort in ("DS26", "DS29")
        }
    )
    verdicts = comparisons([*candidates, *stock.values()], refs)
    csv_file(REPORT / "scores.csv", verdicts)
    csv_file(REPORT / "summary.csv", group_metrics(verdicts, refs, groups))
    optional = ()
    if (DIRECT / "prediction-lock.json").is_file():
        optional = (direct_parity(work, candidates),)
    figures(candidates, stock, new_auth, new_pos, groups)
    members = (
        "prediction-lock.json",
        "figures.json",
        "summary.csv",
        "scores.csv",
        "resources.csv",
        "projection-parity-lock.json",
        *optional,
        *(f"{g}-figure-lock.json" for g in ("all", "hard6", "new2")),
    )
    save_json(
        REPORT / "score-lock.json",
        dict(cases=prediction["cases"], files={name: _sha(REPORT / name) for name in members}),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    score(parser.parse_args().work)
