"""Join sealed original v5 and compact waveform predictions to released geography."""

import argparse
import gzip
from hashlib import sha256
from pathlib import Path

from ..__main__ import save_json
from ..scoring import ARMS, distance_km, validate_result
from ..variants.compact_tile_interior import margin
from . import screening_figures
from . import waveform_v5 as trial
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

RETRO_TRUTH = "ef1774b64cb48b5805b05eed64f4c8fe179ddb4b31f188debb7067f945503ffa"
COMPACT = {
    "retrospective": ("waveform_site_phase_release",),
    "holdout": ("waveform_holdout_phase_release", "waveform_holdout_interior"),
}
LABELS = {
    "containing": "25 km containing offer",
    "omitted": "25 km near-omitted offer",
    "far-omitted": "25 km far-omitted offer",
}
PINS = ("input_sha256", "native_sha256", "catalogue_sha256")


def sealed(folder, name, digest=None):
    path = folder / name
    if digest is not None:
        trial.original.checked(path, digest)
    doc = trial.original.read(path)
    for item, expected in doc["files"].items():
        trial.original.checked(folder / item, expected)
    return doc


def position_rows(measured, request, query):
    validate_result(measured["result"])
    case = measured["result"]
    tile = dict(center=request["tile"], width_km=25.0)
    truth = query["truth"]
    if (margin(truth, tile) > 0) != (query["condition"] == "containing"):
        raise ValueError("released offer condition disagrees with actual tile containment")
    for arm in ARMS:
        endpoint = case["arms"][arm]
        point = endpoint["latlon"]
        yield dict(
            id=query["id"],
            condition=query["condition"],
            method=measured["method"],
            arm=arm,
            status=case["status"],
            reason=case.get("reason"),
            published=point is not None,
            false_publication=point is not None and query["condition"] != "containing",
            error_km=distance_km(truth, point),
            forced_error_km=distance_km(truth, endpoint.get("forced_latlon")),
            point_face_margin_km=margin(point, tile) if point is not None else None,
            truth_face_margin_km=margin(truth, tile),
            rf_rms_hz=endpoint.get("rf_rms_hz"),
            frequency_score=case["metrics"].get(f"{arm}_frequency_score"),
            worker_wall_s=measured["worker_wall_s"],
            worker_cpu_s=measured["worker_cpu_s"],
            worker_peak_bytes=measured.get("worker_cgroup_peak_bytes"),
            worker_process_rss_kib=measured.get("peak_rss_kib"),
            prepared_observations=case["metrics"].get("native_observations"),
            associated_observations=case["metrics"].get(f"{arm}_associated_observations"),
            tracks=case["metrics"].get("tracks"),
            **{key: measured[key] for key in PINS},
        )


def matched_rows(rows, requests, queries, methods, legacy):
    expected = {(ident, method) for ident in requests for method in methods}
    if len(rows) != len(expected) or {(r["id"], r["method"]) for r in rows} != expected:
        raise ValueError("each registered method must return one result per offer")
    if set(queries) != set(requests):
        raise ValueError("truth release and authenticated prediction offers differ")
    output = []
    for row in rows:
        ident = row["id"]
        case, query = requests[ident], queries[ident]
        expected_input = trial.blind.digest_json(case)
        if row["method"] == trial.METHOD and row.get("service"):
            if row["tile"] != dict(center=case["tile"], width_km=25) or (
                row["screen_center"] != case["screen_center"]
                or row["config_sha256"] != case["config_sha256"]
            ):
                raise ValueError("the original service changed its offered tile, screen or config")
            if legacy:
                rebound = dict(case, cutoff_utc_ns=row["cutoff_utc_ns"])
                if row["input_sha256"] != trial.blind.digest_json(rebound):
                    raise ValueError("the retrospective original rebound request differs")
                row = dict(row, input_sha256=expected_input)
        if (
            row["input_sha256"] != expected_input
            or row["native_sha256"] != case["native_sha256"]
            or row["catalogue_sha256"] != case["catalog_sha256"]
            or any(row.get(k) != value for k, value in query["bindings"].items())
        ):
            raise ValueError("the original and compact receivers do not use the same input")
        output.append(row)
    return output


def within_method(scored):
    fields = ("error_km", "rf_rms_hz", "frequency_score")
    pairs = {}
    for row in scored:
        pairs.setdefault((row["id"], row["method"]), {})[row["arm"]] = row
    return [
        dict(
            id=ident,
            method=method,
            condition=fits["c0"]["condition"],
            **{
                f"fitted_minus_zero_{field}": fits["fitted_c"][field] - fits["c0"][field]
                if all(fits[arm][field] is not None for arm in ARMS)
                else None
                for field in fields
            },
        )
        for (ident, method), fits in pairs.items()
    ]


