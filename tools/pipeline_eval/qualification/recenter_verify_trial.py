"""Bind and replay the native verification cohort and separate diagnosed stress."""

import argparse
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scipy.optimize import root

from .. import scoring
from ..__main__ import encoded, save_json
from ..variants import recenter_verify
from . import boundary_roof as journal
from . import boundary_roof_offers as geom
from . import native_clock_full as clock
from . import native_clock_model_worker as base_worker

METHODS = (recenter_verify.METHOD, clock.METHOD)
REPORT = geom.REPORT.with_name("recenter-verify")
WORK = geom.WORK.with_name("recenter-verify-replay")
WORKER = Path(__file__).with_name("recenter_verify_worker.py")
phase = clock.phase
SEED = "recenter-roof-v1:"
COHORTS = ("prospective", "diagnosed-stress")


def keyed(purpose, key):
    return sha256(f"{SEED}{purpose}:{key}".encode()).hexdigest()


def roster(plan):
    excluded = {ident for group in geom.roster(plan).values() for ident in group}
    candidates = {q["recording"] for q in plan["cases"] if q["cohort"] == "roof"} - excluded
    if not all(ident.startswith("DS26-") for ident in candidates):
        raise ValueError("authenticated DS29 exclusion differs from the frozen protocol")
    return sorted(candidates, key=lambda i: keyed("roster", i))[:10]


def new_offers(ident, truth, original):
    face = int(keyed("face", ident)[:2], 16) % 4
    normal = geom.NORMALS[face]
    perpendicular = np.array((-normal[1], normal[0]))
    along = 8 * geom.fraction(keyed("along", ident)) - 4
    surface = geom.Region(
        "", truth, geom.geodetic_to_ecef_km(*truth, 0), geom.ecef_to_enu_matrix(*truth)
    )
    for condition, requested in zip(geom.CONDITIONS, (None, 1.5, -1.5, -6.0), strict=True):
        tile = dict(original, id=keyed("tile", f"{ident}:{condition}")[:20], width_km=25.0)
        if requested is not None:
            target = (12.5 - requested) * normal + along * perpendicular

            def mismatch(x, target=target):
                return geom.tangent(truth, surface.site(x)[1]) - target

            solution = root(mismatch, -target)
            if np.max(np.abs(mismatch(solution.x))) > 1e-6:
                raise ValueError("could not generate the exact tangent-plane offer")
            tile["center"] = surface.site(solution.x)[1]
        margin = float(12.5 - np.max(np.abs(geom.tangent(truth, tile["center"]))))
        yield (
            tile,
            dict(
                id=keyed("query", f"{ident}:{condition}")[:20],
                recording=ident,
                condition=condition,
                truth=truth,
                face=geom.FACES[face] if requested is not None else None,
                requested_margin_km=requested,
                true_margin_km=margin,
            ),
        )


def sources(plan):
    files = (
        Path(__file__),
        WORKER,
        Path(recenter_verify.__file__),
        Path(scoring.__file__),
        Path(journal.__file__),
        Path(geom.__file__),
        REPORT / "PROTOCOL.md",
    )
    return dict(
        source=plan["source"],
        code={p.name: phase.digest(p) for p in files},
        clock_plan_sha256=phase.digest(clock.REPORT / "plan.json"),
        prior_challenge_locks={
            cohort: phase.digest(geom.REPORT / cohort / "prediction-lock.json")
            for cohort in ("primary", "reserve")
        },
    )


def stress_inputs():
    report = geom.REPORT / "reserve"
    lock = phase._read(report / "prediction-lock.json")
    if phase.digest(report / "evaluator.json") != lock["evaluator_sha256"]:
        raise ValueError("diagnosed stress must use the exact sealed prior offers")
    rows = phase._read(report / "evaluator.json")["labels"]
    selected = [
        r
        for r in rows
        if r["recording"] == "DS26-0070" and r["condition"] in ("near-outside", "six-outside")
    ]
    if len(selected) != 2:
        raise ValueError("expected the two diagnosed false-fit challenges")
    return selected


