"""Qualify the sealed native winner rule and run the same blind v5 solver on both c arms."""

import argparse
import json
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
from time import perf_counter, process_time

from tools.pipeline_eval.corpus import _references
from tools.pipeline_eval.qualification.full_v5_check import (
    ALIAS_HZ,
    BULK,
    CFO_TOLERANCE_HZ,
    EPOCH_TOLERANCE_SAMPLES,
    FRAME_HZ,
    FROZEN,
    REPO,
    _load_case,
    _sha,
    _wrapped,
)
from tools.pipeline_eval.qualification.recording_to_v5 import bind_request, digest, save
from tools.pipeline_eval.scoring import ARMS, distance_km, distribution, validate_result
from tools.pipeline_eval.variants import native_winner

SEAL = REPO / "reports/2026_11_19_receiver_frontend/winner/calibration.json"
SEAL_SHA256 = "61ce09ea5001ab9586c6aaf07087ac6bdf9eee55c0f4284769cf33ffeaa6d792"
COMPLETE = BULK / "leo-dev/pipeline-eval-20261118/full-v5-check"
SMOKE_INPUTS = {
    "DS26-0036": (
        COMPLETE / "native-complete/native.json",
        "41b74326231d17abcc1ed6e8cfd37574a2f5752c366bc1e8b959c39c1ec5f94e",
    ),
    "DS29-0082": (
        COMPLETE / "native-complete-ds29/native.json",
        "9b66406e24a94f2cf11adfe858289dbd45696d4e1244d5374b5679d32e8bec49",
    ),
}
ARMS_OF_TRIAL = ("reference", "native", "calibrated")
OUTCOMES = (
    "matched",
    "changed_winner",
    "reference_positive_only",
    "native_positive_only",
    "both_null",
)


def _read(path, expected=None):
    data = path.read_bytes()
    if expected is not None and sha256(data).hexdigest() != expected:
        raise ValueError(f"Input digest differs from recorded authority: {path}")
    return json.loads(data)


def _seal():
    receipt = _read(SEAL, SEAL_SHA256)
    if (
        _sha(Path(native_winner.__file__)) != receipt["policy_source_sha256"]
        or receipt["policy"] != native_winner.POLICY
        or receipt["minimum_margin"] != native_winner.MINIMUM_MARGIN
    ):
        raise ValueError("Native winner policy differs from the DS26 calibration seal")
    return receipt


def archived_candidate(candidates):
    """Use the published v5 winner rule including the gate recorded by its producer."""
    return max(
        (c for c in candidates if c["passed_fractional_margin_gate"] is True),
        key=lambda c: (c["fractional_margin"], -c["candidate_rank"]),
        default=None,
    )


def _physical_match(left, right, frame):
    if left is None or right is None:
        return None
    dt = _wrapped(
        right["integer_epoch_sample"]
        + right["fractional_epoch_offset_samples"]
        - left["integer_epoch_sample"]
        - left["fractional_epoch_offset_samples"],
        frame,
    )
    raw = right["fractional_tracking_cfo_hz"] - left["fractional_tracking_cfo_hz"]
    alias = _wrapped(raw, ALIAS_HZ)
    if abs(dt) <= EPOCH_TOLERANCE_SAMPLES and abs(alias) <= CFO_TOLERANCE_HZ:
        return dt, raw, alias
    return None


def _counts(counter):
    result = {name: counter[name] for name in OUTCOMES}
    result.update(
        oracle_complete=counter["oracle_complete"], oracle_stock_gate=counter["oracle_stock_gate"]
    )
    result["probes"] = sum(result[name] for name in OUTCOMES)
    positives = result["matched"] + result["changed_winner"]
    reference = positives + result["reference_positive_only"]
    native = positives + result["native_positive_only"]
    result.update(
        reference_positive=reference,
        native_positive=native,
        matched_f1=2 * result["matched"] / (reference + native) if reference + native else None,
    )
    return result


