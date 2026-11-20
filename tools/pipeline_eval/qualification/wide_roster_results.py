"""Normalize sealed stock whole-IQ attempts, then score the predeclared recording roster."""

import argparse
import gzip
import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from .. import iq_service, whole_iq
from ..__main__ import encoded, local_output, save_json
from ..scoring import ARMS, ROLES, distance_km, distribution, validate_result
from . import wide_roster as trial
from .full_held_scores import held_references
from .full_v5_check import _load_case, _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

PRIMARY, FIRST = "wide_iq_roster_primary", "wide_iq_roster_original_first"
COMMON = (
    "input_manifest_sha256",
    "raw_authority",
    "clock_sha256",
    "excluded_sha256",
    "probes_sha256",
)


def verified_sources(study, pin):
    seal = whole_iq.read(
        whole_iq.checked(study.folder / "prediction-lock.json", pin["prediction_sha256"])
    )
    if seal["files"]["source-lock.json"] != pin["source_sha256"]:
        raise ValueError("study source is outside the declared roster")
    return seal, whole_iq.read(
        whole_iq.checked(study.folder / "source-lock.json", pin["source_sha256"])
    )


def manifested_receiver(root, hashes):
    path = whole_iq.checked(root / "native/manifest.json", hashes["native/manifest.json"])
    return json.loads(path.read_text().replace(str(root), "<receiver-root>"))


def same_receiver(stock, base, root):
    manifest = "native/manifest.json"
    reference = base["receiver_files"]
    if stock.keys() != reference.keys() or any(
        stock[k] != reference[k] for k in reference if k != manifest
    ):
        raise ValueError("stock phase-release changed bundled source or native code")
    if stock[manifest] != reference[manifest] and manifested_receiver(
        root, stock
    ) != manifested_receiver(Path(base["receiver"]), reference):
        raise ValueError("only phase-release installation paths may change")


def same_case(row, source_case, case):
    if (
        source_case["recording"] != case["recording"]
        or row["tile"] != source_case["tile"]
        or row["tile"] != case["regions"][0]
        or row["tile"].get("width_km", 25) != 25
        or row["catalog_sha256"] != case["catalog"]["sha256"]
        or source_case["catalog_sha256"] != case["catalog"]["sha256"]
        or source_case.get("request_sha256", source_case.get("frozen_request_sha256"))
        != case["request"]["sha256"]
        or row.get("original_request_sha256", case["request"]["sha256"])
        != case["request"]["sha256"]
    ):
        raise ValueError("measurement changed record, tile, request or catalogue")


def whole_support(measurement, case, clock):
    counts = measurement["counts"]
    if (
        counts["recording_windows"] != case["recording"]["window_count"]
        or counts["processed_windows"] + counts["invalid_capture"] != counts["recording_windows"]
        or counts["processed_windows"] != measurement["dual_calls"]
        or counts["probe_rows"] != 2 * counts["processed_windows"]
        or counts["iq_bytes"] != 1_600_000 * counts["recording_windows"]
        or measurement["input_manifest_sha256"] != clock
        or any(not measurement[key] for key in COMMON)
    ):
        raise ValueError("service did not cover the complete received IQ and original exclusions")


def cgroup_stages(measurement):
    stages = measurement["stages"]
    if not stages or any(
        mark["cgroup"] != stages[0]["cgroup"]
        or mark["memory.max"] != whole_iq.MEMORY
        or mark["memory.swap.max"] != 0
        or mark["memory.swap.current"] != 0
        for mark in stages
    ):
        raise ValueError("service departed from the capped zero-swap boundary")
    if any(m["monotonic_s"] < p["monotonic_s"] for p, m in zip(stages, stages[1:], strict=False)):
        raise ValueError("service lifecycle reads out of order")


def case_timing(measurement):
    return dict(
        {
            key: measurement.get(key)
            for key in (
                "wall_s",
                "cpu_s",
                "raw_s",
                "position_s",
                "assembly_s",
                "wall_to_failure_s",
                "cpu_to_failure_s",
                "max_bytes",
                "charged_peak_to_failure_bytes",
                "dual_calls",
                "within_20ms",
                "detector_call_wall_ms",
                "detector_call_cpu_ms",
            )
        },
        service_wall_s=measurement["service"].get("service_wall_s"),
    )


