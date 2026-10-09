"""Frozen matched slope-prior sensitivity; run only after experiment71 terminates."""

import argparse
import hashlib
import sys
from pathlib import Path

import numpy as np
from sensitivity_policy import accepted, regional_path, source_stage

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_09_position_error_iter51"))
from cohort_inputs import load, read  # noqa: E402

sys.path.insert(0, str(REPORTS / "2026_10_08_position_error_iter28"))
from extension import (  # noqa: E402
    HARD60_SCORE,
    Hard60Objective,
    SlopePrior,
    arm_selected,
    error_km,
    fit,
    json_value,
)

ARMS = ("fitted-c", "zero-c")


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    import json

    path.write_text(json.dumps(value, indent=2) + "\n")


def evaluate(binding, plan, digest):
    label = binding["member"]["inventory_label"]
    destination = HERE / "results" / f"{label}.json"
    if destination.exists():
        assert read(destination)["protocol_sha256"] == digest
        return
    result = read(ROOT / binding["result_source"])
    try:
        case, baseline, _ = load(binding["loader_binding"])
        path = regional_path(result, ROOT / binding["result_source"], ROOT)
        document = read(path) if path is not None else baseline
        upstream, extension = result["upstream"], result["extension"]
        if upstream["stopped"] is not None:
            write(
                destination,
                dict(
                    status="upstream_stopped",
                    member=binding["member"],
                    operational={str(s): extension["operational"] for s in plan["sigmas"]},
                    reason=upstream["stopped"],
                    protocol_sha256=digest,
                ),
            )
            return
        source = source_stage(upstream)
        assert source == extension["source_stage"]
        chosen = upstream["stages"][source]["fitted-c"]
        clock = np.asarray(chosen["clock_coefficients"])
        if source != "drift-50":
            clock = np.r_[clock, 0.0, 0.0]
        seed = np.asarray(chosen["vector"])
        selected = arm_selected(document, "fitted-c")
        calibration = document["diagnostics"]["calibrations"][selected["source_basin"]]
        correction = calibration["correction"]
        lookup = {int(n): i for i, n in enumerate(case.bank.numbers)}
        base = Hard60Objective(
            case.prepared.observations,
            case.bank.select([lookup[n] for n in extension["satellites"]]),
            case.prior,
            HARD60_SCORE,
            receiver_baseline_hz=np.asarray(calibration["receiver_baseline_hz"]),
        )

        def model(sigma):
            return SlopePrior(
                base, correction["nodes_s"], correction["knots_hz"], extension["centers_s"], sigma
            )

        control = model(0.25)
        for arm in ARMS:
            old = extension["stages"]["slope-0.25"][arm]
            objective = control.evaluate_joint(
                np.asarray(old["vector"]), np.asarray(old["clock_coefficients"])
            )[0]
            np.testing.assert_allclose(objective, old["objective"], rtol=0, atol=1e-6)
        raw, operational = {}, {}
        for sigma in plan["sigmas"]:
            current = model(sigma)
            raw[str(sigma)], operational[str(sigma)] = {}, {}
            for arm in ARMS:
                receipt = HERE / "attempts" / label / f"{sigma}-{arm}.json"
                if receipt.exists():
                    stored = read(receipt)
                    assert stored["protocol_sha256"] == digest
                    row = stored["fit"]
                else:
                    row = json_value(
                        fit(
                            current,
                            seed.copy(),
                            arm=arm,
                            clock_seed=current.expand_clock(clock),
                            maximum_seconds=90,
                            maximum_iterations=600,
                        )
                    )
                    if arm == "zero-c":
                        assert row["vector"][6] == 0
                        assert row["rf_drift_coefficients"] == [0, 0]
                    row.update(
                        stage=f"slope-{sigma}",
                        arm=arm,
                        error_km=error_km(case.prior, row["vector"], document),
                    )
                    write(receipt, dict(protocol_sha256=digest, fit=row))
                raw[str(sigma)][arm] = row
                operational[str(sigma)][arm] = accepted(row, extension["control_operational"][arm])
        write(
            destination,
            dict(
                status="complete",
                member=binding["member"],
                raw=raw,
                operational=operational,
                source_stage=source,
                protocol_sha256=digest,
            ),
        )
    except Exception as error:
        write(
            destination,
            dict(
                status="failed", member=binding["member"], error=repr(error), protocol_sha256=digest
            ),
        )
    print(label, read(destination)["status"], flush=True)


def main(shard):
    plan = read(HERE / "protocol.json")
    assert 0 <= shard < plan["shards"]
    for path, expected in plan["source_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, path
    digest = hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest()
    for ordinal, binding in enumerate(plan["members"]):
        if ordinal % plan["shards"] == shard:
            evaluate(binding, plan, digest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard", type=int, required=True)
    main(parser.parse_args().shard)
