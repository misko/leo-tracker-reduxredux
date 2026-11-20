"""Join sealed native measurements to all four original v5 role receipts."""

import argparse
import csv
import io
import json
from collections import Counter
from pathlib import Path

from .. import corpus
from ..__main__ import encoded, local_output, read_predictions, save_json
from ..scoring import ARMS, ROLES, distance_km, distribution, thresholds
from . import full_receiver_comparison as shared
from . import roof_selection_native as trial
from .prefix_figures import csv_file
from .v5_postfit import ARCHIVE

SAMPLE = "reports/2026_11_18_v5_blind_comparison/sample-errors.csv"
ALL_POSITIONS = "positions.jsonl.gz"
EXCLUDED_POSITIONS = "excluded-positions.jsonl.gz"


def validate_native(row, query, *, fresh=False):
    if "unavailable" in query:
        if row != trial.unavailable(query):
            raise ValueError(f"{query['id']} lacks its frozen absent-native reason")
        return
    expected = trial.clock.bindings(query)
    expected.pop("cohort")
    shared.require_fields(row, expected)
    result = row["result"]
    status = result["status"]
    if set(result.get("arms", {})) != set(ARMS):
        raise ValueError(f"{row['id']} lost a calibration arm")
    if fresh and (
        row["worker_attempted"] != (status != "missing")
        or (row["worker_attempted"] and row["cpu"] not in trial.CPUS)
    ):
        raise ValueError(f"{row['id']} disagrees with the dispatch receipt")
    if status in ("ok", "withheld") and (
        not row.get("observation_sha256")
        or row["address_space_limit_mib"] != 512
        or not 0 < row["proc_memory_kib"]["VmPeak"] <= 512 * 1024
        or not result["metrics"].get("fixed_assignment_clock")
        or not {"archive_and_peak_selection", "graph", "clock_backend"} <= row["stages"].keys()
        or any("localization_v3" in p or "/v5_" in p for p in row["imported_first_party"])
    ):
        raise ValueError(f"{row['id']} was not a complete source-bound native clock worker")


def native_rows(output, inputs, common, order, seals):
    fresh = shared.seal(output, "fresh-lock.json", (trial.RAW, "plan.json"))
    plan = shared.read(output / "plan.json")
    archive = trial.clock.REPORT
    parent_lock = shared.seal(archive, "prediction-lock.json", ("positions.jsonl.gz", "plan.json"))
    parent = shared.read(archive / "plan.json")
    shared.require_fields(
        plan,
        dict(
            all159=list(inputs),
            common127=common,
            excluded32=order,
            input_inventory_sha256=seals["inputs.jsonl"],
            panel_inventory_sha256=seals["panels.json"],
            jobs=[trial.bound_query(inputs[i]) for i in order],
            source=parent["source"],
            runner_sha256=shared.sha(Path(trial.__file__)),
            parent_prediction_lock_sha256=shared.sha(archive / "prediction-lock.json"),
            protocol_sha256=shared.sha(trial.REPORT / "PROTOCOL.md"),
        ),
    )
    samples = read_predictions(output / trial.RAW)
    shared.roster_matches(samples, order, "complement replay")
    shared.require_fields(
        fresh,
        dict(
            cases=order,
            attempted=sum(r["worker_attempted"] for r in samples.values()),
            statuses=dict(Counter(r["result"]["status"] for r in samples.values())),
        ),
    )
    if not 0 < fresh["wall_s"] <= plan["wall_cap_s"] <= trial.WALL_CAP_S:
        raise ValueError("complement timing exceeded the sealed cap")
    for query in plan["jobs"]:
        validate_native(samples[query["id"]], query, fresh=True)
    old = read_predictions(archive / "positions.jsonl.gz")
    shared.roster_matches(old, parent_lock["cases"], "native archive")
    selected = {
        key: r for key, r in old.items() if r["cohort"] == "roof" and key.startswith("DS26-")
    }
    shared.roster_matches(selected, common, "archived common127")
    parent_queries = {q["id"]: q for q in parent["cases"]}
    for ident, row in selected.items():
        query = trial.bound_query(inputs[ident])
        shared.require_fields(parent_queries[ident], dict(query, cohort="roof"))
        validate_native(row, query)
    return {
        ident: normalize(samples[ident] if ident in samples else selected[ident], ident in samples)
        for ident in inputs
    }


