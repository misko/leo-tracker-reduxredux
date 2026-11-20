"""Authenticate two exact same-recording joins across original-support studies."""

import csv
import gzip
import json
from hashlib import sha256

from .. import whole_iq
from ..scoring import ARMS, ROLES, distribution
from ..variants.capture_bursts import inventories
from .complete_detector_roster import member, same_capture, scored
from .fresh_replay_results import sealed
from .full_held_scores import held_references
from .full_v5_check import _sha
from .whole_pressure_trial import rows_from

QUEUE_CASE = "DS29-0082"
PERIODIC_CASE = "DS26-0162"
RAW = "raw-prediction-lock.json"
PRED = "prediction-lock.json"
POS = "positions.jsonl.gz"
QUEUE_POLICIES = (
    ("fifo-1", "paced-original", "raw/original/trace.json.gz", "paced_capture_original"),
    ("oldest_rf-1", "paced-rf", "raw/trace.json.gz", "paced_oldest_rf"),
)


def readgz(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def same_slot_ledger(document):
    valid = dict(inventories(document))
    source = document["source"]
    size = source["sample_rate_hz"] * source["probe_ms"] // 1000
    starts = {p["visit_index"]: p["valid_start_counter"] for p in source["probes"]}
    excluded = {
        p["visit"]: (p["sample_start"], p["sample_end"])
        for p in document["provenance"]["excluded_windows"]
    }
    clocks = document["delivery_clocks"]
    first = clocks[0]["monotonic_ns"]
    return [
        dict(
            visit=i,
            arrival_ns=clock["monotonic_ns"] - first,
            delivery_clock=clock,
            sample_start=starts[i] if i in valid else excluded[i][0],
            sample_end=starts[i] + size if i in valid else excluded[i][1],
            status="processed" if i in valid else "invalid_capture",
        )
        for i, clock in enumerate(clocks)
    ]


def compare_trace(ledger, forecast, trace=None):
    valid = {r["visit"]: r["arrival_ns"] for r in ledger if r["status"] == "processed"}
    modeled = {v for v, _, _ in forecast}
    if len(modeled) != len(forecast) or any(
        v not in valid or not valid[v] <= start <= finish for v, start, finish in forecast
    ):
        raise ValueError("forecast admissions do not match original capture arrivals")
    model_age = distribution((finish - valid[v]) / 1e6 for v, _, finish in forecast)
    result = dict(
        physical_arrivals=len(ledger),
        valid_arrivals=len(valid),
        invalid_arrivals=len(ledger) - len(valid),
        modeled_emitted=len(modeled),
        modeled_dropped=len(valid) - len(modeled),
        modeled_visit_set_sha256=whole_iq.recording.digest(sorted(modeled)),
        modeled_age_median_ms=model_age["p50"],
        modeled_age_p95_ms=model_age["p95"],
        modeled_at_20_ms=sum(end - valid[v] <= 20_000_000 for v, _, end in forecast),
        modeled_cpu_s=sum(end - start for _, start, end in forecast) / 1e9,
    )
    live = None
    if trace is not None:
        for expected, received in zip(ledger, trace, strict=True):
            if any(received[k] != v for k, v in expected.items()):
                raise ValueError(
                    "measured trace differs from original physical delivery/sample clocks"
                )
            if expected["status"] == "invalid_capture":
                outcome_ok = received["outcome"] == "invalid_capture"
            elif received["outcome"] == "emitted":
                outcome_ok = (
                    expected["arrival_ns"] <= received["started_ns"] <= received["emitted_ns"]
                )
            else:
                outcome_ok = received["outcome"] == "queue_drop"
            if not outcome_ok:
                raise ValueError("measured trace has an invalid terminal state or age")
        live = {r["visit"]: r for r in trace if r["outcome"] == "emitted"}
    age = distribution((r["emitted_ns"] - r["arrival_ns"]) / 1e6 for r in (live or {}).values())
    return dict(
        result,
        live_emitted=len(live) if live is not None else None,
        live_dropped=len(valid) - len(live) if live is not None else None,
        live_visit_set_sha256=whole_iq.recording.digest(sorted(live)) if live is not None else None,
        overlap=len(modeled & live.keys()) if live is not None else None,
        only_modeled=len(modeled - live.keys()) if live is not None else None,
        only_live=len(live.keys() - modeled) if live is not None else None,
        union=len(modeled | live.keys()) if live is not None else None,
        jaccard=len(modeled & live.keys()) / len(modeled | live.keys())
        if live is not None and (modeled or live)
        else None,
        live_age_median_ms=age["p50"],
        live_age_p95_ms=age["p95"],
        live_age_max_ms=age["max"],
        live_at_20_ms=sum(r["emitted_ns"] - r["arrival_ns"] <= 20_000_000 for r in live.values())
        if live is not None
        else None,
        live_detector_cpu_s=sum(r["native_cpu_ns"] for r in live.values()) / 1e9
        if live is not None
        else None,
        live_serial_detector_wall_s=sum(r["native_wall_ns"] for r in live.values()) / 1e9
        if live is not None
        else None,
    )


def one_row(folder, lock, ident, method):
    path = member(folder, lock, POS)
    (row,) = [r for r in rows_from(path) if r["id"] == ident and r["method"] == method]
    return row


def geographic(rows, ident):
    _, (reference,) = held_references(None, [ident])
    candidate = scored(rows, {ident: reference})
    for score, row in zip(candidate, (r for r in rows for _ in ARMS), strict=True):
        score["position_wall_s"] = (row.get("position_resources") or {}).get("wall_s")
        score["timing_scope"] = "position fit"
    for role in ROLES:
        for arm in ARMS:
            fit = reference["reference"][role][arm]
            baseline = reference["reference"]["baseline"][arm]["error_km"]
            error = fit.get("error_km")
            eligible = error is not None and baseline is not None
            candidate.append(
                {key: None for key in candidate[0]}
                | dict(
                    id=ident,
                    method=f"original_v5_{role}",
                    arm=arm,
                    status=fit["status"],
                    error_km=error,
                    rf_rms_hz=fit.get("rf_rms_hz"),
                    within_5pct=eligible and error <= 1.05 * baseline,
                    within_10pct=eligible and error <= 1.10 * baseline,
                    position_wall_s=fit.get("wall_s"),
                    timing_scope="archived original request",
                )
            )
    return candidate


def queue(root, checks):
    folder = root / "queue-selection"
    lock_name = "forecast-lock.json"
    if not (folder / lock_name).is_file():
        return [], []
    forecast = sealed(folder, lock_name)
    pred = sealed(folder, PRED)
    checks["queue_forecast_sha256"] = _sha(folder / lock_name)
    inputs = whole_iq.read(member(folder, pred, "inputs.json"))
    if (
        forecast["case"] != QUEUE_CASE
        or inputs["forecast_sha256"] != checks["queue_forecast_sha256"]
    ):
        raise ValueError("modeled queue inputs differ from the sealed forecast cohort")
    parent = root.parent / "antenna-confirmation" / "capture-whole"
    parent_lock = sealed(parent, PRED, forecast["parent_sha256"])
    checks["queue_original_capture_prediction_sha256"] = forecast["parent_sha256"]
    ledger = same_slot_ledger(readgz(member(parent, parent_lock, "native.json.gz")))
    expected = readgz(member(folder, forecast, "forecasts.json.gz"))
    output, positions, emitted_by_policy = [], [], {}
    for policy, scope, trace_name, method in QUEUE_POLICIES:
        model = one_row(folder, pred, QUEUE_CASE, f"original_queue_{policy}")
        (job,) = (row for row in inputs["jobs"] if row["method"] == model["method"])
        same_capture(model, job)
        if model["native_sha256"] != job["native_sha256"] or job["selected_visits"] != len(
            expected[policy]
        ):
            raise ValueError("modeled queue fit did not use its frozen selection")
        positions.append(model)
        live = root / scope
        state, trace = "awaiting_raw_seal", None
        if (live / RAW).is_file():
            receipt = sealed(live, RAW)
            checks[f"{scope}_raw_sha256"] = _sha(live / RAW)
            raw_plan = whole_iq.read(member(live, receipt, "source-lock.json"))
            if raw_plan["waiting_slots"] != 1 or receipt["cases"] != [QUEUE_CASE]:
                raise ValueError("live queue policy did not use the same one-slot recording")
            if scope == "paced-rf":
                whole_iq.checked(
                    root / "paced-original/source-lock.json", raw_plan["original_parent_sha256"]
                )
                whole_iq.checked(folder / lock_name, raw_plan["forecast_lock_sha256"])
                status = whole_iq.read(member(live, receipt, "timing.json"))["status"] == "complete"
                events_name = "events.json.gz"
            else:
                status = whole_iq.read(member(live, receipt, "raw/original/status.json"))[
                    "complete"
                ]
                events_name = "original-events.json.gz"
            state = "complete" if status else "failed_or_partial"
            if status:
                trace = readgz(member(live, receipt, trace_name))
                events = readgz(member(live, receipt, events_name))
                if any(
                    raw["full_visit_sha256"] != source["full_visit_sha256"]
                    for raw, source in zip(trace, events, strict=True)
                ):
                    raise ValueError("actual queue used a different captured visit payload")
                emitted_by_policy[policy] = {r["visit"] for r in trace if r["outcome"] == "emitted"}
            if (live / PRED).is_file():
                fitted = sealed(live, PRED)
                checks[f"{scope}_prediction_sha256"] = _sha(live / PRED)
                member(live, fitted, RAW)
                actual = one_row(live, fitted, QUEUE_CASE, method)
                same_capture(model, actual)
                if trace is not None and actual["emitted_visits"] != [
                    r["visit"] for r in trace if r["outcome"] == "emitted"
                ]:
                    raise ValueError("live compact fit retained a different visit set")
                positions.append(actual)
        output.append(
            dict(
                id=QUEUE_CASE,
                policy=policy,
                live_state=state,
                **compare_trace(
                    ledger,
                    expected[policy],
                    trace,
                ),
            )
        )
    if len(emitted_by_policy) == len(QUEUE_POLICIES):
        fifo, fair = (emitted_by_policy[policy] for policy, *_ in QUEUE_POLICIES)
        checks["actual_queue_compared"] = dict(
            case=QUEUE_CASE,
            overlap=len(fifo & fair),
            union=len(fifo | fair),
            jaccard=len(fifo & fair) / len(fifo | fair) if fifo or fair else None,
        )
    return output, geographic(positions, QUEUE_CASE)


def physical_payload(document):
    return (
        document["source"]["probes"],
        document["delivery_clocks"],
        document["clock_anchor"],
        document["last_sample_counter"],
        document["provenance"]["excluded_windows"],
    )


def equal_payload(stored, actual):
    if physical_payload(stored) != physical_payload(actual):
        raise ValueError("scheduled waveform and stored replay have different probes or clocks")


def periodic(root, checks):
    stored, actual = root / "frequency-schedule", root / "scheduled-waveform"
    name = "overlap-native-lock.json"
    if not (stored / name).is_file() or not (actual / PRED).is_file():
        return []
    receipt = sealed(stored, name)
    released = sealed(actual, PRED, receipt["raw_prediction_lock_sha256"])
    checks["periodic_raw_prediction_sha256"] = _sha(actual / PRED)
    checks["periodic_stored_native_sha256"] = _sha(stored / name)
    stored_bytes = gzip.decompress(
        member(stored, receipt, f"native/{PERIODIC_CASE}-periodic4.json.gz").read_bytes()
    )
    actual_bytes = gzip.decompress(member(actual, released, "native.json.gz").read_bytes())
    if (sha256(stored_bytes).hexdigest(), sha256(actual_bytes).hexdigest()) != (
        receipt["native_sha256"],
        receipt["measured_native_sha256"],
    ):
        raise ValueError("scheduled native documents differ from their separate lineage seals")
    left, right = json.loads(stored_bytes), json.loads(actual_bytes)
    equal_payload(left, right)
    probes, clock, _, _, excluded = physical_payload(left)
    audit = whole_iq.read(member(actual, released, "audit.json"))
    bound = audit["raw"]
    if (
        not bound["complete"]
        or whole_iq.recording.digest(probes) != bound["projected_probe_sha256"]
    ):
        raise ValueError("physical payload differs from independently projected probe hash")
    plan = whole_iq.read(whole_iq.checked(stored / "plan.json", receipt["plan_sha256"]))
    record = one_row(actual, released, PERIODIC_CASE, "original_capture_phase_staggered_four")
    complete = one_row(actual, released, PERIODIC_CASE, "original_capture_all_factors_compact")
    same_capture(record, complete)
    record["position_resources"] = audit["position"]["scheduled"]
    complete["position_resources"] = audit["position"]["full"]
    direct_request = whole_iq.read(
        member(actual, released, "receipts/scheduled/recording/request.json")
    )["job"]
    (task,) = [
        r for r in plan["tasks"] if r["id"] == PERIODIC_CASE and r["condition"] == "periodic4"
    ]
    for key in ("id", "paired_capture_sha256", "catalog_sha256", "original_request_sha256"):
        if record[key] != task[key] or record[key] != complete[key]:
            raise ValueError("periodic and whole receiver position request lineage differs")
    if (record["tile"]["center"], task["tile"]["center"], task["tile"]["screen"]) != (
        direct_request["search_center"],
        direct_request["search_center"],
        direct_request["screen_center"],
    ):
        raise ValueError("periodic stored and directly replayed offers/screens differ")
    schedule = whole_iq.read(member(actual, released, "schedule.json"))
    invalid = {row["visit"] for row in excluded}
    selected = [v for v, row in enumerate(schedule) if row[-1] and v not in invalid]
    stored_schedule = whole_iq.read(
        whole_iq.checked(stored / "schedule.json", plan["schedule_sha256"])
    )
    with member(actual, released, "timing.csv").open() as stream:
        processed = [int(r["visit"]) for r in csv.DictReader(stream) if r["status"] == "processed"]
    if sorted(selected) != sorted(processed) or selected != sorted(
        stored_schedule[PERIODIC_CASE]["periodic4"]
    ):
        raise ValueError("direct actual and projected schedules selected different physical visits")
    if record["native_sha256"] != receipt["measured_native_sha256"]:
        raise ValueError("direct periodic compact fit did not use the actual native replay")
    checks["periodic"] = dict(
        case=PERIODIC_CASE,
        physical_payload_exact=True,
        identical_complete_native_file=stored_bytes == actual_bytes,
        measured_native_sha256=record["native_sha256"],
        stored_native_sha256=receipt["native_sha256"],
        visits=len(clock),
        selected_valid_visits=len(selected),
        invalid_visits=len(excluded),
        physical_probes=len(probes),
        candidate_rows=sum(len(p["candidates"]) for p in probes),
        raw_elapsed_s=bound["raw_wall_s"],
        detector_cpu_s=bound["total_detector_cpu_s"],
    )
    rows = [record, complete]
    if (stored / PRED).is_file():
        lock = sealed(stored, PRED)
        checks["periodic_stored_prediction_sha256"] = _sha(stored / PRED)
        projection = one_row(stored, lock, PERIODIC_CASE, task["method"])
        if (
            any(
                projection[k] != task[k]
                for k in (
                    "native_sha256",
                    "paired_capture_sha256",
                    "original_request_sha256",
                    "catalog_sha256",
                    "tile",
                )
            )
            or projection["native_sha256"] != receipt["native_sha256"]
        ):
            raise ValueError(
                "projected periodic fit used a different native input or position query"
            )
        full = one_row(stored, lock, PERIODIC_CASE, "frequency_schedule_full")
        if full["native_sha256"] != complete["native_sha256"] or full["tile"] != task["tile"]:
            raise ValueError("full periodic control changed native inputs or the offered tile")
        for measured, prepared in ((record, projection), (complete, full)):
            a, b = measured["result"], prepared["result"]
            if any(a.get(key) != b.get(key) for key in ("arms", "status", "reason")) or any(
                a["metrics"][f"{arm}_frequency_score"] != b["metrics"][f"{arm}_frequency_score"]
                for arm in ARMS
            ):
                raise ValueError("periodic raw and stored numerical endpoints differ")
        checks["periodic"]["periodic_and_full_numerical_arms_equal"] = True
        rows.append(projection)
    return geographic(rows, PERIODIC_CASE)


def compare(root):
    checks = {"schema": "original-support-overlap/v1"}
    adm, queue_positions = queue(root, checks)
    return adm, queue_positions, periodic(root, checks), checks
