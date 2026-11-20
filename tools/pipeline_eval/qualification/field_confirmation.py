"""Seal, predict and score one fresh panel from the unchanged synthetic generator."""

import argparse
import gzip
import hashlib
import json
import os
import shutil
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from importlib.metadata import version
from pathlib import Path
from time import perf_counter

from .. import scoring
from ..__main__ import encoded, save_json, write
from ..corpus import DEFAULT_BLIND, REPO
from ..reference import grid, receiver
from ..variants import arc_validation

GENERATOR_FILES = ("publish.py", "protocol.json", "test_publish.py")
ARC_RELEASE = "22f70e82aa63bd74c240824f3df3d3468d0cef90432c26cb5c7ef85499a7c79f"
METHODS = ("arc_validation", "regional_grid")


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path):
    return json.loads(path.read_bytes())


def _write_new(path, raw):
    with path.open("xb") as stream:
        stream.write(raw)


def _sources():
    originals = {
        f"generator/{name}": DEFAULT_BLIND / "holdout_private" / name for name in GENERATOR_FILES
    }
    originals["generator/transfer_exclusions.json"] = (
        DEFAULT_BLIND.parent / "2026_11_18_location_transfer/protocol.json"
    )
    for module in (arc_validation, receiver, grid, scoring):
        path = Path(module.__file__).resolve()
        originals[str(path.relative_to(REPO))] = path
    for path in (REPO / "src/leo/sky").glob("*.py"):
        originals[str(path.relative_to(REPO))] = path
    originals["runner"] = Path(__file__).resolve()
    return originals


def prepare(root, predeclaration):
    root.mkdir(mode=0o700)
    private = root / "holdout_private"
    private.mkdir(mode=0o700)
    for name in GENERATOR_FILES:
        shutil.copyfile(DEFAULT_BLIND / "holdout_private" / name, private / name)
    exclusions = root.parent / "2026_11_18_location_transfer"
    exclusions.mkdir()
    shutil.copyfile(_sources()["generator/transfer_exclusions.json"], exclusions / "protocol.json")
    files = {name: _sha(path) for name, path in _sources().items()}
    if files["tools/pipeline_eval/variants/arc_validation.py"] != ARC_RELEASE:
        raise ValueError("arc validation release differs from the predeclared release")
    _write_new(
        root / "sources.json",
        encoded(
            dict(
                files=files,
                predeclaration_sha256=_sha(predeclaration),
                python=sys.version,
                libraries={name: version(name) for name in ("numpy", "sgp4", "matplotlib")},
            )
        )
        + b"\n",
    )


def _verify_sources(root):
    fixed = _read(root / "sources.json")["files"]
    current = {name: _sha(path) for name, path in _sources().items()}
    if current != fixed or current["tools/pipeline_eval/variants/arc_validation.py"] != ARC_RELEASE:
        raise ValueError("runner, receiver or generator has changed since source lock")
    for name in GENERATOR_FILES:
        if _sha(root / "holdout_private" / name) != fixed[f"generator/{name}"]:
            raise ValueError(f"copied generator file changed: {name}")
    if (
        _sha(root.parent / "2026_11_18_location_transfer/protocol.json")
        != fixed["generator/transfer_exclusions.json"]
    ):
        raise ValueError("copied generator exclusions have changed")


def _public_commitment(public):
    return {str(p.relative_to(public)): _sha(p) for p in sorted(public.rglob("*")) if p.is_file()}


def _regional(observation_path, catalogue_path, regions):
    result = receiver.solve(_read(observation_path), regions, catalogue_path.read_bytes())
    return dict(
        latlon=result["latlon"],
        forced_latlon=result["best_latlon"],
        selected_region=result["best_region"],
        region_accepted=result["diagnostics"]["region_result"]["status"] == "accepted",
        reason=result["reason"],
    )


def _arc(observation_path, catalogue_path, regions):
    result = arc_validation.run(
        dict(observation_path=observation_path, catalog_path=catalogue_path, regions=regions), None
    )
    if result["status"] == "unavailable" or result["arms"]["c0"] != result["arms"]["fitted_c"]:
        raise ValueError("missing synthetic result or unequal calibration arms")
    return dict(
        **result["arms"]["c0"],
        selected_region=result["metrics"].get("selected_region_id"),
        region_accepted=result["metrics"].get("region_accepted", False),
        reason=result["reason"],
    )


