#!/usr/bin/env python3
"""Research local joint fit on complete causal state caches, with explicit audit status."""

import argparse
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
from build_shared_orbit_rate_cache import digest
from fit_cached_shared_orbit_rates import verified_refinement, write
from load_compressed_joint_cache import load_compressed_joint_cache

from leo.analysis.research.joint_orbit_position import fit_joint_orbit_position
from leo.analysis.research.orbit_rate_states import OrbitRateStateGrid
from leo.analysis.research.regional_doppler import Region, ScoreConfig
from leo.analysis.research.shared_orbit_rate_fit import FixedPositionRateEpisode


def load_caches(paths, sessions, *, training_only=False):
    """Require the exact sealed cohort; never silently fit a partial set."""
    if not isinstance(training_only, bool):
        raise ValueError("training_only must be boolean")
    manifests = [json.loads((p / "manifest.json").read_text()) for p in paths]
    names = [m["session_id"] for m in manifests]
    if len(set(names)) != len(names) or set(names) != set(sessions):
        raise ValueError("cache sessions must match the complete sealed cohort")
    episodes, provenance, exclusions = [], {}, []
    for root, manifest in zip(paths, manifests, strict=True):
        if not manifest.get("complete") or manifest.get("truth_accessed") is not False:
            raise ValueError("complete blind caches required")
        session = manifest["session_id"]
        provenance[session] = digest(root / "manifest.json")
        for row in manifest["tracks"]:
            if Path(row["file"]).name != row["file"]:
                raise ValueError("unsafe shard filename")
            shard = root / row["file"]
            if digest(shard) != row["digest"]:
                raise ValueError("shard digest mismatch")
            with np.load(shard, allow_pickle=False) as z:
                training = (
                    np.ones(len(z["training"]), dtype=bool) if training_only else z["training"]
                )
                episodes.append(
                    FixedPositionRateEpisode(
                        session + "/" + row["episode_id"],
                        z["observed_hz"],
                        z["candidate_norad"],
                        z["segment"],
                        training,
                        OrbitRateStateGrid(
                            z["rate_nodes_s_h"], z["position_nodes_km"], z["velocity_nodes_km_s"]
                        ),
                        manifest["catalogue_size"],
                    )
                )
            exclusions.extend(
                {"session_id": session, "episode_id": row["episode_id"], **bad}
                for bad in row["invalid_support"]
            )
    return episodes, provenance, exclusions


def load_fit_caches(paths, sessions, *, training_only=False, compressed_paths=None):
    if compressed_paths is None:
        episodes, provenance, exclusions = load_caches(paths, sessions, training_only=training_only)
        return episodes, provenance, exclusions, None
    if len(compressed_paths) != len(paths):
        raise ValueError("compressed caches must align one-for-one with raw caches")
    manifests = [json.loads((root / "manifest.json").read_text()) for root in paths]
    names = [manifest["session_id"] for manifest in manifests]
    if len(set(names)) != len(names) or set(names) != set(sessions):
        raise ValueError("cache sessions must match the complete fitting cohort")
    episodes, provenance, exclusions, compressed = [], {}, [], {}
    for raw_root, compressed_root, manifest in zip(paths, compressed_paths, manifests, strict=True):
        if manifest.get("complete") is not True or manifest.get("truth_accessed") is not False:
            raise ValueError("complete blind raw caches required")
        session = manifest["session_id"]
        loaded, binding = load_compressed_joint_cache(compressed_root, raw_root)
        if training_only:
            loaded = [replace(ep, training=np.ones(len(ep.training), dtype=bool)) for ep in loaded]
        episodes.extend(loaded)
        provenance[session] = digest(raw_root / "manifest.json")
        compressed[session] = binding
        exclusions.extend(
            {"session_id": session, "episode_id": row["episode_id"], **bad}
            for row in manifest["tracks"]
            for bad in row["invalid_support"]
        )
    return episodes, provenance, exclusions, compressed


