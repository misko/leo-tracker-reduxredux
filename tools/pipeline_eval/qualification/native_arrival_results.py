"""Seal bounded queue fits, then score and render both calibration arms."""

import argparse
import gzip
from collections import Counter
from pathlib import Path

from .. import corpus, iq_service, whole_iq
from ..__main__ import encoded, local_output, save_json, write
from ..scoring import ARMS, ROLES, distribution, validate_result
from . import accelerated_command_results as accelerated
from . import native_arrival as trial
from . import native_arrival_pace, screening_figures
from . import portable_field_scores as field
from .full_v5_check import _load_case, _sha
from .prefix_figures import csv_file

PREDICTIONS = "positions.jsonl.gz"
FULL = "full-portable-c"
ARCHIVE = "archived-compact"
PREDICTION_LOCK = "prediction-lock.json"
SCORE_LOCK = "score-lock.json"
FIT_SOURCES = ("archived_native_sha256", "catalog_sha256", "original_request_sha256", "tile")
LABELS = {
    FULL: "Full C",
    ARCHIVE: "Archived compact",
    trial.MISSING: "Next delivery",
    **{
        trial.method(w, p): f"{w} worker{'s' if w > 1 else ''} · {p.value}"
        for w, p in trial.POLICY_ORDER
    },
}


def source_scores(case):
    """Verify archived original v5 terminals without accessing the truth roster."""
    path = whole_iq.checked(field.HISTORICAL / SCORE_LOCK, field.HISTORICAL_SCORE_SHA)
    expected = whole_iq.read(path)["files"]["original-v5-receipts.json"]
    source = whole_iq.checked(field.HISTORICAL / "original-v5-receipts.json", expected)
    receipts = whole_iq.read(source)
    directory = accelerated.V5_ARCHIVE / f"{case['id']}-r0"
    originals = {}
    for role in ROLES:
        receipt = receipts[role]
        request = whole_iq.read(whole_iq.checked(
            directory / role / "experimental-request.json", receipt["request_file_sha256"],
        ))
        execution = whole_iq.read(whole_iq.checked(
            directory / (role + "-execution.json"), receipt["execution_sha256"],
        ))
        if (request["role"] != role or execution["status"] != receipt["status"]
            or execution["request_sha256"] != receipt["request_sha256"]):
            raise ValueError("original v5 terminal differs from its published source authority")
        worker = execution.get("worker", {})
        success = execution["status"] == "complete"
        originals[role] = dict(
            method=role, native_sha256=case["native"]["sha256"],
            result=dict(
                status="ok" if success else "timed_out",
                reason=None if success else "archived service deadline",
                boundary="Authentic original v5 archived execution",
                metrics=dict(position_attempted=True),
                arms={
                    arm: dict(
                        latlon=worker.get("arms", {}).get(arm, {}).get("endpoint_latlon"),
                        rf_rms_hz=worker.get("arms", {}).get(arm, {}).get("residual_rms_hz"),
                    ) for arm in ARMS
                },
            ),
        )
    return originals, receipts


def validate_fit(row, work, case, schedules, schedule_lock):
    key = row["method"]
    selection = schedules[key]
    if row["selected"] != len(selection["selected"]):
        raise ValueError("fit differs from the sealed queue selection")
    if not row["selected"]:
        if key != trial.MISSING or row["fit"] is not None:
            raise ValueError("only the next delivery control may omit a scheduled solve")
        return
    base = work / key
    source_path = base / "source-lock.json"
    source = whole_iq.read(source_path)
    if (source["schedule_lock_sha256"] != _sha(schedule_lock)
        or source["schedule_sha256"] != trial.recording.digest(selection)
        or source["tile"] != case["regions"][0]):
        raise ValueError("measured compact fit has no causal queue source binding")
    attempt = base / "position"
    native = whole_iq.checked(base / "native.json", row["native_sha256"])
    raw = whole_iq.read(attempt / "raw.json")
    request = whole_iq.checked(attempt / "recording/request.json", raw["request_sha256"])
    if raw["native_sha256"] != row["native_sha256"]:
        raise ValueError("compact run consumed another native file")
    whole_iq.verify_request(
        whole_iq.read(request), trial.original.binding(case), native_path=str(native),
        native_sha256=row["native_sha256"],
    )
    service = row["fit"]["service"]
    whole_iq.checked(attempt / "service.json", _sha(attempt / "service.json"))
    if whole_iq.read(attempt / "service.json") != service:
        raise ValueError("recorded fit service differs from the terminal receipt")
    plan = whole_iq.read(attempt / "plan.json")
    result, fit = accelerated.position_state(
        base, service, trial.original.failure_status((service,)), _sha(source_path),
        source["receiver"], plan["cpus"][0],
    )
    if (row["result"], row["fit"]) != (result, fit):
        raise ValueError("sealed outcome differs from the authenticated compact terminal")