def _worker(job):
    cpu, public, ids = job
    os.sched_setaffinity(0, {cpu})
    rows = []
    for case_id in ids:
        query_path = public / "queries" / f"{case_id}.json"
        query = _read(query_path)
        if query["id"] != case_id or set(query) != {"id", "regions", "observation", "catalog"}:
            raise ValueError("unexpected blind query fields")
        observation_path = public / "observations" / f"{query['observation']}.json"
        catalogue_path = public / "orbits" / f"{query['catalog']}.tle"
        if (
            _sha(observation_path) != observation_path.stem
            or _sha(catalogue_path) != catalogue_path.stem
        ):
            raise ValueError("query input hash mismatch")
        started = perf_counter()
        arc = _arc(observation_path, catalogue_path, query["regions"])
        arc_time = perf_counter() - started
        started = perf_counter()
        base = _regional(observation_path, catalogue_path, query["regions"])
        rows.append(
            dict(
                id=case_id,
                observation_sha256=query["observation"],
                catalog_sha256=query["catalog"],
                query_sha256=_sha(query_path),
                arc_validation=dict(arc, runtime_s=arc_time),
                regional_grid=dict(base, runtime_s=perf_counter() - started),
            )
        )
    return rows


def predict(root, cpus):
    _verify_sources(root)
    public = root / "public_synthetic"
    receipt = _read(root / "holdout-receipt.json")
    tree = _public_commitment(public)
    expected = receipt["sha256"]
    digest = hashlib.sha256(encoded(tree) + b"\n").hexdigest()
    if digest != expected["public_tree"] or tree["manifest.json"] != expected["public_manifest"]:
        raise ValueError("generator public commitment mismatch")
    ids = _read(public / "manifest.json")["queries"]
    if len(set(ids)) != len(ids) or len(ids) != 80:
        raise ValueError("expected 80 distinct blind queries")
    jobs = [(cpu, public, ids[i :: len(cpus)]) for i, cpu in enumerate(cpus)]
    with ProcessPoolExecutor(len(cpus)) as workers:
        rows = {r["id"]: r for batch in workers.map(_worker, jobs) for r in batch}
    _verify_sources(root)
    _write_new(
        root / "predictions.jsonl.gz",
        gzip.compress(b"".join(encoded(rows[i]) + b"\n" for i in ids), mtime=0),
    )
    _write_new(
        root / "prediction-lock.json",
        encoded(
            dict(
                predictions_sha256=_sha(root / "predictions.jsonl.gz"),
                sources_sha256=_sha(root / "sources.json"),
                generator_receipt_sha256=_sha(root / "holdout-receipt.json"),
                public_tree_sha256=digest,
                queries=len(rows),
                methods=list(METHODS),
                calibration_invariant=True,
            )
        )
        + b"\n",
    )


def _score_row(row, label, simulated):
    truth = label["latlon"]
    point = row["latlon"]
    true_region = label["true_region"]
    missing = label["condition"] == "missing"
    return dict(
        query_id=label["id"],
        acquisition_id=label["pair"],
        site_group=label["site_group"],
        scene=label["difficulty"],
        condition=label["condition"],
        correct_region=true_region,
        selected_region=row["selected_region"],
        correct_nomination=row["selected_region"] == true_region if not missing else None,
        region_accepted=row["region_accepted"],
        false_region_acceptance=missing and row["region_accepted"],
        published=point is not None,
        false_publication=missing and point is not None,
        error_km=scoring.distance_km(point, truth),
        forced_error_km=scoring.distance_km(row["forced_latlon"], truth),
        reason=row["reason"],
        track_count=len(simulated["tracks"]),
        corrupt_tracks=sum(t["corrupt"] for t in simulated["tracks"]),
    )


def _summaries(scored):
    summaries = []
    for method, cases in scored.items():
        groups = defaultdict(list)
        for row in cases:
            groups[row["scene"], row["condition"]].append(row)
            groups["all", row["condition"]].append(row)
        for (scene, condition), rows in sorted(groups.items()):
            errors = [r["error_km"] for r in rows]
            summaries.append(
                dict(
                    method=method,
                    scene=scene,
                    condition=condition,
                    trials=len(rows),
                    fixes=sum(r["published"] for r in rows),
                    correct_nominations=sum(r["correct_nomination"] is True for r in rows)
                    if condition == "present"
                    else None,
                    accepted_regions=sum(r["region_accepted"] for r in rows),
                    false_region_acceptances=sum(r["false_region_acceptance"] for r in rows),
                    false_publications=sum(r["false_publication"] for r in rows),
                    within_km=scoring.thresholds(errors),
                    error_km=scoring.distribution(errors),
                    forced_error_km=scoring.distribution(r["forced_error_km"] for r in rows),
                )
            )
    return summaries


