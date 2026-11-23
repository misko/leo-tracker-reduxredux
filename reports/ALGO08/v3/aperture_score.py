"""Score completed aperture receipts against the archived evaluation references."""

import argparse
import csv
import gzip
from hashlib import sha256
import json
from pathlib import Path
from statistics import median

from aperture_trial import ARMS, CASES, read
from tools.pipeline_eval.scoring import distance_km
from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km


HERE = Path(__file__).resolve().parent
PHYSICAL = HERE.parents[1] / "2026_11_21_ds30_full/reference-audit.json"
SIMULATED = HERE.parent / "regional-release/scoring-key.json"
RECORDINGS = {"north": "0abe7b4514be674d9f5388e3", "south": "6bd1f26bfa0bedfcf3f100f8"}


def references():
    physical, = [case for case in read(PHYSICAL)["cases"] if case["dataset_label"] == "DS30-0008"]
    if not physical["authority_eligible"]:
        raise ValueError("Physical development recording lacks an eligible reference")
    point = physical["reference"]
    truth = {"DS30-0008": (point["latitude_deg"], point["longitude_deg"])}
    for site, key in RECORDINGS.items():
        position, = {tuple(row["truth"]) for row in read(SIMULATED)["answers"].values() if row["recording"] == key}
        for name in ("containing", "far"):
            truth[f"{site}-{name}"] = position
    return truth


def overlap(reference, compared):
    reference = {tuple(row[:-1]): row[-1] for row in reference}
    compared = {tuple(row[:-1]): row[-1] for row in compared}
    common = reference.keys() & compared.keys()
    return dict(common=len(common), changed=sum(reference[key] != compared[key] for key in common),
                dropped=len(reference.keys() - compared.keys()), added=len(compared.keys() - reference.keys()))


def compare(reference, row, truth):
    if row["identity"] != reference["identity"]:
        raise ValueError("Compared solver inputs differ in source recording or offer")
    clearance = face_clearance_km(row["identity"]["offer"], truth)
    containing = clearance >= 0
    returned = row["status"] == "ok"
    scores = {}
    for arm in ARMS:
        base = reference["arms"].get(arm, {}).get("latlon")
        estimate = row["arms"].get(arm, {}).get("latlon")
        base_error = None if base is None else distance_km(base, truth)
        error = None if estimate is None else distance_km(estimate, truth)
        base_rms = reference["arms"].get(arm, {}).get("rf_rms_hz")
        rms = row["arms"].get(arm, {}).get("rf_rms_hz")
        scores[arm] = dict(
            error_km=error, error_delta_km=None if error is None or base_error is None else error - base_error,
            rf_rms_hz=rms, rf_rms_delta_hz=None if rms is None or base_rms is None else rms - base_rms,
            ownership=overlap(reference.get("owner_rows", {}).get(arm, []), row.get("owner_rows", {}).get(arm, [])),
        )
    within = (returned and all(arm["error_delta_km"] is not None and arm["error_delta_km"] <= 0.25
                              for arm in scores.values()) if containing else not returned and row["status"] != "failed")
    return dict(
        status=row["status"], reason=row["reason"], arm_scores=scores, contained=containing,
        truth_clearance_km=clearance, triage_pass=within,
        calibration=dict(
            fitted_minus_zero_error_km=None if not returned else scores["fitted_c"]["error_km"] - scores["c0"]["error_km"],
            fitted_minus_zero_rf_rms_hz=None if not returned else scores["fitted_c"]["rf_rms_hz"] - scores["c0"]["rf_rms_hz"],
        ),
    )


def budget(dense, ingress):
    with (HERE / "first-55/stage-clocks.csv").open() as stream:
        stage, = [row for row in csv.DictReader(stream) if row["recording"] == "DS30-0008"]
    full = dense["full"]
    prefix = {mode: [next(row for row in pair if row["mode"] == mode) for pair in ingress["rotations"]]
              for mode in ("full", "fixed", "no-dsp")}
    prefix_skips = len(prefix["full"][0]["planned_skips"])
    saved_per_skip = median([row["eligible_detector_cpu_s"] for row in prefix["full"]]) / prefix_skips
    original_cpu = float(stage["cpu_s"])
    results = {}
    for mode in ("fixed", "guarded"):
        row = dense[mode]
        skips = len(row["mask"]["dropped"])
        dsp = saved_per_skip * skips
        solver = full["cpu_s"] - row["cpu_s"]
        # A fallback with retained skipped I/Q and measured raw factors restores
        # the skipped DSP and starts a full solve. Continued selection is free here.
        retry = dsp + full["cpu_s"]
        results[mode] = dict(
            skipped_visits=skips, skipped_iq_bytes_if_retained=skips * 1_600_000,
            optimistic_detector_cpu_saved_s=dsp, measured_solver_cpu_saved_s=solver,
            optimistic_total_cpu_s=original_cpu - dsp - solver,
            optimistic_total_cpu_ratio=(original_cpu - dsp - solver) / original_cpu,
            minimum_retry_cpu_s=retry, optimistic_retry_break_even=(dsp + solver) / retry,
            cpu_s_if_retry=original_cpu + row["cpu_s"],
        )
    return dict(warm_stage=stage, prefix_medians={mode: {
        key: median([row[key] for row in rows]) for key in ("cpu_s", "elapsed_s", "detector_cpu_s", "eligible_detector_cpu_s")
    } for mode, rows in prefix.items()}, saved_cpu_per_skip_s=saved_per_skip, masks=results)


def score(directory, output, summary):
    paths = sorted(directory.glob("*.json"))
    truth_by_case = references()
    rows = {case: {mode: read(directory / f"{case}-{mode}.json") for mode in ("full", "fixed", "guarded")}
            for case in CASES}
    results = {case: {mode: compare(modes["full"], row, truth_by_case[case])
                      for mode, row in modes.items()} for case, modes in rows.items()}
    for case, modes in rows.items():
        for mode, row in modes.items():
            # Large per-point keys stay in the same compressed receipt as the
            # derived overlap, allowing an independent audit of ownership.
            row["score"] = results[case][mode]
    result = dict(
        verification=dict(files={path.name: sha256(path.read_bytes()).hexdigest() for path in paths},
                          references={str(path.relative_to(HERE.parents[2])): sha256(path.read_bytes()).hexdigest()
                                      for path in (PHYSICAL, SIMULATED)}),
        cases=rows, ingress=read(directory / "ingress.json"),
    )
    result["budget"] = budget(rows["DS30-0008"], result["ingress"])
    with output.open("xb") as stream:
        stream.write(gzip.compress(json.dumps(result, sort_keys=True, separators=(",", ":"),
                                             allow_nan=False).encode(), mtime=0))
    fields = ("cpu_s", "elapsed_s", "associated", "families", "tracks", "grid_points")
    numbers = {case: {mode: {
        **{key: row.get(key) for key in fields}, **row["score"],
        "opportunities": row["mask"]["opportunities"],
        "dropped_visits": len(row["mask"]["dropped"]),
        "escalated_visits": len(row["mask"]["escalated"]),
        "observations": row["mask"]["resulting_observations"],
        "restricted_observations": row["restricted"]["resulting_observations"],
    } for mode, row in modes.items()} for case, modes in rows.items()}
    with summary.open("x") as stream:
        json.dump(dict(cases=numbers, budget=result["budget"]), stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("summary", type=Path)
    score(**vars(parser.parse_args()))
