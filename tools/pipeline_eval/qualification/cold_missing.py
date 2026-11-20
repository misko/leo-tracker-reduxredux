"""Test frozen GLRT-only receivers with one tile from each omitted-region query."""

import argparse
import gzip
import json
import os
import site
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from time import perf_counter

from .. import corpus
from ..__main__ import ROOT, THREAD_ENV, encoded, read_predictions, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from .cold_input import load

REPORT = ROOT / "reports/2026_11_19_glrt_cold_start"
CASES = {
    "DS29-0082": "5ef5a3952fe49b857695d9f63d085ed0",
    "DS29-0174": "707b8121bb30276e1198a559bc78a8c4",
    "DS29-0247": "86046e4d1891a089b3df6c82e6879d98",
}
METHODS = {
    "point_votes": (
        "point-votes",
        "f8186edc25eccb52556e22855d3fb870037d64c643f956bd606461de71d02fcf",
    ),
    "rate_triplets": (
        "rate-triplets",
        "42612cc63e15011d8ec731d87d1c2b90508150fbb78dc9e66e7e4c1fd38920a8",
    ),
    "folded_doppler": (
        "folded-doppler",
        "dd6f48e9509fcbfe526a22ad7bc9484588d441b804d57e9e750b8b487ec7cffa",
    ),
}
CPUS = (6, 7, 22, 23)
DEADLINE_S = 90
BOUNDARY = "Full native GLRT and causal TLE to position with one supplied tile"
WORKER = """
import json
import sys
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

import solver

started = perf_counter()
request = json.load(sys.stdin)
source = Path(solver.__file__)
digest = sha256(source.read_bytes())
if source.with_suffix('.c').exists():
    digest.update(source.with_suffix('.c').read_bytes())
if digest.hexdigest() != request['implementation_sha256']:
    raise ValueError('worker source differs from the prospectively frozen digest')
document = request['capture']
capture = SimpleNamespace(**dict(document, catalog=document['catalog'].encode('ascii')))
tile = request['tile']
result = solver.run(capture, tile=tile) if hasattr(solver, 'run') else solver.solve(
    capture, tile=tile['center'],
)
json.dump(dict(result=result, solver_wall_s=perf_counter()-started), sys.stdout, allow_nan=False)
"""


def select_query(native, query_rows, conditions, expected_id):
    """Determine a single offer using the authoritative declared list order."""
    matches = [
        query
        for query in query_rows
        if (
            conditions[query["id"]] == "missing"
            and query["observation"] == native["observation"]
            and query["catalog"] == native["catalog"]["sha256"]
            and query["catalog_timestamp_ns"] == native["catalog_timestamp_ns"]
            and query["panel"] == native["panel"]
        )
    ]
    if len(matches) != 1 or matches[0]["id"] != expected_id:
        raise ValueError("expected exactly the frozen matching omitted-region query")
    query = matches[0]
    if len(query["regions"]) != 4:
        raise ValueError("the frozen query must contain four ordered tiles")
    first = query["regions"][0]
    return query, dict(id=first["id"], center=first["center"], width_km=first.get("width_km", 25.0))


def bindings():
    ids, files = corpus._selection("transfer124")
    inputs = corpus._index(corpus._read_frozen("inputs.jsonl", files))
    targets = corpus._index(corpus._read_frozen("targets.jsonl", files))
    conditions = {key: targets[key]["condition"] for key in ids}
    del targets
    records = []
    for case, expected in CASES.items():
        entry = inputs[case]
        query, tile = select_query(entry, (inputs[key] for key in ids), conditions, expected)
        public = corpus.DEFAULT_BLIND / query["blind_tree"]
        obs, cat = query["observation"], query["catalog"]
        observation = (public / "observations" / f"{obs}.json").read_bytes()
        catalog = (public / "orbits" / f"{cat}.tle").read_bytes()
        if sha256(observation).hexdigest() != obs or sha256(catalog).hexdigest() != cat:
            raise ValueError(
                "portable observation or catalogue bytes differ from the frozen identity"
            )
        query_bytes = (public / "queries" / f"{expected}.json").read_bytes()
        if json.loads(query_bytes) != {
            key: query[key]
            for key in (
                "id",
                "observation",
                "catalog",
                "regions",
            )
        }:
            raise ValueError("public query differs from the frozen ordered offers")
        records.append(
            dict(
                id=case,
                query_id=expected,
                query_sha256=sha256(query_bytes).hexdigest(),
                native_sha256=entry["native"]["sha256"],
                observation_sha256=obs,
                catalog_sha256=cat,
                catalog_timestamp_ns=query["catalog_timestamp_ns"],
                supplied_tile=tile,
                supplied_offer_index=0,
            )
        )
    return records


