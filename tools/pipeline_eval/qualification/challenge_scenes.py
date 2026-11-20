"""Score the sealed two-cohort regional publication challenge."""

import argparse
import gzip
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

from ..__main__ import encoded, save_json, write
from ..scoring import distribution, validate_result
from . import challenge_scenes_generator as generator
from . import cold_scenes, fresh_scenes

REPO = cold_scenes.REPO
REPORT = REPO / "reports/2026_11_19_receiver_convergence/fresh-transfer"
PROTOCOL = REPORT / "PROTOCOL.md"
METHODS = ("joint_pass_id", "region_challenge")
CPUS = {8, 9}
TIMEOUT = 100
DEVELOPMENT = (
    REPO / "reports/2026_11_19_glrt_cold_start/scenes/manifest.json",
    REPO / "reports/2026_11_19_short_receiver/fresh-scenes/capture-manifest.json",
)
_read = fresh_scenes._read
_sha = fresh_scenes._sha
_new = fresh_scenes._new


def _sources():
    paths = [
        PROTOCOL,
        Path(__file__).resolve(),
        Path(generator.__file__).resolve(),
        Path(fresh_scenes.__file__).resolve(),
        Path(cold_scenes.__file__).resolve(),
        REPO / "tools/pipeline_eval/qualification/cold_input.py",
        REPO / "tools/pipeline_eval/scoring.py",
        REPO / "tools/pipeline_eval/variants/rate_triplets.py",
        REPO / "src/leo/sky/frames.py",
        REPO / "src/leo/sky/propagation.py",
        *DEVELOPMENT,
    ]
    for method in METHODS:
        path = REPO / f"tools/pipeline_eval/variants/{method}.py"
        paths.append(path)
        if path.with_suffix(".c").exists():
            paths.append(path.with_suffix(".c"))
    return {str(path.relative_to(REPO)): _sha(path) for path in paths}


def _disjoint(manifests):
    seen_ids, seen_data = set(), set()
    for manifest in manifests:
        cases = manifest["cases"]
        if seen_ids.intersection(cases) or seen_data.intersection(cases.values()):
            raise ValueError("fresh cohort reuses an input ID or native SHA")
        seen_ids.update(cases)
        seen_data.update(cases.values())


def prepare(root, releases):
    if set(releases) != set(METHODS):
        raise ValueError("both prospective method releases are required")
    sources = _sources()
    if any(
        sources[f"tools/pipeline_eval/variants/{method}.py"] != digest
        for method, digest in releases.items()
    ):
        raise ValueError("method source differs from its declared acceptance release")
    root.mkdir(mode=0o700)
    _new(root / "source-lock.json", dict(sources=sources, methods=list(METHODS), timeout_s=TIMEOUT))
    for cohort in generator.COHORTS:
        generator.generate(root / cohort, cohort)
    _disjoint(
        [
            *(_read(path) for path in DEVELOPMENT),
            *(_read(root / c / "public/manifest.json") for c in generator.COHORTS),
        ]
    )
    _new(
        root / "input-lock.json",
        dict(
            sources_sha256=_sha(root / "source-lock.json"),
            cohort_locks={c: _sha(root / c / "cohort-lock.json") for c in generator.COHORTS},
        ),
    )


def _check(root):
    inputs = _read(root / "input-lock.json")
    source = root / "source-lock.json"
    sealed = _read(source)
    if (
        inputs["sources_sha256"] != _sha(source)
        or sealed["methods"] != list(METHODS)
        or sealed["sources"] != _sources()
    ):
        raise ValueError("source or protocol changed after generation")
    queries = {}
    for cohort in generator.COHORTS:
        path = root / cohort
        lock = path / "cohort-lock.json"
        if inputs["cohort_locks"][cohort] != _sha(lock):
            raise ValueError("cohort lock has changed")
        hashes = _read(lock)
        for file, key in (
            ("public/manifest.json", "manifest_sha256"),
            ("public/orbit.tle", "catalogue_sha256"),
            ("public/offers.json", "offers_sha256"),
            ("generator/input-lock.json", "generator_input_lock_sha256"),
        ):
            if _sha(path / file) != hashes[key]:
                raise ValueError(f"public cohort input changed: {cohort}/{file}")
        rows = _read(path / "public/offers.json")
        if len(rows) != 9 or len({r["id"] for r in rows}) != 9:
            raise ValueError("each cohort requires nine prospective offers")
        queries[cohort] = rows
    if len({r["id"] for group in queries.values() for r in group}) != 18:
        raise ValueError("cohorts reuse a public query ID")
    return queries


