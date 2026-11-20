"""Generate and score the frozen four-offer Doppler endpoint experiment."""

import argparse
import gzip
import hashlib
import json
import os
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from decimal import Decimal
from pathlib import Path
from runpy import run_path
from time import perf_counter

import numpy as np

from .. import corpus, scoring
from ..__main__ import DEFAULT_OUT, encoded, read_predictions, save_json, write
from ..variants import arc_validation

PANEL = "transfer124"
SEALED_TRUTH = {
    "field": "field_private",
    "field2": "field2_private",
    "synthetic": "holdout_private",
    "recorded": "recorded_private",
}


def _read(path):
    return json.loads(path.read_bytes())


def _study_root():
    return Path(os.environ.get("PIPELINE_EVAL_BLIND_ROOT", corpus.DEFAULT_BLIND)).resolve()


def public_cases(cache):
    """Resolve frozen public packets without opening the scorer-only rows."""
    ids, files = corpus._selection(PANEL)
    inputs = corpus._index(corpus._read_frozen("inputs.jsonl", files))
    bulk = Path(os.environ.get("PIPELINE_EVAL_BULK_ROOT", corpus.DEFAULT_BULK)).resolve()
    blind = _study_root()
    return [corpus._public(inputs[case_id], bulk, blind, cache) for case_id in ids]


def _predict_chunk(job):
    cpu, cases = job
    os.sched_setaffinity(0, {cpu})
    implementation = hashlib.sha256(Path(arc_validation.__file__).read_bytes()).hexdigest()
    records = []
    for case in cases:
        started = perf_counter()
        result = arc_validation.run(case, None)
        elapsed = perf_counter() - started
        scoring.validate_result(result)
        records.append(
            dict(
                id=case["id"],
                input_sha256=hashlib.sha256(encoded(case)).hexdigest(),
                implementation_sha256=implementation,
                worker_wall_s=elapsed,
                result=result,
            )
        )
    return records


def predict(cache, output, jobs):
    cases = public_cases(cache)
    cpus = sorted(os.sched_getaffinity(0))[:jobs]
    chunks = [(cpu, cases[i :: len(cpus)]) for i, cpu in enumerate(cpus)]
    with ProcessPoolExecutor(max_workers=len(cpus)) as executor:
        predictions = {
            r["id"]: r for records in executor.map(_predict_chunk, chunks) for r in records
        }
    raw = b"".join(encoded(predictions[case["id"]]) + b"\n" for case in cases)
    write(output, gzip.compress(raw, mtime=0) if output.suffix == ".gz" else raw)


def _locked_records():
    truth, control = {}, {}
    study = _study_root()
    lock = _read(study / "locks/prediction-lock.json")["sha256"]
    for tree, private in SEALED_TRUTH.items():
        target = study / private / "truth.json"
        baseline = study / "predictions" / f"{tree}.json"
        target_lock = _read(study / "locks" / f"{tree}.json")["truth_sha256"]
        sources = ((target, target_lock, truth), (baseline, lock[baseline.name], control))
        for path, digest, records in sources:
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError(f"sealed file digest mismatch for {path}")
            records.update({row["id"]: row for row in json.loads(raw)["cases"]})
    return truth, control


def _region_row(row, label, result, baseline):
    metrics = result["metrics"]
    selected = metrics.get("selected_region_id")
    original = baseline["best_region"]
    correct = label["true_region"]
    accepted = metrics.get("region_accepted", False)
    original_accepted = baseline["diagnostics"]["region_result"]["status"] == "accepted"
    return dict(
        id=row["id"],
        recording=row["recording"],
        dataset=row["group"],
        condition=row["condition"],
        true_region=correct,
        site_group=label["site_group"],
        selected_region=selected,
        selected_correct=(selected == correct) if correct else None,
        region_accepted=accepted,
        baseline_selected_region=original,
        baseline_selected_correct=(original == correct) if correct else None,
        baseline_region_accepted=original_accepted,
        held_region_lead=metrics.get("held_region_lead"),
        held_rms_hz=metrics.get("held_rms_hz"),
        regional_scores=metrics.get("regional_scores"),
        reason=result["reason"],
        baseline_reason=baseline["reason"],
        baseline_published_error_km=scoring.distance_km(baseline["latlon"], row["truth"]),
        baseline_forced_error_km=scoring.distance_km(baseline["best_latlon"], row["truth"]),
    )


