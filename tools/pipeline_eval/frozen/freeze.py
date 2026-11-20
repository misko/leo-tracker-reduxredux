"""Recover frozen inputs and oracle tables from the original comparison archives."""

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
from tempfile import NamedTemporaryFile

ROOT = Path(__file__).resolve().parents[3]
REPORTS = ROOT / "reports"
COMPARISON = REPORTS / "2026_11_18_v5_blind_comparison"
BLIND = REPORTS / "2026_11_18_blind_regional_receiver"
BULK = Path("/srv/bulk")
DS26 = BULK / "leo-dev/accuracy-repair-20261115/ds26-four-configs-twice-001"
DS29 = BULK / "leo-dev/ds29-20261113/snapshot"
DS29_RUNS = BULK / "leo-dev/blind-v5-comparison-20261118/ds29"
GRAPHS = BULK / "leo/research/algo07v3-20261104/tracks001/candidate"
PANEL = REPORTS / "2026_11_18_embedded_prototypes/panel.json"
BLIND_PANELS = {
    "recorded": ("DS29", "recorded_private"),
    "field": ("StarLoc", "field_private"),
    "synthetic": ("Synthetic", "holdout_private"),
    "field2": ("Altrincham", "field2_private"),
}
DATA_FILES = ("inputs.jsonl", "targets.jsonl", "scores.csv", "panels.json")


def output_paths(output):
    output = output.resolve()
    names = (*DATA_FILES, "provenance.json")
    paths = {name: output / name for name in names}
    if any(
        path.resolve().is_relative_to(Path("/mnt/qnap01")) for path in (output, *paths.values())
    ):
        raise ValueError("Frozen benchmark fixtures must be written outside /mnt/qnap01")
    return paths


