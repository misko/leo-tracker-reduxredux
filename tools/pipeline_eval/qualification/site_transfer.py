"""Compare prepared-track receivers on a sealed geographic holdout with measured disturbances."""

import argparse
import gzip
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from ..__main__ import encoded, save_json, write
from ..scoring import ARMS, distribution, validate_result
from . import cold_scenes, fresh_scenes
from . import site_transfer_samples as samples
from .challenge_scenes import DEVELOPMENT, _disjoint
from .fresh_scenes import _new, _read, _sha
from .full_v5_check import FROZEN

REPO = cold_scenes.REPO
REPORT = REPO / "reports/2026_11_19_receiver_screening/site-transfer"
METHODS = ("robust_orbit_fit", "robust_support")
TIMEOUT_S = 100
CPUS = {8, 9}
SEEDS = ("capture", "disturbance", "offer")
PAST_MANIFESTS = (
    *DEVELOPMENT,
    *(
        samples.ROOT
        / "reports/2026_11_19_receiver_convergence/fresh-transfer"
        / f"capture-manifest-{cohort}.json"
        for cohort in ("exact", "perturbed")
    ),
)
WORKER = """
import importlib
import json
import sys
from resource import RUSAGE_SELF, getrusage
from time import process_time

start = process_time()
request = json.load(sys.stdin)
solver = importlib.import_module('tools.pipeline_eval.variants.' + request.pop('method'))
result = solver.infer(request['observation'], request['offer'], request['catalogue'])
json.dump(dict(
    result=result,
    worker_cpu_s=process_time() - start,
    max_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss,
), sys.stdout, allow_nan=False)
"""


def _sources():
    paths = (
        REPORT / "PROTOCOL.md",
        Path(__file__).resolve(),
        Path(samples.__file__),
        Path(fresh_scenes.__file__),
        Path(cold_scenes.__file__),
        Path(_disjoint.__code__.co_filename),
        samples.TRACE,
        samples.AUDIT,
        *samples.OLD_LABELS,
        *PAST_MANIFESTS,
        FROZEN / "provenance.json",
        FROZEN / "inputs.jsonl",
        REPO / "tools/pipeline_eval/reference/grid.py",
        REPO / "tools/pipeline_eval/scoring.py",
        REPO / "tools/pipeline_eval/qualification/cold_input.py",
        REPO / "tools/pipeline_eval/qualification/full_v5_check.py",
        REPO / "tools/pipeline_eval/variants/robust_em.py",
        REPO / "tools/pipeline_eval/variants/projected_fit.py",
        REPO / "src/leo/sky/frames.py",
        REPO / "src/leo/sky/propagation.py",
        *(REPO / "tools/pipeline_eval/variants" / f"{method}.py" for method in METHODS),
    )
    return {str(path.relative_to(REPO)): _sha(path) for path in paths}


def _clock():
    return datetime.now(UTC).isoformat()


def prepare(root, releases):
    source = _sources()
    if set(releases) != set(METHODS) or any(
        source[f"tools/pipeline_eval/variants/{method}.py"] != digest
        for method, digest in releases.items()
    ):
        raise ValueError("both explicit method releases must match their measured source")
    root.mkdir(mode=0o700)
    _new(root / "source-lock.json", dict(sources=source, releases=releases, locked_utc=_clock()))
    samples.generate(root)
    _disjoint([*map(_read, PAST_MANIFESTS), _read(root / "public/manifest.json")])
    _new(
        root / "input-lock.json",
        dict(
            locked_utc=_clock(),
            files={
                name: _sha(root / name)
                for name in (
                    "source-lock.json",
                    "donor-receipt.json",
                    "public/manifest.json",
                    "public/offers.json",
                    "public/orbit.tle",
                    "private/labels.json",
                    "private/realized-disturbances.json",
                    *(f"private/seed-{purpose}.bin" for purpose in SEEDS),
                )
            },
        ),
    )