def check_archive(study, seal, row, resource, case, repeated):
    ident = row["id"]
    compressed = (
        f"native/{ident}.json.gz" if study.branch == "wide" else f"native/control/{ident}.json.gz"
    )
    if compressed in seal["files"]:
        path = whole_iq.checked(study.folder / compressed, seal["files"][compressed])
        raw = gzip.decompress(path.read_bytes())
        evidence = str(path.relative_to(trial.SCREEN))
    elif binding := resource["service"].get("binding"):
        out = Path(binding["attempt"])
        whole_iq.checked(out / "plan.json", binding["plan_sha256"])
        path = whole_iq.checked(out / "recording/native.json", row["native_sha256"])
        raw = path.read_bytes()
        evidence = str(path)
    else:
        original = repeated[ident]
        if row["native_sha256"] != original["native_sha256"] or any(
            original[key] != resource[key] for key in COMMON
        ):
            raise ValueError(
                "repeat does not authenticate against the sealed identical stock archive"
            )
        return original["native_archive"]
    if sha256(raw).hexdigest() != row["native_sha256"]:
        raise ValueError("native archive differs from replay result")
    doc = json.loads(raw)
    if (
        doc["source"]["session_id"] != case["session_id"]
        or doc["source"]["input_manifest_sha256"] != resource["input_manifest_sha256"]
        or doc["provenance"]["detector_sha256"] != "sha256:" + trial.STOCK_SHA
    ):
        raise ValueError("native replay factors do not bind the exact original stock detector")
    return evidence


def whole_winner_resource(row, source, base):
    out = Path(row["service"]["binding"]["attempt"])
    plan = whole_iq.read(
        whole_iq.checked(out / "plan.json", row["service"]["binding"]["plan_sha256"])
    )
    raw = whole_iq.read(out / "raw.json")
    stock = source["bindings"]["stock"]
    if (
        plan["receiver_files"] != stock
        or plan["native_sources"] != base["native_sources"]
        or plan["capture_era_request"] != source["cases"][row["id"]]["frozen_request_sha256"]
        or plan["detector_sha256"] != trial.STOCK_SHA
        or plan["limit_s"] != source["limit_s"]
    ):
        raise ValueError("whole-winner stock plan differs from its sealed common receiver")
    same_receiver(stock, base, Path(plan["receiver"]))
    stages = [row[k] for k in ("start", "raw_end", "position_start", "end") if row.get(k)]
    if any(raw[k] != row["decoder_provenance"][k] for k in COMMON):
        raise ValueError("whole-winner stock support differs from sealed projections")
    start, raw_end, position, end = stages
    times = [timing for lane in raw["lanes"] for timing in lane["native_timings_s"]]
    return dict(
        raw,
        service=row["service"],
        stages=stages,
        detector_sha256=trial.STOCK_SHA,
        dual_calls=len(times),
        within_20ms=sum(wall <= 0.02 for wall, _ in times),
        detector_call_wall_ms=distribution(wall * 1000 for wall, _ in times),
        detector_call_cpu_ms=distribution(cpu * 1000 for _, cpu in times),
        wall_s=end["monotonic_s"] - start["monotonic_s"],
        raw_s=raw_end["monotonic_s"] - start["monotonic_s"],
        assembly_s=position["monotonic_s"] - raw_end["monotonic_s"],
        position_s=end["monotonic_s"] - position["monotonic_s"],
        cpu_s=(end["cpu.stat.usage_usec"] - start["cpu.stat.usage_usec"]) / 1e6,
        max_bytes=end["memory.peak"],
    )


def input_metadata(case):
    cutoff = case.get("cutoff_utc_ns")
    catalog = case.get("catalog_timestamp_ns")
    return dict(
        cutoff_utc=datetime.fromtimestamp(cutoff / 1e9, UTC).isoformat() if cutoff else None,
        causal_catalogue_age_h=(cutoff - catalog) / 3.6e12
        if cutoff and catalog and cutoff >= catalog
        else None,
    )