def _region_summary(rows, baseline=False):
    prefix = "baseline_" if baseline else ""
    select = f"{prefix}selected_correct"
    accept = f"{prefix}region_accepted"
    offered = rows[0]["condition"] == "present"
    return dict(
        nominations=sum(r[f"{prefix}selected_region"] is not None for r in rows),
        correct_nominations=sum(r[select] is True for r in rows) if offered else None,
        accepted=sum(r[accept] for r in rows),
        accepted_correct=sum(r[accept] and r[select] is True for r in rows) if offered else None,
        false_acceptances=sum(r[accept] and not r[select] for r in rows),
        reasons=dict(Counter(row[f"{prefix}reason"] for row in rows)),
    )


def score(prediction_path, output, summary_path=None):
    predictions = read_predictions(prediction_path)
    refs = list(corpus.references(PANEL))
    truth, controls = _locked_records()
    ids = {r["id"] for r in refs}
    if predictions.keys() != ids or truth.keys() != ids or controls.keys() != ids:
        raise ValueError("expected every frozen paired input and every sealed answer")
    if any(
        truth[r["id"]]["latlon"] != r["truth"] or truth[r["id"]]["condition"] != r["condition"]
        for r in refs
    ):
        raise ValueError("sealed coordinates differ from frozen scoring rows")
    if not all(
        (r["result"].get("arms") or {}).get("c0") == (r["result"].get("arms") or {}).get("fitted_c")
        for r in predictions.values()
    ):
        raise ValueError("fixed-RF additive calibration must cancel in both arms")
    summary, errors = scoring.score(refs, predictions)
    hashes = {r["implementation_sha256"] for r in predictions.values()}
    if len(hashes) != 1:
        raise ValueError("prediction batch contains more than one implementation")
    summary.update(
        prediction_sha256=hashlib.sha256(prediction_path.read_bytes()).hexdigest(),
        implementation_sha256=hashes.pop(),
    )
    regions = defaultdict(list)
    for row in refs:
        case_id = row["id"]
        result = predictions[case_id]["result"]
        regions[row["group"], row["condition"]].append(
            _region_row(row, truth[case_id], result, controls[case_id])
        )
    groups = [
        dict(
            dataset=dataset,
            condition=condition,
            attempts=len(rows),
            arc_validation=_region_summary(rows),
            baseline=_region_summary(rows, baseline=True),
            baseline_published_km=scoring.distribution(
                r["baseline_published_error_km"] for r in rows
            ),
            baseline_forced_km=scoring.distribution(r["baseline_forced_error_km"] for r in rows),
            selected_held_rms_hz=scoring.distribution(r["held_rms_hz"] for r in rows),
            held_region_lead=scoring.distribution(r["held_region_lead"] for r in rows),
        )
        for (dataset, condition), rows in sorted(regions.items())
    ]
    save_json(
        output,
        dict(
            summary=summary,
            errors=errors,
            region_summary=groups,
            region_cases=[r for group in regions.values() for r in group],
        ),
    )
    if summary_path:
        save_json(summary_path, summary)


