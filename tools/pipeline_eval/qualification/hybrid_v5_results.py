"""Score original v5 and both compact profiles on like-for-like waveform factors."""

import argparse
from pathlib import Path

from ..__main__ import local_output, save_json
from ..scoring import ARMS, coordinate, distance_km, validate_result
from ..variants.compact_tile_interior import margin
from . import hybrid_v5 as trial
from . import screening_figures
from . import v5_regional_blind as blind
from . import v5_regional_reference as original
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

FIGURE_ID = "hybrid-v5-matched-waveform"
MODES = (trial.METHOD, "hybrid_phase_release", "hybrid_interior")
LABELS = ("Original v5 no repair", "Compact phase-release", "Compact 20 m interior")
CONDITIONS = {
    "containing": "Hybrid · containing offer",
    "omitted": "Hybrid · near-omitted offer",
    "donor-only": "Donor only · no injected pilot",
}


def sealed(path, digest):
    original.checked(path, digest)
    lock = original.read(path)
    for name, checksum in lock["files"].items():
        member = blind.public_path(path.parent, name)
        original.checked(member, checksum)
    return lock


def normalized(rows, requests, labels):
    result = {}
    for row in rows:
        method = labels.get(row["method"])
        ident = row["id"]
        if method is None or ident not in requests:
            continue
        key = ident, method
        if key in result:
            raise ValueError("duplicate attempt in sealed comparison")
        request = requests[ident]
        fields = dict(
            input_sha256=blind.digest_json(request),
            native_sha256=request["native_sha256"],
            catalogue_sha256=request["catalog_sha256"],
        )
        if any(row.get(k) != v for k, v in fields.items()):
            raise ValueError("receiver used different factor, causal catalogue or offer bytes")
        validate_result(row["result"])
        result[key] = dict(row, method=method)
    return result


def confirm_pair(report, compact_lock, compact_sha):
    original_lock = report / "prediction-lock.json"
    lock = sealed(original_lock, original.sha(original_lock))
    upstream = sealed(compact_lock, compact_sha)
    detector_path = compact_lock.parent / "detector-lock.json"
    detector = sealed(detector_path, upstream["files"][detector_path.name])
    requests, cohorts = {}, {}
    for cohort in trial.COHORTS:
        case_folder = report / cohort
        proof = sealed(
            case_folder / "prediction-lock.json", lock["files"][f"{cohort}/prediction-lock.json"]
        )
        orig = original.read(case_folder / "input-lock.json")
        if detector["files"][f"{cohort}/detector-lock.json"] != orig["detector_lock_sha256"]:
            raise ValueError("original and phase-release did not receive the same detector seal")
        for row in original.read(case_folder / "requests.json"):
            ident = f"{cohort}-{row['id']}"
            requests[ident], cohorts[ident] = row, cohort
        if set(proof["cases"]) != {ident for ident in requests if cohorts[ident] == cohort}:
            raise ValueError("original position seal differs from its immutable roster")
    orig_rows = rows_from(report / "positions.jsonl.gz")
    compact = [
        dict(row, id=f"{row['variant']}-{row['id']}", offer_id=row["id"], cohort=row["variant"])
        for row in rows_from(compact_lock.parent / "positions.jsonl.gz")
    ]
    rows = normalized(
        [*orig_rows, *compact],
        requests,
        {
            trial.METHOD: trial.METHOD,
            "hybrid_site_compact": MODES[1],
            "hybrid_site_interior": MODES[2],
        },
    )
    if set(rows) != {(ident, method) for ident in requests for method in MODES}:
        raise ValueError("original and phase-release comparison has unpaired work")
    return rows, requests, cohorts


