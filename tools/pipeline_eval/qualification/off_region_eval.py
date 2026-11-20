"""Predict and seal the transfer and fresh panels before opening their answers."""

import argparse
import gzip
import hashlib
import json
import os
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from time import perf_counter

from .. import corpus, scoring
from ..__main__ import encoded, save_json, write
from ..variants import off_region_test
from . import field_confirmation as fresh
from . import field_shapes as transfer

METHODS = ("arc_validation", "off_region_test")
PROTOCOL = corpus.REPO / "reports/2026_11_19_receiver_frontend/regions/PROTOCOL.md"


def _sources():
    return {
        str(path.relative_to(corpus.REPO)): fresh._sha(path)
        for path in (
            PROTOCOL,
            Path(__file__).resolve(),
            Path(off_region_test.__file__).resolve(),
            Path(transfer.__file__).resolve(),
            Path(corpus.__file__).resolve(),
            corpus.FROZEN / "provenance.json",
        )
    }


def prepare(root):
    fresh.prepare(root, PROTOCOL)
    fresh._write_new(root / "algorithm-lock.json", encoded(_sources()) + b"\n")


def _verify_sources(root):
    fresh._verify_sources(root)
    if fresh._read(root / "algorithm-lock.json") != _sources():
        raise ValueError("longitude control, protocol or runner changed after lock")


def _fresh_cases(root):
    public = root / "public_synthetic"
    tree = fresh._public_commitment(public)
    digest = hashlib.sha256(encoded(tree) + b"\n").hexdigest()
    expected = fresh._read(root / "holdout-receipt.json")["sha256"]
    if digest != expected["public_tree"] or tree["manifest.json"] != expected["public_manifest"]:
        raise ValueError("generator public commitment mismatch")
    ids = fresh._read(public / "manifest.json")["queries"]
    if len(set(ids)) != 80 or len(ids) != 80:
        raise ValueError("expected 80 distinct fresh queries")
    for case_id in ids:
        path = public / "queries" / f"{case_id}.json"
        query = fresh._read(path)
        if query["id"] != case_id or set(query) != {"id", "regions", "observation", "catalog"}:
            raise ValueError("unexpected blind query fields")
        observation = public / "observations" / f"{query['observation']}.json"
        catalog = public / "orbits" / f"{query['catalog']}.tle"
        if fresh._sha(observation) != observation.stem or fresh._sha(catalog) != catalog.stem:
            raise ValueError("fresh query input hash mismatch")
        yield dict(
            id=case_id,
            regions=query["regions"],
            observation_path=observation,
            catalog_path=catalog,
            query_sha256=fresh._sha(path),
        )


def _worker(job):
    cpu, cases = job
    os.sched_setaffinity(0, {cpu})
    rows = []
    for panel, case in cases:
        if not case["observation_path"] or not case["catalog_path"]:
            raise ValueError(f"missing track or orbit input for {case['id']}")
        observation = Path(case["observation_path"])
        catalog = Path(case["catalog_path"])
        baseline, candidate = off_region_test.compare(
            fresh._read(observation), case["regions"], catalog.read_bytes()
        )
        for result in (baseline, candidate):
            scoring.validate_result(result)
            if result["arms"]["c0"] != result["arms"]["fitted_c"]:
                raise ValueError("calibration arms differ")
        rows.append(
            dict(
                panel=panel,
                id=case["id"],
                observation_sha256=fresh._sha(observation),
                catalog_sha256=fresh._sha(catalog),
                query_sha256=case.get("query_sha256"),
                results=dict(zip(METHODS, (baseline, candidate), strict=True)),
            )
        )
        if len(rows) % 10 == 0:
            print(f"CPU {cpu} predicted {len(rows)}/{len(cases)}", flush=True)
    return rows


def _lock(root):
    files = ("predictions.jsonl.gz", "algorithm-lock.json", "sources.json", "holdout-receipt.json")
    return {name: fresh._sha(root / name) for name in files}


def predict(root):
    _verify_sources(root)
    cpus = sorted(os.sched_getaffinity(0))
    if not cpus or not set(cpus) <= {17, 18, 19}:
        raise ValueError("restrict process affinity to cores 17–19")
    started = perf_counter()
    cases = [
        *(("fresh80", case) for case in _fresh_cases(root)),
        *(("transfer124", case) for case in transfer.public_cases(root / "cache")),
    ]
    jobs = [(cpu, cases[i :: len(cpus)]) for i, cpu in enumerate(cpus)]
    with ProcessPoolExecutor(len(jobs)) as workers:
        rows = {(r["panel"], r["id"]): r for batch in workers.map(_worker, jobs) for r in batch}
    _verify_sources(root)
    if len(rows) != len(cases) or len(rows) != 204:
        raise ValueError("expected 204 distinct frozen and fresh queries")
    payload = b"".join(encoded(rows[panel, case["id"]]) + b"\n" for panel, case in cases)
    fresh._write_new(root / "predictions.jsonl.gz", gzip.compress(payload, mtime=0))
    receipt = dict(files=_lock(root), cpus=cpus, wall_s=perf_counter() - started)
    fresh._write_new(root / "prediction-lock.json", encoded(receipt) + b"\n")


