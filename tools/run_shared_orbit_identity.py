"""Build exact candidate orbit sensitivities for the matched Stage-D replay.

This deliberately reuses the reviewed causal catalogue and shortlist machinery.
The resulting NPZ is a reusable numerical boundary: every candidate has centre
and orbit-time +/-1 second states, never the clock-shift states used elsewhere.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import prototype_mixture_position as old
from replay_regional_doppler import load_observations, state_arrays
from scipy.optimize import minimize

import leo.analysis.research.orbit_identity_mixture as model_module
from leo.analysis.research.formal_orbit import (
    doppler_hz,
    phase_rate_design_hz_per_s_h,
)
from leo.analysis.research.identity_mixture import MixtureConfig, profile_offsets
from leo.analysis.research.orbit_identity_mixture import (
    SharedMapEpisode,
    fit_shared_satellite_map,
)
from leo.analysis.research.regional_doppler import Region
from leo.sky.propagation import parse_element_set_records, parse_element_sets


def fit_cache(cache_path: Path, run_path: Path, output_path: Path) -> None:
    if output_path.exists():
        raise ValueError("fresh fit output path required")
    with np.load(cache_path, allow_pickle=False) as archive:
        cache = {key: archive[key] for key in archive.files}
    if str(cache["schema_version"].item()) != "orbit-identity-cache-v1":
        raise ValueError("unsupported candidate phase cache")
    if float(cache["orbit_phase_step_s"]) != 1.0:
        raise ValueError("one-second orbital sensitivity required")
    source_hashes = {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (Path(__file__), Path(model_module.__file__))
    }
    parent = json.loads((run_path / "inference.json").read_text())
    region = Region(**parent["region"])
    count = int(cache["episode_count"])
    config = MixtureConfig()

    def episodes_at(x_km: np.ndarray, fixed_identity: bool) -> list[SharedMapEpisode]:
        point = region.points([x_km[0]], [x_km[1]])
        receiver, up = point.ecef_km[0], point.up[0]
        result = []
        for index in range(count):
            norad = cache[f"norad_{index}"]
            p = cache[f"p_centre_{index}"]
            v = cache[f"v_centre_{index}"]
            pm, vm = cache[f"p_minus_{index}"], cache[f"v_minus_{index}"]
            pp, vp = cache[f"p_plus_{index}"], cache[f"v_plus_{index}"]
            training = cache[f"training_{index}"].astype(bool)
            predicted = doppler_hz(receiver, p, v)
            design = phase_rate_design_hz_per_s_h(
                receiver,
                pm,
                vm,
                pp,
                vp,
                cache[f"age_h_{index}"][:, None],
            )
            delta = p - receiver
            elevation_sine = np.sum(delta * up, axis=-1) / np.linalg.norm(delta, axis=-1)
            visible = np.min(elevation_sine[:, training], axis=1) >= np.sin(np.deg2rad(-1.0))
            if fixed_identity:
                winner = int(cache[f"winner_norad_{index}"])
                chosen = np.flatnonzero(norad == winner)
                if len(chosen) != 1:
                    raise ValueError("fixed-identity winner absent from shortlist")
                chosen = chosen[:1]
                norad, predicted, design, visible = (
                    value[chosen] for value in (norad, predicted, design, visible)
                )
            result.append(
                SharedMapEpisode(
                    cache[f"observed_{index}"],
                    predicted,
                    design,
                    norad,
                    cache[f"segment_{index}"],
                    training,
                    int(cache[f"catalogue_size_{index}"]),
                    visible,
                )
            )
        return result

    bounds = [
        (
            max(-region.width_km / 2, cache["initial_x_km"][0] - 500),
            min(region.width_km / 2, cache["initial_x_km"][0] + 500),
        ),
        (
            max(-region.height_km / 2, cache["initial_x_km"][1] - 500),
            min(region.height_km / 2, cache["initial_x_km"][1] + 500),
        ),
    ]
    models = []
    for fixed in (True, False):
        began = time.monotonic()
        evaluations = 0
        last = None

        def objective(x, fixed_identity=fixed, started=began):
            nonlocal evaluations, last
            evaluations += 1
            last = fit_shared_satellite_map(
                episodes_at(np.asarray(x), fixed_identity),
                config=config,
                return_diagnostics=False,
            )
            if evaluations % 10 == 0:
                print(
                    json.dumps(
                        {
                            "fixed_identity": fixed_identity,
                            "evaluations": evaluations,
                            "seconds": time.monotonic() - started,
                            "inner_converged": last["converged"],
                        }
                    ),
                    flush=True,
                )
            return last["negative_log_posterior"]

        answer = minimize(
            objective,
            cache["initial_x_km"],
            method="Nelder-Mead",
            bounds=bounds,
            options={
                "maxiter": 250,
                "xatol": 2e-3,
                "fatol": 1e-6,
                "initial_simplex": np.asarray(cache["initial_x_km"])
                + np.asarray([[0.0, 0.0], [10.0, 0.0], [0.0, 10.0]]),
            },
        )
        final_episodes = episodes_at(answer.x, fixed)
        final = fit_shared_satellite_map(final_episodes, config=config)
        rates = dict(zip(final["norad"], final["rate_corrections_s_h"], strict=True))
        episode_summaries = []
        for index, (episode, diagnostic) in enumerate(
            zip(final_episodes, final["episodes"], strict=True)
        ):
            correction = np.asarray([rates[norad] for norad in episode.candidate_norad])
            residual, _ = profile_offsets(
                episode.observed_hz[None, :]
                - episode.base_predicted_hz
                - episode.design_hz_per_s_h * correction[:, None],
                episode.segment,
                episode.training,
            )
            leader = int(np.argmax(diagnostic["candidate_posterior"]))
            episode_summaries.append(
                {
                    "session_id": str(cache[f"session_id_{index}"].item()),
                    "episode_id": str(cache[f"episode_id_{index}"].item()),
                    "candidate_norad": episode.candidate_norad.tolist(),
                    "candidate_posterior": diagnostic["candidate_posterior"].tolist(),
                    "unassigned_posterior": diagnostic["unassigned_posterior"],
                    "heldout_log_predictive": diagnostic["heldout_log_predictive"],
                    "training_leader_norad": int(episode.candidate_norad[leader]),
                    "leader_training_rms_hz": float(
                        np.sqrt(np.mean(residual[leader, episode.training] ** 2))
                    ),
                    "leader_heldout_rms_hz": float(
                        np.sqrt(np.mean(residual[leader, ~episode.training] ** 2))
                    ),
                }
            )
        heldout_log_predictive = float(
            sum(row["heldout_log_predictive"] for row in final["episodes"])
        )
        lat, lon = region.coordinates(*answer.x)
        models.append(
            {
                "identity_model": "fixed_strict_winner" if fixed else "joint_candidate_mixture",
                "x_km": answer.x.tolist(),
                "latitude_deg": float(lat),
                "longitude_deg": float(lon),
                "negative_log_posterior": final["negative_log_posterior"],
                "heldout_log_predictive": heldout_log_predictive,
                "converged": bool(answer.success and final["converged"]),
                "position_evaluations": evaluations,
                "rate_iterations": final["iterations"],
                "fitted_satellites": len(final["norad"]),
                "seconds": time.monotonic() - began,
                "episodes": episode_summaries,
                "rate_corrections_s_h": {
                    str(int(n)): float(r)
                    for n, r in zip(final["norad"], final["rate_corrections_s_h"], strict=True)
                },
            }
        )
        checkpoint = output_path.with_suffix(".checkpoint.json")
        temporary = checkpoint.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {"complete": False, "source_hashes": source_hashes, "models": models},
                indent=2,
                allow_nan=False,
            )
            + "\n"
        )
        temporary.replace(checkpoint)
        print(
            json.dumps(
                {
                    "model_completed": models[-1]["identity_model"],
                    "seconds": models[-1]["seconds"],
                    "converged": models[-1]["converged"],
                }
            ),
            flush=True,
        )
    if any(
        hashlib.sha256(Path(path).read_bytes()).hexdigest() != sha
        for path, sha in source_hashes.items()
    ):
        raise ValueError("source changed during fit; checkpoint remains diagnostic only")
    payload = (
        json.dumps(
            {
                "sealed_before_truth": True,
                "source_hashes": source_hashes,
                "complete": True,
                "cache": str(cache_path),
                "model": "shared-satellite linearized phase-rate MAP; pseudo-Huber iid noise",
                "optimizer": "bounded local Nelder-Mead, common 10 km simplex",
                "phase_rate_prior_sigma_s_h": 0.09176615913014215,
                "cache_sha256": hashlib.sha256(cache_path.read_bytes()).hexdigest(),
                "source_inference_sha256": hashlib.sha256(
                    (run_path / "inference.json").read_bytes()
                ).hexdigest(),
                "models": models,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(payload)
    temporary.replace(output_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--strict", type=Path, required=True)
    parser.add_argument("--reranking", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--log-margin", type=float, default=25.0)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--fit-output", type=Path)
    args = parser.parse_args()
    if args.cache.exists() and args.fit_output is not None:
        fit_cache(args.cache, args.run, args.fit_output)
        return
    if args.cache.exists():
        raise ValueError("fresh cache path required")
    parent = json.loads((args.run / "inference.json").read_text())
    strict = json.loads((args.strict / "strict-inference.json").read_text())
    strict_states = dict(np.load(args.strict / "strict-states.npz"))
    reranking = json.loads(args.reranking.read_text())
    if args.limit is not None:
        parent = dict(parent, assignments=parent["assignments"][: args.limit])
    root = args.evidence / "evidence"
    rows = reranking["rows"]
    captures = {
        sid: json.loads((root / f"{sid}.json").read_text())["inventory"]["reference_utc_ns"]
        for sid in {row["session_id"] for row in rows}
    }
    catalogues = old.causal_catalogues(args.archive, reranking, captures)
    region = Region(**parent["region"])
    centre = np.asarray(
        next(
            model
            for model in strict["models"]
            if model["selection"] == "all" and model["clock_model"] == "fixed"
        )["x_km"][:2]
    )
    raw = [("centre", centre)]
    for radius in (100.0, 300.0):
        raw.extend(
            (label, centre + delta)
            for label, delta in (
                (f"east-{radius}", [radius, 0]),
                (f"west-{radius}", [-radius, 0]),
                (f"north-{radius}", [0, radius]),
                (f"south-{radius}", [0, -radius]),
            )
        )
    points = region.points([point[0] for _, point in raw], [point[1] for _, point in raw])
    probes = {
        "labels": [label for label, _ in raw],
        "ecef": points.ecef_km,
        "up": points.up,
    }
    shim = argparse.Namespace(evidence=args.evidence, log_margin=args.log_margin)
    episodes = old.build_episodes(
        shim,
        parent,
        strict,
        reranking,
        catalogues,
        probes,
        MixtureConfig(),
        strict_states,
        {},
    )
    output: dict[str, np.ndarray] = {}
    for number, episode in enumerate(episodes):
        doc = json.loads((root / f"{episode.session_id}.json").read_text())
        arc = dict(load_observations(doc, 0))[episode.episode_id]
        catalogue = parse_element_sets(catalogues[episode.session_id].text)
        records = parse_element_set_records(catalogues[episode.session_id].text)
        by_norad = {
            int(norad): record.text
            for norad, record in zip(catalogue.satellite_numbers, records, strict=True)
        }
        short = parse_element_sets(
            "\n".join(by_norad[int(n)].strip() for n in episode.candidate_norad) + "\n"
        )
        output[f"norad_{number}"] = episode.candidate_norad
        capture_ns = int(doc["inventory"]["reference_utc_ns"])
        output[f"age_h_{number}"] = (
            capture_ns - np.asarray(short.element_epoch_utc_ns(), dtype=np.int64)
        ) / 3_600_000_000_000
        output[f"session_id_{number}"] = np.asarray(episode.session_id)
        output[f"episode_id_{number}"] = np.asarray(str(episode.episode_id))
        output[f"winner_norad_{number}"] = np.asarray(episode.winner_norad)
        output[f"capture_start_utc_ns_{number}"] = np.asarray(capture_ns)
        output[f"time_s_{number}"] = arc.time_s
        output[f"catalogue_digest_{number}"] = np.asarray(catalogues[episode.session_id].digest)
        output[f"observed_{number}"] = episode.y
        output[f"segment_{number}"] = episode.segment
        output[f"training_{number}"] = episode.training
        output[f"catalogue_size_{number}"] = np.asarray(episode.catalogue_size)
        for label, phase in (("minus", -1.0), ("centre", 0.0), ("plus", 1.0)):
            p, v, valid = state_arrays(
                short,
                list(range(len(short.satellite_numbers))),
                doc["inventory"]["reference_utc_ns"],
                arc.time_s,
                orbit_time_s=phase,
            )
            if list(valid) != list(range(len(short.satellite_numbers))):
                raise ValueError(f"invalid phase state for episode {number}")
            output[f"p_{label}_{number}"] = p
            output[f"v_{label}_{number}"] = v
        if (number + 1) % 25 == 0:
            print("phase cached", number + 1, "/", len(episodes), flush=True)
    output["episode_count"] = np.asarray(len(episodes))
    output["initial_x_km"] = centre
    output["schema_version"] = np.asarray("orbit-identity-cache-v1")
    output["orbit_phase_step_s"] = np.asarray(1.0)
    output["reranking_sha256"] = np.asarray(hashlib.sha256(args.reranking.read_bytes()).hexdigest())
    np.savez_compressed(args.cache, **output)


if __name__ == "__main__":
    main()
