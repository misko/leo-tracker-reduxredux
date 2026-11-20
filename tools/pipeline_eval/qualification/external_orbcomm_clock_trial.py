"""Fit a shared receiver CFO offset on one disjoint final Bellaterra day pair."""

import argparse
import gzip
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import numpy as np

from ..__main__ import encoded, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from ..variants import external_orbcomm_clock as solve_model
from . import external_orbcomm_availability as audit
from . import external_orbcomm_trial as base
from . import screening_figures
from .armijo_finish_results import pack
from .prefix_figures import csv_file

REPORT = base.REPORT / "clock-transfer"
START = datetime(2026, 4, 7, tzinfo=UTC)
SEED = 67238015
METHODS = solve_model.METHODS
read, digest = base.read, base.digest


def causal_bank(orbits, archive, cutoff):
    chosen = {}
    for norad, records in archive.items():
        valid = [
            (r["epoch_ns"], r["first_used_ns"], key)
            for key, r in orbits.items()
            if r["norad"] == int(norad)
            and r["first_used_ns"] is not None
            and r["epoch_ns"] <= cutoff
            and r["first_used_ns"] <= cutoff
            and audit.confirmed(records, r, cutoff)["available_before_cutoff"]
        ]
        if valid:
            chosen[int(norad)] = max(valid)[2]
    return chosen