def score(root, output):
    _verify_sources(root)
    locked = _read(root / "prediction-lock.json")
    if (
        _sha(root / "predictions.jsonl.gz") != locked["predictions_sha256"]
        or _sha(root / "sources.json") != locked["sources_sha256"]
        or _sha(root / "holdout-receipt.json") != locked["generator_receipt_sha256"]
    ):
        raise ValueError("predictions, sources or generator receipt differ from the seal")
    private = root / "holdout_private"
    sealed = _read(root / "holdout-receipt.json")["sha256"]
    for name in ("seed.bin", "truth.json", "provenance.json"):
        if _sha(private / name) != sealed[name]:
            raise ValueError(f"generator private commitment mismatch: {name}")
    truth = {r["id"]: r for r in _read(private / "truth.json")["cases"]}
    provenance = _read(private / "provenance.json")
    scored = {m: [] for m in METHODS}
    with gzip.open(root / "predictions.jsonl.gz", "rt") as stream:
        predictions = [json.loads(line) for line in stream]
    if {r["id"] for r in predictions} != truth.keys() or len(predictions) != 80:
        raise ValueError("sealed prediction and truth rosters do not match")
    for record in predictions:
        label = truth[record["id"]]
        for method in METHODS:
            scored[method].append(_score_row(record[method], label, provenance[label["pair"]]))
    for name in (
        "predictions.jsonl.gz",
        "holdout-receipt.json",
        "sources.json",
        "prediction-lock.json",
    ):
        write(output / name, (root / name).read_bytes())
    write(output / "seed.hex", private.joinpath("seed.bin").read_bytes().hex().encode() + b"\n")
    save_json(output / "scores.json", dict(cases=scored, groups=_summaries(scored)))


def figure(scores, output):
    import matplotlib.pyplot as plt

    cases = _read(scores)["cases"]
    order = sorted({(r["scene"], r["acquisition_id"]) for r in cases[METHODS[0]]})
    indices = {pair: i for i, (_, pair) in enumerate(order)}
    positions = defaultdict(list)
    for index, (scene, _) in enumerate(order):
        positions[scene].append(index)
    fig, panels = plt.subplots(2, 2, figsize=(12, 7), sharex=True, sharey=True)
    shortest = min(
        (r["error_km"] for rows in cases.values() for r in rows if r["error_km"] is not None),
        default=0.3,
    )
    withheld = min(0.1, max(shortest, 0.001) / 3)
    for col, (method, title) in enumerate(
        zip(METHODS, ("Held arc endpoints", "Frozen grid"), strict=True)
    ):
        panels[0, col].set_title(title, loc="left", fontweight="bold")
        for row, condition in enumerate(("present", "missing")):
            ax = panels[row, col]
            selected = [r for r in cases[method] if r["condition"] == condition]
            publishes = [r for r in selected if r["published"]]
            withholds = [r for r in selected if not r["published"]]
            color = "#115f70" if condition == "present" else "#a63a29"
            ax.scatter(
                [indices[r["acquisition_id"]] for r in publishes],
                [max(r["error_km"], 2 * withheld) for r in publishes],
                color=color,
                s=23,
                zorder=4,
            )
            ax.scatter(
                [indices[r["acquisition_id"]] for r in withholds],
                [withheld] * len(withholds),
                color="#596774",
                marker="x",
                linewidth=1.0,
                s=22,
                zorder=4,
            )
            for scene_indices in list(positions.values())[:-1]:
                ax.axvline(scene_indices[-1] + 0.5, color="#e0e5e7", linewidth=0.8)
            ax.axhline(5, linestyle="--", color="#5a6670", linewidth=0.8)
            ax.text(
                0.985,
                0.95,
                f"{len(publishes)}/{len(selected)} fixes",
                transform=ax.transAxes,
                ha="right",
                va="top",
                fontsize=9,
            )
            ax.set(yscale="log", ylim=(withheld / 1.35, 25000), xlim=(-0.7, len(order) - 0.3))
            ax.set_yticks(
                [withheld, 0.5, 5, 50, 500, 5000], ["Withheld", "0.5", "5", "50", "500", "5,000"]
            )
            ax.spines[["right", "top"]].set_visible(False)
    panels[0, 0].set_ylabel("Present offer\nError (km)")
    panels[1, 0].set_ylabel("Missing offer\nError (km)")
    for ax in panels[1]:
        ax.set_xticks(
            [sum(ix) / len(ix) for ix in positions.values()],
            [s.replace("_", "\n") for s in positions],
            fontsize=8,
        )
    fig.suptitle(
        "New synthetic confirmation across 40 paired acquisitions",
        x=0.105,
        ha="left",
        fontweight="bold",
        fontsize=15,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(output.with_suffix(".png"), dpi=180)
    fig.savefig(output.with_suffix(".pdf"))
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    for operation in ("prepare", "predict", "score", "figure"):
        cmd = sub.add_parser(operation)
        cmd.add_argument("path", type=Path)
        if operation != "predict":
            cmd.add_argument("other", type=Path)
    args = parser.parse_args()
    if args.operation == "predict":
        predict(args.path, sorted(os.sched_getaffinity(0)))
    else:
        {"prepare": prepare, "score": score, "figure": figure}[args.operation](
            args.path, args.other
        )


if __name__ == "__main__":
    main()