def _sources(method):
    path = ROOT / "tools/pipeline_eval/variants" / f"{method}.py"
    sources = [path, path.with_suffix(".c")] if method == "folded_doppler" else [path]
    digest = sha256(b"".join(path.read_bytes() for path in sources)).hexdigest()
    if digest != METHODS[method][1]:
        raise ValueError(f"{method} changed after the omitted-region source lock")
    return sources, digest


def _sandbox(cpu, sources):
    (packages,) = site.getsitepackages()
    command = [
        "taskset",
        "-c",
        str(cpu),
        "bwrap",
        "--unshare-all",
        "--die-with-parent",
        "--clearenv",
        "--tmpfs",
        "/tmp",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--chdir",
        "/tmp",
        "--setenv",
        "PYTHONPATH",
        "/worker:/source:/packages",
    ]
    mounts = [
        ("/usr", "/usr"),
        ("/lib", "/lib"),
        ("/lib64", "/lib64"),
        (sys.base_prefix, "/python"),
        (packages, "/packages"),
        (str(ROOT / "src/leo"), "/source/leo"),
        *((str(path), f"/worker/solver{path.suffix}") for path in sources),
    ]
    for key, value in THREAD_ENV.items():
        command.extend(("--setenv", key, value))
    if len(sources) == 2:
        command.extend(("--setenv", "PATH", "/usr/bin"))
        mounts.append(("/etc/alternatives", "/etc/alternatives"))
    for source, target in mounts:
        command.extend(("--ro-bind", source, target))
    interpreter = f"/python/bin/python{sys.version_info.major}.{sys.version_info.minor}"
    return [*command, interpreter, "-B", "-c", WORKER]


def _predict(method, binding, cpu, sources, digest):
    start = perf_counter()
    capture = load(binding["id"])
    for key in ("native_sha256", "catalog_sha256", "catalog_timestamp_ns"):
        if getattr(capture, key) != binding[key]:
            raise ValueError("native GLRT capture no longer binds to the omitted query")
    payload = encoded(
        dict(
            capture=vars(capture) | {"catalog": capture.catalog.decode("ascii")},
            tile=binding["supplied_tile"],
            implementation_sha256=digest,
        )
    )
    try:
        run = subprocess.run(
            _sandbox(cpu, sources),
            input=payload,
            capture_output=True,
            check=True,
            timeout=DEADLINE_S,
        )
        fields = json.loads(run.stdout)
    except (subprocess.SubprocessError, OSError) as error:
        status = "timed_out" if isinstance(error, subprocess.TimeoutExpired) else "failed"
        detail = (getattr(error, "stderr", None) or b"").decode(errors="replace")[-1600:]
        fields = dict(
            solver_wall_s=None,
            result=dict(
                status=status,
                boundary=BOUNDARY,
                reason=detail or str(error),
                metrics={},
                arms={arm: dict(latlon=None, forced_latlon=None) for arm in ARMS},
            ),
        )
    validate_result(fields["result"])
    row = dict(
        **binding,
        method=method,
        mode="omitted-tile",
        cpu=cpu,
        input_sha256=sha256(payload).hexdigest(),
        implementation_sha256=digest,
        sandbox="Bubblewrap process and network namespaces, one tile and native capture on stdin",
        worker_wall_s=perf_counter() - start,
        **fields,
    )
    print(method, row["id"], row["result"]["status"], round(row["worker_wall_s"], 2), flush=True)
    return row


def _correct(method, expected, digest):
    directory = REPORT / METHODS[method][0]
    path = directory / "matched-tile.jsonl.gz"
    data = path.read_bytes()
    if (lock_path := directory / "prediction-lock.json").is_file():
        lock = json.loads(lock_path.read_bytes())
        if lock["files"][path.name] != sha256(data).hexdigest():
            raise ValueError("correct-tile prediction differs from its lock")
    predictions = read_predictions(path)
    for binding in expected:
        row = predictions[binding["id"]]
        if (
            row["mode"] != "matched-tile"
            or row["method"] != method
            or row["implementation_sha256"] != digest
            or any(row[k] != binding[k] for k in ("native_sha256", "catalog_sha256"))
        ):
            raise ValueError("correct-tile comparison is not the same frozen solver and input")
    return path, sha256(data).hexdigest(), predictions


