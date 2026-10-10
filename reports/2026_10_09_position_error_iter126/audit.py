"""Fixed endpoint frame-convention audit; no optimizer/reference evaluation."""

import argparse
import hashlib
import json
import os
import runpy
import time
from pathlib import Path

import numpy as np

from leo.analysis.hard60_score import likelihood, predict_orbits
from leo.analysis.regional_position_score import observer

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def audit_model(model, archive):
    began = time.monotonic()
    estimated = 8 * len(model.observations.times_s) * len(model.bank.numbers) * 40
    if estimated > 512 * 1024**2:
        raise MemoryError("Fixed512MiB estimated array budget exceeded")
    phase = runpy.run_path(str(HERE / "phase.py"))
    arms = {}
    for arm in ("fitted-c", "zero-c"):
        if time.monotonic() - began > 500:
            raise TimeoutError("500s soft post-reconstruction audit budget exceeded")
        endpoint = archive["stages"]["B7"][arm]
        vector = np.asarray(endpoint["vector"])
        clock = np.asarray(endpoint["clock_coefficients"])
        score, _, _, original = model.evaluate_joint(vector, clock)
        assert abs(score - endpoint["objective"]) <= 1e-6
        relative = model.basis @ vector[8:]
        query = model.observations.times_s[:, None] + vector[7] + relative[None, :]
        nodes = model.bank.nodes_s
        assert np.all((query >= nodes[0]) & (query <= nodes[-1]))
        index = np.minimum(np.searchsorted(nodes, query, side="right") - 1, len(nodes) - 2)
        sat = np.arange(len(relative))[None, :]
        dt = nodes[index + 1] - nodes[index]
        fraction = (query - nodes[index]) / dt
        states = []
        for array in (model.bank.position_km, model.bank.velocity_km_s):
            left, right = array[sat, index], array[sat, index + 1]
            states.append(
                phase["transformed"](
                    left + fraction[..., None] * (right - left),
                    (right - left) / dt[..., None],
                    relative,
                )
            )
        (p, pc, pr), (v, vc, vr) = states
        site, up = observer(model.prior, vector[:2])
        delta = p - site
        distance = np.linalg.norm(delta, axis=-1)
        direction = delta / distance[..., None]
        radial = np.sum(direction * v, axis=-1)
        factor = model.observations.rf_hz[:, None] / 299792.458
        prediction = -factor * radial

        def timing(
            dp, dv, factor=factor, v=v, radial=radial, direction=direction, distance=distance
        ):
            return -factor * (
                np.sum((v - radial[..., None] * direction) * dp, axis=-1) / distance
                + np.sum(direction * dv, axis=-1)
            )

        common_timing, relative_timing = timing(pc, vc), timing(pr, vr)
        visible = np.sum(direction * up, axis=-1) >= 0
        oldprediction, oldvisible, _, _ = predict_orbits(
            model.bank,
            model.observations,
            model.prior,
            vector[:2],
            vector[7] + relative,
            derivatives=False,
        )
        if np.all(relative == 0):
            np.testing.assert_allclose(prediction, oldprediction, atol=1e-8, rtol=0)
            np.testing.assert_array_equal(visible, oldvisible)
        correction = (model.design @ vector[2:7] + model.baseline + model.clock_design @ clock)[
            :, None
        ]
        offsets, slopes = model.physical_corrections(clock)
        correction = correction + offsets[None, :] + model.delta_time * (100 * slopes)[None, :]
        alternative = likelihood(
            model.observations.measured_hz, prediction + correction, visible, model.score
        )

        count = len(relative)

        def normalizer(mask, count=count):
            lp = -model.score.clutter_rate + mask.sum(axis=1) * np.log1p(
                -model.score.detection_budget / count
            )
            return float(np.sum(-lp + np.log(-np.expm1(lp))))

        arms[arm] = {
            "original_score_parity_delta": float(score - endpoint["objective"]),
            "nll_delta": float(alternative.nll - original.nll),
            "normalizer_delta": normalizer(visible) - normalizer(oldvisible),
            "visibility_changed": int(np.sum(visible != oldvisible)),
            "prediction_delta_rms_hz": float(np.sqrt(np.mean((prediction - oldprediction) ** 2))),
            "common_gradient_data": float(np.sum(alternative.prediction_gradient * common_timing)),
            "relative_gradient_data": np.sum(
                alternative.prediction_gradient * relative_timing, axis=0
            ).tolist(),
            "observations": len(query),
            "satellites": len(relative),
            "scope": (
                "Unchanged endpoints; priors cancel; alternative frame model, no accuracy claim"
            ),
        }
    return {"arms": arms, "estimated_array_bytes": estimated}


def main():
    assert all(
        os.environ.get(k) == "1"
        for k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard", required=True, type=int, choices=(0, 1))
    args = parser.parse_args()
    plan = json.loads((HERE / "protocol.json").read_text())
    for path, digest in plan["frozen_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
    api = runpy.run_path(str(HERE.parent / "2026_10_09_position_error_iter117/audit.py"))
    api["evaluate"].__globals__["audit_model"] = audit_model
    digest = hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest()
    for binding in plan["members"][args.shard :: 2]:
        api["evaluate"](binding, digest, directory=HERE / "results")


if __name__ == "__main__":
    main()
