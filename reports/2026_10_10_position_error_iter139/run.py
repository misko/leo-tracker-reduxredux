"""Exact138 pair reuse and two saved endpoint calls; no optimizer or truth port."""

import importlib.util
import json
from pathlib import Path

import numpy as np
from core import diagnostic

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PREVIOUS = HERE.parent / "2026_10_10_position_error_iter138"
spec = importlib.util.spec_from_file_location("isolated138_for139", PREVIOUS / "run.py")
wrapper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wrapper)
implementation = wrapper.implementation
implementation.HERE = HERE
sha = implementation.sha


def analyze(model, archive, predecessor):
    ids = list(model.observations.window_ids)
    if ids != [r["window_id"] for r in predecessor["support"]["rows"]]:
        raise ValueError("original observation order differs")
    if float(model.score.sigma_hz) != 125:
        raise ValueError("fixed frequency scale differs")
    arms = {}
    pair_keys = None
    for arm in ("fitted-c", "zero-c"):
        endpoint = archive["stages"]["B7"][arm]
        value, _, _, terms = model.evaluate_joint(
            np.asarray(endpoint["vector"]).copy(), np.asarray(endpoint["clock_coefficients"]).copy()
        )
        if not np.isfinite(value) or abs(value - endpoint["objective"]) > 1e-6:
            raise ValueError("saved objective mismatch")
        original = predecessor["arms"][arm]
        details = original["pair_details"]
        keys = [
            (d["first_window_id"], d["second_window_id"], d["group"], d["alternating_block"])
            for d in details
        ]
        if pair_keys is not None and pair_keys != keys:
            raise ValueError("both c arms must share exact pairs")
        pair_keys = keys
        lookup = {name: i for i, name in enumerate(ids)}
        for row in details:
            i, j = lookup[row["first_window_id"]], lookup[row["second_window_id"]]
            w = terms.responsibilities[i] * terms.responsibilities[j]
            product = float(np.sum(w * terms.residual_hz[i] * terms.residual_hz[j] / 125**2))
            mass = float(w.sum())
            if abs(product - row["score"]) > 1e-10 or abs(mass - row["shared_label_mass"]) > 1e-12:
                raise ValueError("138 individual pair score/mass parity failed")
        result = diagnostic(
            terms.responsibilities, terms.residual_hz / 125, details, ids, model.bank.numbers
        )
        if not np.isclose(
            result["weighted_product_sum"], original["score_sum"], rtol=1e-12, atol=1e-10
        ):
            raise ValueError("138 aggregate score parity failed")
        result["archive_objective_delta"] = float(value - endpoint["objective"])
        result["frequency_nll"] = float(terms.nll)
        arms[arm] = result
    return dict(
        status="complete",
        arms=arms,
        observations=len(ids),
        support=predecessor["support"],
        pairing=predecessor["pairing"],
        optimizer_calls=0,
        position_evaluation=False,
    )


def perform(plan, binding):
    predecessor = None
    try:
        predecessor = json.loads((ROOT / binding["predecessor_receipt"]).read_text())
        if (
            predecessor["status"] != "complete"
            or predecessor["label"] != binding["label"]
            or predecessor["protocol_sha256"] != plan["predecessor_protocol_sha256"]
        ):
            raise ValueError("foreign or failed predecessor")
        model, projection, _ = implementation.reconstruct(plan, binding)
        return analyze(model, projection["archive"], predecessor)
    except Exception as error:
        return dict(
            status="failed",
            error=repr(error),
            optimizer_calls=0,
            position_evaluation=False,
            support=predecessor.get("support") if predecessor else None,
        )


implementation.perform = perform


def main():
    implementation.main()


if __name__ == "__main__":
    main()