def generate(work, bundle):
    plan, _ = clock.prepare(bundle)
    parents = {q["recording"]: q for q in plan["cases"] if q["cohort"] == "roof"}
    ids = roster(plan)
    truth = {r["id"]: r["truth"] for r in phase.corpus.references("ds26-common127")}
    prospective = [
        dict(label, tile=tile)
        for ident in ids
        for tile, label in new_offers(ident, truth[ident], parents[ident]["packet"]["offer"])
    ]
    for cohort, rows in zip(COHORTS, (prospective, stress_inputs()), strict=True):
        cases, labels = [], []
        for row in rows:
            ident = row["recording"]
            packet = dict(parents[ident]["packet"], offer=row["tile"])
            checksum = phase.corpus._sha(encoded(packet))
            if cohort == "diagnosed-stress" and checksum != row["input_sha256"]:
                raise ValueError("diagnosed stress changed the original native packet")
            labels.append(dict(row, input_sha256=checksum))
            cases.append(dict(id=row["id"], recording=ident, cohort=cohort, packet=packet))
        cases.sort(key=lambda q: keyed("order", q["id"]))
        dest = work / cohort
        dest.mkdir(parents=True, exist_ok=False)
        save_json(dest / "evaluator.json", dict(cohort=cohort, labels=labels))
        save_json(
            dest / "requests.json",
            dict(
                cohort=cohort,
                cases=cases,
                sources=sources(plan),
                evaluator_sha256=phase.digest(dest / "evaluator.json"),
            ),
        )


def prepare(work, bundle):
    data = phase._read(work / "requests.json")
    plan, originals = clock.prepare(bundle)
    if data["sources"] != sources(plan):
        raise ValueError("recenter sources differ from the frozen blind request")
    bounds = {
        q["recording"]: (q["packet"], files) for q, files in originals if q["cohort"] == "roof"
    }
    cohort = data["cohort"]
    cases = data["cases"]
    expected = {(i, 4) for i in roster(plan)} if cohort == "prospective" else {("DS26-0070", 2)}
    if {
        (i, sum(q["recording"] == i for q in cases)) for i in {q["recording"] for q in cases}
    } != expected:
        raise ValueError("recenter attempts differ from the frozen recording roster")
    jobs = []
    for query in cases:
        original, paths = bounds[query["recording"]]
        tile = query["packet"]["offer"]
        if query["packet"] != dict(original, offer=tile) or tile["width_km"] != 25.0:
            raise ValueError("recenter offer changed non-offer data")
        jobs.extend((method, query, paths) for method in METHODS)
    return dict(
        data,
        methods=list(METHODS),
        requests_sha256=phase.digest(work / "requests.json"),
        cpus=list(journal.CPUS),
        worker_cap_s=clock.base.CAP,
        wall_cap_s=journal.WALL_CAP_S,
    ), jobs


def command(cpu, paths, bundle):
    argv = clock.command(cpu, paths, bundle)
    argv[argv.index(str(clock.WORKER))] = str(WORKER)
    for module, dest in (
        (base_worker, "qualification/native_clock_model_worker.py"),
        (recenter_verify, "variants/recenter_verify.py"),
        (scoring, "scoring.py"),
    ):
        argv[-3:-3] = [
            "--ro-bind",
            str(Path(module.__file__)),
            f"/worker/tools/pipeline_eval/{dest}",
        ]
    return argv


def run(work, bundle, output):
    with (
        patch.object(journal, "METHODS", METHODS),
        patch.object(journal, "prepare", prepare),
        patch.object(journal.fixed, "command", command),
    ):
        for cohort in COHORTS:
            journal.run(work / cohort, bundle, output / cohort)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("stage", choices=("generate", "run"))
    cli.add_argument("--work", type=Path, default=WORK)
    cli.add_argument("--output", type=Path, default=REPORT)
    cli.add_argument("--bundle", type=Path, default=clock.base.BUNDLE)
    args = cli.parse_args()
    if args.stage == "generate":
        generate(args.work, args.bundle)
    else:
        run(args.work, args.bundle, args.output)


if __name__ == "__main__":
    main()