def normalize(study, pin, base, cases, repeated):
    seal, source = verified_sources(study, pin)
    folder = study.folder
    if study.branch == "stock":
        detector, memory, swap = (source[k] for k in ("detector_sha256", "memory", "swap"))
        receiver = source["bindings"]["stock"]
    else:
        detector = source["detectors"][study.branch]["sha256"]
        memory, swap = source["memory_max"], source["swap_max"]
        receiver = source["receiver_files"]
        same_receiver(receiver, base, Path(source["receiver"]))
        if source["native_sources"] != base["native_sources"]:
            raise ValueError("stock compile inputs changed")
    if (detector, memory, swap) != (trial.STOCK_SHA, whole_iq.MEMORY, 0):
        raise ValueError("recording service lacks the declared stock binary and resource cap")
    method = f"{study.prefix}_control" if study.branch == "control" else study.prefix
    predictions = rows_from(
        whole_iq.checked(folder / "positions.jsonl.gz", seal["files"]["positions.jsonl.gz"])
    )
    stock_rows = [row for row in predictions if row["method"] == method]
    if sorted(row["id"] for row in stock_rows) != sorted(pin["cases"]):
        raise ValueError("stock attempts do not match the sealed source roster")
    data = (
        whole_iq.read(whole_iq.checked(folder / "resources.json", seal["files"]["resources.json"]))
        if study.branch != "stock"
        else {}
    )
    for row in stock_rows:
        ident = row["id"]
        case, source_case = cases[ident], source["cases"][ident]
        same_case(row, source_case, case)
        validate_result(row["result"])
        if study.branch == "stock":
            resource = whole_winner_resource(row, source, base)
        else:
            resource = data[ident] if study.branch == "wide" else data[ident][study.branch]
        cgroup_stages(resource)
        service = resource["service"]
        if (row["result"]["status"] in {"ok", "withheld"}) != iq_service.succeeded(service):
            raise ValueError("recorded terminal service is inconsistent with the prediction")
        clock = source_case.get("clock_authority") or repeated[ident]["input_manifest_sha256"]
        whole_support(resource, case, clock)
        evidence = check_archive(study, seal, row, resource, case, repeated)
        if study.branch != "stock" and resource["detector_sha256"] != detector:
            raise ValueError("service detector differs from the sealed build")
        yield dict(
            id=ident,
            study=study.name,
            branch=study.branch,
            method=method,
            study_prediction_sha256=pin["prediction_sha256"],
            study_source_sha256=pin["source_sha256"],
            execution_plan_sha256=service.get("binding", {}).get("plan_sha256"),
            receiver_files_sha256=sha256(encoded(receiver)).hexdigest(),
            detector_sha256=detector,
            native_sha256=row["native_sha256"],
            native_archive=evidence,
            started_monotonic_s=resource["stages"][0]["monotonic_s"],
            deadline_s=source["limit_s"],
            memory_max_bytes=memory,
            swap_limit_bytes=swap,
            full_raw_verified=True,
            service_unit=service["unit"],
            service_log_sha256=service["log_sha256"],
            service_result=service["systemd"].get("Result"),
            original_request_sha256=case["request"]["sha256"],
            catalog_sha256=case["catalog"]["sha256"],
            capture_era_native_sha256=case["native"]["sha256"],
            tile=row["tile"],
            **{k: resource[k] for k in COMMON},
            **case_timing(resource),
            **input_metadata(case),
            cpu_pins=resource["stages"][0]["cpus"],
            result=row["result"],
        )


