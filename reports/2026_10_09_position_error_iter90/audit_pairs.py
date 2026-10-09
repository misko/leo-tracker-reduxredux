"""Frozen-state paired receiver diagnostics; no position or nuisance optimizer."""

import argparse
import hashlib
import json
import runpy
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPORTS = HERE.parent
AUDIT = runpy.run_path(str(REPORTS / "2026_10_09_position_error_iter87/audit.py"))
sys.path.insert(0, str(REPORTS / "2026_10_09_position_error_iter88"))
from linear_contrast import (  # noqa: E402
    fit_projected_contrasts,
    projected_ridge,
    shrink_zero_sum_means,
)

sys.path.insert(0, str(HERE))
from paired_join import extract_pairs  # noqa: E402

ARMS = ("fitted-c", "zero-c")
CONTRAST_SIGMA_HZ = 30.0
WINDOW_SIGMA_HZ = float(AUDIT["HARD60_SCORE"].sigma_hz)
PAIR_VARIANCE_HZ2 = 2 * WINDOW_SIGMA_HZ**2


def json_value(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_value(item) for item in value]
    return value


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(json_value(value), stream, indent=2, allow_nan=False)
        stream.write("\n")


def smooth_sensitivity(joined, primary, weights):
    """Remove existing B7 smooth-clock span; add no new clock basis functions."""
    eligible = np.asarray(primary["eligible_satellite_ids"])
    if len(eligible) < 2:
        return dict(primary, sensitivity="existing B7 smooth-clock span", attempted=False)
    satellites = np.asarray(joined["satellite"])
    mask = np.isin(satellites, eligible)
    times = np.asarray(joined["time_s"])[mask]
    channels = np.asarray(joined["channel"])[mask]
    background = np.column_stack(
        [np.ones(mask.sum()), (times - primary["time_center_s"]) / primary["time_scale_s"]]
        + [(channels == item).astype(float) for item in np.unique(channels)[1:]]
    )
    smooth = np.asarray(joined["smooth_design"])[mask]
    background = np.column_stack([background, smooth])
    basis = np.linalg.svd(np.ones((1, len(eligible))), full_matrices=True)[2][1:].T
    design = basis[np.searchsorted(eligible, satellites[mask])]
    fitted = projected_ridge(
        np.asarray(joined["y_hz"])[mask], design, background, weights[mask], CONTRAST_SIGMA_HZ
    )
    result = dict(primary)
    result.update(fitted)
    result["contrasts_hz"] = np.zeros(len(primary["satellite_ids"]))
    result["contrasts_hz"][np.searchsorted(primary["satellite_ids"], eligible)] = (
        basis @ fitted["coefficients"]
    )
    result.update(
        sensitivity="existing B7 smooth-clock span",
        attempted=True,
        background_columns=primary["background_columns"]
        + [f"b7_smooth_clock_{i}" for i in range(smooth.shape[1])],
        weak_modes=basis @ fitted["weak_modes"],
        unsupported_zero=fitted["data_rank"] == 0,
        no_op=fitted["data_rank"] == 0,
    )
    return result


def diagnose_pairs(joined):
    values = np.asarray(joined["y_hz"])
    satellites = np.asarray(joined["satellite"])
    times = np.asarray(joined["time_s"])
    channels = np.asarray(joined["channel"])
    weights = np.full(len(values), 1 / PAIR_VARIANCE_HZ2)
    projected = fit_projected_contrasts(
        values,
        satellites,
        times,
        channels,
        sigma_hz=CONTRAST_SIGMA_HZ,
        weights=weights,
    )
    means = shrink_zero_sum_means(
        values,
        satellites,
        sigma_hz=CONTRAST_SIGMA_HZ,
        weights=weights,
    )
    return dict(
        pair_count=len(values),
        raw_pair_mean_hz=float(values.mean()) if len(values) else None,
        raw_pair_rms_hz=float(np.sqrt(np.mean(values**2))) if len(values) else None,
        unadjusted_shrinkage=means,
        background_projected=projected,
        smooth_clock_projected=smooth_sensitivity(joined, projected, weights),
        paired_rows=joined["pairs"],
        paired_smooth_clock_design=joined["smooth_design"],
    )


def evaluate(binding, digest):
    member = binding["member"]
    destination = HERE / "results" / f"{member['inventory_label']}.json"
    if destination.exists():
        assert json.loads(destination.read_text())["protocol_sha256"] == digest
        return
    started = time.monotonic()
    receipt = dict(
        member=member,
        loader_kind=binding["loader_binding"]["kind"],
        protocol_sha256=digest,
        source_result=binding["b7_source"],
        objective_checks={},
    )
    try:
        archived = AUDIT["read"](ROOT / binding["b7_source"])
        assert archived["status"] == "complete" and archived["member"] == member
        model = AUDIT["reconstruct"](binding, archived)
        evaluated = {}
        for arm in ARMS:
            row = archived["stages"]["B7"][arm]
            assert row["stage"] == "B7" and row["converged"]
            vector, clock = np.asarray(row["vector"]), np.asarray(row["clock_coefficients"])
            if arm == "zero-c":
                assert vector[6] == 0 and np.all(clock[-2:] == 0)
            objective, _, _, terms = model.evaluate_joint(vector, clock)
            receipt["objective_checks"][arm] = dict(
                stored=float(row["objective"]),
                reconstructed=float(objective),
                delta=float(objective - row["objective"]),
            )
            np.testing.assert_allclose(objective, row["objective"], atol=1e-6, rtol=0)
            evaluated[arm] = terms
        fitted = evaluated["fitted-c"]
        indices = fitted.responsibilities.argmax(axis=1)
        probability = fitted.responsibilities[np.arange(len(indices)), indices]
        numbers = np.where(probability > 0.5, model.bank.numbers[indices], 0)
        arms = {}
        for arm in ARMS:
            residuals = evaluated[arm].residual_hz[np.arange(len(indices)), indices]
            joined = extract_pairs(
                model.observations,
                numbers,
                residuals,
                assignment_probability=probability,
                smooth_clock_design=model.clock_design[:, : model.smooth_clock_count],
            )
            arms[arm] = diagnose_pairs(joined)
        keys = ("satellite", "channel", "tick_ms", "rx0_count", "rx1_count")
        assert [tuple(row[key] for key in keys) for row in arms["fitted-c"]["paired_rows"]] == [
            tuple(row[key] for key in keys) for row in arms["zero-c"]["paired_rows"]
        ]
        receipt.update(
            status="complete",
            arms=arms,
            observation_count=len(indices),
            assigned_count=int(np.sum(numbers > 0)),
            unassigned_count=int(np.sum(numbers == 0)),
            sigma_hz=CONTRAST_SIGMA_HZ,
            pair_variance_hz2=PAIR_VARIANCE_HZ2,
            shared_assignment_policy="Fitted B7 maximum responsibility strictly above0.5",
        )
    except Exception as error:
        receipt.update(status="failed", error=repr(error))
    receipt["elapsed_s"] = time.monotonic() - started
    write(destination, receipt)
    print(member["inventory_label"], receipt["status"], flush=True)


def main(shard):
    path = HERE / "protocol.json"
    plan = json.loads(path.read_text())
    assert 0 <= shard < plan["shards"]
    for name, expected in plan["source_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    assert plan["window_sigma_hz"] == WINDOW_SIGMA_HZ
    assert plan["contrast_sigma_hz"] == CONTRAST_SIGMA_HZ
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    for ordinal, binding in enumerate(plan["members"]):
        if ordinal % plan["shards"] == shard:
            evaluate(binding, digest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard", type=int, required=True)
    main(parser.parse_args().shard)