def predict(output, methods):
    expected = bindings()
    sources = {method: _sources(method) for method in methods}
    if "folded_doppler" in sources:
        _correct("folded_doppler", expected, sources["folded_doppler"][1])
    output.mkdir(parents=True, exist_ok=True)
    locks = {}
    for method, (_, digest) in sources.items():
        for name in (f"{method}.jsonl.gz", f"{method}-lock.json"):
            if (output / name).exists():
                raise ValueError("use a new directory for a new prediction measurement")
        path = output / f"{method}-plan.json"
        plan = dict(
            cpus=CPUS,
            method=method,
            implementation_sha256=digest,
            timeout_s=DEADLINE_S,
            bindings=expected,
        )
        save_json(path, plan)
        locks[method] = sha256(path.read_bytes()).hexdigest()
    jobs = [(method, binding) for method in methods for binding in expected]

    def run(cpu, assignments):
        return [_predict(method, binding, cpu, *sources[method]) for method, binding in assignments]

    with ThreadPoolExecutor(max_workers=len(CPUS)) as pool:
        workers = [
            pool.submit(run, cpu, jobs[index :: len(CPUS)]) for index, cpu in enumerate(CPUS)
        ]
        rows = {(r["method"], r["id"]): r for job in workers for r in job.result()}
    for method in methods:
        raw = b"".join(encoded(rows[method, case]) + b"\n" for case in CASES)
        compressed = gzip.compress(raw, mtime=0)
        write(output / f"{method}.jsonl.gz", compressed)
        save_json(
            output / f"{method}-lock.json",
            dict(
                plan_sha256=locks[method],
                prediction_sha256=sha256(compressed).hexdigest(),
            ),
        )


def scored_arm(row, arm, truth, *, omitted):
    decision = row["result"]
    endpoint = decision.get("arms", {}).get(arm, {})
    published, forced = endpoint.get("latlon"), endpoint.get("forced_latlon")
    status = decision["status"]
    if status == "ok" and published is None:
        status = "withheld"
    return dict(
        id=row["id"],
        method=row["method"],
        arm=arm,
        omitted=omitted,
        status=status,
        reason=decision.get("reason"),
        published=published is not None,
        false_publication=omitted and published is not None,
        published_error_km=distance_km(published, truth),
        forced_error_km=distance_km(forced, truth),
        worker_wall_s=row["worker_wall_s"],
        solver_wall_s=row.get("solver_wall_s"),
        conditional_rms_hz=endpoint.get("conditional_rms_hz"),
    )


def score(output, methods):
    expected = bindings()
    pairs, receipts = {}, {}
    for method in methods:
        prediction = output / f"{method}.jsonl.gz"
        plan = output / f"{method}-plan.json"
        lock = json.loads((output / f"{method}-lock.json").read_bytes())
        if (
            sha256(prediction.read_bytes()).hexdigest() != lock["prediction_sha256"]
            or sha256(plan.read_bytes()).hexdigest() != lock["plan_sha256"]
        ):
            raise ValueError("omitted predictions or their protocol changed after sealing")
        omitted = read_predictions(prediction)
        if set(omitted) != set(CASES) or json.loads(plan.read_bytes())["bindings"] != expected:
            raise ValueError("omitted recording roster no longer matches the prospective plan")
        for binding in expected:
            row = omitted[binding["id"]]
            if (
                row["mode"] != "omitted-tile"
                or row["method"] != method
                or row["implementation_sha256"] != METHODS[method][1]
                or any(row[key] != value for key, value in binding.items())
            ):
                raise ValueError("omitted prediction differs from the frozen single-tile input")
        path, digest, correct = _correct(method, expected, METHODS[method][1])
        pairs[method] = (correct, omitted)
        receipts[method] = dict(correct_prediction=str(path), correct_sha256=digest, **lock)

    truth = {
        row["id"]: row for row in corpus.references("transfer124") if row["id"] in CASES.values()
    }
    rows = []
    for correct, omitted in pairs.values():
        for binding in expected:
            case, query = binding["id"], binding["query_id"]
            ref = truth[query]
            if ref["condition"] != "missing" or ref["recording"] != case:
                raise ValueError("scorer matched an unrelated or present-region query")
            for arm in ARMS:
                for row in (correct[case], omitted[case]):
                    rows.append(
                        scored_arm(row, arm, ref["truth"], omitted=row["mode"] == "omitted-tile")
                        | dict(query_id=query)
                    )
    summary = []
    for method in methods:
        for arm in ARMS:
            for omitted in (False, True):
                subset = [
                    r
                    for r in rows
                    if (r["method"], r["arm"], r["omitted"]) == (method, arm, omitted)
                ]
                summary.append(
                    dict(
                        method=method,
                        arm=arm,
                        omitted=omitted,
                        attempts=len(subset),
                        published=sum(r["published"] for r in subset),
                        false_publications=sum(r["false_publication"] for r in subset),
                        withheld=sum(r["status"] == "withheld" for r in subset),
                        forced=sum(r["forced_error_km"] is not None for r in subset),
                    )
                )
    save_json(output / "scores.json", dict(rows=rows, summary=summary, receipts=receipts))
    plot(output, rows, summary)


