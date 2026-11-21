"""Lock every Gauss prediction before joining surveys and scoring paired recording replays."""

import math
import re
from copy import deepcopy
from pathlib import Path

from .. import corpus
from ..scoring import ARMS, arm_outcome, distance_km, distribution, thresholds, validate_result
from .blind_compact_roster import DS29, METHODS, OUT, WORK, seal
from .full_v5_check import _sha
from .reverse_glrt_reference import read_bound
from .reverse_glrt_report import read, write_csv
from .timing_first_position import full_identity


def verified_request(case, original, bound, native):
    job = bound["job"]
    expected = deepcopy(original)
    digest = "sha256:" + _sha(native)
    expected["job"]["native_input"] = dict(path=str(native), sha256=digest)
    expected["job"]["identity"].update(input_sha256=digest, run_id=full_identity(case["id"], bound))
    expected["job"]["output_root"] = str(native.parent / "position")
    if bound != expected or job["evaluation_reference"] is not None:
        raise ValueError("replay changed frozen scientific settings or disclosed a survey")
    return digest.removeprefix("sha256:")


def inventory(output=None, work=None):
    output = OUT if output is None else output
    work = WORK if work is None else work
    roster = read(output / "roster.json")
    builds = read(output / "build.json")
    if roster["protocol_sha256"] != _sha(output / "PROTOCOL.md") or builds["roster_sha256"] != _sha(
        output / "roster.json"
    ):
        raise ValueError("roster or protocol was altered")
    library_lock = _sha(output / "build.json")
    methods, predictions = {}, {}
    for row in roster["cases"]:
        case = row["case"]
        ident = case["id"]
        original = read_bound(case["request"])
        authority = None
        for method in METHODS:
            result_path = work / "runs" / ident / method / "outcome.json"
            if not result_path.is_file():
                raise ValueError(f"prediction still pending for {ident}, {method}")
            r = read(result_path)
            path = Path(r["prediction_path"])
            folder = path.parent
            if (
                not folder.is_relative_to(result_path.parent)
                or path.name != "prediction.json"
                or (r["case"], r["dataset"], r["method"], r["cpu"])
                != (ident, case["panel"], method, row["cpu"])
                or r["roster_sha256"] != builds["roster_sha256"]
                or r["build_sha256"] != library_lock
                or r["binding_sha256"] != _sha(folder / "binding.json")
                or r["prediction_sha256"] != _sha(path)
            ):
                raise ValueError(f"replay evidence changed for {ident}, {method}")
            bound = read(folder / "binding.json")
            if r["native_sha256"] != verified_request(
                case, original, bound, folder / "native.json"
            ):
                raise ValueError("native factor digest differs from the replay receipt")
            effective_path = folder / "solver/request.json"
            bound["job"]["output_root"] = str(effective_path.parent)
            if bound != read(effective_path):
                raise ValueError("the compact worker received different inputs")
            if not math.isclose(
                r["acquisition_wall_s"] + r["solver_wall_s"], r["end_to_end_wall_s"]
            ):
                raise ValueError("end-to-end clock disagrees with stage boundaries")
            physical = tuple(
                r[k] for k in ("raw_authority", "visits", "excluded", "antenna_probes")
            )
            if (
                authority is not None
                and physical != authority
                or r["visits"] != case["recording"]["window_count"]
                or 2 * (r["visits"] - r["excluded"]) != r["antenna_probes"]
            ):
                raise ValueError(f"the three runs used different physical samples for {ident}")
            authority = physical
            prediction = read(path)
            validate_result(prediction)
            if r["status"] != prediction["status"] or r["reason"] != prediction.get("reason"):
                raise ValueError("prediction and timing receipt disagree")
            key = (ident, method)
            if key in predictions:
                raise ValueError("duplicate physical recording and method")
            methods[key] = dict(
                r,
                order=row["order"].index(method) + 1,
                receipt_sha256=_sha(result_path),
                effective_request_sha256=_sha(effective_path),
            )
            predictions[key] = prediction
    lock = dict(
        roster_sha256=builds["roster_sha256"],
        build_sha256=library_lock,
        predictions=[
            dict(
                case=k[0],
                method=k[1],
                **{
                    f: r[f]
                    for f in (
                        "receipt_sha256",
                        "prediction_sha256",
                        "binding_sha256",
                        "effective_request_sha256",
                        "native_sha256",
                        "raw_authority",
                    )
                },
            )
            for k, r in methods.items()
        ],
    )
    seal(output / "prediction-lock.json", lock)
    return methods, predictions