def whole_winner_initial(study, pin, case, base):
    seal, source = verified_sources(study, pin)
    first = whole_iq.read(
        whole_iq.checked(study.folder / "initial-launch.json", seal["files"]["initial-launch.json"])
    )
    service = first["result"]
    attempt = Path(service["binding"]["attempt"])
    plan_sha = service["binding"]["plan_sha256"]
    plan = whole_iq.read(whole_iq.checked(attempt / "plan.json", plan_sha))
    state = service["systemd"]
    if (
        plan_sha != first["plan_sha256"]
        or plan["case"] != case["id"]
        or plan["capture_era_request"] != case["request"]["sha256"]
        or plan["detector_sha256"] != trial.STOCK_SHA
        or plan["native_sources"] != base["native_sources"]
        or plan["recording"] != case["recording"]
        or plan["limit_s"] != source["limit_s"]
        or state["MainPID"] != "0"
        or state["ControlPID"] != "0"
        or state["MemoryMax"] != str(whole_iq.MEMORY)
        or state["MemorySwapMax"] != "0"
        or (attempt / "raw.json").exists()
        or (attempt / "end.json").exists()
        or (attempt / "recording/native.json").exists()
    ):
        raise ValueError("initial setup failure is outside the stock capped service")
    same_receiver(plan["receiver_files"], base, Path(plan["receiver"]))
    whole_iq.checked(attempt / "service.log", service["log_sha256"])
    return dict(
        id=case["id"],
        study=study.name,
        branch="stock-initial-setup",
        method=study.prefix,
        study_prediction_sha256=pin["prediction_sha256"],
        study_source_sha256=first["study_sha256"],
        execution_plan_sha256=plan_sha,
        receiver_files_sha256=sha256(encoded(plan["receiver_files"])).hexdigest(),
        detector_sha256=trial.STOCK_SHA,
        service_unit=service["unit"],
        service_log_sha256=service["log_sha256"],
        service_result=state["Result"],
        started_monotonic_s=service["monotonic"]["active_enter_usec"] / 1e6,
        deadline_s=plan["limit_s"],
        memory_max_bytes=whole_iq.MEMORY,
        swap_limit_bytes=0,
        full_raw_verified=False,
        service_wall_s=service["service_wall_s"],
        wall_to_failure_s=service["service_wall_s"],
        cpu_to_failure_s=int(state["CPUUsageNSec"]) / 1e9,
        charged_peak_to_failure_bytes=int(state["MemoryPeak"]),
        original_request_sha256=case["request"]["sha256"],
        catalog_sha256=case["catalog"]["sha256"],
        capture_era_native_sha256=case["native"]["sha256"],
        tile=case["regions"][0],
        cpu_pins=plan["cpus"],
        **input_metadata(case),
        result=dict(
            status="failed",
            reason=first["classification"],
            boundary="Whole recorded IQ attempt",
            metrics={},
            arms={arm: {"latlon": None} for arm in ARMS},
        ),
    )


def choose_attempts(attempts, selected):
    groups = {ident: [] for ident in selected}
    for row in attempts:
        groups[row["id"]].append(row)
    for ident, rows in groups.items():
        if len({r["service_unit"] for r in rows}) != len(rows):
            raise ValueError("one service appeared twice under different study names")
        first = min(rows, key=lambda r: r["started_monotonic_s"])
        (primary,) = (r for r in rows if r["study"] == selected[ident])
        if len({r["started_monotonic_s"] for r in rows}) != len(rows):
            raise ValueError("service start chronology is ambiguous")
        for row in rows:
            row.update(primary=row is primary, original_first=row is first)
            row["decision"] = (
                "fixed study precedence"
                if row is primary
                else "earliest eligible launch"
                if row is first
                else "retained secondary repeat"
                if row["full_raw_verified"]
                else "retained failed setup"
            )
    return attempts


def seal_attempts(report):
    roster = whole_iq.read(report / "roster-lock.json")
    whole_iq.checked(report / "PROTOCOL.md", roster["protocol_sha256"])
    registered = roster["studies"]
    if roster["primary"] != trial.primary_ids({k: v["cases"] for k, v in registered.items()}):
        raise ValueError("primary roster changed after its metadata-only declaration")
    _, base = verified_sources(trial.STUDIES[0], registered[trial.STUDIES[0].name])
    cases = {ident: _load_case(ident) for ident in roster["primary"]}
    attempts, repeated = [], {}
    for study in trial.STUDIES:
        pin = registered[study.name]
        for record in normalize(study, pin, base, cases, repeated):
            ident = record["id"]
            if ident in repeated and any(
                record[k] != repeated[ident][k] for k in (*COMMON, "native_sha256")
            ):
                raise ValueError("duplicate studies differ in complete stock waveform or factors")
            repeated.setdefault(ident, record)
            attempts.append(record)
        if study.branch == "stock":
            attempts.append(whole_winner_initial(study, pin, cases["DS29-0082"], base))
    choose_attempts(attempts, roster["primary"])
    save_json(report / "attempts.json", attempts)
    rows = [
        dict(
            {
                k: row[k]
                for k in (
                    "id",
                    "tile",
                    "catalog_sha256",
                    "original_request_sha256",
                    "capture_era_native_sha256",
                    "native_sha256",
                    "result",
                )
            },
            method=method,
        )
        for method, choice in ((PRIMARY, "primary"), (FIRST, "original_first"))
        for row in attempts
        if row[choice]
    ]
    pack(report / "positions.jsonl.gz", rows)
    names = ("PROTOCOL.md", "roster-lock.json", "attempts.json", "positions.jsonl.gz")
    save_json(
        report / "prediction-lock.json",
        dict(
            cases=list(roster["primary"]),
            files={name: _sha(report / name) for name in names},
            publisher_sha256=_sha(Path(__file__)),
        ),
    )


