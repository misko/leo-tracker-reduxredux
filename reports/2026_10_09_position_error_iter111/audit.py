"""Prepared bounded saved-endpoint audit; no optimization or reference evaluation."""

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
ARMS = ("fitted-c", "zero-c")
DESIGN_BUDGET_BYTES = 512 * 1024**2
QR_CHUNK_ROWS = 4096


def check_threads(environment):
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        if environment.get(name) != "1":
            raise ValueError(f"{name}=1 required before recording reconstruction")


def selected_members(plan, pilot):
    assert plan["members"] == pilot["members"]
    assert plan["potential_members"] == pilot["potential_members"]
    assert len(plan["potential_members"]) == 148 and len(plan["members"]) == 12
    assert all(b in plan["potential_members"] for b in plan["members"])
    return plan["members"]


def design_budget(model):
    n, k = len(model.observations.times_s), len(model.bank.numbers)
    p = model.size + len(model.initial_clock)
    # Main full Jacobian; residualized and weighted diagnostic copies coexist.
    estimate = 8 * n * k * (3 * p + 16) + 8 * (QR_CHUNK_ROWS * p * 4 + p * p * 8)
    if estimate > DESIGN_BUDGET_BYTES:
        raise MemoryError(
            f"Conditional design shape N={n},K={k},P={p}; estimated workspace "
            f"{estimate} bytes exceeds512MiB budget"
        )
    return dict(
        observations=n,
        satellites=k,
        parameters=p,
        full_design_bytes=8 * n * k * p,
        conservative_workspace_bytes=estimate,
        design_budget_bytes=DESIGN_BUDGET_BYTES,
    )


def audit_model(model, archive, *, adapter=None, observability=None, mixture=None):
    adapter = adapter or runpy.run_path(str(HERE / "adapter.py"))["construct"]
    observability = (
        observability or runpy.run_path(str(HERE / "observability.py"))["streamed_diagnose"]
    )
    mixture = mixture or runpy.run_path(str(HERE / "mixture_curvature.py"))["curvature"]
    shape = design_budget(model)  # Before any N*K*P allocation.
    arms = {}
    for arm in ARMS:
        endpoint = archive["stages"]["B7"][arm]
        assert endpoint["stage"] == "B7"
        design = adapter(model, endpoint, arm)
        data = observability(
            design["spatial"],
            design["nuisance"],
            design["weights"],
            chunk_rows=QR_CHUNK_ROWS,
        )
        _, _, _, terms = model.evaluate_joint(
            np.asarray(endpoint["vector"]), np.asarray(endpoint["clock_coefficients"])
        )
        spatial = mixture(
            design["full_jacobian"][:, :, :2],
            terms.residual_hz,
            terms.responsibilities,
            model.score.sigma_hz,
        )
        arms[arm] = dict(
            objective_delta=design["objective_delta"],
            data_only=data,
            spatial_blocks=spatial,
            spatial_block_eigenvalues={
                key: np.linalg.eigvalsh(value) for key, value in spatial.items()
            },
            prior_information_separate=design["prior_information_separate"],
            nuisance_parameter_indices=design["nuisance_parameter_indices"],
            locked_parameter_indices=design["locked_parameter_indices"],
            physical_parameter_scales=design["model_parameter_scales"],
            bounds_omitted=True,
            observed_schur_complement=None,
            scope="Nuisance-relaxed conditional complete-label PSD proxy; "
            "observed spatial block fixes nuisance and uses local affine mixture curvature; "
            "nonlinear prediction second derivatives omitted; no inverse/covariance claim",
        )
        del design, terms
    return dict(shape=shape, arms=arms)


def serial(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, dict):
        return {k: serial(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serial(v) for v in value]
    return value


def evaluate(binding, digest, *, reconstruct=None, read=None, directory=None):
    directory = HERE / "results" if directory is None else Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (binding["member"]["inventory_label"] + ".json")
    if path.exists():
        old = json.loads(path.read_text())
        assert old["member"] == binding["member"] and old["protocol_sha256"] == digest
        return old
    begun = time.monotonic()
    result = dict(
        member=binding["member"],
        protocol_sha256=digest,
        source=binding["b7_source"],
        status="failed",
    )
    try:
        if reconstruct is None:
            previous = HERE.parent / "2026_10_09_position_error_iter108"
            sys.path.insert(0, str(previous))
            reconstruction = runpy.run_path(str(previous / "audit.py"))
            reconstruct = reconstruction["reconstruct"]
        read = read or (lambda p: json.loads(p.read_text()))
        archive_path = ROOT / binding["b7_source"]
        archive = read(archive_path)
        assert archive["member"] == binding["member"] and archive["status"] == "complete"
        model, _ = reconstruct(binding, archive)
        result.update(
            audit_model(model, archive),
            status="complete",
            source_sha256=hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        )
    except Exception as error:
        result["error"] = repr(error)
    result["elapsed_s"] = time.monotonic() - begun
    with path.open("x") as stream:
        json.dump(serial(result), stream, indent=2, allow_nan=False)
        stream.write("\n")
    return result


def main():
    check_threads(os.environ)
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard", type=int, choices=(0, 1), required=True)
    args = parser.parse_args()
    protocol = HERE / "protocol.json"
    plan = json.loads(protocol.read_text())
    assert plan["optimizer_calls"] == 0 and plan["threads_per_worker"] == 1
    assert plan["shards"] == 2 and plan["design_budget_bytes"] == DESIGN_BUDGET_BYTES
    assert plan["svd_rtol"] is None
    assert plan["qr_chunk_rows"] == QR_CHUNK_ROWS
    for name, expected in plan["frozen_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    pilot = json.loads(
        (HERE.parent / "2026_10_09_position_error_iter110/protocol.json").read_text()
    )
    assert (
        plan["pilot_protocol_sha256"]
        == hashlib.sha256(
            (HERE.parent / "2026_10_09_position_error_iter110/protocol.json").read_bytes()
        ).hexdigest()
    )
    digest = hashlib.sha256(protocol.read_bytes()).hexdigest()
    for binding in selected_members(plan, pilot)[args.shard :: 2]:
        receipt = evaluate(binding, digest)
        print(binding["member"]["inventory_label"], receipt["status"], flush=True)


if __name__ == "__main__":
    main()