def write_atomic(path, raw):
    with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(raw)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def packed(doc):
    return (json.dumps(doc, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def locator(path, digest):
    return {"path": str(Path(path).relative_to(BULK)), "sha256": digest.removeprefix("sha256:")}


def distance_km(a, b):
    lat_a, lat_b = math.radians(a[0]), math.radians(b[0])
    dlon = math.radians(math.remainder(b[1] - a[1], 360))
    chord = math.sin((lat_b - lat_a) / 2) ** 2
    chord += math.cos(lat_a) * math.cos(lat_b) * math.sin(dlon / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(min(1.0, chord)))


def blind_fixture(rows, sources):
    records = {
        r["observation_sha256"]: r["dataset_label"]
        for r in read(BLIND / "recorded_private/provenance.json")["observations"]
    }
    scores, inputs = {}, {}
    prediction_lock = read(BLIND / "locks/prediction-lock.json")["sha256"]
    sources.add(BLIND / "locks/prediction-lock.json")
    for tree, (group, private) in BLIND_PANELS.items():
        lock_path = BLIND / "locks" / f"{tree}.json"
        truth_path = BLIND / private / "truth.json"
        prediction_path = BLIND / "predictions" / f"{tree}.json"
        public = BLIND / f"public_{tree}"
        manifest = public / "manifest.json"
        lock = read(lock_path)
        assert sha(truth_path) == lock["truth_sha256"]
        assert sha(prediction_path) == prediction_lock[prediction_path.name]
        assert sha(manifest) == lock["files"]["manifest.json"]
        sources.update((lock_path, truth_path, prediction_path, manifest))
        predictions = {r["id"]: r for r in read(prediction_path)["cases"]}
        truth = {r["id"]: r for r in read(truth_path)["cases"]}
        assert set(read(manifest)["queries"]) == set(predictions) == set(truth)
        for query_id, score in truth.items():
            assert query_id not in scores
            query_path = public / "queries" / f"{query_id}.json"
            assert sha(query_path) == lock["files"][f"queries/{query_id}.json"]
            query = read(query_path)
            assert set(query) == {"id", "regions", "observation", "catalog"}
            assert query["id"] == query_id and len(query["regions"]) == 4
            observation = public / "observations" / f"{query['observation']}.json"
            catalog = public / "orbits" / f"{query['catalog']}.tle"
            for path in (observation, catalog):
                assert sha(path) == path.stem == lock["files"][str(path.relative_to(public))]
            offered = {r["id"] for r in query["regions"]}
            if score["condition"] == "missing":
                assert score["true_region"] is None
            else:
                assert score["true_region"] in offered
            recording = records[query["observation"]] if tree == "recorded" else score["pair"]
            scores[query_id] = dict(
                id=query_id,
                group=group,
                recording=recording,
                truth=score["latlon"],
                condition=score["condition"],
            )
            inputs[query_id] = dict(
                id=query_id,
                panel=group,
                regions=query["regions"],
                blind_tree=f"public_{tree}",
                observation=query["observation"],
                catalog=query["catalog"],
                catalog_timestamp_ns=read(observation)["catalog_timestamp_ns"],
            )
            prediction = predictions[query_id]
            for row in rows[query_id]:
                assert row["case"] == recording and row["condition"] == score["condition"]
                assert row["observation_sha256"] == query["observation"]
                check_prediction(row, prediction)
    assert set(scores) == set(inputs) == set(rows)
    return scores, inputs


def check_prediction(row, prediction):
    point = [float(row[k]) for k in ("latitude_deg", "longitude_deg")] if row["error_km"] else None
    if row["method"].startswith("grid_forced_"):
        expected = prediction["best_latlon"]
        status = "estimate" if expected is not None else "no_estimate"
    else:
        expected = prediction["latlon"]
        status = prediction["status"]
    assert point == expected and row["status"] == status


def roof_fixture(roof_rows, prior8, sources):
    science_path = DS26 / "plans/science.json"
    common_path = DS26 / "results/repeat-comparison.json"
    ds29_plan = Path.home() / ".cache/accuracy-repair-20261115/one-track-plan.json"
    ds29_truth = DS29 / "evaluation-references.json"
    raw_manifests = {
        "DS26": BULK / "leo/research/ds26-20261030/dataset/manifest.json",
        "DS29": DS29 / "dataset-manifest.json",
    }
    science = read(science_path)
    cohorts = {"DS26": science["cohorts"]["DS26"], "DS29": read(ds29_plan)["cohorts"]["DS29"]}
    cohorts["DS29"]["references"] = read(ds29_truth)
    common = set(read(common_path)["same_successful_cases"])
    assert len(common) == 127
    sources.update((science_path, common_path, ds29_plan, ds29_truth, *raw_manifests.values()))
    by_case, recordings = {}, {}
    for group, path in raw_manifests.items():
        for member in read(path)["members"]:
            case = member["dataset_label"]
            if case in roof_rows:
                segments = member["raw_recording"]["segments"]
                if segments:
                    recordings[case] = dict(
                        segments=[locator(r["path"], r["sha256"]) for r in segments],
                        window_count=member["window_count"],
                    )
        by_case.update({m["dataset_label"]: m for m in cohorts[group]["members"]})

    scores, inputs = {}, {}
    for case, rows in roof_rows.items():
        group = rows[0]["panel"]
        member = by_case[case]
        reference = cohorts[group]["references"][case]
        truth = [reference["latitude_deg"], reference["longitude_deg"]]
        for row in rows:
            if group == "DS26":
                assert int(row["in_original_127"]) == (case in common)
                assert int(row["in_prior_ds26_eight"]) == (case in prior8)
            if row["native_sha256"]:
                assert row["native_sha256"] == member["input_sha256"]
        scores[case] = dict(id=case, group=group, recording=case, truth=truth, condition="present")

        proto = read(COMPARISON / "prototype" / f"{case}.json")
        assert proto["case"] == case
        assert proto["offers"]["one"] == [{"id": "original", "center": [37.906, -122.545]}]
        item = dict(
            id=case,
            panel=group,
            regions=proto["offers"]["one"],
            recording=recordings.get(case),
            session_id=member["session_id"],
            run_id=member["run_id"],
        )
        inputs[case] = item
        if member["availability"] != "available":
            item["unavailable"] = member["availability"]
            assert proto["status"] == "input_unavailable"
            continue
        for row in rows:
            if row["method"].startswith("grid_"):
                check_prediction(row, proto["predictions"][row["method"].rsplit("_", 1)[-1]])
        native = Path(member["frozen_native_path"])
        cutoff = member["cutoff_utc_ns"]
        stamp, catalog_name, catalog_digest = max(
            (int(name.split("-")[0]), name, digest)
            for name, digest in member["causal_snapshots"].items()
            if int(name.split("-")[0]) < cutoff
        )
        assert proto["provenance"]["native"] == member["input_sha256"]
        assert proto["catalog"] == catalog_digest.removeprefix("sha256:")
        item.update(
            native=locator(native, member["input_sha256"]),
            cutoff_utc_ns=cutoff,
            catalog_timestamp_ns=stamp,
            observation=proto["observation"],
            catalog=locator(
                native.parent / "tle/archive/space-track" / catalog_name, catalog_digest
            ),
        )
        if group == "DS26":
            graph = GRAPHS / f"{case}.json"
            receipt = read(GRAPHS / f"{case}-receipt.json")
            assert receipt["dataset_label"] == case
            assert receipt["output_sha256"] == proto["provenance"]["graph"]
            item["graph"] = locator(graph, receipt["output_sha256"])
            archive = DS26 / "results"
        else:
            item["blind_tree"] = "public_recorded"
            archive = DS29_RUNS
        request = archive / f"{case}-r0/baseline/experimental-request.json"
        if request.is_file():
            request_doc = read(request)
            job = request_doc["job"]
            original_digest = next(
                r["worker_request_sha256"] for r in rows if r["method"] == "baseline"
            )
            assert hashlib.sha256(
                packed(request_doc)[:-1]
            ).hexdigest() == original_digest.removeprefix("sha256:")
            assert (
                job["evaluation_reference"] is None
                and job["native_input"]["sha256"] == member["input_sha256"]
            )
            assert job["identity"]["session_id"] == member["session_id"]
            assert request_doc["causal_snapshots"] == member["causal_snapshots"]
            item["request"] = locator(request, sha(request))
            item["track_config"] = locator(
                job["track_config"]["path"], job["track_config"]["sha256"]
            )
    roof = sorted(prior8 | {case for case in scores if scores[case]["group"] == "DS29"})
    assert len(roof) == 16 and len(scores) == 167
    return (
        scores,
        inputs,
        {
            "roof16": roof,
            "ds26-common127": sorted(common),
            "ds26-all159": sorted(case for case in scores if case.startswith("DS26-")),
        },
    )


def freeze(output):
    paths = output_paths(output)
    sample = COMPARISON / "sample-errors.csv"
    blind_provenance = BLIND / "recorded_private/provenance.json"
    sources = {sample, PANEL, blind_provenance}
    with sample.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    roof_rows, blind_rows = {}, {}
    for row in rows:
        table, key = (blind_rows, row["query_id"]) if row["query_id"] else (roof_rows, row["case"])
        table.setdefault(key, []).append(row)

    scores, inputs, panels = roof_fixture(roof_rows, set(read(PANEL)["cases"]), sources)
    transfer_scores, transfer_inputs = blind_fixture(blind_rows, sources)
    assert len(transfer_scores) == 124 and set(scores).isdisjoint(transfer_scores)
    for target in transfer_scores.values():
        if target["group"] == "DS29":
            assert target["truth"] == scores[target["recording"]]["truth"]
    panels.update(smoke=["DS26-0036", "DS29-0082"], transfer124=sorted(transfer_scores))
    scores.update(transfer_scores)
    inputs.update(transfer_inputs)
    data = {"panels.json": packed(panels)}
    for filename, mapping in (("inputs.jsonl", inputs), ("targets.jsonl", scores)):
        data[filename] = b"".join(packed(mapping[key]) for key in sorted(mapping))
    fields = (
        "method",
        "arm",
        "status",
        "error_km",
        "latitude_deg",
        "longitude_deg",
        "rms_hz",
        "matched_rms_hz",
        "matched_observations",
        "wall_s",
    )
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(("id", *fields))
    for key, records in sorted((roof_rows | blind_rows).items()):
        truth = scores[key]["truth"]
        for row in records:
            if row["error_km"]:
                point = [float(row[k]) for k in ("latitude_deg", "longitude_deg")]
                assert math.isclose(
                    distance_km(truth, point), float(row["error_km"]), rel_tol=1e-10, abs_tol=1e-10
                )
            else:
                assert not (row["latitude_deg"] or row["longitude_deg"])
            writer.writerow((key, *(row[k] for k in fields)))
    data["scores.csv"] = stream.getvalue().encode()
    provenance = dict(
        schema=1,
        files={name: hashlib.sha256(data[name]).hexdigest() for name in DATA_FILES},
        sources={
            str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path): sha(path)
            for path in sorted(sources)
        },
    )
    paths["provenance.json"].parent.mkdir(parents=True, exist_ok=True)
    for filename in DATA_FILES:
        write_atomic(paths[filename], data[filename])
    write_atomic(paths["provenance.json"], packed(provenance))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="directory for review of regenerated fixtures")
    freeze(parser.parse_args().output)