def join_survey(methods, predictions, truths):
    rows = []
    for key, r in methods.items():
        ident, method = key
        prediction = predictions[key]
        for name in ARMS:
            arm = prediction["arms"][name]
            point = arm["latlon"]
            status, reason = arm_outcome(prediction, arm)
            rms = prediction["metrics"].get(f"{name}_conditional_rms_hz", arm.get("rf_rms_hz"))
            rows.append(
                dict(
                    case=ident,
                    dataset=r["dataset"],
                    method=method,
                    calibration=name,
                    fix=point is not None,
                    status=status,
                    reason=reason,
                    error_km=distance_km(truths[ident], point),
                    latitude_deg=point[0] if point else None,
                    longitude_deg=point[1] if point else None,
                    conditional_rf_rms_hz=rms,
                    **{
                        f: r[f]
                        for f in (
                            "end_to_end_wall_s",
                            "acquisition_wall_s",
                            "detector_cpu_s",
                            "detector_wall_s",
                            "solver_wall_s",
                            "order",
                            "cpu",
                            "visits",
                            "excluded",
                            "antenna_probes",
                            "admitted",
                            "raw_authority",
                            "receipt_sha256",
                            "prediction_sha256",
                        )
                    },
                )
            )
    return rows


def strongest(probe):
    accepted = (f for f in probe["candidates"] if f["passed_fractional_margin_gate"])
    return max(accepted, key=lambda f: (f["fractional_margin"], -f["candidate_rank"]), default=None)


def solver_failures(methods):
    records = []
    for (case, method), r in methods.items():
        if r["status"] == "ok":
            continue
        log = Path(r["prediction_path"]).parent / "solver/worker.log"
        frames = re.findall(r'File "([^"]+)", line (\d+), in ([^\n]+)', log.read_text())
        filename, line, function = frames[-1] if frames else (None, None, None)
        records.append(
            dict(
                case=case,
                dataset=r["dataset"],
                method=method,
                status=r["status"],
                reason=r["reason"],
                source_file=Path(filename).name if filename else None,
                line=line,
                function=function,
                worker_log=str(log),
            )
        )
    return records


def original_replay_parity(methods, output=None):
    """Check the reconstructed baseline against the archived detector after the blind lock."""
    rows = []
    for assigned in read((OUT if output is None else output) / "roster.json")["cases"]:
        case = assigned["case"]
        document = read_bound(case["native"])
        source = document["source"]
        archived = source["probes"]
        starts = [r["valid_start_counter"] for r in archived]
        starts.extend(e["sample_start"] for e in document["provenance"]["excluded_windows"])
        replay = Path(methods[case["id"], "original"]["prediction_path"]).with_name("native.json")
        fresh = read(replay)["source"]["probes"]
        old = {(r["visit_index"], r["receiver_id"]): strongest(r) for r in archived}
        both, passed_old, passed_new, match = 0, 0, 0, 0
        for r in fresh:
            a, b = old.pop((r["visit_index"], r["receiver_id"])), strongest(r)
            passed_old += a is not None
            passed_new += b is not None
            if a is not None and b is not None:
                both += 1
                dt = a["integer_epoch_sample"] + a["fractional_epoch_offset_samples"]
                dt -= b["integer_epoch_sample"] + b["fractional_epoch_offset_samples"]
                df = a["fractional_tracking_cfo_hz"] - b["fractional_tracking_cfo_hz"]
                match += abs(math.remainder(dt, 13333.0)) <= 0.01 and abs(df) <= 1
        if old:
            raise ValueError("missing original detector comparison probes")
        rows.append(
            dict(
                case=case["id"],
                dataset=case["panel"],
                hardware_span_s=(document["last_sample_counter"] - min(starts))
                / source["sample_rate_hz"],
                invalid_capture_visits=document["provenance"]["invalid_capture"],
                skipped_fast_score=document["provenance"]["skipped_fast_score"],
                paired_probes=len(fresh),
                archived_passes=passed_old,
                fresh_passes=passed_new,
                both_passed=both,
                pass_status_agrees=len(fresh) - passed_old - passed_new + 2 * both,
                strongest_agrees_within_1hz_and_0p01_sample=match,
            )
        )
    return rows