def normalize(row, fresh):
    return dict(
        row,
        method=trial.METHOD,
        parent_method=trial.clock.METHOD,
        cohort="excluded32" if fresh else "common127",
        measurement="fresh_excluded32" if fresh else "sealed_common127",
        worker_attempted=row.get("worker_attempted", True),
    )


def original_request(path, item, role, digest):
    if "unavailable" in item:
        if path.exists() or digest != "sha256:" + corpus._sha(b"null"):
            raise ValueError(f"{item['id']} unexpected request on absent native input")
        return
    raw = path.read_bytes()
    request = json.loads(raw)
    (tile,) = item["regions"]
    job = request["job"]
    expected = "sha256:" + corpus._sha(encoded(request))
    snapshot = max(
        (int(name.split("-")[0]), value.removeprefix("sha256:"))
        for name, value in request["causal_snapshots"].items()
        if int(name.split("-")[0]) < item["cutoff_utc_ns"]
    )
    if (
        request["role"] != role
        or expected != digest
        or (role == "baseline" and corpus._sha(raw) != item["request"]["sha256"])
        or job["identity"]["session_id"] != item["session_id"]
        or job["evaluation_reference"] is not None
        or job["search_center"] != tile["center"]
        or job["native_input"]["sha256"] != "sha256:" + item["native"]["sha256"]
        or job["track_config"]["sha256"] != "sha256:" + item["track_config"]["sha256"]
        or snapshot != (item["catalog_timestamp_ns"], item["catalog"]["sha256"])
        or request["source"]["sha256"] != shared.secant_full.phase.v5_lean.SOURCE_SHA256
    ):
        raise ValueError(f"{item['id']}/{role} original request differs from the frozen inputs")


def verify_originals(inputs, references, common):
    proof = shared.read(corpus.FROZEN / "provenance.json")
    raw = (corpus.REPO / SAMPLE).read_bytes()
    if corpus._sha(raw) != proof["sources"][SAMPLE]:
        raise ValueError("published original score source differs from its freeze provenance")
    historical = {}
    for row in csv.DictReader(io.StringIO(raw.decode())):
        key = row["case"], row["method"], row["arm"]
        if row["panel"] == "DS26" and not row["query_id"] and key[0] in inputs and key[1] in ROLES:
            if key in historical:
                raise ValueError(f"duplicate original scored arm {key}")
            historical[key] = row
    if len(historical) != len(inputs) * len(ROLES) * len(ARMS):
        raise ValueError("original archived roles do not cover every joined case and arm")
    compact_dir = shared.secant_full.REPORT
    shared.seal(compact_dir, "receipt.json", ("original-v5-inputs.json",))
    common_locks = shared.read(compact_dir / "original-v5-inputs.json")
    verified = {}
    for ident, item in inputs.items():
        ref, directory = references[ident], ARCHIVE / f"{ident}-r0"
        per_role = {}
        for role in ROLES:
            path = directory / f"{role}-execution.json"
            blob = path.read_bytes()
            receipt, checksum = json.loads(blob), corpus._sha(blob)
            digest = receipt["request_sha256"]
            if ident in common:
                shared.require_fields(
                    common_locks[ident][role],
                    dict(request_sha256=digest, execution_sha256=checksum),
                )
            original_request(directory / role / "experimental-request.json", item, role, digest)
            status = receipt["status"]
            process = receipt.get("process", {})
            worker = receipt.get("worker", {})
            points = worker.get("arms", {})
            if receipt["role"] != role or (status == "complete" and set(points) != set(ARMS)):
                raise ValueError(f"{ident}/{role} original execution identity or arms changed")
            for arm in ARMS:
                row, target = historical[ident, role, arm], ref["reference"][role][arm]
                expected = "fix" if status == "complete" else status
                latlon = points.get(arm, {}).get("endpoint_latlon")
                if (
                    row["worker_status"] != status
                    or row["worker_request_sha256"] != digest
                    or int(row["in_original_127"]) != (ident in common)
                    or row["status"] != expected
                    or target["status"] != expected
                    or target["latlon"] != latlon
                    or target["wall_s"] != process.get("wall_seconds")
                    or (status == "complete" and worker["request_sha256"] != digest)
                    or (
                        latlon is not None
                        and abs(distance_km(latlon, ref["truth"]) - target["error_km"]) > 1e-6
                    )
                ):
                    raise ValueError(
                        f"{ident}/{role}/{arm} original archive differs from frozen scores"
                    )
            per_role[role] = dict(
                status=status,
                request_sha256=digest,
                execution_sha256=checksum,
                cpu_s=process.get("cpu_seconds"),
                cpu_complete=process.get("cpu_complete"),
            )
        verified[ident] = per_role
    return verified