def score(cohort):
    out = trial.REPORT / cohort
    parent = trial.RETROSPECTIVE if cohort == "retrospective" else trial.HOLDOUT
    predictions = sealed(out, "prediction-lock.json")
    plan = trial.original.read(out / "source-lock.json")
    trial.original.checked(
        parent / plan.get("parent_seal", "prediction-lock.json"), plan["parent_sha256"]
    )
    if cohort == "retrospective":
        raw = gzip.decompress((out / "as-measured-launcher.py.gz").read_bytes())
        if sha256(raw).hexdigest() != plan["launcher_sha256"]:
            raise ValueError("the original compared launcher's exact source was lost")
    elif plan["launcher_sha256"] != trial.original.sha(Path(trial.__file__)):
        raise ValueError("held-out as-measured launcher changed")
    compact = sealed(
        parent,
        "prediction-lock.json",
        trial.RETROSPECTIVE_PIN if cohort == "retrospective" else None,
    )
    truth = sealed(parent, "score-lock.json", RETRO_TRUTH if cohort == "retrospective" else None)
    if truth["files"]["prediction-lock.json"] != trial.original.sha(
        parent / "prediction-lock.json"
    ):
        raise ValueError("truth release did not bind compact predictions")
    if cohort == "holdout" and truth["files"]["reference-prediction-lock.json"] != (
        trial.original.sha(out / "prediction-lock.json")
    ):
        raise ValueError("holdout truth release did not bind terminal original v5 predictions")
    methods = (trial.METHOD, *COMPACT[cohort])
    attempts = rows_from(out / "positions.jsonl.gz")
    attempts.extend(r for r in rows_from(parent / "positions.jsonl.gz") if r["method"] in methods)
    requests = {r["id"]: r for r in trial.original.read(parent / "requests.json")}
    query_path = parent / "figure-queries.json"
    query_rows = trial.read_checked(query_path, truth["files"][query_path.name])
    if isinstance(query_rows, dict):
        query_rows = query_rows["queries"]
    queries = {r["id"]: r for r in query_rows}
    if set(predictions["cases"]) != set(compact["cases"]):
        raise ValueError("terminal waveform rosters changed after estimation")
    rows = matched_rows(attempts, requests, queries, methods, cohort == "retrospective")
    scored = [
        score
        for row in rows
        for score in position_rows(row, requests[row["id"]], queries[row["id"]])
    ]
    csv_file(out / "scores.csv", scored)
    csv_file(out / "calibration.csv", within_method(scored))
    save_json(out / "figure-queries.json", {"queries": list(queries.values())})
    pack(out / "matched-positions.jsonl.gz", rows)
    save_json(
        out / "parent-seals.json",
        dict(
            original_predictions=trial.original.sha(out / "prediction-lock.json"),
            parent_prediction=trial.original.sha(parent / "prediction-lock.json"),
            released_truth=trial.original.sha(parent / "score-lock.json"),
            truth_queries=trial.original.sha(query_path),
            scorer=trial.original.sha(Path(__file__)),
        ),
    )
    evidence = [
        "source-lock.json",
        "prediction-lock.json",
        "parent-seals.json",
        "scores.csv",
        "calibration.csv",
    ]
    if cohort == "retrospective":
        evidence.append("as-measured-launcher.py.gz")
    rows_name = "matched-positions.jsonl.gz"
    query_name = "figure-queries.json"
    files = [*evidence, rows_name, query_name]
    save_json(
        out / "figure-lock.json",
        dict(
            cases=predictions["cases"],
            files={name: trial.original.sha(out / name) for name in files},
        ),
    )
    conditions = {r["condition"] for r in queries.values()}
    series = [
        dict(key="candidate", label="Original v5 no-repair", file=rows_name, value=methods[0]),
        dict(
            key="stock",
            label="Installed compact phase release",
            file=rows_name,
            value=methods[1],
            match=list(PINS),
        ),
    ]
    if len(methods) == 3:
        series.append(
            dict(
                key="one",
                label="Installed compact 20 m interior",
                forced_label="Compact interior forced fit",
                file=rows_name,
                value=methods[2],
                match=list(PINS),
            )
        )
    save_json(
        out / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id=f"waveform-v5-{cohort}",
                    method=trial.METHOD,
                    scope="transfer",
                    cases="sealed",
                    title=f"Original v5 and compact on the same {cohort} waveform factors",
                    caption=(
                        "The receivers used identical complete stock GLRT factors, TrackConfig, "
                        "causal catalogue and 25 km offer. Each chart shows one calibration arm."
                    ),
                    queries=query_name,
                    seal="figure-lock.json",
                    provenance=evidence,
                    condition_labels={k: v for k, v in LABELS.items() if k in conditions},
                    series=series,
                )
            ],
        ),
    )
    screening_figures.generate(out / "charts", evidence=out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cohort", choices=COMPACT)
    score(parser.parse_args().cohort)