def plot(output, rows, summary):
    import matplotlib.pyplot as plt

    labels = list(dict.fromkeys((r["method"], r["arm"]) for r in summary))
    fig, (count, error) = plt.subplots(1, 2, figsize=(10.3, 4.6), width_ratios=(0.8, 1.4))
    colors = {False: "#176b87", True: "#c05338"}
    for index, (method, arm) in enumerate(labels):
        for omitted, offset in ((False, -0.16), (True, 0.16)):
            info = next(
                r
                for r in summary
                if (r["method"], r["arm"], r["omitted"]) == (method, arm, omitted)
            )
            at, color = index + offset, colors[omitted]
            count.barh(at, info["attempts"], height=0.25, color="#e9edf1")
            count.barh(at, info["published"], height=0.25, color=color)
            count.text(3.1, at, f"{info['published']}/{info['attempts']}", color=color, va="center")
            subset = [
                r for r in rows if (r["method"], r["arm"], r["omitted"]) == (method, arm, omitted)
            ]
            for row in subset:
                if row["forced_error_km"] is not None:
                    error.scatter(
                        row["forced_error_km"],
                        at,
                        facecolors="none",
                        edgecolors=color,
                        marker="o",
                        s=42,
                        linewidth=1.2,
                    )
                if row["published_error_km"] is not None:
                    error.scatter(row["published_error_km"], at, color=color, marker="o", s=26)
    names = [
        f"{method.replace('_', ' ').title()}  ·  {arm.replace('_', ' ')}" for method, arm in labels
    ]
    for axis in (count, error):
        axis.set_ylim(len(labels) - 0.5, -0.5)
        axis.spines[["top", "right", "left"]].set_visible(False)
        axis.tick_params(axis="y", length=0)
    count.set(
        yticks=range(len(labels)),
        yticklabels=names,
        xlim=(0, 3.7),
        xticks=range(4),
        xlabel="Published attempts",
    )
    error.set(xscale="log", yticks=[], xlabel="Distance from reference (km)")
    error.grid(axis="x", alpha=0.25)
    fig.suptitle("Single-tile decisions when the correct region is omitted", fontsize=14)
    fig.text(0.23, 0.91, "Correct tile", color=colors[False], weight="bold")
    fig.text(0.40, 0.91, "Correct region omitted", color=colors[True], weight="bold")
    fig.text(0.70, 0.91, "○ Forced    ● Published", color="#373e45")
    fig.tight_layout(rect=(0, 0, 1, 0.89))
    fig.savefig(output / "omitted-tile.png", dpi=190)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("predict", "score"))
    parser.add_argument("--out", type=Path, default=REPORT / "wrong-tiles")
    parser.add_argument("--method", nargs="+", choices=METHODS, default=tuple(METHODS))
    args = parser.parse_args()
    if not set(CPUS) <= os.sched_getaffinity(0):
        parser.error("use the preregistered four CPUs")
    if len(set(args.method)) != len(args.method):
        parser.error("each solver requires a single attempt per recording")
    if args.action == "predict":
        predict(args.out, args.method)
    else:
        score(args.out, args.method)


if __name__ == "__main__":
    main()