def attempt_scores(attempts, references):
    scores = []
    for row in attempts:
        case, result = references[row["id"]], row["result"]
        for arm in ARMS:
            endpoint = result["arms"][arm]
            limit = case["reference"]["baseline"][arm]["error_km"]
            error = distance_km(case["truth"], endpoint["latlon"])
            scores.append(
                dict(
                    id=row["id"],
                    study=row["study"],
                    branch=row["branch"],
                    arm=arm,
                    status=result["status"],
                    reason=result.get("reason"),
                    published=error is not None,
                    error_km=error,
                    original_v5_km=limit,
                    within_5pct=error is not None and limit is not None and error <= 1.05 * limit,
                    within_10pct=error is not None and limit is not None and error <= 1.10 * limit,
                    conditional_rms_hz=endpoint.get("rf_rms_hz"),
                    historical_rms_hz=None,
                    conditional_frequency_score=result["metrics"].get(f"{arm}_frequency_score"),
                    **{
                        k: row.get(k)
                        for k in (
                            "primary",
                            "original_first",
                            "decision",
                            "full_raw_verified",
                            "started_monotonic_s",
                            "deadline_s",
                            "study_prediction_sha256",
                            "study_source_sha256",
                            "execution_plan_sha256",
                            "receiver_files_sha256",
                            "detector_sha256",
                            "native_sha256",
                            "native_archive",
                            "service_unit",
                            "service_log_sha256",
                            "service_result",
                            "cutoff_utc",
                            "causal_catalogue_age_h",
                            "original_request_sha256",
                            "input_manifest_sha256",
                            "capture_era_native_sha256",
                            "catalog_sha256",
                            "clock_sha256",
                            "raw_authority",
                            "excluded_sha256",
                            "probes_sha256",
                            "memory_max_bytes",
                            "swap_limit_bytes",
                            "wall_s",
                            "service_wall_s",
                            "cpu_s",
                            "raw_s",
                            "position_s",
                            "wall_to_failure_s",
                            "cpu_to_failure_s",
                            "max_bytes",
                            "charged_peak_to_failure_bytes",
                            "dual_calls",
                            "within_20ms",
                        )
                    },
                )
            )
    return scores


def summarize(arms, attempts):
    paired = {}
    for row in arms:
        paired.setdefault(row["service_unit"], {})[row["arm"]] = row
    return dict(
        trials=len(attempts),
        complete_raw=sum(row["full_raw_verified"] for row in attempts),
        geography={
            arm: dict(
                published=sum(r["published"] for r in arms if r["arm"] == arm),
                within_5pct=sum(r["within_5pct"] for r in arms if r["arm"] == arm),
                within_10pct=sum(r["within_10pct"] for r in arms if r["arm"] == arm),
                error_km=distribution([r["error_km"] for r in arms if r["arm"] == arm]),
            )
            for arm in ARMS
        },
        calibration_fitted_minus_zero={
            key: distribution(
                [
                    fit["fitted_c"][key] - fit["c0"][key]
                    for fit in paired.values()
                    if all(fit[arm][key] is not None for arm in ARMS)
                ]
            )
            for key in ("error_km", "conditional_rms_hz", "conditional_frequency_score")
        },
        conditional_rms_hz={
            arm: distribution([r["conditional_rms_hz"] for r in arms if r["arm"] == arm])
            for arm in ARMS
        },
        timing={
            key: distribution([r.get(key) for r in attempts])
            for key in (
                "wall_s",
                "service_wall_s",
                "cpu_s",
                "raw_s",
                "position_s",
                "wall_to_failure_s",
                "cpu_to_failure_s",
                "causal_catalogue_age_h",
            )
        },
        measured_dual_visits=sum(
            r["dual_calls"] for r in attempts if r.get("within_20ms") is not None
        ),
        within_20ms=sum(r["within_20ms"] for r in attempts if r.get("within_20ms") is not None),
    )