def scored(rows, requests, targets, cohort):
    queries, output = [], []
    donor_labels = {
        ident: n
        for n, ident in enumerate(sorted(i for i in requests if cohort[i] == "donor-only"), 1)
    }
    for ident, request in requests.items():
        target = targets[ident]
        location = coordinate(target["truth"])
        condition = target["condition"]
        tile = dict(center=request["tile"], width_km=25.0)
        actual_margin = margin(location, tile) if location is not None else None
        if cohort[ident] == "donor-only":
            if condition != "donor-only" or location is not None:
                raise ValueError("donor-only waveform must have no synthetic truth")
            recording = f"One donor waveform · offer {donor_labels[ident]}"
        else:
            if (
                condition not in ("containing", "omitted")
                or actual_margin is None
                or ((actual_margin > 0) != (condition == "containing"))
            ):
                raise ValueError("hybrid label and supplied tile geometry disagree")
            recording = "One hybrid waveform site"
        seat = rows[ident, trial.METHOD]
        queries.append(
            dict(
                id=ident,
                condition=condition,
                recording=recording,
                truth=location,
                bindings={
                    k: seat[k] for k in ("input_sha256", "native_sha256", "catalogue_sha256")
                },
            )
        )
        for mode in MODES:
            row = rows[ident, mode]
            fit = row["result"]
            for arm in ARMS:
                endpoint = fit["arms"].get(arm, {})
                found = endpoint.get("latlon")
                forced = endpoint.get("forced_latlon")
                output.append(
                    dict(
                        id=ident,
                        condition=condition,
                        method=mode,
                        arm=arm,
                        status=fit["status"],
                        reason=fit.get("reason"),
                        published=found is not None,
                        false_publication=found is not None and condition != "containing",
                        error_km=distance_km(location, found),
                        forced_error_km=distance_km(location, forced),
                        rf_rms_hz=endpoint.get("rf_rms_hz"),
                        frequency_score=fit["metrics"].get(f"{arm}_frequency_score"),
                        truth_face_margin_km=actual_margin,
                        position_face_margin_km=margin(found, tile) if found else None,
                        forced_face_margin_km=margin(forced, tile) if forced else None,
                        worker_wall_s=row.get("worker_wall_s"),
                        worker_cpu_s=row.get("worker_cpu_s"),
                        peak_rss_kib=row.get("peak_rss_kib"),
                        worker_cgroup_peak_bytes=row.get("worker_cgroup_peak_bytes"),
                    )
                )
    if {q["condition"] for q in queries} != set(CONDITIONS):
        raise ValueError("both blind offer roles and the no-injection control must be retained")
    return queries, output


def publish(report, compact_lock, compact_sha, truth, truth_sha):
    if (report / "score-lock.json").exists():
        raise FileExistsError("official hybrid matched scoring is already sealed")
    rows, requests, cohorts = confirm_pair(report, compact_lock, compact_sha)
    custodian = truth.parent / "score-lock.json"
    release = sealed(custodian, original.sha(custodian))["files"]
    original_sha = original.sha(report / "prediction-lock.json")
    if (
        release.get(truth.name) != truth_sha
        or release.get("prediction-lock.json") != compact_sha
        or release.get("reference-prediction-lock.json") != original_sha
    ):
        raise ValueError("custodian labels must follow both exact prediction seals")
    released = original.read(truth)["targets_by_background"]
    targets = {
        ident: released[cohorts[ident]][request["id"]] for ident, request in requests.items()
    }
    queries, scores = scored(rows, requests, targets, cohorts)
    files = ("matched-positions.jsonl.gz", "figure-queries.json", "scores.csv", "references.json")
    pack(report / files[0], [rows[pair] for pair in sorted(rows)])
    save_json(report / files[1], dict(queries=queries))
    csv_file(report / files[2], scores)
    save_json(
        report / files[3],
        dict(
            original_prediction_lock_sha256=original_sha,
            compact_prediction_lock_sha256=compact_sha,
            evaluator_sha256=truth_sha,
            custodian_score_lock_sha256=original.sha(custodian),
            source_sha256=original.sha(Path(__file__)),
        ),
    )
    seal = "score-lock.json"
    save_json(
        report / seal,
        dict(cases=list(requests), files={name: original.sha(report / name) for name in files}),
    )
    pairs = ["input_sha256", "native_sha256", "catalogue_sha256"]
    keys = ("one", "stock", "candidate")
    chart = dict(
        id=FIGURE_ID,
        method=MODES[2],
        scope="transfer",
        cases="sealed",
        seal=seal,
        title="Original and compact v5 on the same hybrid waveform factors",
        caption=(
            "One simulated pilot site over archived receiver background, with two 25 km "
            "offers. The donor-only waveform carries no injected emitter. An output on either "
            "donor-only offer is a false publication with no geographic error to plot."
        ),
        queries=files[1],
        condition_labels=CONDITIONS,
        provenance=list(files[2:]),
        series=[
            dict(
                key=key,
                label=label,
                file=files[0],
                value=method,
                **(
                    {"match": pairs}
                    if key != "candidate"
                    else {"forced_label": "Interior forced fit"}
                ),
            )
            for key, label, method in zip(keys, LABELS, MODES, strict=True)
        ],
    )
    save_json(report / "figures.json", dict(version=1, charts=[chart]))
    screening_figures.generate(report / "charts", methods=[FIGURE_ID], evidence=report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=local_output, default=trial.REPORT)
    parser.add_argument("--compact-lock", type=Path, required=True)
    parser.add_argument("--compact-sha256", required=True)
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--truth-sha256", required=True)
    args = parser.parse_args()
    publish(args.out, args.compact_lock, args.compact_sha256, args.truth, args.truth_sha256)
