"""Audit fitted shared-orbit identity rates and conservative catalogue tails."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
import prototype_mixture_position as old
from replay_regional_doppler import state_arrays

from leo.analysis.research.formal_orbit import doppler_hz, phase_rate_design_hz_per_s_h
from leo.analysis.research.identity_mixture import (
    logsumexp,
    profile_offsets,
    pseudo_huber_log_likelihood,
)
from leo.analysis.research.regional_doppler import Region
from leo.sky.propagation import parse_element_set_records, parse_element_sets


def quadratic_state(centre, minus, plus, phase_s):
    """Three-point state interpolation used only as a pre-exact audit diagnostic."""
    phase = np.asarray(phase_s)[..., None, None]
    return centre + 0.5 * (plus - minus) * phase + 0.5 * (plus + minus - 2 * centre) * phase**2


def conservative_omitted_fraction_bound(
    retained_log_likelihood: np.ndarray,
    omitted_count: int,
    observation_count: int,
    sigma_hz: float,
) -> float:
    """Bound omitted signal mass even if every omitted orbit fits perfectly.

    Pseudo-Huber energy is nonnegative, hence ``-n log(sigma)`` is an upper
    bound on every candidate likelihood after any bounded rate correction and
    profiled offset.  The result can be loose but cannot favor the shortlist.
    """
    if omitted_count < 0 or observation_count < 1 or sigma_hz <= 0:
        raise ValueError("invalid tail-bound inputs")
    retained = logsumexp(np.asarray(retained_log_likelihood, float))
    if omitted_count == 0:
        return 0.0
    omitted_upper = np.log(omitted_count) - observation_count * np.log(sigma_hz)
    total_upper = logsumexp(np.asarray([retained, omitted_upper]))
    return float(np.exp(omitted_upper - total_upper))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--fit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--reranking", type=Path, required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--tolerance-hz", type=float, default=0.2)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("fresh output required")
    fit = json.loads(args.fit.read_text())
    cache = dict(np.load(args.cache, allow_pickle=False))
    if hashlib.sha256(args.cache.read_bytes()).hexdigest() != fit["cache_sha256"]:
        raise ValueError("fit/cache digest mismatch")
    if hashlib.sha256(args.reranking.read_bytes()).hexdigest() != str(
        cache["reranking_sha256"].item()
    ):
        raise ValueError("causal reranking digest mismatch")
    region = Region(**json.loads(args.region))
    captures, wanted = {}, {}
    for index in range(int(cache["episode_count"])):
        sid = str(cache[f"session_id_{index}"].item())
        captures[sid] = int(cache[f"capture_start_utc_ns_{index}"])
        wanted.setdefault(sid, set()).update(map(int, cache[f"norad_{index}"]))
    catalogues = old.causal_catalogues(
        args.archive, json.loads(args.reranking.read_text()), captures
    )
    elements, saved_elements = {}, {}
    for sid, catalogue in catalogues.items():
        records = {
            record.satellite_number: record.text
            for record in parse_element_set_records(catalogue.text)
            if record.satellite_number in wanted[sid]
        }
        if set(records) != wanted[sid]:
            raise ValueError("retained candidate missing from causal catalogue")
        elements[sid] = {norad: parse_element_sets(text) for norad, text in records.items()}
        saved_elements[sid] = {
            "catalogue_digest": catalogue.digest,
            "capture_start_utc_ns": captures[sid],
            "records": records,
        }
    print(f"rebuilt {len(elements)} causal retained catalogues", flush=True)
    audits = []
    for model in fit["models"]:
        rates = {int(key): value for key, value in model["rate_corrections_s_h"].items()}
        maximum_state_delta = 0.0
        point = region.points([model["x_km"][0]], [model["x_km"][1]])
        receiver, up = point.ecef_km[0], point.up[0]
        all_error, all_shape_error, tail_bounds, episode_audits = [], [], [], []
        for index in range(int(cache["episode_count"])):
            norad = cache[f"norad_{index}"]
            phase = (
                np.asarray([rates.get(int(value), 0.0) for value in norad])
                * cache[f"age_h_{index}"]
            )
            quadratic = quadratic_state(
                cache[f"p_centre_{index}"],
                cache[f"p_minus_{index}"],
                cache[f"p_plus_{index}"],
                phase,
            )
            maximum_state_delta = max(
                maximum_state_delta,
                float(np.max(np.linalg.norm(quadratic - cache[f"p_centre_{index}"], axis=-1))),
            )
            sid = str(cache[f"session_id_{index}"].item())
            if catalogues[sid].digest != str(cache[f"catalogue_digest_{index}"].item()):
                raise ValueError("candidate catalogue digest mismatch")
            indices = [
                int(np.flatnonzero(norad == value)[0])
                for value in model["episodes"][index]["candidate_norad"]
            ]
            training = cache[f"training_{index}"].astype(bool)
            centre_p = cache[f"p_centre_{index}"][indices]
            centre_v = cache[f"v_centre_{index}"][indices]
            design = phase_rate_design_hz_per_s_h(
                receiver,
                cache[f"p_minus_{index}"][indices],
                cache[f"v_minus_{index}"][indices],
                cache[f"p_plus_{index}"][indices],
                cache[f"v_plus_{index}"][indices],
                cache[f"age_h_{index}"][indices, None],
            )
            retained_rates = np.asarray([rates[int(norad[i])] for i in indices])
            predicted = doppler_hz(receiver, centre_p, centre_v) + design * retained_rates[:, None]
            errors, shape_errors = [], []
            for candidate, original in enumerate(indices):
                p, v, valid = state_arrays(
                    elements[sid][int(norad[original])],
                    [0],
                    captures[sid],
                    cache[f"time_s_{index}"],
                    orbit_time_s=float(phase[original]),
                    clock_s=0,
                )
                if len(valid) != 1:
                    raise ValueError("exact fitted candidate propagation failed")
                difference = predicted[candidate] - doppler_hz(receiver, p[0], v[0])
                errors.extend(difference.tolist())
                centered, _ = profile_offsets(difference, cache[f"segment_{index}"], training)
                shape_errors.extend(centered.tolist())
            all_error.extend(errors)
            all_shape_error.extend(shape_errors)
            residual, _ = profile_offsets(
                cache[f"observed_{index}"][None, :] - predicted, cache[f"segment_{index}"], training
            )
            ll = pseudo_huber_log_likelihood(residual, training, 250.0)
            visible = old.visibility(centre_p, receiver, up, training)
            ll = np.where(visible, ll, -np.inf)
            bound = conservative_omitted_fraction_bound(
                ll,
                int(cache[f"catalogue_size_{index}"]) - len(indices),
                int(training.sum()),
                250.0,
            )
            tail_bounds.append(bound)
            episode_audits.append(
                {
                    "session_id": sid,
                    "episode_id": str(cache[f"episode_id_{index}"].item()),
                    "retained_candidates": len(indices),
                    "omitted_fraction_upper_bound": bound,
                    "maximum_absolute_approximation_error_hz": float(np.max(np.abs(errors))),
                }
            )
        error = np.asarray(all_error)
        shape_error = np.asarray(all_shape_error)
        exact_pass = bool(np.max(np.abs(error)) <= args.tolerance_hz)
        audits.append(
            {
                "identity_model": model["identity_model"],
                "maximum_quadratic_state_shift_km": maximum_state_delta,
                "exact_sgp4_checked": True,
                "exact_sgp4_verified": exact_pass,
                "rms_approximation_error_hz": float(np.sqrt(np.mean(error**2))),
                "maximum_absolute_approximation_error_hz": float(np.max(np.abs(error))),
                "exact_tolerance_hz": args.tolerance_hz,
                "training_offset_removed_rms_error_hz": float(np.sqrt(np.mean(shape_error**2))),
                "training_offset_removed_maximum_error_hz": float(np.max(np.abs(shape_error))),
                "full_catalogue_tail_certified": bool(max(tail_bounds) < 1e-6),
                "maximum_omitted_fraction_upper_bound": max(tail_bounds),
                "tail_policy": "perfect-fit likelihood ceiling for every omitted candidate",
                "status": "diagnostic only: loose tail bound cannot certify the shortlist",
                "episodes": episode_audits,
            }
        )
    args.output.write_text(
        json.dumps(
            {
                "audits": audits,
                "inputs": {
                    "cache_sha256": fit["cache_sha256"],
                    "fit_sha256": hashlib.sha256(args.fit.read_bytes()).hexdigest(),
                    "reranking_sha256": hashlib.sha256(args.reranking.read_bytes()).hexdigest(),
                },
            },
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    )
    args.output.with_suffix(".retained-tles.json.gz").write_bytes(
        gzip.compress(json.dumps(saved_elements, sort_keys=True).encode(), mtime=0)
    )
    print(
        json.dumps(
            [{key: value for key, value in row.items() if key != "episodes"} for row in audits]
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
