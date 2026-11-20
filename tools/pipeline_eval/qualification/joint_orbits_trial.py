"""Seal measured and geographic joint-assignment evaluations before opening references."""

import argparse
import gzip
import json
import os
import secrets
import subprocess
from collections import Counter
from pathlib import Path
from time import perf_counter

from .. import corpus
from ..__main__ import encoded, references, save_json, write
from ..scoring import ARMS, distribution, validate_result
from . import cold_scenes as cold
from . import fresh_scenes as fresh
from . import joint_orbits_inputs as inputs
from . import robust_orbit_fit_diagnostic as audit
from . import robust_orbit_fit_trials as prior
from . import site_transfer_samples as disturbance

ROOT = cold.REPO
REPORT = ROOT / "reports/2026_11_19_receiver_screening/inference/joint-orbits"
METHODS = ("joint_orbits", "robust_orbit_fit", "robust_em")
PREDICTIONS = "predictions.jsonl.gz"
TRACES = "owner-traces.jsonl.gz"
TIMEOUT = 60


def sources():
    controls = prior.locked_sources()
    if controls != fresh._read(prior.OUTPUT / "source-lock.json"):
        raise ValueError("the controls differ from their archive releases")
    local = Path(__file__).parent
    paths = (
        REPORT / "PROTOCOL.md",
        Path(__file__),
        *(
            local / f"{name}.py"
            for name in (
                "joint_orbits_inputs",
                "joint_orbits_worker",
                "cold_scenes",
                "fresh_scenes",
                "robust_em_trials",
                "robust_orbit_fit_trials",
                "robust_orbit_fit_diagnostic",
                "lean_support_trial",
                "site_transfer_samples",
                "full_v5_check",
            )
        ),
        disturbance.TRACE,
        disturbance.AUDIT,
        inputs.support.OFFERS,
        corpus.FROZEN / "provenance.json",
        ROOT / "tools/pipeline_eval/scoring.py",
        ROOT / "src/leo/sky/frames.py",
        ROOT / "src/leo/sky/propagation.py",
        *(ROOT / "tools/pipeline_eval/variants" / f"{m}.py" for m in METHODS),
    )
    return dict(
        files={str(p.resolve().relative_to(ROOT)): fresh._sha(p) for p in paths},
        control_dependencies=controls,
        cases=inputs.archive_cases(),
        methods=METHODS,
    )


def prepare(root, cache):
    root.mkdir(mode=0o700)
    private = root / "private"
    private.mkdir(mode=0o700)
    fresh._new(root / "source-lock.json", sources())
    seed = secrets.token_bytes(32)
    cold._new(private / "seed.bin", seed)
    synthetic, labels, draws = inputs.synthetic_packets(seed)
    fresh._new(private / "labels.json", labels)
    fresh._new(private / "disturbances.json", draws)
    queries = [*inputs.archive_packets(cache), *synthetic]
    cold._new(root / "queries.json.gz", gzip.compress(encoded(queries) + b"\n", mtime=0))
    fresh._new(
        root / "input-lock.json",
        dict(
            samples={r["id"]: cold._sha(encoded(r["packet"])) for r in queries},
            bindings={r["id"]: {k: v for k, v in r.items() if k != "packet"} for r in queries},
            queries_sha256=fresh._sha(root / "queries.json.gz"),
            source_lock_sha256=fresh._sha(root / "source-lock.json"),
            private={p.name: fresh._sha(p) for p in private.iterdir()},
        ),
    )


def _queries(root):
    lock = fresh._read(root / "input-lock.json")
    if (
        lock["source_lock_sha256"] != fresh._sha(root / "source-lock.json")
        or lock["queries_sha256"] != fresh._sha(root / "queries.json.gz")
        or encoded(fresh._read(root / "source-lock.json")) != encoded(sources())
    ):
        raise ValueError("sources or queries changed after the draw")
    with gzip.open(root / "queries.json.gz", "rt") as stream:
        queries = json.load(stream)
    if lock["samples"] != {r["id"]: cold._sha(encoded(r["packet"])) for r in queries}:
        raise ValueError("a public worker packet changed")
    return queries, lock