def validated_resume_state(prior, result):
    if prior.get("loss", "gaussian") != result["loss"]:
        raise ValueError("resume loss mismatch")
    if prior.get("training_only", False) != result["training_only"]:
        raise ValueError("resume training mode mismatch")
    if (
        prior.get("prior_sigma_s_h", 0.09176615913014215) != result["prior_sigma_s_h"]
        or prior.get("score_config", ScoreConfig().__dict__) != result["score_config"]
    ):
        raise ValueError("resume prior or score settings mismatch")
    for key in ("manifest_digests", "refinement_digest", "fit_rates", "sessions"):
        if prior.get(key) != result[key]:
            raise ValueError("resume fit inputs or configuration mismatch")
    legacy_defaults = {
        "seed_sessions": prior.get("sessions"),
        "fitting_inventory_digest": None,
        "fitting_evidence_digests": result["fitting_evidence_digests"],
        "initialization_mode": "sealed-refinement-cohort",
        "compressed_manifest_digests": None,
    }
    explicit = result["initialization_mode"] != "sealed-refinement-cohort"
    for key, legacy in legacy_defaults.items():
        if key not in prior and explicit:
            raise ValueError("explicit fitting-cohort resume needs complete provenance")
        if prior.get(key, legacy) != result[key]:
            raise ValueError("resume fit inputs or configuration mismatch")
    if prior.get("truth_accessed") is not False:
        raise ValueError("resume requires blind fit")
    state = prior.get("accepted_training_iterate")
    if state is None:
        raise ValueError("no accepted iterate to resume")
    return state


def fitting_cohort(refinement, fitting_evidence):
    seed_sessions = list(refinement["sessions"])
    if not seed_sessions or len(seed_sessions) != len(set(seed_sessions)):
        raise ValueError("sealed refinement needs unique nonempty seed sessions")
    if fitting_evidence is None:
        return {
            "sessions": seed_sessions,
            "seed_sessions": seed_sessions,
            "fitting_inventory_digest": None,
            "fitting_evidence_digests": {
                session: refinement["provenance"][session]["rf_digest"] for session in seed_sessions
            },
            "initialization_mode": "sealed-refinement-cohort",
        }
    inventory_path = fitting_evidence / "inventory.json"
    inventory = json.loads(inventory_path.read_text())
    if (
        inventory.get("known_position_used") is not False
        or inventory.get("prior_matched_norads_used") is not False
    ):
        raise ValueError("blind fitting evidence inventory required")
    included = [row for row in inventory.get("scans", []) if row.get("included") is True]
    sessions = [row["session_id"] for row in included]
    if not sessions or len(sessions) != len(set(sessions)):
        raise ValueError("fitting inventory needs unique nonempty included sessions")
    if not set(seed_sessions).issubset(sessions):
        raise ValueError("seed sessions must be a subset of fitting sessions")
    evidence_digests = {}
    for row in included:
        path = fitting_evidence / "evidence" / f"{row['session_id']}.json"
        document = json.loads(path.read_text())
        authority = document.get("inventory", {})
        if (
            authority.get("session_id") != row["session_id"]
            or authority.get("reference_utc_ns") != row.get("reference_utc_ns")
            or authority.get("known_position_used") is not False
            or authority.get("fixed_candidates")
        ):
            raise ValueError("fitting inventory/evidence authority or blindness mismatch")
        evidence_digests[row["session_id"]] = digest(path)
    return {
        "sessions": sessions,
        "seed_sessions": seed_sessions,
        "fitting_inventory_digest": digest(inventory_path),
        "fitting_evidence_digests": evidence_digests,
        "initialization_mode": "sealed-refinement-seed-for-explicit-fitting-cohort",
    }


def cache_evidence_digest(manifest):
    direct = manifest.get("provenance", {}).get("evidence")
    if direct is None:
        raise ValueError("cache has no evidence provenance")
    return direct


