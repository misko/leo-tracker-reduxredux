#!/usr/bin/env python3
"""Exact replay of a converged joint fit, counting the shared orbit prior once."""

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from build_shared_orbit_rate_cache import digest
from fit_cached_shared_orbit_rates import write
from replay_fitted_shared_orbit import run as replay_one

from leo.analysis.research.regional_doppler import Region


def aggregate(fit, receipts, prior_sigma):
    """Each replay has the full shared rate vector; remove duplicated priors."""
    if len(receipts) != len(fit["sessions"]) or not receipts:
        raise ValueError("complete cohort receipts required")
    if not all(r["sampled_finalist_qualified"] for r in receipts):
        raise ValueError("a cohort member failed exact replay")
    if any(r.get("loss", "gaussian") != fit.get("loss", "gaussian") for r in receipts):
        raise ValueError("replay likelihood mismatch")
    training_only = fit.get("training_only", False)
    if not isinstance(training_only, bool) or any(
        r.get("training_only", False) != training_only for r in receipts
    ):
        raise ValueError("replay training mode mismatch")
    if training_only:
        if fit.get("heldout_log_predictive") is not None or any(
            r.get("heldout_log_predictive") is not None for r in receipts
        ):
            raise ValueError("training-only replay must not contain held-out scores")
    elif any(not np.isfinite(r.get("heldout_log_predictive", np.nan)) for r in receipts):
        raise ValueError("held-out replay score required")
    elif not np.isfinite(fit.get("heldout_log_predictive", np.nan)):
        raise ValueError("held-out fit score required")
    prior = 0.5 * sum((r["rate_s_h"] / prior_sigma) ** 2 for r in fit["rates"])
    objective = sum(r["negative_log_posterior"] for r in receipts) - (len(receipts) - 1) * prior
    predictive = (
        None if training_only else sum(r["heldout_log_predictive"] for r in receipts)
    )
    delta = objective - fit["negative_log_posterior"]
    held_delta = None if training_only else predictive - fit["heldout_log_predictive"]
    return {
        "negative_log_posterior": objective,
        "heldout_log_predictive": predictive,
        "objective_difference": delta,
        "heldout_difference": held_delta,
        "shared_prior_count": 1,
        "evaluated_cases": sum(r["evaluated_cases"] for r in receipts),
        "maximum_doppler_error_hz": max(r["maximum_doppler_error_hz"] for r in receipts),
        "score_agreement": abs(delta) < 1e-4 and (
            training_only or abs(held_delta) < 1e-4
        ),
        "training_only": training_only,
    }


def run(args):
    if args.output.exists():
        raise FileExistsError(args.output)
    fit = json.loads(args.fit.read_text())
    if not fit.get("converged") or fit.get("truth_accessed") is not False:
        raise ValueError("converged blind fit required")
    roots = {}
    for root in args.cache:
        manifest = json.loads((root / "manifest.json").read_text())
        session = manifest["session_id"]
        if session in roots or digest(root / "manifest.json") != fit["manifest_digests"][session]:
            raise ValueError("duplicate or changed cache")
        roots[session] = root
    if set(roots) != set(fit["sessions"]):
        raise ValueError("complete cohort caches required")
    region = Region(**fit["region"])
    xy = fit["east_north_km"]
    receiver = region.points([xy[0]], [xy[1]]).ecef_km[0]
    sigma = fit.get("prior_sigma_s_h", 0.09176615913014215)
    args.output.mkdir(parents=True)
    receipts, bindings = [], []
    for session in fit["sessions"]:
        adapter = args.output / f"{session}-input.json"
        receipt_path = args.output / f"{session}-exact.json"
        write(
            adapter,
            {
                "schema": "joint-fit-to-exact-replay-adapter/v1",
                "source_joint_digest": digest(args.fit),
                "session_id": session,
                "receiver_ecef_km": np.asarray(receiver).tolist(),
                "prior_sigma_s_h": sigma,
                "rates": fit["rates"],
                "loss": fit.get("loss", "gaussian"),
                "score_config": fit.get("score_config", {}),
                "training_only": fit.get("training_only", False),
                "heldout_log_predictive": fit.get("heldout_log_predictive"),
                "provenance": {"manifest": fit["manifest_digests"][session]},
                "truth_accessed": False,
            },
        )
        replay_one(
            SimpleNamespace(
                fit=adapter,
                cache=roots[session],
                evidence=args.evidence,
                phase_sidecar=args.phase_sidecars / f"{session}.json",
                output=receipt_path,
            )
        )
        receipts.append(json.loads(receipt_path.read_text()))
        bindings.append(
            {"session": session, "input": digest(adapter), "receipt": digest(receipt_path)}
        )
    result = aggregate(fit, receipts, sigma)
    result.update(
        {
            "schema": "joint-cohort-exact-replay/v1",
            "truth_accessed": False,
            "fit_digest": digest(args.fit),
            "receipts": bindings,
            "source_digest": digest(Path(__file__)),
        }
    )
    write(args.output / "result.json", result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("fit", "evidence", "phase-sidecars", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--cache", type=Path, action="append", required=True)
    run(parser.parse_args())