def _public(root):
    lock = _read(root / "input-lock.json")
    if any(
        _sha(root / name) != digest
        for name, digest in lock["files"].items()
        if not name.startswith("private/")
    ):
        raise ValueError("public file or provenance changed after predeclared draw")
    if _read(root / "source-lock.json")["sources"] != _sources():
        raise ValueError("implementation or prior evidence changed after source lock")
    offers = _read(root / "public/offers.json")
    ids = [r["id"] for r in offers]
    if len(ids) != 13 or len(set(ids)) != 13:
        raise ValueError("expected twelve supplied-tile trials and one null")
    return offers


def _packets(root, offers):
    packets = {}
    public = root / "public"
    for capture_id in {r["capture_id"] for r in offers}:
        capture = cold_scenes._capture(public, capture_id)
        observation = samples.projection(capture)
        packets[capture_id] = (
            dict(
                observation=observation,
                catalogue=capture.catalog.decode("ascii"),
            ),
            dict(
                native_sha256=capture.native_sha256,
                catalog_sha256=capture.catalog_sha256,
                observation_sha256=cold_scenes._sha(encoded(observation)),
            ),
        )
    return packets


def _attempt(method, offer, packet, bindings, cpu):
    standard = packet | {"offer": offer["tile"]}
    sandbox = fresh_scenes._sandbox(cpu)
    sandbox[-1] = WORKER
    started = perf_counter()
    try:
        response = subprocess.run(
            sandbox,
            input=encoded(standard | {"method": method}),
            capture_output=True,
            check=True,
            timeout=TIMEOUT_S,
        )
        outcome = json.loads(response.stdout)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError, ValueError) as err:
        timed_out = isinstance(err, subprocess.TimeoutExpired)
        message = (getattr(err, "stderr", None) or b"").decode(errors="replace")[-1600:]
        outcome = dict(
            worker_cpu_s=None,
            max_rss_kib=None,
            result=dict(
                status="timed_out" if timed_out else "failed",
                reason=message or ("fixed worker deadline" if timed_out else str(err)),
                boundary="Anonymous GLRT tracks and causal TLE to a supplied-tile decision",
                metrics={},
                arms={arm: {"latlon": None, "forced_latlon": None} for arm in ARMS},
            ),
        )
    elapsed = perf_counter() - started
    validate_result(outcome["result"])
    print(method, offer["id"], f"{elapsed:.2f}s", flush=True)
    return dict(
        **offer,
        **bindings,
        **outcome,
        method=method,
        cohort="measured-residual-replay",
        mode="supplied-tile",
        worker_input_sha256=cold_scenes._sha(encoded(standard)),
        wall_s=elapsed,
    )


def predict(root):
    cpu_set = sorted(os.sched_getaffinity(0))
    if not cpu_set or not set(cpu_set) <= CPUS:
        raise ValueError("pin the acceptance workers to CPUs 8 and 9")
    offers = _public(root)
    packets = _packets(root, offers)
    jobs = [(method, offer) for method in METHODS for offer in offers]

    def lane(cpu, work):
        return [
            _attempt(method, offer, *packets[offer["capture_id"]], cpu) for method, offer in work
        ]

    with ThreadPoolExecutor(len(cpu_set)) as pool:
        pending = [pool.submit(lane, cpu, jobs[i :: len(cpu_set)]) for i, cpu in enumerate(cpu_set)]
        rows = [r for job in pending for r in job.result()]
    _public(root)
    raw = gzip.compress(b"".join(encoded(r) + b"\n" for r in rows), mtime=0)
    cold_scenes._new(root / "predictions.jsonl.gz", raw)
    _new(
        root / "prediction-lock.json",
        dict(
            input_lock_sha256=_sha(root / "input-lock.json"),
            predictions_sha256=_sha(root / "predictions.jsonl.gz"),
            locked_utc=_clock(),
            cases=[r["id"] for r in offers],
            methods=METHODS,
            cpus=cpu_set,
            timeout_s=TIMEOUT_S,
            mode="supplied-tile",
        ),
    )