def run(args):
    if args.output.exists():
        raise FileExistsError(args.output)
    refinement = verified_refinement(args.refinement)
    cohort = fitting_cohort(refinement, getattr(args, "fitting_evidence", None))
    training_only = bool(getattr(args, "training_only", False))
    episodes, provenance, exclusions, compressed_provenance = load_fit_caches(
        args.cache,
        cohort["sessions"],
        training_only=training_only,
        compressed_paths=getattr(args, "compressed_cache", None),
    )
    for root in args.cache:
        manifest = json.loads((root / "manifest.json").read_text())
        evidence_digest = cohort["fitting_evidence_digests"][manifest["session_id"]]
        if cache_evidence_digest(manifest) != evidence_digest:
            raise ValueError("cache evidence differs from bound fitting evidence")
    region = Region(**refinement["region"])
    seed = refinement["selected"]
    result = {
        "schema": "cached-joint-orbit-position/v1",
        "status": "running",
        "truth_accessed": False,
        "complete_cohort": True,
        "scope": "local refinement of sealed blind basin; exact finalist audit required",
        "region": refinement["region"],
        "sessions": cohort["sessions"],
        "seed_sessions": cohort["seed_sessions"],
        "fitting_inventory_digest": cohort["fitting_inventory_digest"],
        "fitting_evidence_digests": cohort["fitting_evidence_digests"],
        "initialization_mode": cohort["initialization_mode"],
        "manifest_digests": provenance,
        "compressed_manifest_digests": (
            None
            if compressed_provenance is None
            else {
                session: binding["compressed_manifest"]
                for session, binding in compressed_provenance.items()
            }
        ),
        "refinement_digest": digest(args.refinement),
        "source_digest": digest(Path(__file__)),
        "numerical_source_digests": {
            name: digest(Path(__file__).parents[2] / "src/leo/analysis/research" / name)
            for name in (
                "joint_orbit_position.py",
                "shared_gaussian_orbit.py",
                "orbit_rate_states.py",
                "compressed_orbit_states.py",
                "robust_track_location.py",
            )
        },
        "compressed_loader_digest": (
            None
            if compressed_provenance is None
            else digest(Path(__file__).with_name("load_compressed_joint_cache.py"))
        ),
        "fit_rates": not args.fixed_rates,
        "prior_sigma_s_h": 0.09176615913014215,
        "score_config": ScoreConfig().__dict__,
        "loss": getattr(args, "loss", "gaussian"),
        "training_only": training_only,
        "track_count": len(episodes),
        "observation_count": sum(len(e.observed_hz) for e in episodes),
        "explicit_propagation_exclusions": exclusions,
        "exact_finalist_verified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    resume_state = None
    if args.resume_fit is not None:
        prior = json.loads(args.resume_fit.read_text())
        resume_state = validated_resume_state(prior, result)
        result["resumed_fit_digest"] = digest(args.resume_fit)
    write(args.output, result)

    def checkpoint(state):
        result["accepted_training_iterate"] = state
        write(args.output, result)

    fit = fit_joint_orbit_position(
        episodes,
        region,
        [seed["east_km"], seed["north_km"]],
        prior_sigma_s_h=result["prior_sigma_s_h"],
        maximum_iterations=args.maximum_iterations,
        maximum_evaluations=args.maximum_evaluations,
        fit_rates=not args.fixed_rates,
        progress_callback=checkpoint,
        maximum_seconds=args.maximum_seconds,
        resume_state=resume_state,
        loss=result["loss"],
        training_only=result["training_only"],
    )
    latitude, longitude = region.coordinates(*fit.east_north_km)
    associations = []
    for episode, diagnostic in zip(episodes, fit.diagnostics.episodes, strict=True):
        order = np.argsort(-diagnostic.candidate_training_posterior)[:10]
        associations.append(
            {
                "episode_id": episode.episode_id,
                "null_weight": diagnostic.unassigned_training_posterior,
                "top_candidates": [
                    {
                        "norad": int(episode.candidate_norad[i]),
                        "weight": float(diagnostic.candidate_training_posterior[i]),
                    }
                    for i in order
                ],
                "retained_weight": float(np.sum(diagnostic.candidate_training_posterior[order])),
                "heldout_log_predictive": diagnostic.heldout_log_predictive,
            }
        )
    result.update(
        {
            "status": "converged-audit-pending" if fit.converged else "insufficient-nonconvergence",
            "converged": fit.converged,
            "message": fit.message,
            "evaluations": fit.evaluations,
            "projected_gradient_max": fit.projected_gradient_max,
            "negative_log_posterior": fit.objective,
            "east_north_km": fit.east_north_km.tolist(),
            "latitude_deg": float(latitude),
            "longitude_deg": float(longitude),
            "heldout_log_predictive": (
                None
                if result["training_only"]
                else sum(d.heldout_log_predictive for d in fit.diagnostics.episodes)
            ),
            "rates": [
                {"norad": int(n), "rate_s_h": float(r)}
                for n, r in zip(fit.rate_norad, fit.rate_s_h, strict=True)
            ],
            "association_weight_interpretation": (
                "composite likelihood weights; not calibrated identity probabilities"
            ),
            "associations": associations,
        }
    )
    write(args.output, result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, action="append", required=True)
    parser.add_argument(
        "--compressed-cache",
        type=Path,
        action="append",
        help="fit-only compressed cache aligned one-for-one with each raw --cache",
    )
    parser.add_argument("--refinement", type=Path, required=True)
    parser.add_argument(
        "--fitting-evidence",
        type=Path,
        help="blind evidence directory defining the complete fitting cohort",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fixed-rates", action="store_true")
    parser.add_argument("--maximum-iterations", type=int, default=60)
    parser.add_argument("--maximum-evaluations", type=int, default=90)
    parser.add_argument("--maximum-seconds", type=float, default=480)
    parser.add_argument("--resume-fit", type=Path)
    parser.add_argument("--loss", choices=["gaussian", "pseudo_huber"], default="gaussian")
    parser.add_argument(
        "--training-only",
        action="store_true",
        help="use every cached observation row as training; produce no held-out score",
    )
    run(parser.parse_args())
