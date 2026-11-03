"""Tight nuisance refits and finite-difference checks of a sampled local minimum."""

import argparse
import hashlib
import json
import time
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np

from leo.analysis.glrt_frequency_input import frequency_evidence
from leo.analysis.sparse_glrt_likelihood import SparseConfig, fit_sparse
from tools.evaluate_sparse_glrt import coordinates, local_output, prediction, write_json


def local_curvature(loss, step_km):
    """Gradient and Hessian from a symmetric 3x3 stencil in east/north km."""
    g = np.array([(loss[1, 0] - loss[-1, 0]), (loss[0, 1] - loss[0, -1])]) / (2 * step_km)
    cross = (loss[1, 1] - loss[1, -1] - loss[-1, 1] + loss[-1, -1]) / (4 * step_km**2)
    h = np.array(
        [
            [(loss[1, 0] - 2 * loss[0, 0] + loss[-1, 0]) / step_km**2, cross],
            [cross, (loss[0, 1] - 2 * loss[0, 0] + loss[0, -1]) / step_km**2],
        ]
    )
    return g, h


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=240.0)
    parser.add_argument("--step-m", type=float, default=250.0)
    args = parser.parse_args()
    local_output(args.output)
    args.output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    result = json.loads((args.run / "result.json").read_text())
    metadata = json.loads((args.bundle / "input-receipt.json").read_text())
    input_payload = (args.bundle / "tracking-input.json").read_bytes()
    input_digest = hashlib.sha256(input_payload).hexdigest()
    orbit_digest = hashlib.sha256((args.bundle / "orbit-bank.npz").read_bytes()).hexdigest()
    if (
        input_digest != metadata["input_sha256"]
        or input_digest != result["input_digest"]
        or orbit_digest != metadata["orbit_bank_sha256"]
        or orbit_digest != result["orbit_digest"]
    ):
        raise ValueError("minimum check inputs differ from the spatial replay")
    document = json.loads(input_payload)
    evidence, _, _ = frequency_evidence(document, uniform_marks=result["uniform_marks"])
    bank = dict(np.load(args.bundle / "orbit-bank.npz"))
    config = replace(SparseConfig(**result["config"]), iterations=20, em_iterations=100)
    # Give every location the same union of fitted starts, including the reference.
    seeds = [
        dict(offsets_hz=r["offsets_hz"], active=r["active"])
        for r in (result["best"], result["reference"])
    ]
    center = np.array([result["best"]["east_m"], result["best"]["north_m"]])
    rows = []
    output = dict(
        completed=False,
        step_m=args.step_m,
        seeds=seeds,
        config=asdict(config),
        input_digest=input_digest,
        orbit_digest=orbit_digest,
        source_digests={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (Path(__file__), Path("src/leo/analysis/sparse_glrt_likelihood.py"))
        },
        warning="Composite-score curvature is not calibrated position uncertainty.",
    )
    write_json(args.output / "protocol.json", output)

    def evaluate(point, kind):
        if time.monotonic() - started > args.seconds:
            raise TimeoutError("minimum-check budget exhausted")
        if np.linalg.norm(point) > 5000.0001:
            raise ValueError("finite-difference stencil leaves the declared 5 km disk")
        pred, visible = prediction(bank, evidence, metadata["site"], point)
        fit = fit_sparse(evidence, pred, visible, seeds, config)
        fit.update(
            east_m=float(point[0]),
            north_m=float(point[1]),
            distance_m=float(np.linalg.norm(point)),
            kind=kind,
            latitude_deg=coordinates(metadata["site"], *point)[0],
            longitude_deg=coordinates(metadata["site"], *point)[1],
            norad=[int(bank["norad"][i]) for i in fit["active"]],
            selected_visibility_sha256=hashlib.sha256(
                np.ascontiguousarray(visible[:, sorted(fit["active"])]).tobytes()
            ).hexdigest(),
        )
        rows.append(fit)
        with (args.output / "evaluations.jsonl").open("a") as f:
            f.write(json.dumps(fit) + "\n")
        print(
            json.dumps(dict(kind=kind, score=fit["score"], converged=fit["converged"])), flush=True
        )
        return fit

    try:
        reference = evaluate(np.zeros(2), "reference-tight")
        center_fit = evaluate(center, "center-tight")
        output.update(reference=reference, center=center_fit)
        if np.linalg.norm(center) + np.sqrt(2) * args.step_m > 5000:
            output["boundary_limited"] = True
        else:
            loss = {(0, 0): -center_fit["score"]}
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                fit = evaluate(center + args.step_m * np.array([dx, dy]), f"stencil-{dx}-{dy}")
                loss[dx, dy] = -fit["score"]
            gradient, hessian = local_curvature(loss, args.step_m / 1000)
            eigenvalues = np.linalg.eigvalsh(hessian)
            output.update(
                gradient_loss_per_km=gradient.tolist(),
                hessian_loss_per_km2=hessian.tolist(),
                eigenvalues_per_km2=eigenvalues.tolist(),
                stencil_same_satellite_set=all(
                    set(r["active"]) == set(center_fit["active"]) for r in rows[1:]
                ),
                all_stencil_fits_converged=all(r["converged"] for r in rows),
                selected_visibility_stable=all(
                    r["selected_visibility_sha256"] == center_fit["selected_visibility_sha256"]
                    for r in rows[1:]
                ),
            )
            output["curvature_interpretation"] = (
                "conditional finite-difference curvature; not calibrated uncertainty"
                if output["selected_visibility_stable"]
                else "stencil crosses horizon switches; this is not a smooth local Hessian"
            )
            if np.min(eigenvalues) > 0 and output["selected_visibility_stable"]:
                step = -1000 * np.linalg.solve(hessian, gradient)
                if np.linalg.norm(step) <= 500 and np.linalg.norm(center + step) <= 5000:
                    proposal = evaluate(center + step, "newton-check")
                    output["newton_step_m"] = step.tolist()
                    output["newton_improvement"] = proposal["score"] - center_fit["score"]
        output["completed"] = True
    except (TimeoutError, ValueError) as error:
        output["stop_reason"] = str(error)
    output.update(elapsed_seconds=time.monotonic() - started, evaluations=len(rows))
    if rows:
        output["best"] = max(rows, key=lambda r: r["score"])
    write_json(args.output / "result.json", output)


if __name__ == "__main__":
    main()
