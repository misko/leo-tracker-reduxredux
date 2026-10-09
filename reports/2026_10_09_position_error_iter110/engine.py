"""Prepared consumed-development persistence pilot; no execution without freeze."""

import argparse
import hashlib
import json
import os
import runpy
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_09_position_error_iter108"))
CENSUS = runpy.run_path(str(REPORTS / "2026_10_09_position_error_iter108/audit.py"))
CONTROL = runpy.run_path(str(REPORTS / "2026_10_09_position_error_iter106/engine.py"))
PersistenceObjective = runpy.run_path(
    str(REPORTS / "2026_10_09_position_error_iter109/objective.py")
)["PersistenceObjective"]
ARMS = ("fitted-c", "zero-c")
RHOS = (0.0, 0.5)
SEED = "position-persistence-pilot110-seed20261009"


def select_members(members, seed=SEED):
    """Whole-recording pseudorandom rank independent of input quality or outcomes."""
    assert len(members) == 148
    assert len({b["member"]["session_id"] for b in members}) == 148
    chosen, ranks = [], []
    for dataset, count in (("DS16", 63), ("DS17", 51), ("DS18", 34)):
        group = [b for b in members if b["member"]["dataset"] == dataset]
        assert len(group) == count

        def rank(binding, dataset=dataset):
            member = binding["member"]
            message = json.dumps([seed, dataset, member["session_id"]], separators=(",", ":"))
            return hashlib.sha256(message.encode()).hexdigest(), member["inventory_label"]

        ordered = sorted(group, key=rank)
        chosen.extend(ordered[:4])
        ranks.extend(
            dict(
                label=b["member"]["inventory_label"],
                dataset=dataset,
                rank_sha256=rank(b)[0],
                selected=i < 4,
            )
            for i, b in enumerate(ordered)
        )
    return sorted(chosen, key=lambda b: b["member"]["inventory_label"]), ranks


def verify_control(model, control, archive):
    checks = CONTROL["check_archive"](model, archive)
    for arm in ARMS:
        fit = archive["stages"]["B7"][arm]
        v, c = np.asarray(fit["vector"]), np.asarray(fit["clock_coefficients"])
        a, b = model.evaluate_joint(v, c), control.evaluate_joint(v, c)
        for index in range(3):
            np.testing.assert_array_equal(a[index], b[index])
    return checks


def evaluate(binding, digest):
    member = binding["member"]
    label = member["inventory_label"]
    destination = HERE / "results" / f"{label}.json"
    read, write = CONTROL["AUDIT"]["read"], CONTROL["write"]
    if destination.exists():
        stored = read(destination)
        assert stored["protocol_sha256"] == digest and stored["member"] == member
        return
    begun = time.monotonic()
    receipt = dict(
        protocol_sha256=digest,
        member=member,
        loader_kind=binding["loader_binding"]["kind"],
        source=binding["b7_source"],
    )
    try:
        archive = read(ROOT / binding["b7_source"])
        assert archive["status"] == "complete" and archive["member"] == member
        reconstruction_started = time.monotonic()
        base, tracks = CENSUS["reconstruct"](binding, archive)
        receipt["reconstruction_seconds"] = time.monotonic() - reconstruction_started
        assert base.score.sigma_hz == 125 and base.score.relative_sigma_s == 2
        layout = CENSUS["prepare_segments"](tracks, base.observations)
        models = {
            str(rho): PersistenceObjective(base, layout["permutation"], layout["reset"], rho=rho)
            for rho in RHOS
        }
        receipt["objective_checks"] = verify_control(base, models["0.0"], archive)
        fitted = archive["stages"]["B7"]["fitted-c"]
        seed, clock = np.asarray(fitted["vector"]), np.asarray(fitted["clock_coefficients"])
        receipt.update(
            shared_start=dict(vector=seed, clock_coefficients=clock),
            coverage=layout["counts"],
            permutation=layout["permutation"],
            reset=layout["reset"],
        )
        raw, operational = {}, {}
        for rho in RHOS:
            name = str(rho)
            raw[name], operational[name] = {}, {}
            for arm in ARMS:
                path = HERE / "attempts" / label / f"rho{name}-{arm}.json"
                if path.exists():
                    attempt = read(path)
                    assert attempt["protocol_sha256"] == digest and attempt["member"] == member
                    assert attempt["rho"] == rho and attempt["arm"] == arm
                else:
                    attempt = dict(protocol_sha256=digest, member=member, rho=rho, arm=arm)
                    try:
                        fit = CONTROL["run_attempt"](models[name], seed, clock, arm)
                        fit["optimizer_iterations_reported"] = fit.get("iterations")
                        attempt.update(status="complete", fit=fit)
                    except Exception as error:
                        attempt.update(status="failed", error=repr(error))
                    write(path, attempt)
                raw[name][arm] = attempt
                fallback, source = archive["stages"]["B7"][arm], "archived-B7"
                if rho and not operational["0.0"][arm]["fallback"]:
                    fallback, source = operational["0.0"][arm]["fit"], "rho0-control"
                operational[name][arm] = CONTROL["choose"](attempt, fallback, source)
        receipt.update(status="complete", raw=raw, operational=operational)
    except Exception as error:
        receipt.update(status="failed", error=repr(error))
    receipt["elapsed_s"] = time.monotonic() - begun
    write(destination, receipt)
    print(label, receipt["status"], flush=True)


def main(label):
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        assert os.environ.get(key) == "1", key
    path = HERE / "protocol.json"
    plan = json.loads(path.read_text())
    selected, ranks = select_members(plan["potential_members"], plan["selection_seed"])
    assert selected == plan["members"] and ranks == plan["selection_ranks"]
    assert plan["rhos"] == list(RHOS) and plan["maximum_seconds"] == 90
    assert plan["maximum_iterations"] == 600 and plan["stationarity_threshold"] == 0.001
    assert label in [b["member"]["inventory_label"] for b in selected]
    for name, expected in plan["source_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    evaluate(next(b for b in selected if b["member"]["inventory_label"] == label), digest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    main(parser.parse_args().label)