def audit_source(source, output):
    """Rebuild the portable observations and causal catalogs without GNSS files."""
    study = _study_root()
    prep = run_path(str(study / "field_private/prepare_starloc.py"))
    public = study / "public_field"
    inputs = {
        doc["anchor_utc_ns"]: (path.stem, doc)
        for path in (public / "observations").glob("*.json")
        if (doc := _read(path))
    }
    query_catalogs = defaultdict(set)
    for path in (public / "queries").glob("*.json"):
        query = _read(path)
        query_catalogs[query["observation"]].add(query["catalog"])
    recording_rows, track_rows, available = [], [], {}
    cfg = sorted(_read(source / "configs.json"), key=lambda x: Decimal(x["start"]))
    for record in cfg:
        anchor = int(Decimal(record["start"]) * 10**9)
        obs_id, obs = inputs[anchor]
        if not anchor == obs["catalog_timestamp_ns"] == obs["cutoff_utc_ns"]:
            raise ValueError(f"public cutoff does not match the source UTC start for {obs_id}")
        folder = source / "data" / record["key"]
        tones = folder / "tracked_tones.mat"
        tracks, duplicates = prep["read_tracks"](tones)
        rebuilt = [
            dict(
                times=np.round(times, 8).tolist(),
                values=np.round(values, 6).tolist(),
                receiver=1,
                channel=prep["CHANNEL"],
                rf_hz=prep["RADIO_HZ"],
            )
            for times, values in tracks
        ]
        if rebuilt != obs["tracks"]:
            raise ValueError(f"source tracks do not reproduce the frozen input for {obs_id}")
        catalog, source_digest = prep["parse_catalog"](folder / "Starlink.tle")
        available.setdefault(source_digest, catalog)
        causal, causal_metrics = prep["orbit_for"](anchor, list(available.items()))
        digest = hashlib.sha256(causal).hexdigest()
        frozen = public / "orbits" / f"{digest}.tle"
        if query_catalogs[obs_id] != {digest} or frozen.read_bytes() != causal:
            raise ValueError(f"source catalogue does not reproduce the frozen input for {obs_id}")
        recording_rows.append(
            dict(
                observation_sha256=obs_id,
                orbit_sha256=digest,
                source_tones_sha256=hashlib.sha256(tones.read_bytes()).hexdigest(),
                source_orbit_sha256=source_digest,
                anchor_utc_ns=anchor,
                tracks=len(tracks),
                duplicates_removed=len({d["removed"] for d in duplicates}),
                early_tracks=sum(bool(t[-1] <= obs["duration_s"] / 2) for t, _ in tracks),
                late_tracks=sum(bool(t[0] >= obs["duration_s"] / 2) for t, _ in tracks),
                **causal_metrics,
            )
        )
        for times, values in tracks:
            centered = times - times.mean()
            fit = [np.polyfit(centered, values, degree) for degree in (1, 2, 3)]
            rms = [float(np.sqrt(np.mean((values - np.polyval(p, centered)) ** 2))) for p in fit]
            lattice = times / 0.007
            track_rows.append(
                dict(
                    observation_sha256=obs_id,
                    samples=len(times),
                    duration_s=float(times[-1] - times[0]),
                    longest_gap_s=float(np.diff(times).max()),
                    slope_hz_s=float(fit[0][0]),
                    linear_rms_hz=rms[0],
                    quadratic_rms_hz=rms[1],
                    cubic_rms_hz=rms[2],
                    max_time_grid_error_s=float(np.max(abs(lattice - np.rint(lattice))) * 0.007),
                )
            )
    if len(inputs) != len(recording_rows):
        raise ValueError("source input archive does not cover all frozen StarLoc acquisitions")
    save_json(output, dict(recordings=recording_rows, tracks=track_rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    inference = commands.add_parser("predict")
    inference.add_argument("output", type=Path)
    inference.add_argument("--cache", type=Path, default=DEFAULT_OUT / "inputs")
    inference.add_argument("--jobs", type=int, choices=range(1, 25), default=1)
    assessment = commands.add_parser("score")
    assessment.add_argument("predictions", type=Path)
    assessment.add_argument("output", type=Path)
    assessment.add_argument("--summary", type=Path)
    audit = commands.add_parser("audit")
    audit.add_argument("source_archive", type=Path)
    audit.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.operation == "predict":
        predict(args.cache, args.output, args.jobs)
    elif args.operation == "audit":
        audit_source(args.source_archive, args.output)
    else:
        score(args.predictions, args.output, args.summary)


if __name__ == "__main__":
    main()