def proximity(native, original):
    return native is not None and original is not None and native <= 1.1 * original


def per_arms(records, refs, audited):
    for ident, record in records.items():
        ref, decision = refs[ident], record["result"]
        for arm in ARMS:
            point = decision["arms"][arm]
            error = distance_km(point["latlon"], ref["truth"])
            forced = point.get("forced_latlon")
            memory = record.get("proc_memory_kib", {})
            row = dict(
                id=ident,
                cohort=record["cohort"],
                arm=arm,
                status=decision["status"],
                reason=decision["reason"],
                latlon=point["latlon"],
                forced_latlon=forced,
                error_km=error,
                forced_error_km=distance_km(forced, ref["truth"]),
                conditional_rf_rms_hz=point.get("rf_rms_hz"),
                worker_attempted=record["worker_attempted"],
                cpu=record.get("cpu"),
                worker_cpu_s=record.get("worker", {}).get("cpu_s"),
                worker_wall_s=record.get("worker_wall_s"),
                peak_rss_kib=memory.get("VmHWM"),
                peak_virtual_kib=memory.get("VmPeak"),
                input_sha256=record["input_sha256"],
                observation_sha256=record.get("observation_sha256"),
                native_sha256=record["native_sha256"],
                catalog_sha256=record["catalog_sha256"],
            )
            for role in ROLES:
                old = ref["reference"][role][arm]
                for key in ("status", "latlon", "error_km", "wall_s", "rf_rms_hz"):
                    row[f"{role}_{key}"] = old[key]
                row[f"{role}_cpu_s"] = audited[ident][role]["cpu_s"]
                row[f"{role}_cpu_complete"] = audited[ident][role]["cpu_complete"]
                row[f"{role}_within_10pct"] = proximity(error, old["error_km"])
            yield row


def summarize(rows):
    groups = []
    for cohort in ("all159", "common127", "excluded32"):
        for arm in ARMS:
            part = [r for r in rows if r["arm"] == arm and cohort in ("all159", r["cohort"])]
            native = [r["error_km"] for r in part]
            original = {}
            for role in ROLES:
                old = [r[f"{role}_error_km"] for r in part]
                pairs = list(zip(native, old, strict=True))
                original[role] = dict(
                    statuses=dict(Counter(r[f"{role}_status"] for r in part)),
                    published=sum(e is not None for e in old),
                    error_km=distribution(old),
                    paired_fixes=sum(x is not None and y is not None for x, y in pairs),
                    native_within_10pct=sum(proximity(x, y) for x, y in pairs),
                    native_only=sum(x is not None and y is None for x, y in pairs),
                    original_only=sum(x is None and y is not None for x, y in pairs),
                )
            groups.append(
                dict(
                    cohort=cohort,
                    arm=arm,
                    offered=len(part),
                    statuses=dict(Counter(r["status"] for r in part)),
                    worker_attempts=sum(r["worker_attempted"] for r in part),
                    published=sum(e is not None for e in native),
                    within_km=thresholds(native),
                    error_km=distribution(native),
                    originals=original,
                    **{
                        key: distribution(r[key] for r in part)
                        for key in (
                            "forced_error_km",
                            "conditional_rf_rms_hz",
                            "worker_cpu_s",
                            "worker_wall_s",
                            "peak_rss_kib",
                            "peak_virtual_kib",
                        )
                    },
                )
            )
    return groups