def _attempt(root, method, cohort, query, cpu):
    public = root / cohort / "public"
    capture = cold_scenes._capture(public, query["capture_id"])
    inputs = dict(
        capture=asdict(capture) | {"catalog": capture.catalog.decode("ascii")},
        tile=query["tile"],
    )
    serialized = encoded(inputs)
    started = perf_counter()
    boundary = "Causal TLE and native GLRT candidates to a 25 km supplied-tile decision"
    try:
        done = subprocess.run(
            fresh_scenes._sandbox(cpu),
            input=encoded(inputs | {"method": method}),
            capture_output=True,
            check=True,
            timeout=TIMEOUT,
        )
        result = json.loads(done.stdout)
    except subprocess.TimeoutExpired:
        result = dict(
            status="timed_out", reason="fixed acceptance deadline", boundary=boundary, metrics={}
        )
    except (subprocess.CalledProcessError, OSError, ValueError) as err:
        detail = (getattr(err, "stderr", None) or b"").decode(errors="replace")[-1600:]
        result = dict(status="failed", reason=detail or str(err), boundary=boundary, metrics={})
    validate_result(result)
    return dict(
        id=query["id"],
        capture_id=query["capture_id"],
        cohort=cohort,
        method=method,
        mode="supplied-tile",
        tile=query["tile"],
        native_sha256=capture.native_sha256,
        catalog_sha256=capture.catalog_sha256,
        worker_input_sha256=cold_scenes._sha(serialized),
        wall_s=perf_counter() - started,
        result=result,
    )


def predict(root):
    cpus = sorted(os.sched_getaffinity(0))
    if not cpus or not set(cpus) <= CPUS:
        raise ValueError("restrict acceptance workers to CPUs 8 and 9")
    queries = _check(root)
    jobs = [
        (method, cohort, row)
        for method in METHODS
        for exact, perturbed in zip(*(queries[c] for c in generator.COHORTS), strict=True)
        for cohort, row in zip(generator.COHORTS, (exact, perturbed), strict=True)
    ]

    def run(cpu, grouped):
        predictions = []
        for method, cohort, query in grouped:
            predictions.append(_attempt(root, method, cohort, query, cpu))
            print(method, cohort, query["id"], "sealed worker completed", flush=True)
        return predictions

    with ThreadPoolExecutor(max_workers=len(cpus)) as pool:
        workers = [pool.submit(run, cpu, jobs[i :: len(cpus)]) for i, cpu in enumerate(cpus)]
        rows = [row for response in workers for row in response.result()]
    _check(root)
    raw = gzip.compress(b"".join(encoded(r) + b"\n" for r in rows), mtime=0)
    cold_scenes._new(root / "predictions.jsonl.gz", raw)
    _new(
        root / "prediction-lock.json",
        dict(
            input_lock_sha256=_sha(root / "input-lock.json"),
            predictions_sha256=cold_scenes._sha(raw),
            mode="supplied-tile",
            methods=list(METHODS),
            cpus=cpus,
            timeout_s=TIMEOUT,
            cases={c: [r["id"] for r in group] for c, group in queries.items()},
        ),
    )


def _checked_records(rows, queries, manifests):
    indexed = {(r["cohort"], r["method"], r["id"]): r for r in rows}
    expected = {
        (cohort, method, q["id"])
        for cohort, offers in queries.items()
        for q in offers
        for method in METHODS
    }
    if len(rows) != len(expected) or set(indexed) != expected:
        raise ValueError("predictions do not include every paired cohort and method")
    for cohort, offers in queries.items():
        for query in offers:
            cases = [indexed[cohort, method, query["id"]] for method in METHODS]
            for r in cases:
                if (
                    r["capture_id"] != query["capture_id"]
                    or r["tile"] != query["tile"]
                    or r["native_sha256"] != manifests[cohort]["cases"][r["capture_id"]]
                    or r["catalog_sha256"] != cold_scenes.CATALOG_SHA256
                ):
                    raise ValueError("prediction differs from its sealed public trial")
            if len({r["worker_input_sha256"] for r in cases}) != 1:
                raise ValueError("the two methods received different serialized inputs")


