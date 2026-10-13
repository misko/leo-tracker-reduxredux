"""Transport completed spatial incumbents to a common, declared search origin."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from leo.analysis.glrt_position_seed_transport import transport_bias_phase
from leo.analysis.glrt_residual_diagnostics import signal_candidate_residuals
from leo.analysis.wrapped_glrt_likelihood import WrappedConfig, nuisance_design
from tools.audit_wrapped_full_catalogue import common_seed, embed_incumbent
from tools.evaluate_sparse_glrt import local_output, write_json
from tools.evaluate_wrapped_fast_scan import load_bundle, load_phase_bank, phase_provider


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--surface", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    local_output(args.output)
    args.output.mkdir(parents=True, exist_ok=False)
    data, bank, meta, _ = load_bundle(args.bundle)
    result_path = args.surface / "result.json"
    result = json.loads(result_path.read_text())
    phases, receipt = load_phase_bank(args.bundle, bank)
    if (
        not result["completed"]
        or result["input_digest"] != meta["input_sha256"]
        or result["orbit_digest"] != meta["orbit_bank_sha256"]
        or result["phase_receipt"] != receipt
        or result["phase_model"] != "fixed-reception-frame-orbital-phase"
    ):
        raise ValueError("completed spatial profile on identical fixed-frame evidence required")
    cfg = WrappedConfig(**result["config"])
    if cfg.satellite_bias_sigma_hz is None or cfg.relative_phase_sigma_s is None:
        raise ValueError("joint additive source bias and relative phase required")
    origin = phase_provider(phases, bank, data, meta["site"], (0, 0), inertial_phase=True)
    seeds, states, pool = [], [], set(result["candidate_norad"])
    points = [result["reference"], result["best"]["zero-c"], result["best"]["fitted-c"]]
    distinct = {(row["east_m"], row["north_m"]): row for row in points}
    for point, row in distinct.items():
        source = phase_provider(phases, bank, data, meta["site"], point, inertial_phase=True)
        for arm in ("zero-c", "fitted-c"):
            fit = embed_incumbent(row["arms"][arm], result["candidate_norad"], bank["norad"])
            active = np.asarray(fit["active"], int)
            delta, bias = np.asarray(fit["satellite_phase_s"]), np.asarray(fit["satellite_bias_hz"])
            pred, opp, _, _ = source.predict(fit["phase_s"] + delta[active], active)
            design, _, _ = nuisance_design(
                data,
                bank["rf_hz"],
                coefficient=fit["coefficient_enabled"],
                band_drift=cfg.band_drift_sigma_hz_s is not None,
            )
            _, mass, _ = signal_candidate_residuals(
                data, pred + bias[active], opp, design, fit["beta"], cfg, fit["weights"]
            )
            target, _, timing, _ = origin.predict(fit["phase_s"] + delta[active], active)
            delta[active], bias[active], rms = transport_bias_phase(
                pred,
                target,
                timing,
                mass.sum(axis=1),
                delta[active],
                bias[active],
                scale_hz=cfg.scale_hz,
                phase_sigma_s=cfg.relative_phase_sigma_s,
                bias_sigma_hz=cfg.satellite_bias_sigma_hz,
            )
            seed = common_seed(fit)
            seed.update(satellite_phase_s=delta.tolist(), satellite_bias_hz=bias.tolist())
            seeds.append(seed)
            pool.update(fit["norad"])
            states.append(
                dict(
                    source_point=list(point),
                    source_arm=arm,
                    source_score=fit["score"],
                    satellites=fit["norad"],
                    linear_transport_rms_hz=rms.tolist(),
                )
            )
    write_json(
        args.output / "initialization.json",
        dict(
            input_digest=meta["input_sha256"],
            orbit_digest=meta["orbit_bank_sha256"],
            phase_receipt=receipt,
            source_point=[0, 0],
            selected_seeds=seeds,
            source_states=states,
            source_config=result["config"],
            source_surface_sha256=hashlib.sha256(result_path.read_bytes()).hexdigest(),
            scope=(
                "Score-selected incumbents moved to common origin; "
                "no position error selects states"
            ),
            source_digests={
                str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (
                    Path(__file__),
                    Path("src/leo/analysis/glrt_position_seed_transport.py"),
                    Path("src/leo/analysis/glrt_residual_diagnostics.py"),
                )
            },
        ),
    )
    write_json(
        args.output / "candidate-pool.json",
        dict(
            input_digest=meta["input_sha256"],
            orbit_digest=meta["orbit_bank_sha256"],
            norad=sorted(pool),
        ),
    )


if __name__ == "__main__":
    main()