def _check_pair(rows, offers, packets):
    records = {(r["method"], r["id"]): r for r in rows}
    expected = {(method, query["id"]) for method in METHODS for query in offers}
    if len(rows) != len(expected) or set(records) != expected:
        raise ValueError("paired evidence omits or duplicates supplied queries")
    for method, identifier in expected:
        row = records[method, identifier]
        query = next(q for q in offers if q["id"] == identifier)
        packet, bindings = packets[query["capture_id"]]
        if any(row[key] != value for key, value in (query | bindings).items()) or row[
            "worker_input_sha256"
        ] != cold_scenes._sha(encoded(packet | {"offer": query["tile"]})):
            raise ValueError("both arms and methods must use the same prospective packet")


def score(root, output):
    offers = _public(root)
    prediction = root / "predictions.jsonl.gz"
    lock = _read(root / "prediction-lock.json")
    if (
        lock["input_lock_sha256"] != _sha(root / "input-lock.json")
        or lock["predictions_sha256"] != _sha(prediction)
        or lock["cases"] != [r["id"] for r in offers]
        or lock["methods"] != list(METHODS)
    ):
        raise ValueError("predictions differ from their public seal")
    with gzip.open(prediction, "rt") as stream:
        rows = list(map(json.loads, stream))
    _check_pair(rows, offers, _packets(root, offers))
    input_lock = _read(root / "input-lock.json")
    if any(
        _sha(root / name) != digest
        for name, digest in input_lock["files"].items()
        if name.startswith("private/")
    ):
        raise ValueError("private draws differ from the pre-score commitment")
    labels = _read(root / "private/labels.json")
    if set(labels) != set(lock["cases"]):
        raise ValueError("label IDs do not match the sealed predictions")
    scores = list(fresh_scenes._score_rows(rows, labels))
    for row in scores:
        row["cohort"] = "measured-residual-replay"
    # Use the standard reporting groups for each of the two distinct omitted strata.
    groups = []
    for omitted in samples.CONDITIONS[1:3]:
        matching = [
            dict(r, condition="missing") if r["condition"] == omitted else r
            for r in scores
            if r["condition"] in {"present", omitted, "shuffle"}
        ]
        for group in fresh_scenes._groups(matching, METHODS):
            condition = group["condition"]
            if condition == "missing":
                group["condition"] = omitted
            elif omitted != "missing-near":
                continue
            batch = [
                r
                for r in scores
                if (r["method"], r["arm"], r["condition"])
                == (group["method"], group["arm"], group["condition"])
            ]
            group["conditional_rf_rms_hz"] = distribution(
                r["rf_rms_hz"] if r["rf_rms_hz"] is not None else r["conditional_rms_hz"]
                for r in batch
            )
            groups.append(group)
    for name in (
        "source-lock.json",
        "input-lock.json",
        "prediction-lock.json",
        "predictions.jsonl.gz",
        "donor-receipt.json",
        "public/manifest.json",
        "public/offers.json",
        "private/labels.json",
        "private/realized-disturbances.json",
    ):
        target = "capture-manifest.json" if name == "public/manifest.json" else Path(name).name
        write(output / target, (root / name).read_bytes())
    for purpose in SEEDS:
        raw = (root / "private" / f"seed-{purpose}.bin").read_bytes()
        write(output / f"seed-{purpose}.hex", raw.hex().encode() + b"\n")
    save_json(output / "scores.json", dict(cases=scores, groups=groups))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    for action in ("prepare", "predict", "score"):
        command = actions.add_parser(action)
        command.add_argument("root", type=Path)
        if action == "prepare":
            command.add_argument("--release", action="append", required=True)
        elif action == "score":
            command.add_argument("--out", default=REPORT, type=Path)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.root, dict(value.split("=", 1) for value in args.release))
    elif args.action == "predict":
        predict(args.root)
    else:
        score(args.root, args.out)


if __name__ == "__main__":
    main()