def score(root, output):
    queries = _check(root)
    lock = _read(root / "prediction-lock.json")
    prediction = root / "predictions.jsonl.gz"
    if (
        lock["input_lock_sha256"] != _sha(root / "input-lock.json")
        or lock["predictions_sha256"] != _sha(prediction)
        or lock["cases"] != {c: [r["id"] for r in group] for c, group in queries.items()}
    ):
        raise ValueError("prediction file differs from its sealed roster")
    with gzip.open(prediction, "rt") as stream:
        records = list(map(json.loads, stream))
    manifests = {c: _read(root / c / "public/manifest.json") for c in queries}
    _checked_records(records, queries, manifests)
    groups, cases = [], []
    for cohort in generator.COHORTS:
        path = root / cohort
        private = path / "generator/private"
        lock = _read(path / "cohort-lock.json")
        private_files = {
            "labels": private / "offer-labels.json",
            "perturbations": private / "perturbations.json",
        }
        if any(_sha(p) != lock[f"{k}_sha256"] for k, p in private_files.items()):
            raise ValueError("private scorer inputs changed after prediction")
        truth = _read(private_files["labels"])
        rows = list(
            fresh_scenes._score_rows([row for row in records if row["cohort"] == cohort], truth)
        )
        cases.extend(dict(row, cohort=cohort) for row in rows)
        for summary in fresh_scenes._groups(rows, METHODS):
            batch = [
                r
                for r in rows
                if (r["method"], r["arm"], r["condition"])
                == (summary["method"], summary["arm"], summary["condition"])
            ]
            groups.append(
                dict(
                    summary,
                    cohort=cohort,
                    conditional_rms_hz=distribution(r["conditional_rms_hz"] for r in batch),
                    heldout_frame_rms_us=distribution(r["heldout_frame_rms_us"] for r in batch),
                )
            )
        for name, file in (
            (f"capture-manifest-{cohort}.json", path / "public/manifest.json"),
            (f"offers-{cohort}.json", path / "public/offers.json"),
            (f"cohort-lock-{cohort}.json", path / "cohort-lock.json"),
            (f"generator-lock-{cohort}.json", path / "generator/input-lock.json"),
            (f"labels-{cohort}.json", private_files["labels"]),
            (f"perturbations-{cohort}.json", private_files["perturbations"]),
        ):
            write(output / name, file.read_bytes())
        seeds = {
            "capture": "seed.bin",
            "offer": "offer-seed.bin",
            "perturbation": "perturbation-seed.bin",
        }
        for key, digest in lock["seeds_sha256"].items():
            seed = (private / seeds[key]).read_bytes()
            if cold_scenes._sha(seed) != digest:
                raise ValueError("reproduction seed changed after prediction")
            write(output / f"seed-{cohort}-{key}.hex", seed.hex().encode() + b"\n")
    for name in (
        "source-lock.json",
        "input-lock.json",
        "prediction-lock.json",
        "predictions.jsonl.gz",
    ):
        write(output / name, (root / name).read_bytes())
    save_json(output / "scores.json", dict(cases=cases, groups=groups))


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    actions = cli.add_subparsers(dest="action", required=True)
    for name in ("prepare", "predict", "score"):
        cmd = actions.add_parser(name)
        cmd.add_argument("root", type=Path)
        if name == "prepare":
            cmd.add_argument(
                "--release", required=True, action="append", help="method=source_sha256"
            )
        if name == "score":
            cmd.add_argument("--out", type=Path, default=REPORT)
    args = cli.parse_args()
    if args.action == "prepare":
        prepare(args.root, dict(value.split("=", 1) for value in args.release))
    elif args.action == "predict":
        predict(args.root)
    else:
        score(args.root, args.out)


if __name__ == "__main__":
    main()