def compare(reference, native, calibrated):
    """Compare the selected observations on each identical measured probe."""
    docs = (native, calibrated)
    source = reference["source"]
    for other in docs:
        if any(
            other[key] != reference[key]
            for key in ("clock_anchor", "delivery_clocks", "last_sample_counter")
        ):
            raise ValueError("Detector documents use different recorded clock inputs")
        if any(
            other["source"][k] != v
            for k, v in source.items()
            if k not in ("analysis_manifest_sha256", "probes")
        ):
            raise ValueError("Detector documents use different capture metadata")
        for key in ("window_count", "processed_windows", "invalid_capture", "excluded_windows"):
            if other["provenance"][key] != reference["provenance"][key]:
                raise ValueError(f"Detector documents have different capture authority: {key}")

    totals = defaultdict(Counter)
    lanes = defaultdict(lambda: defaultdict(Counter))
    deltas = defaultdict(list)
    frame = round(source["sample_rate_hz"] / FRAME_HZ)
    for ref_probe, raw_probe, gated_probe in zip(
        source["probes"], *(o["source"]["probes"] for o in docs), strict=True
    ):
        support = {key: val for key, val in ref_probe.items() if key != "candidates"}
        if any(
            {key: val for key, val in p.items() if key != "candidates"} != support
            for p in (raw_probe, gated_probe)
        ):
            raise ValueError("Detector probes differ in captured sample support or ordering")
        lane = (ref_probe["channel"], ref_probe["receiver_id"])
        ref = archived_candidate(ref_probe["candidates"])
        possible = [
            c for c in raw_probe["candidates"] if _physical_match(ref, c, frame) is not None
        ]
        oracle_stock = any(c["passed_fractional_margin_gate"] is True for c in possible)
        for name, probe in (("native", raw_probe), ("calibrated", gated_probe)):
            choice = archived_candidate(probe["candidates"])
            match = _physical_match(ref, choice, frame)
            if match is not None:
                outcome = "matched"
                deltas[name].append(match)
            elif ref is not None:
                outcome = "reference_positive_only" if choice is None else "changed_winner"
            else:
                outcome = "both_null" if choice is None else "native_positive_only"
            for count in (totals[name], lanes[name][lane]):
                count[outcome] += 1
                count["oracle_complete"] += bool(possible)
                count["oracle_stock_gate"] += oracle_stock
    return {
        name: dict(
            overall=_counts(totals[name]),
            channel_receiver=[
                dict(channel=ch, receiver=rx, **_counts(counts))
                for (ch, rx), counts in sorted(lanes[name].items())
            ],
            matched_alias_branch_changes=sum(
                abs(raw) > CFO_TOLERANCE_HZ for _, raw, _ in deltas[name]
            ),
            matched_absolute_aliased_cfo_delta_hz=distribution(
                abs(alias) for _, _, alias in deltas[name]
            ),
            matched_signed_aliased_cfo_delta_hz=distribution(alias for _, _, alias in deltas[name]),
        )
        for name in ("native", "calibrated")
    }


def prepare(case, output, native_path):
    """Write the calibrated factor document and detector audit before position runs."""
    _seal()
    pinned = SMOKE_INPUTS.get(case["id"])
    if native_path is None and pinned is None:
        raise ValueError("Pass --native for this complete recording")
    path = native_path.resolve(strict=True) if native_path is not None else pinned[0]
    path_sha = _sha(path)
    if pinned is not None and path_sha != pinned[1]:
        raise ValueError("Complete smoke native factors differ from the frozen IQ replay")
    native = _read(path, path_sha)
    ref = case["native"]
    reference = _read(BULK / ref["path"], ref["sha256"])
    source, provenance = native["source"], native["provenance"]
    if (
        source["session_id"] != case["session_id"]
        or provenance["window_count"] != case["recording"]["window_count"]
        or provenance["skipped_fast_score"] != 0
        or len(source["probes"]) != 2 * provenance["processed_windows"]
    ):
        raise ValueError("Native replay does not bind the selected complete recording")
    native_identity = digest(
        [
            "native-short-window-glrt/fractional-epoch",
            provenance["detector_sha256"],
            source["input_manifest_sha256"],
            source["probes"],
            provenance["excluded_windows"],
        ]
    )
    if source["analysis_manifest_sha256"] != native_identity:
        raise ValueError("Qualification requires ordinary dual-receiver native replay factors")

    # Measure the same per-probe operation a streaming caller would perform.
    start = process_time()
    winners = [native_winner.select_candidate(p["candidates"]) for p in source["probes"]]
    selector_cpu_s = process_time() - start
    start = perf_counter()
    calibrated = native_winner.apply_document(native)
    document_wall_s = perf_counter() - start
    if [p["candidates"] for p in calibrated["source"]["probes"]] != [
        [c] if c is not None else [] for c in winners
    ]:
        raise ValueError("Document and streaming rule selected different winners")
    audit = compare(reference, native, calibrated)
    output.mkdir(parents=True, exist_ok=False)
    derived = output / "native-calibrated.json"
    save(derived, calibrated)
    save(
        output / "detector.json",
        dict(
            case=case["id"],
            seal_sha256=SEAL_SHA256,
            input_path=str(path),
            input_sha256=path_sha,
            reference_sha256=ref["sha256"],
            calibrated_sha256=_sha(derived),
            processed_windows=native["provenance"]["processed_windows"],
            excluded_windows=native["provenance"]["invalid_capture"],
            selector_cpu_s=selector_cpu_s,
            selector_cpu_us_per_probe=selector_cpu_s * 1e6 / len(winners),
            document_wall_s=document_wall_s,
            detector_results=audit,
        ),
    )