def _attempt(row, method, source, cpu):
    packet = row["packet"]
    command = fresh._sandbox(cpu)
    command[-2:] = ["-m", "tools.pipeline_eval.qualification.joint_orbits_worker"]
    started = perf_counter()
    try:
        result = subprocess.run(
            command,
            input=encoded(packet | {"method": method}),
            capture_output=True,
            timeout=TIMEOUT,
            check=True,
        )
        outcome = json.loads(result.stdout)
    except (ValueError, OSError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as err:
        msg = (getattr(err, "stderr", None) or b"").decode(errors="replace")[-1600:]
        outcome = dict(
            owners=[],
            heldout_diagnostics={},
            worker_cpu_s=None,
            max_rss_kib=None,
            result=dict(
                status="timed_out" if isinstance(err, subprocess.TimeoutExpired) else "failed",
                reason=msg or str(err),
                boundary="Prepared anonymous GLRT tracks",
                metrics={},
                arms={a: {"latlon": None, "forced_latlon": None} for a in ARMS},
            ),
        )
    validate_result(outcome["result"])
    wall = perf_counter() - started
    print(method, row["id"], outcome["result"]["status"], round(wall, 2), flush=True)
    return dict(
        **{k: v for k, v in row.items() if k != "packet"},
        **outcome,
        capture_id=row["recording"],
        method=method,
        mode="supplied-tile",
        tile=packet["offer"],
        wall_s=wall,
        input_sha256=cold._sha(encoded(packet)),
        implementation_sha256=source[f"tools/pipeline_eval/variants/{method}.py"],
    )


def _jsonl(path, rows):
    return cold._new(path, gzip.compress(b"".join(encoded(r) + b"\n" for r in rows), mtime=0))


def predict(root):
    (cpu,) = os.sched_getaffinity(0)
    queries, _ = _queries(root)
    source = fresh._read(root / "source-lock.json")["files"]
    rows = [
        _attempt(row, method, source, cpu)
        for i, row in enumerate(queries)
        for method in (*METHODS[i % len(METHODS) :], *METHODS[: i % len(METHODS)])
    ]
    _queries(root)
    _jsonl(
        root / TRACES, [dict(id=r["id"], method=r["method"], rows=r.pop("owners")) for r in rows]
    )
    _jsonl(root / PREDICTIONS, rows)
    fresh._new(
        root / "prediction-lock.json",
        dict(
            cases=[r["id"] for r in queries],
            input_lock_sha256=fresh._sha(root / "input-lock.json"),
            source_lock_sha256=fresh._sha(root / "source-lock.json"),
            files={name: fresh._sha(root / name) for name in (PREDICTIONS, TRACES)},
        ),
    )


def _verify(root):
    queries, inputs_lock = _queries(root)
    lock = fresh._read(root / "prediction-lock.json")
    if (
        lock["source_lock_sha256"] != fresh._sha(root / "source-lock.json")
        or lock["input_lock_sha256"] != fresh._sha(root / "input-lock.json")
        or any(fresh._sha(root / name) != digest for name, digest in lock["files"].items())
        or lock["cases"] != [r["id"] for r in queries]
    ):
        raise ValueError("prediction commitments changed before scoring")
    with gzip.open(root / PREDICTIONS, "rt") as stream:
        predictions = list(map(json.loads, stream))
    observed = Counter((r["id"], r["method"]) for r in predictions)
    expected = Counter((query["id"], m) for query in queries for m in METHODS)
    if observed != expected or any(
        r["input_sha256"] != inputs_lock["samples"][r["id"]] for r in predictions
    ):
        raise ValueError("the methods did not receive a paired fixed roster")
    if any(fresh._sha(root / "private" / name) != d for name, d in inputs_lock["private"].items()):
        raise ValueError("private scorer inputs changed")
    return predictions


def _ownership(root, genuine):
    receipts = {case: audit.published(case) for case in genuine}
    summaries = []
    with gzip.open(root / TRACES, "rt") as stream:
        for record in map(json.loads, stream):
            case = record["id"]
            if case not in receipts:
                continue
            reference, digest = receipts[case]
            counts = Counter()
            for row in record["rows"]:
                key = audit.key(row["receiver"], row["channel"], row["time_s"], row["cfo_hz"])
                owners = reference.get(key, ())
                if len(owners) == 1:
                    counts["agree" if row["norad"] in owners else "disagree"] += 1
                else:
                    counts["ambiguous"] += bool(owners)
                    counts["unmatched"] += not owners
            summaries.append(
                dict(
                    case=case,
                    method=record["method"],
                    points=len(record["rows"]),
                    counts=counts,
                    v5_receipt_sha256=digest,
                )
            )
    return summaries


def score(root, output):
    predictions = _verify(root)
    ids = inputs.archive_cases()
    reference = {}
    for panel, selected in (
        ("ds26-common127", [c for c in ids if c.startswith("DS26")]),
        ("roof16", [c for c in ids if c.startswith("DS29")]),
    ):
        reference.update((r["id"], r["truth"]) for r in references(panel, selected)[1])
    synthetic = fresh._read(root / "private/labels.json")
    labels = {}
    for p in predictions:
        cohort = p["cohort"]
        condition = (
            "missing"
            if cohort.endswith("omitted")
            else "shuffle"
            if cohort.endswith("shuffle")
            else "present"
        )
        site = (
            synthetic[p["id"]]
            if cohort in inputs.SYNTHETIC
            else (None if condition == "shuffle" else reference[p["recording"]])
        )
        labels[p["id"]] = dict(condition=condition, latlon=site)
    cases = []
    for p in predictions:
        for row in fresh._score_rows([p], labels):
            held = p["heldout_diagnostics"].get(row["arm"], {})
            cases.append(dict(row, cohort=p["cohort"], heldout=held))
    groups = []
    for cohort in (*inputs.PHYSICAL, *inputs.SYNTHETIC):
        rows = [r for r in cases if r["cohort"] == cohort]
        for item in fresh._groups(rows, METHODS):
            if item["attempts"]:
                matched = [
                    r for r in rows if r["method"] == item["method"] and r["arm"] == item["arm"]
                ]
                groups.append(
                    dict(
                        item,
                        cohort=cohort,
                        conditional_rms_hz=distribution(r["rf_rms_hz"] for r in matched),
                        held_normalized_loss=distribution(
                            r["heldout"].get("held_normalized_mean_loss") for r in matched
                        ),
                    )
                )
    owners = _ownership(root, ids)
    for name in (
        PREDICTIONS,
        TRACES,
        "prediction-lock.json",
        "input-lock.json",
        "source-lock.json",
    ):
        write(output / name, (root / name).read_bytes())
    save_json(output / "scores.json", dict(cases=cases, groups=groups, labels=labels))
    save_json(output / "ownership.json", owners)
    write(output / "seed.hex", (root / "private/seed.bin").read_bytes().hex().encode() + b"\n")
    write(output / "synthetic-disturbances.json", (root / "private/disturbances.json").read_bytes())


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    commands = cli.add_subparsers(dest="action", required=True)
    for action in ("prepare", "predict", "score"):
        command = commands.add_parser(action)
        command.add_argument("root", type=Path)
        if action == "prepare":
            command.add_argument("--cache", type=Path, required=True)
        if action == "score":
            command.add_argument("--out", type=Path, default=REPORT)
    args = cli.parse_args()
    if args.action == "prepare":
        prepare(args.root, args.cache)
    elif args.action == "predict":
        predict(args.root)
    else:
        score(args.root, args.out)


if __name__ == "__main__":
    main()