def seal(output, native, work):
    case = _load_case(trial.CASE)
    request, causal = field.causal_authority(case)
    reference = field.historical(case)
    full, evidence, _, _, _, _, _ = field.verify_live(native, case, request, reference)
    original, original_receipts = source_scores(case)
    fits = trial.unpack(output / "queue-fits.json.gz")
    modes = [trial.method(w, p) for w, p in trial.POLICY_ORDER] + [trial.MISSING]
    if [r["method"] for r in fits] != modes:
        raise ValueError("a scheduled policy is missing its compact terminal")
    schedule_files = []
    for label in trial.EXPRESS, trial.NATIVE:
        schedule_lock = output / f"{label}-schedule-lock.json"
        bind = whole_iq.read(schedule_lock)
        field.checked_files(output, bind["files"])
        for path, digest in bind["sources"].items():
            whole_iq.checked(Path(path), digest)
        schedule_files.extend([schedule_lock.name, *bind["files"]])
    source = bind["source"]
    if (source["native_document_sha256"].removeprefix("sha256:")
        != trial.recording.digest(whole_iq.read(native / "native.json")).removeprefix("sha256:")
        or evidence["live_source_lock_sha256"] != source["source_lock"]):
        raise ValueError("the full C control and retained fits do not share the complete C input")
    schedules = trial.unpack(output / f"{trial.NATIVE}-schedules.json.gz")["cpu"]
    for row in fits:
        validate_fit(row, work, case, schedules, schedule_lock)
    pace = whole_iq.read(output / "paced-fifo.json")
    if (pace["source_sha256"] != source["source_lock"]
        or pace["run_seal_sha256"] != evidence["live_seal_sha256"]
        or len(pace["events"]) != 64
        or not set(pace["models"]) == {"cpu", "wall"}):
        raise ValueError("bounded one-worker clock does not bind the same raw run")
    authority = dict(
        id=case["id"], archived_native_sha256=case["native"]["sha256"],
        catalog_sha256=case["catalog"]["sha256"], original_request_sha256=case["request"]["sha256"],
        tile=case["regions"][0],
    )
    predictions = [
        *({k: row[k] for k in ("method", "native_sha256", "result", "selected")} for row in fits),
        dict(method=FULL, native_sha256=evidence["native_sha256"], result=full),
        reference["archived"] | {"method": ARCHIVE},
        *original.values(),
    ]
    for row in predictions:
        validate_result(row["result"])
    write(output / PREDICTIONS, gzip.compress(
        b"".join(encoded(row | authority) + b"\n" for row in predictions), mtime=0,
    ))
    save_json(output / "source-bindings.json", dict(
        causal=causal, full_run_seal=evidence["live_seal_sha256"],
        full_native=evidence["native_sha256"], full_compact=evidence["fit"],
        original_v5=original_receipts,
    ))
    names = (*schedule_files, "PROTOCOL.md", "paced-fifo.json", "queue-fits.json.gz",
             PREDICTIONS, "source-bindings.json")
    save_json(output / PREDICTION_LOCK, dict(
        cases=[case["id"]], files={p: _sha(output / p) for p in names},
        sources={Path(m).name: _sha(Path(m)) for m in (__file__, native_arrival_pace.__file__)},
    ))