def position(case, output, arm, solver):
    from tools.pipeline_eval.variants import compact_finish, v5_lean

    _seal()
    audit = _read(output / "detector.json")
    if audit["seal_sha256"] != SEAL_SHA256 or audit["case"] != case["id"]:
        raise ValueError("Prepare the sealed detector evidence for this case first")
    if arm == "reference":
        locator = case["native"]
        path, expected = BULK / locator["path"], locator["sha256"]
    elif arm == "native":
        path, expected = Path(audit["input_path"]), audit["input_sha256"]
    else:
        path, expected = output / "native-calibrated.json", audit["calibrated_sha256"]
    if _sha(path) != expected:
        raise ValueError("Position factors differ from the prepared detector audit")
    destination = output / arm
    destination.mkdir(exist_ok=False)
    experiment = bind_request(case, path, destination / "experimental-request.json")
    run = {"v5-lean": v5_lean.run, "compact-finish": compact_finish.run}[solver]
    start = perf_counter()
    result = run(experiment, destination / "position")
    validate_result(result)
    save(
        destination / "prediction.json",
        dict(
            id=case["id"],
            variant=arm,
            solver=solver,
            result=result,
            worker_wall_s=perf_counter() - start,
        ),
    )


def score(case, output):
    """Resolve the frozen evaluation target only after positioning artifacts exist."""
    inputs = [output / arm / "prediction.json" for arm in ARMS_OF_TRIAL]
    predictions = [_read(path) for path in inputs if path.is_file()]
    if not predictions or len({row["solver"] for row in predictions}) != 1:
        raise ValueError("Scoring requires at least one frozen prediction from the same solver")
    inventory = _read(FROZEN / "provenance.json")["files"]
    target = next(_references([case["id"]], inventory))
    rows = []
    for prediction in predictions:
        if prediction["id"] != case["id"]:
            raise ValueError("Prediction belongs to a different recording")
        result = prediction["result"]
        rows.append(
            dict(
                variant=prediction["variant"],
                solver=prediction["solver"],
                status=result["status"],
                worker_wall_s=prediction["worker_wall_s"],
                tracks=result["metrics"].get("tracks"),
                observations=result["metrics"].get("native_observations"),
                arms={
                    arm: dict(
                        error_km=distance_km(result["arms"][arm]["latlon"], target["truth"]),
                        conditional_rms_hz=result["metrics"].get(f"{arm}_conditional_rms_hz"),
                        frequency_score=result["metrics"].get(f"{arm}_frequency_score"),
                        associated_observations=result["metrics"].get(
                            f"{arm}_associated_observations"
                        ),
                    )
                    for arm in ARMS
                },
            )
        )
    save(
        output / "scores.json",
        dict(case=case["id"], rows=rows, historical=target["reference"].get("baseline")),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", *ARMS_OF_TRIAL, "score"))
    parser.add_argument("case")
    parser.add_argument("output", type=Path)
    parser.add_argument("--native", type=Path)
    parser.add_argument("--solver", choices=("v5-lean", "compact-finish"), default="v5-lean")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to("/mnt/qnap01") or output.is_relative_to(BULK / "leo"):
        parser.error("Trial output must be outside the recording archives")
    case = _load_case(args.case)
    if args.stage == "prepare":
        prepare(case, output, args.native)
    elif args.stage == "score":
        score(case, output)
    else:
        position(case, output, args.stage, args.solver)


if __name__ == "__main__":
    main()