def prepare(source, work, out):
    if (out / "input-lock.json").exists():
        raise FileExistsError("final measured day pair is already bound")
    base.check(base.REPORT, "availability-lock.json")
    base.check(base.REPORT, "prediction-lock.json")
    sources = (
        Path(__file__),
        Path(solve_model.__file__),
        Path(base.__file__),
        Path(base.solver.__file__),
        Path(audit.__file__),
        out / "PROTOCOL.md",
    )
    body = base.authenticate(source)
    save_json(
        out / "source-lock.json",
        dict(
            sources={str(p): digest(p.read_bytes()) for p in sources},
            publisher=body,
            prior_prediction_sha256=digest((base.REPORT / "prediction-lock.json").read_bytes()),
            prior_availability_sha256=digest((base.REPORT / "availability-lock.json").read_bytes()),
            strict_tle_cutoff_ns=base.ns(START) - base.OLD_NS,
            seed=SEED,
        ),
    )
    # Match against published, earlier IAU collection records from the first study's remote audit.
    histories = json.loads(
        gzip.decompress((base.REPORT / "iau-history-bodies.json.gz").read_bytes())
    )
    archive = {n: json.loads(b)["data"] for n, b in histories.items()}
    groups, orbits, _ = base.parse_tracks(source)
    start, cutoff = base.ns(START), base.ns(START) - base.OLD_NS
    selected = causal_bank(orbits, archive, cutoff)
    by_trace, count = {}, {}
    for role, d in (("training", start // base.DAY_NS), ("held", start // base.DAY_NS + 1)):
        by_trace[role], original_rows = [], 0
        for (day, norad, band), observations in groups.items():
            if day != d or norad not in selected:
                continue
            for row, _, m in base.passes(observations, selected[norad], norad, band):
                by_trace[role].append(row)
                original_rows += m
        count[role] = dict(
            original_rows=original_rows,
            traces=len(by_trace[role]),
            sampled_rows=sum(len(r["cfo_hz"]) for r in by_trace[role]),
            norads=sorted({r["norad"] for r in by_trace[role]}),
        )
    if any(v["traces"] < 6 or len(v["norads"]) < 3 for v in count.values()):
        raise ValueError(
            "final measured day pair lacks the independently corroborated predeclared support"
        )
    by_trace["elements"] = {k: orbits[k] for k in selected.values()}
    proofs = {
        k: audit.confirmed(archive[str(r["norad"])], r, cutoff)
        for k, r in by_trace["elements"].items()
    }
    save_json(
        out / "support.json",
        dict(count, selected_elements=by_trace["elements"], before_cutoff=proofs),
    )
    public = work / "public"
    public.mkdir(parents=True, mode=0o700)
    rng = np.random.default_rng(SEED)
    direction = int(rng.integers(0, 2))
    sign = int(rng.choice((-1, 1)))
    offers, labels = [], {}
    track_sha = digest(encoded({k: by_trace[k] for k in ("training", "held")}))
    catalogue_sha = digest(encoded(by_trace["elements"]))
    for group, distance in (("containing", float(rng.uniform(6, 9))), ("omitted", 14.0)):
        ident = rng.bytes(12).hex()
        shift = [0.0, 0.0]
        shift[direction] = sign * distance
        tile = base.solver.geographic(base.SITE, shift)
        data = encoded(dict(packet=by_trace, tile=tile))
        write(public / f"{ident}.json", data)
        offers.append(
            dict(
                id=ident,
                input_sha256=digest(data),
                native_sha256=track_sha,
                catalogue_sha256=catalogue_sha,
            )
        )
        labels[ident] = dict(site=base.SITE, condition=group)
    rng.shuffle(offers)
    save_json(work / "labels.json", labels)
    save_json(out / "requests.json", offers)
    names = ("support.json", "source-lock.json", "requests.json")
    save_json(
        out / "input-lock.json",
        dict(
            files={n: digest((out / n).read_bytes()) for n in names},
            labels_sha256=digest((work / "labels.json").read_bytes()),
        ),
    )


def invocation(cpu):
    cmd = base.invocation(cpu)
    bound = cmd.index(str(base.solver.__file__))
    cmd[bound] = str(solve_model.__file__)
    exe = cmd.index(str(Path(sys.executable)))
    cmd[exe:exe] = ["--ro-bind", str(base.solver.__file__), "/solver/external_orbcomm.py"]
    return cmd


def solve(work, out):
    base.check(out, "input-lock.json")
    if any(
        digest(Path(p).read_bytes()) != h
        for p, h in read(out / "source-lock.json")["sources"].items()
    ):
        raise ValueError("final measured estimator source changed")
    cases = read(out / "requests.json")

    def run(case, cpu):
        data = (work / "public" / f"{case['id']}.json").read_bytes()
        if digest(data) != case["input_sha256"]:
            raise ValueError("held packet differs from its locked data")
        start = perf_counter()
        outcome = subprocess.run(
            invocation(cpu), input=data, capture_output=True, timeout=30, check=True
        )
        wall = perf_counter() - start
        result = json.loads(outcome.stdout)
        return [
            dict(case, method=method, result=row, support=result["support"], worker_wall_s=wall)
            for method, row in result["results"].items()
        ]

    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(run, r, cpu) for r, cpu in zip(cases, base.CORES, strict=True)]
        rows = [v for j in jobs for v in j.result()]
    for r in rows:
        validate_result(r["result"])
    pack(out, "positions.jsonl.gz", rows)
    names = ("positions.jsonl.gz", "input-lock.json", "source-lock.json", "support.json")
    save_json(
        out / "prediction-lock.json",
        dict(
            cases=[r["id"] for r in cases], files={n: digest((out / n).read_bytes()) for n in names}
        ),
    )


def score(work, out):
    seal = base.check(out, "prediction-lock.json")
    inputs = base.check(out, "input-lock.json")
    labels = (work / "labels.json").read_bytes()
    if digest(labels) != inputs["labels_sha256"]:
        raise ValueError("final survey commitment changed")
    truth = json.loads(labels)
    with gzip.open(out / "positions.jsonl.gz", "rt") as stream:
        rows = list(map(json.loads, stream))
    requests = {r["id"]: r for r in read(out / "requests.json")}
    if len(rows) != len(seal["cases"]) * len(METHODS) or {(r["id"], r["method"]) for r in rows} != {
        (i, m) for i in requests for m in METHODS
    }:
        raise ValueError("not every frozen final hypothesis produced a terminal result")
    stats, queries = [], []
    for ident, case in requests.items():
        label = truth[ident]
        hashes = {k: case[k] for k in ("input_sha256", "native_sha256", "catalogue_sha256")}
        queries.append(
            dict(
                id=ident,
                condition=label["condition"],
                truth=label["site"],
                recording="2026-04-07/08",
                bindings=hashes,
            )
        )
        for row in (r for r in rows if r["id"] == ident):
            if any(row[k] != v for k, v in hashes.items()):
                raise ValueError("comparison controls differ from the same final input")
            for arm in ARMS:
                fit = row["result"]["arms"][arm]
                science = row["result"]["metrics"]
                slot = (science.get(arm) or {}) if row["method"] == METHODS[0] else science
                stats.append(
                    dict(
                        id=ident,
                        method=row["method"],
                        arm=arm,
                        condition=label["condition"],
                        status=fit.get("status", row["result"]["status"]),
                        reason=fit.get("reason"),
                        geographic_km=distance_km(fit["latlon"], label["site"]),
                        forced_km=distance_km(fit.get("forced_latlon"), label["site"]),
                        held_rf_rms_hz=fit.get("rf_rms_hz"),
                        shared_receiver_offset_hz=slot.get("receiver_offset_hz"),
                        rf_hz_per_mhz=slot.get("c_hz_per_mhz"),
                        held_repeat_km=slot.get("held_stability_km"),
                        held_gain_hz=slot.get("held_center_gain_hz"),
                        rf_relative_leverage=science.get("rf_relative_leverage"),
                        joint_wall_s=row["worker_wall_s"],
                    )
                )
    csv_file(out / "scores.csv", stats)
    write(out / "truth-after-lock.json", labels)
    save_json(out / "figure-queries.json", dict(queries=queries))
    names = (
        "prediction-lock.json",
        "positions.jsonl.gz",
        "scores.csv",
        "truth-after-lock.json",
        "figure-queries.json",
    )
    save_json(
        out / "score-lock.json",
        dict(cases=seal["cases"], files={n: digest((out / n).read_bytes()) for n in names}),
    )
    chart(out)


def chart(out):
    labels = (
        "Shared receiver offset",
        "Zero offsets",
        "Free per pass",
        "Time reversal",
        "Offer center",
    )

    def series(key, i):
        row = dict(key=key, label=labels[i], file="positions.jsonl.gz", value=METHODS[i])
        if key != "candidate":
            row["match"] = ["input_sha256", "native_sha256", "catalogue_sha256"]
        return row

    common = dict(
        method=METHODS[0],
        scope="transfer",
        cases="sealed",
        seal="score-lock.json",
        queries="figure-queries.json",
        provenance=["prediction-lock.json", "scores.csv"],
        condition_labels=dict(containing="25 km containing", omitted="25 km near omitted"),
    )
    specs = [
        dict(
            common,
            id=ident,
            title=heading,
            caption=(
                "One measured Bellaterra receiver, unused April 7/8 observations. "
                "Only the shared-offset model estimates a conditional RF slope."
            ),
            series=values,
        )
        for ident, heading, values in (
            (
                "external-orbcomm-shared-offset",
                "Shared receiver carrier offset on the final VHF day pair",
                [series(k, i) for i, k in enumerate(("candidate", "stock", "one", "four"))],
            ),
            (
                "external-orbcomm-shared-offset-prior",
                "Shared offset against the offered local center",
                [series("candidate", 0), series("stock", 4)],
            ),
        )
    ]
    save_json(out / "figures.json", dict(version=2, charts=specs))
    screening_figures.generate(out / "charts", evidence=out)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("prepare", "solve", "score"))
    p.add_argument("work", type=Path)
    p.add_argument("--source", type=Path)
    p.add_argument("--out", type=Path, default=REPORT)
    a = p.parse_args()
    if a.action == "prepare":
        prepare(a.source, a.work, a.out)
    elif a.action == "solve":
        solve(a.work, a.out)
    else:
        score(a.work, a.out)


if __name__ == "__main__":
    main()
