"""Matched full148 fixed geometry-prior prototype; no per-scan truth choices."""

import argparse
import functools
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from model import PositionProtectedSlope, SlopePrior

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_09_position_error_iter78"))
from sensitivity_policy import regional_path, source_stage  # noqa: E402

sys.path.insert(0, str(REPORTS / "2026_10_09_position_error_iter51"))
from cohort_inputs import load, read  # noqa: E402

sys.path.insert(0, str(REPORTS / "2026_10_09_position_error_iter82"))
from protocol_loader import verified_protocol  # noqa: E402

sys.path.insert(0, str(REPORTS / "2026_10_08_position_error_iter28"))
from extension import (  # noqa: E402
    HARD60_SCORE,
    Hard60Objective,
    arm_selected,
    error_km,
    fit,
    json_value,
)

baseline_module = sys.modules["baseline"]
assert Path(baseline_module.__file__).resolve() == (
    REPORTS / "2026_10_08_position_error_iter01/baseline.py"
)
baseline_module.protocol = functools.partial(verified_protocol, baseline_module.HERE)
ARMS = ("fitted-c", "zero-c")


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    assert not path.exists(), f"Preserve immutable receipt: {path}"
    path.write_text(json.dumps(value, indent=2) + "\n")


def evaluate(binding, digest):
    member = binding["member"]
    label = member["inventory_label"]
    destination = HERE / "results" / f"{label}.json"
    if destination.exists():
        assert read(destination)["protocol_sha256"] == digest
        return
    archived = read(ROOT / binding["control_source"])
    assert archived["status"] == "complete" and archived["member"] == member
    fallback = archived["operational"]["0.5"]
    try:
        result_path = ROOT / binding["result_source"]
        result = read(result_path)
        case, baseline, _ = load(binding["loader_binding"])
        path = regional_path(result, result_path, ROOT)
        document = read(path) if path is not None else baseline
        upstream, extension = result["upstream"], result["extension"]
        assert upstream["stopped"] is None
        source = source_stage(upstream)
        assert source == extension["source_stage"]
        chosen = upstream["stages"][source]["fitted-c"]
        seed = np.asarray(chosen["vector"])
        clock = np.asarray(chosen["clock_coefficients"])
        if source != "drift-50":
            clock = np.r_[clock, 0., 0.]
        selected = arm_selected(document, "fitted-c")
        cal = document["diagnostics"]["calibrations"][selected["source_basin"]]
        correction = cal["correction"]
        lookup = {int(n): i for i, n in enumerate(case.bank.numbers)}
        base = Hard60Objective(
            case.prepared.observations,
            case.bank.select([lookup[n] for n in extension["satellites"]]),
            case.prior, HARD60_SCORE,
            receiver_baseline_hz=np.asarray(cal["receiver_baseline_hz"]),
        )
        parameters = base, correction["nodes_s"], correction["knots_hz"], extension["centers_s"]
        original = SlopePrior(*parameters, 0.5)
        shared_clock = original.expand_clock(clock)
        models = {
            "uniform0.5": PositionProtectedSlope(
                *parameters, seed, shared_clock, protected_sigma=0.5),
            "protected0.25": PositionProtectedSlope(
                *parameters, seed, shared_clock, protected_sigma=0.25),
        }
        for arm in ARMS:
            old = archived["raw"]["0.5"][arm]
            vector, coefficients = np.asarray(old["vector"]), np.asarray(old["clock_coefficients"])
            expected = original.evaluate_joint(vector, coefficients)
            actual = models["uniform0.5"].evaluate_joint(vector, coefficients)
            np.testing.assert_allclose(actual[0], old["objective"], rtol=0, atol=1e-6)
            for index in range(3):
                np.testing.assert_allclose(actual[index], expected[index], rtol=0, atol=1e-10)
        raw, operational = {}, {}
        for variant, model in models.items():
            raw[variant], operational[variant] = {}, {}
            for arm in ARMS:
                path = HERE / "attempts" / label / f"{variant}-{arm}.json"
                if path.exists():
                    stored = read(path)
                    assert stored["protocol_sha256"] == digest
                    row = stored["fit"]
                else:
                    row = json_value(fit(model, seed.copy(), arm=arm,
                                         clock_seed=shared_clock.copy(), maximum_seconds=90,
                                         maximum_iterations=600))
                    if arm == "zero-c":
                        assert row["vector"][6] == 0 and row["rf_drift_coefficients"] == [0, 0]
                    row.update(stage=variant, arm=arm,
                               error_km=error_km(case.prior, row["vector"], document))
                    write(path, dict(protocol_sha256=digest, fit=row))
                raw[variant][arm] = row
                operational[variant][arm] = row if row["converged"] else fallback[arm]
        write(destination, dict(
            status="complete", member=member, protocol_sha256=digest,
            raw=raw, operational=operational, archived_control=fallback,
            geometry=models["protected0.25"].geometry_diagnostics,
        ))
    except Exception as error:
        write(destination, dict(status="failed", member=member, protocol_sha256=digest,
                                error=repr(error), archived_control=fallback))
    print(label, read(destination)["status"], flush=True)


def main(shard):
    plan = read(HERE / "protocol.json")
    assert 0 <= shard < plan["shards"]
    for name, expected in plan["source_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    digest = hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest()
    for ordinal, binding in enumerate(plan["members"]):
        if ordinal % plan["shards"] == shard:
            evaluate(binding, digest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard", type=int, required=True)
    main(parser.parse_args().shard)