def summaries(rows):
    summaries = []
    for dataset in ("DS26", "DS29", "pooled"):
        for name in ARMS:
            for method in METHODS:
                sample = [
                    r
                    for r in rows
                    if r["method"] == method
                    and r["calibration"] == name
                    and (dataset == "pooled" or r["dataset"] == dataset)
                ]
                original = {
                    r["case"]: r
                    for r in rows
                    if r["method"] == "original" and r["calibration"] == name
                }
                common = [r for r in sample if r["fix"] and original[r["case"]]["fix"]]
                counts = thresholds([r["error_km"] for r in sample])
                conditional = distribution(r["error_km"] for r in sample)
                rf = distribution(r["conditional_rf_rms_hz"] for r in sample if r["fix"])
                pair_speed = distribution(
                    original[r["case"]]["end_to_end_wall_s"] / r["end_to_end_wall_s"]
                    for r in sample
                )
                summaries.append(
                    dict(
                        dataset=dataset,
                        method=method,
                        calibration=name,
                        assigned=len(sample),
                        fixes=conditional["n"],
                        within_recorded_duration=sum(
                            r["end_to_end_wall_s"] <= r["hardware_span_s"] for r in sample
                        ),
                        fix_within_recorded_duration=sum(
                            r["fix"] and r["end_to_end_wall_s"] <= r["hardware_span_s"]
                            for r in sample
                        ),
                        within_1km=counts["1"],
                        within_2km=counts["2"],
                        within_5km=counts["5"],
                        median_error_km=conditional["p50"],
                        p95_error_km=conditional["p95"],
                        median_rf_rms_hz=rf["p50"],
                        paired_median_speedup=pair_speed["p50"],
                        paired_median_speedup_both_fixed=distribution(
                            original[r["case"]]["end_to_end_wall_s"] / r["end_to_end_wall_s"]
                            for r in common
                        )["p50"],
                        paired_median_detector_cpu_speedup=distribution(
                            original[r["case"]]["detector_cpu_s"] / r["detector_cpu_s"]
                            for r in sample
                        )["p50"],
                        faster_than_original=sum(
                            r["end_to_end_wall_s"] < original[r["case"]]["end_to_end_wall_s"]
                            for r in sample
                        ),
                        both_return=len(common),
                        gained_fix=sum(r["fix"] and not original[r["case"]]["fix"] for r in sample),
                        lost_fix=sum(not r["fix"] and original[r["case"]]["fix"] for r in sample),
                        closer_on_common=sum(
                            r["error_km"] < original[r["case"]]["error_km"] for r in common
                        ),
                        paired_median_error_change_km=distribution(
                            r["error_km"] - original[r["case"]]["error_km"] for r in common
                        )["p50"],
                        **{
                            f"median_{f}": distribution(r[f] for r in sample)["p50"]
                            for f in (
                                "end_to_end_wall_s",
                                "acquisition_wall_s",
                                "detector_cpu_s",
                                "solver_wall_s",
                            )
                        },
                        p95_end_to_end_wall_s=distribution(r["end_to_end_wall_s"] for r in sample)[
                            "p95"
                        ],
                    )
                )
    return summaries


def score():
    methods, predictions = inventory()
    write_csv(OUT / "solver-failures.csv", solver_failures(methods))
    parity = original_replay_parity(methods)
    write_csv(OUT / "original-replay-parity.csv", parity)
    truths = {r["id"]: r["truth"] for r in corpus.references("ds26-all159")}
    ds29 = read(DS29 / "evaluation-references.json")
    for ident, _ in methods:
        if ident.startswith("DS29-"):
            truths[ident] = [ds29[ident]["latitude_deg"], ds29[ident]["longitude_deg"]]
    rows = join_survey(methods, predictions, truths)
    spans = {r["case"]: r["hardware_span_s"] for r in parity}
    for r in rows:
        r["hardware_span_s"] = spans[r["case"]]
    write_csv(
        OUT / "runtimes.csv", [dict(r, hardware_span_s=spans[r["case"]]) for r in methods.values()]
    )
    write_csv(OUT / "recordings.csv", rows)
    write_csv(OUT / "summary.csv", summaries(rows))
    from .blind_compact_figures import figures

    figures(rows, OUT)


if __name__ == "__main__":
    score()