def comparison(rows):
    by_key = {(r["method"], r["arm"]): r for r in rows}
    methods = list(dict.fromkeys(r["method"] for r in rows))
    output = {}
    for method in methods:
        samples = {arm: by_key[method, arm] for arm in ARMS}
        c0, fitted = (samples[arm] for arm in ARMS)
        output[method] = dict(
            by_arm={arm: dict(
                absolute_error_km=samples[arm]["error_km"],
                relative_error_percent={
                    ref: 100 * (samples[arm]["error_km"] / by_key[ref, arm]["error_km"] - 1)
                    for ref in (FULL, *ROLES) if samples[arm]["error_km"] is not None
                    and by_key[ref, arm]["error_km"] is not None
                },
                status=samples[arm]["status"],
            ) for arm in ARMS},
            fitted_c_minus_c0={k: field.subtract(fitted[k], c0[k]) for k in
                              ("error_km", "rf_rms_hz", "frequency_score")},
        )
    return output


def pace_summary(pace):
    rows = {r["visit"]: r for r in pace["events"]}
    ready = {i for i, r in rows.items() if r["outcome"] == "ready"}
    started = {i for i, r in rows.items() if "start_ns" in r}
    measured = dict(
        outcomes=dict(Counter(r["outcome"] for r in rows.values())), ready_ids=sorted(ready),
        age_ms=distribution((rows[i]["finish_ns"] - rows[i]["scheduled_ns"]) / 1e6 for i in ready),
        last_delivery=pace["last_delivery"], final_deadline=pace["final_deadline"],
        started=len(started),
    )
    comparisons = {}
    for clock, model in pace["models"].items():
        expected = {int(i) for i, outcome in model["outcomes"].items() if outcome == "ready"}
        shared_start = started & {int(i) for i in model["start_ns"]}
        shared_finish = started & {int(i) for i in model["finish_ns"]}
        comparisons[clock] = dict(
            ready_ids=sorted(expected), shared_ready=sorted(ready & expected),
            outcomes=dict(Counter(model["outcomes"].values())),
            last_delivery=model["last_delivery"], final_deadline=model["deadline"],
            start_delta_ms=distribution((rows[i]["start_ns"] - model["start_ns"][str(i)]) / 1e6
                                        for i in shared_start),
            finish_delta_ms=distribution((rows[i]["finish_ns"] - model["finish_ns"][str(i)]) / 1e6
                                         for i in shared_finish),
        )
    return dict(measured=measured, compared= comparisons)


def score(output):
    lock = whole_iq.read(output / PREDICTION_LOCK)
    field.checked_files(output, lock["files"], (PREDICTIONS,))
    ids, frozen = corpus._selection("ds26-all159")
    reference = next(r for r in corpus._references(ids, frozen) if r["id"] == trial.CASE)
    excluded = trial.CASE in corpus._selection("ds26-excluded32")[0]
    if not excluded:
        raise ValueError("the frozen excluded-32 membership differs from the protocol")
    import json

    with gzip.open(output / PREDICTIONS, "rt") as stream:
        predictions = list(map(json.loads, stream))
    rows = field.measured_scores(predictions, reference["truth"])
    originals, _ = accelerated.original_v5_scores(_load_case(trial.CASE), reference)
    if [r for r in rows if r["method"] in ROLES] != originals:
        raise ValueError("position scores disagree with the four official v5 reference roles")
    csv_file(output / "scores.csv", rows)
    summary = comparison(rows)
    save_json(output / "accuracy.json", dict(excluded32=excluded, comparisons=summary))
    pace = whole_iq.read(output / "paced-fifo.json")
    save_json(output / "paced-comparison.json", pace_summary(pace))
    from . import native_arrival_figures

    stage_files = native_arrival_figures.stage(output, rows)
    names = (PREDICTION_LOCK, "scores.csv", "accuracy.json", "paced-comparison.json", *stage_files)
    save_json(output / SCORE_LOCK, dict(
        cases=lock["cases"], files=lock["files"] | {name: _sha(output / name) for name in names},
        frozen={k: frozen[k] for k in ("inputs.jsonl", "targets.jsonl", "scores.csv")},
        scoring_code_sha256=_sha(Path(__file__)),
    ))
    native_arrival_figures.descriptors(output)
    screening_figures.generate(output / "charts", evidence=output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("seal", "score"))
    parser.add_argument("--output", default=trial.OUT, type=local_output)
    parser.add_argument("--native", type=local_output)
    parser.add_argument("--work", type=local_output)
    args = parser.parse_args()
    if args.stage == "seal":
        if not args.native or not args.work:
            parser.error("seal requires complete raw and compact service evidence")
        seal(args.output, args.native, args.work)
    else:
        score(args.output)


if __name__ == "__main__":
    main()