def calibration(rows):
    d = {(r["id"], r["arm"]): r for r in rows}
    result = {}
    for cohort in ("all159", "common127", "excluded32"):
        pairs = [
            (r, d[r["id"], "fitted_c"])
            for r in rows
            if r["arm"] == "c0" and cohort in ("all159", r["cohort"])
        ]
        scored = [
            (a["error_km"], b["error_km"])
            for a, b in pairs
            if a["error_km"] is not None and b["error_km"] is not None
        ]
        rms = [
            (a["conditional_rf_rms_hz"], b["conditional_rf_rms_hz"])
            for a, b in pairs
            if a["conditional_rf_rms_hz"] is not None and b["conditional_rf_rms_hz"] is not None
        ]
        result[cohort] = dict(
            paired_positions=len(scored),
            fitted_geographic_improved=sum(b < a for a, b in scored),
            fitted_minus_c0_error_km=distribution(b - a for a, b in scored),
            paired_conditional_rms=len(rms),
            fitted_minus_c0_conditional_rf_rms_hz=distribution(b - a for a, b in rms),
        )
    return result


def figures(output, records, audit_files):
    charts = []
    for cohort, selector, title, name in (
        (
            "all159",
            "ds26-all159",
            "Native smooth clock · all 159 DS26",
            ALL_POSITIONS,
        ),
        (
            "excluded32",
            "ds26-excluded32",
            "Native smooth clock · 32 excluded DS26",
            EXCLUDED_POSITIONS,
        ),
    ):
        cases = [i for i, r in records.items() if cohort == "all159" or r["cohort"] == "excluded32"]
        receipt = f"{cohort}-figure-lock.json"
        save_json(
            output / receipt,
            dict(cases=cases, files={**audit_files, name: shared.sha(output / name)}),
        )
        charts.append(
            dict(
                id=f"{trial.METHOD}-{cohort}",
                method=trial.METHOD,
                scope="roof",
                cases=selector,
                title=title,
                caption=(
                    "Both calibration arms use the full frozen recording roster. Attempt counts "
                    "retain original v5 timeouts and failures, and one absent native input."
                ),
                seal=receipt,
                provenance=list(audit_files),
                series=[
                    dict(key="one", label="Native smooth clock", value=trial.METHOD, file=name)
                ],
            )
        )
    save_json(output / "figures.json", dict(version=1, charts=charts))


def score(output):
    inputs, common, order, seals = trial.roster()
    records = native_rows(output, inputs, common, order, seals)
    refs = {r["id"]: r for r in corpus.references("ds26-all159")}
    shared.roster_matches(refs, inputs, "all159 score labels")
    audited = verify_originals(inputs, refs, set(common))
    save_json(output / "original-v5-audit.json", audited)
    rows = list(per_arms(records, refs, audited))
    csv_file(output / "scores.csv", rows)
    csv_file(output / "excluded-scores.csv", [r for r in rows if r["cohort"] == "excluded32"])
    trial.pack(output / ALL_POSITIONS, records.values())
    trial.pack(
        output / EXCLUDED_POSITIONS, [records[ident] for ident in inputs if ident in set(order)]
    )
    save_json(
        output / "summary.json",
        dict(
            replay=shared.read(output / "fresh-lock.json"),
            groups=summarize(rows),
            calibration=calibration(rows),
        ),
    )
    save_json(
        output / "analysis-sources.json",
        dict(
            frozen_fixture=seals,
            original_score_source=SAMPLE,
            original_score_source_sha256=shared.sha(corpus.REPO / SAMPLE),
            archived_parent_prediction_lock_sha256=shared.sha(
                trial.clock.REPORT / "prediction-lock.json"
            ),
            score_join_sha256=shared.sha(Path(__file__)),
        ),
    )
    figures(
        output,
        records,
        {
            name: shared.sha(output / name)
            for name in (
                "fresh-lock.json",
                "original-v5-audit.json",
                "summary.json",
                "analysis-sources.json",
            )
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=trial.REPORT)
    score(local_output(parser.parse_args().out))


if __name__ == "__main__":
    main()
