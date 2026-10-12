"""Reopen all prepared satellites while retaining each known feasible endpoint."""

import argparse
import hashlib
import json
import time
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np

from leo.analysis.wrapped_glrt_likelihood import WrappedConfig, fit_wrapped
from tools.evaluate_sparse_glrt import local_output, write_json
from tools.evaluate_wrapped_fast_scan import (
    load_bundle,
    load_phase_bank,
    phase_provider,
    predictions,
    retain_nested_zero_fit,
)
from tools.report_wrapped_physical_diagnostics import replay_endpoint


def embed_incumbent(fit, candidate_norad, full_norad):
    """Embed a conditional subset into the identical, larger identity universe."""
    lookup = {int(n): i for i, n in enumerate(full_norad)}
    if len(lookup) != len(full_norad) or len(set(candidate_norad)) != len(candidate_norad):
        raise ValueError("distinct physical satellite identities required")
    if any(int(n) not in lookup for n in candidate_norad):
        raise ValueError("conditional identity is absent from the full catalogue")
    pool = np.asarray([lookup[int(n)] for n in candidate_norad])
    active = np.asarray(fit["active"], dtype=int)
    if np.any(active < 0) or np.any(active >= len(pool)):
        raise ValueError("invalid conditional active indices")
    full_active = pool[active]
    if [int(full_norad[i]) for i in full_active] != fit["norad"]:
        raise ValueError("conditional active identities changed")
    if full_active.tolist() != fit["full_catalogue_indices"]:
        raise ValueError("conditional full-catalogue mapping changed")
    delta = np.asarray(fit["satellite_phase_s"], dtype=float)
    if delta.shape != pool.shape:
        raise ValueError("conditional phase dimension mismatch")
    expanded = np.zeros(len(full_norad))
    expanded[pool] = delta
    expanded_bias = None
    if fit.get("satellite_bias_hz") is not None:
        bias = np.asarray(fit["satellite_bias_hz"])
        if bias.shape != pool.shape:
            raise ValueError("conditional bias dimension mismatch")
        expanded_bias = np.zeros(len(full_norad))
        expanded_bias[pool] = bias
        expanded_bias = expanded_bias.tolist()
    return dict(
        fit,
        active=full_active.tolist(),
        satellite_phase_s=expanded.tolist(),
        satellite_bias_hz=expanded_bias,
    )


def common_seed(fit):
    return dict(
        beta=fit["beta"][:-1] if fit["coefficient_enabled"] else fit["beta"],
        coefficient_hz_ghz=fit["coefficient_hz_ghz"],
        active=fit["active"],
        weights=fit["weights"],
        phase_s=fit["phase_s"],
        satellite_phase_s=fit["satellite_phase_s"],
        satellite_bias_hz=fit.get("satellite_bias_hz"),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--surface", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--point", choices=("reference", "zero-c", "fitted-c"), required=True)
    p.add_argument("--iterations", type=int, default=3)
    p.add_argument("--nuisance-iterations", type=int, default=20)
    args = p.parse_args()
    local_output(args.output)
    args.output.mkdir(parents=True, exist_ok=False)
    data, bank, meta, _ = load_bundle(args.bundle)
    source = json.loads((args.surface / "result.json").read_text())
    if (
        not source["completed"]
        or source["input_digest"] != meta["input_sha256"]
        or source["orbit_digest"] != meta["orbit_bank_sha256"]
    ):
        raise ValueError("completed surface bound to the identical recording required")
    row = source["reference"] if args.point == "reference" else source["best"][args.point]
    point = (row["east_m"], row["north_m"])
    phase_bank, receipt = load_phase_bank(args.bundle, bank)
    if receipt != source["phase_receipt"]:
        raise ValueError("phase-bank provenance changed")
    provider = phase_provider(
        phase_bank,
        bank,
        data,
        meta["site"],
        point,
        inertial_phase=source["phase_model"] == "fixed-reception-frame-orbital-phase",
    )
    prediction, opportunity = predictions(bank, meta["site"], point)
    cfg = replace(
        WrappedConfig(**source["config"]),
        iterations=args.iterations,
        nuisance_iterations=args.nuisance_iterations,
    )
    known = {
        arm: embed_incumbent(fit, source["candidate_norad"], bank["norad"])
        for arm, fit in row["arms"].items()
    }
    for fit in known.values():
        active = np.asarray(fit["active"], dtype=int)
        delta = np.asarray(fit["satellite_phase_s"])[active]
        pred, opp, _, _ = provider.predict(fit["phase_s"] + delta, active)
        replay_endpoint(data, bank["rf_hz"], pred, opp, fit, cfg)
    seeds = [common_seed(known[a]) for a in ("zero-c", "fitted-c")]
    protocol = dict(
        input_digest=source["input_digest"],
        orbit_digest=source["orbit_digest"],
        phase_receipt=receipt,
        phase_model=source["phase_model"],
        config=asdict(cfg),
        point=dict(east_m=point[0], north_m=point[1], distance_m=row["distance_m"]),
        candidate_norad=bank["norad"].tolist(),
        seeds=seeds,
        source_surface_sha256=hashlib.sha256(
            (args.surface / "result.json").read_bytes()
        ).hexdigest(),
        source_digests={
            str(path): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (
                Path(__file__),
                Path("src/leo/analysis/wrapped_glrt_likelihood.py"),
                Path("src/leo/analysis/sparse_glrt_likelihood.py"),
                Path("src/leo/analysis/glrt_orbit_phase.py"),
            )
        },
        scope="Full prepared catalogue audit; local subset heuristic, no global certificate",
        ablation="Identical observations, catalogue, non-RF starts, priors and iteration budgets",
    )
    write_json(args.output / "protocol.json", protocol)
    started, arms = time.monotonic(), {}
    for arm in ("zero-c", "fitted-c"):
        enabled = arm == "fitted-c"
        starts = [
            dict(seed, beta=seed["beta"] + ([seed["coefficient_hz_ghz"]] if enabled else []))
            for seed in seeds
        ]
        trial = fit_wrapped(
            data,
            prediction,
            opportunity,
            bank["rf_hz"],
            starts,
            coefficient=enabled,
            config=cfg,
            orbit_provider=provider,
        )
        fit = (
            trial
            if trial["score"] >= known[arm]["score"]
            else dict(
                known[arm],
                converged=False,
                retained_known_incumbent=True,
                attempted_full_fit_score=trial["score"],
            )
        )
        if enabled:
            fit = retain_nested_zero_fit(fit, arms["zero-c"])
        fit["norad"] = [int(bank["norad"][i]) for i in fit["active"]]
        fit["full_catalogue_indices"] = fit["active"]
        active = np.asarray(fit["active"], dtype=int)
        pred, opp, _, _ = provider.predict(
            fit["phase_s"] + np.asarray(fit["satellite_phase_s"])[active],
            active,
        )
        replay_endpoint(data, bank["rf_hz"], pred, opp, fit, cfg)
        fit["known_conditional_score"] = known[arm]["score"]
        arms[arm] = fit
        write_json(
            args.output / "result.json",
            dict(
                protocol, completed=enabled, elapsed_seconds=time.monotonic() - started, arms=arms
            ),
        )
        print(
            json.dumps(
                dict(
                    arm=arm,
                    score=fit["score"],
                    gain=fit["score"] - known[arm]["score"],
                    satellites=fit["norad"],
                )
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