def _answers(root):
    private = root / "holdout_private"
    sealed = fresh._read(root / "holdout-receipt.json")["sha256"]
    for name in ("seed.bin", "truth.json", "provenance.json"):
        if fresh._sha(private / name) != sealed[name]:
            raise ValueError(f"fresh scorer commitment mismatch: {name}")
    labels = defaultdict(dict)
    for row in fresh._read(private / "truth.json")["cases"]:
        labels["fresh80"][row["id"]] = dict(row, group=row["difficulty"])
    truth, _ = transfer._locked_records()
    for row in corpus.references("transfer124"):
        label = truth[row["id"]]
        if label["latlon"] != row["truth"] or label["condition"] != row["condition"]:
            raise ValueError("transfer reference and seal disagree")
        labels["transfer124"][row["id"]] = dict(label, group=row["group"])
    return labels


def _score_result(panel, case_id, method, arm, result, label):
    prediction = result["arms"][arm]
    metrics = result["metrics"]
    taken = metrics.get("selected_region_id")
    correct = taken == label["true_region"] if label["condition"] == "present" else False
    return dict(
        panel=panel,
        id=case_id,
        group=label["group"],
        condition=label["condition"],
        method=method,
        arm=arm,
        reason=result["reason"],
        correct_region=label["true_region"],
        selected_region=taken,
        correct_nomination=correct,
        region_accepted=metrics.get("region_accepted", False),
        published=prediction["latlon"] is not None,
        error_km=scoring.distance_km(prediction["latlon"], label["latlon"]),
        forced_error_km=scoring.distance_km(prediction["forced_latlon"], label["latlon"]),
        held_rms_hz=metrics.get("held_rms_hz"),
        published_held_rms_hz=prediction.get("rf_rms_hz"),
        runtime_s=metrics["candidate_s"],
        longitude_control=metrics.get("longitude_control"),
    )


def _summary(rows):
    groups = defaultdict(list)
    for row in rows:
        for group in (row["group"], "all"):
            key = row["panel"], group, row["condition"], row["method"], row["arm"]
            groups[key].append(row)
    summaries = []
    for (panel, group, condition, method, arm), selected in sorted(groups.items()):
        errors = [r["error_km"] for r in selected]
        summaries.append(
            dict(
                panel=panel,
                group=group,
                condition=condition,
                method=method,
                arm=arm,
                attempts=len(selected),
                publications=sum(r["published"] for r in selected),
                correct_nominations=sum(r["correct_nomination"] for r in selected),
                region_acceptances=sum(r["region_accepted"] for r in selected),
                false_region_acceptances=sum(
                    r["region_accepted"] and not r["correct_nomination"] for r in selected
                ),
                false_publications=sum(
                    r["published"] and not r["correct_nomination"] for r in selected
                ),
                within_km=scoring.thresholds(errors),
                published_error_km=scoring.distribution(errors),
                forced_error_km=scoring.distribution(r["forced_error_km"] for r in selected),
                selected_held_rms_hz=scoring.distribution(r["held_rms_hz"] for r in selected),
                published_held_rms_hz=scoring.distribution(
                    r["published_held_rms_hz"] for r in selected
                ),
                runtime_s=scoring.distribution(r["runtime_s"] for r in selected),
                control_tiles=scoring.distribution(
                    r["longitude_control"]["null_tiles_tested"]
                    for r in selected
                    if r["longitude_control"]
                ),
                reasons=dict(Counter(r["reason"] for r in selected)),
            )
        )
    return summaries


def score(root, output):
    _verify_sources(root)
    receipt = fresh._read(root / "prediction-lock.json")
    if _lock(root) != receipt["files"]:
        raise ValueError("predictions, sources or generator differ from the prediction seal")
    labels = _answers(root)
    with gzip.open(root / "predictions.jsonl.gz", "rt") as stream:
        predictions = list(map(json.loads, stream))
    expected = {(panel, case_id) for panel, cases in labels.items() for case_id in cases}
    if {(r["panel"], r["id"]) for r in predictions} != expected or len(predictions) != 204:
        raise ValueError("predictions and scorer rosters do not match")
    rows = [
        _score_result(row["panel"], row["id"], method, arm, result, labels[row["panel"]][row["id"]])
        for row in predictions
        for method, result in row["results"].items()
        for arm in scoring.ARMS
    ]
    for name in (*receipt["files"], "prediction-lock.json"):
        write(output / name, (root / name).read_bytes())
    write(
        output / "fresh-seed.hex",
        (root / "holdout_private/seed.bin").read_bytes().hex().encode() + b"\n",
    )
    save_json(output / "scores.json", dict(groups=_summary(rows), cases=rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "predict", "score"):
        sub = commands.add_parser(command)
        sub.add_argument("root", type=Path)
        if command == "score":
            sub.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.command == "score":
        score(args.root, args.output)
    else:
        {"prepare": prepare, "predict": predict}[args.command](args.root)


if __name__ == "__main__":
    main()