def score(report):
    prediction = whole_iq.read(report / "prediction-lock.json")
    for name, digest in prediction["files"].items():
        whole_iq.checked(report / name, digest)
    _, references = held_references(None, prediction["cases"])
    references = {ref["id"]: ref for ref in references}
    attempts = whole_iq.read(report / "attempts.json")
    ledger = attempt_scores(attempts, references)
    csv_file(report / "sensitivity.csv", ledger)
    primary = [r for r in ledger if r["primary"]]
    native_hashes = {r["id"]: r["capture_era_native_sha256"] for r in primary}
    for ident, ref in references.items():
        for mode in ROLES:
            for arm in ARMS:
                fit = ref["reference"][mode][arm]
                primary.append(
                    dict(
                        id=ident,
                        study="capture-era-v5",
                        branch=mode,
                        arm=arm,
                        status=fit["status"],
                        published=fit["latlon"] is not None,
                        error_km=fit["error_km"],
                        original_v5_km=ref["reference"]["baseline"][arm]["error_km"],
                        historical_rms_hz=fit["rf_rms_hz"],
                        capture_era_native_sha256=native_hashes[ident],
                    )
                )
    csv_file(report / "scores.csv", primary)
    ids = set(prediction["cases"])
    roles = dict(
        all=ids,
        legacy=trial.LEGACY,
        added=ids - trial.LEGACY,
        exact_wide={r["id"] for r in attempts if r["study"] == "exact-wide-iq"},
        stride_held={"DS26-0162", "DS29-0519"},
        scout_only={"DS26-0014", "DS29-0127"},
        DS26={i for i in ids if i.startswith("DS26")},
        DS29={i for i in ids if i.startswith("DS29")},
    )
    result = {
        role: {
            name: summarize(
                [r for r in ledger if r["id"] in ids and (r[flag] if flag else True)],
                [r for r in attempts if r["id"] in ids and (r[flag] if flag else True)],
            )
            for name, flag in (
                ("primary", "primary"),
                ("original_first", "original_first"),
                ("all_attempts", None),
            )
        }
        for role, ids in roles.items()
    }
    save_json(report / "summary.json", result)
    charts = []
    evidence = [
        "roster-lock.json",
        "prediction-lock.json",
        "sensitivity.csv",
        "scores.csv",
        "summary.json",
    ]
    rows = rows_from(report / "positions.jsonl.gz")
    for key, title in [
        ("all", "Wide GLRT from complete recorded IQ on 12 roof recordings"),
        ("added", "Wide GLRT on six subsequently added roof recordings"),
    ]:
        names = sorted(roles[key])
        file = "positions.jsonl.gz" if key == "all" else "added-positions.jsonl.gz"
        if key != "all":
            pack(report / file, [r for r in rows if r["id"] in names])
        figure_lock = f"{key}-figure-lock.json"
        save_json(
            report / figure_lock,
            dict(cases=names, files={n: _sha(report / n) for n in [file, *evidence]}),
        )
        charts.append(
            dict(
                id=f"wide-iq-roster-{key}",
                method=PRIMARY,
                scope="roof",
                cases=names,
                title=title,
                caption=(
                    "Recorded dual-receiver IQ through the 21-bin, four-start wide detector "
                    "and compact solver. One primary and one earliest eligible attempt per "
                    "recording. One physical roof."
                ),
                seal=figure_lock,
                provenance=evidence,
                series=[
                    dict(
                        key="one",
                        label="Wide · fixed primary roster",
                        file=file,
                        value=PRIMARY,
                        native_field="capture_era_native_sha256",
                    ),
                    dict(
                        key="stock",
                        label="Wide · first eligible attempt",
                        file=file,
                        value=FIRST,
                        native_field="capture_era_native_sha256",
                        match=["tile", "original_request_sha256", "catalog_sha256"],
                    ),
                ],
            )
        )
    save_json(report / "figures.json", dict(version=1, charts=charts))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seal", "score"))
    parser.add_argument("--out", type=local_output, default=trial.REPORT)
    args = parser.parse_args()
    (seal_attempts if args.action == "seal" else score)(args.out)
