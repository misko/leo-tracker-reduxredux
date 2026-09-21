"""Bounded strictly-causal receiver-position fit with uncertain satellite identity.

This research prototype reconstructs each episode's full pre-capture Starlink
catalogue, screens candidates at several truth-blind location probes, then fits
receiver position by marginalizing identity and an unassigned alternative.  It
does not read an evaluation coordinate.  Held-out observations are scored with
training-conditioned identity probabilities and frozen source offsets.
"""

from __future__ import annotations

import argparse
import hashlib
import heapq
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from replay_regional_doppler import digest, load_observations, state_arrays, write_json
from scipy.optimize import minimize

from leo.analysis.research.identity_mixture import MixtureConfig, logsumexp, mixture_statistics
from leo.analysis.research.regional_doppler import LIGHT_KM_S, REFERENCE_RF_HZ, Region
from leo.sky.propagation import parse_element_set_records, parse_element_sets


@dataclass
class Catalogue:
    text: str
    count: int
    digest: str


@dataclass
class Episode:
    session_id: str
    episode_id: int
    winner_norad: int
    y: np.ndarray
    segment: np.ndarray
    training: np.ndarray
    catalogue_size: int
    candidate_norad: np.ndarray
    p: np.ndarray
    v: np.ndarray
    p_minus: np.ndarray
    v_minus: np.ndarray
    p_plus: np.ndarray
    v_plus: np.ndarray
    screening: dict


def archive_snapshots(root: Path, accepted: set[str]) -> list[tuple[int, str, Path]]:
    found = []
    for path in (root / "archive").glob("*/*.tle"):
        pieces = path.stem.split("-", 1)
        if len(pieces) != 2 or not pieces[0].isdigit() or len(pieces[1]) != 64:
            continue
        canonical = "sha256:" + pieces[1]
        if canonical in accepted:
            found.append((int(pieces[0]), canonical, path))
    return sorted(found)


def causal_catalogues(
    archive_root: Path, reranking: dict, captures: dict[str, int]
) -> dict[str, Catalogue]:
    """Rebuild freshest-epoch causal catalogues incrementally over capture time."""
    snapshots = archive_snapshots(archive_root, set(reranking["snapshot_digests"]))
    if not snapshots:
        raise ValueError("no authorized causal archive snapshots found")
    by_capture: dict[int, list[str]] = {}
    for sid, capture in captures.items():
        by_capture.setdefault(capture, []).append(sid)
    best: dict[int, tuple[tuple[int, int, str], str]] = {}
    pending: list[tuple[int, int, int, str, str]] = []
    snapshot_index = 0
    output: dict[str, Catalogue] = {}
    for capture in sorted(by_capture):
        while snapshot_index < len(snapshots) and snapshots[snapshot_index][0] < capture:
            collected, snapshot_digest, path = snapshots[snapshot_index]
            payload = path.read_bytes()
            observed = "sha256:" + hashlib.sha256(payload).hexdigest()
            if observed != snapshot_digest:
                raise ValueError(f"archive digest mismatch: {path}")
            text = payload.decode("ascii")
            cat = parse_element_sets(text)
            records = parse_element_set_records(text)
            epochs = cat.element_epoch_utc_ns()
            if len(records) != len(epochs):
                raise ValueError("catalogue record order mismatch")
            for record, epoch, name, norad in zip(
                records, epochs, cat.names, cat.satellite_numbers, strict=True
            ):
                if name.startswith("STARLINK"):
                    heapq.heappush(
                        pending,
                        (int(epoch), int(norad), collected, snapshot_digest, record.text),
                    )
            snapshot_index += 1
        while pending and pending[0][0] < capture:
            epoch, norad, collected, snapshot_digest, text = heapq.heappop(pending)
            # Greatest epoch, then greatest collection time, then smallest digest.
            key = (epoch, collected, "".join(chr(255 - ord(c)) for c in snapshot_digest))
            if norad not in best or key > best[norad][0]:
                best[norad] = (key, text)
        catalogue_text = "\n".join(best[n][1].strip() for n in sorted(best)) + "\n"
        catalogue_digest = hashlib.sha256(catalogue_text.encode()).hexdigest()
        for sid in by_capture[capture]:
            output[sid] = Catalogue(catalogue_text, len(best), catalogue_digest)
    return output


def doppler(p: np.ndarray, v: np.ndarray, receiver: np.ndarray) -> np.ndarray:
    delta = p - receiver
    return (
        -REFERENCE_RF_HZ / LIGHT_KM_S * np.sum(delta * v, axis=-1) / np.linalg.norm(delta, axis=-1)
    )


def visibility(
    p: np.ndarray, receiver: np.ndarray, up: np.ndarray, training: np.ndarray
) -> np.ndarray:
    delta = p - receiver
    sine = np.sum(delta * up, axis=-1) / np.linalg.norm(delta, axis=-1)
    return np.min(sine[:, training], axis=1) >= np.sin(np.deg2rad(-1.0))


def interpolate(episode: Episode, clock_s: float) -> tuple[np.ndarray, np.ndarray]:
    tau = float(clock_s)
    p = (
        episode.p
        + (episode.p_plus - episode.p_minus) * tau
        + 2 * (episode.p_plus + episode.p_minus - 2 * episode.p) * tau * tau
    )
    v = (
        episode.v
        + (episode.v_plus - episode.v_minus) * tau
        + 2 * (episode.v_plus + episode.v_minus - 2 * episode.v) * tau * tau
    )
    return p, v


def clock_endpoint_states(cat, indices, reference_utc_ns, time_s, clock_s):
    """Propagate a receiver-clock endpoint while retaining reception-time rotation."""
    return state_arrays(
        cat,
        indices,
        reference_utc_ns,
        time_s,
        clock_s=clock_s,
    )


def episode_statistics(
    episode: Episode,
    receiver: np.ndarray,
    up: np.ndarray,
    clock_s: float,
    config: MixtureConfig,
) -> dict:
    p, v = interpolate(episode, clock_s)
    predicted = doppler(p, v, receiver)
    visible = visibility(p, receiver, up, episode.training)
    return mixture_statistics(
        episode.y[None] - predicted,
        episode.y,
        episode.segment,
        episode.training,
        episode.catalogue_size,
        visible=visible,
        config=config,
    )


def screen_episode(
    arc,
    catalogue: Catalogue,
    probes,
    winner_norad: int,
    margin: float,
    config: MixtureConfig,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    cat = parse_element_sets(catalogue.text)
    p, v, valid = state_arrays(
        cat, list(range(len(cat.satellite_numbers))), probes["reference_utc_ns"], arc.time_s
    )
    norads = np.asarray(cat.satellite_numbers)[valid]
    retained: set[int] = set()
    diagnostics = []
    for receiver, up, label in zip(probes["ecef"], probes["up"], probes["labels"], strict=True):
        predicted = doppler(p, v, receiver)
        visible = visibility(p, receiver, up, arc.training)
        stats = mixture_statistics(
            arc.frequency_hz[None] - predicted,
            arc.frequency_hz,
            arc.segment,
            arc.training,
            catalogue.count,
            visible=visible,
            config=config,
        )
        ll = stats["candidate_train_log_likelihood"]
        finite = np.isfinite(ll)
        maximum = float(np.max(ll[finite])) if np.any(finite) else -np.inf
        chosen = np.flatnonzero(finite & (ll >= maximum - margin))
        retained.update(chosen.tolist())
        full_signal = logsumexp(ll[finite]) if np.any(finite) else -np.inf
        kept_signal = logsumexp(ll[chosen]) if len(chosen) else -np.inf
        tail_fraction = (
            0.0 if not np.isfinite(full_signal) else 1 - np.exp(kept_signal - full_signal)
        )
        diagnostics.append(
            {
                "probe": label,
                "visible_candidates": int(np.sum(finite)),
                "within_margin": int(len(chosen)),
                "omitted_signal_fraction": float(max(0.0, tail_fraction)),
            }
        )
    winner = np.flatnonzero(norads == winner_norad)
    if len(winner) != 1:
        raise ValueError("strict winner absent from reconstructed causal catalogue")
    retained.add(int(winner[0]))
    selected = np.asarray(sorted(retained), dtype=int)
    if not len(selected):
        raise ValueError("empty candidate shortlist")
    return (
        norads[selected],
        p[selected],
        v[selected],
        {
            "catalogue_size": catalogue.count,
            "valid_candidates": len(valid),
            "shortlist_size": len(selected),
            "log_likelihood_margin": margin,
            "probe_tail_checks": diagnostics,
        },
    )


def build_episodes(
    args, parent, strict, reranking, catalogues, probes, config, strict_states, evidence_hashes
):
    root = args.evidence / "evidence"
    rows = reranking["rows"]
    lookup = {(r["session_id"], r["episode_id"]): r for r in rows}
    episodes = []
    for index, assignment in enumerate(parent["assignments"]):
        key = (assignment["session_id"], assignment["episode_id"])
        row = lookup[key]
        document_path = root / (key[0] + ".json")
        doc = json.loads(document_path.read_text())
        evidence_hashes.setdefault(str(document_path), digest(document_path))
        arc = dict(load_observations(doc, 0))[key[1]]
        sealed = strict_states["episode"] == index
        if not (
            np.array_equal(arc.frequency_hz, strict_states["y"][sealed])
            and np.array_equal(arc.time_s, strict_states["time"][sealed])
            and np.array_equal(arc.training, strict_states["training"][sealed])
            and np.all(strict_states["norad"][sealed] == row["best_norad"])
        ):
            raise ValueError(f"RF observations or strict-state binding mismatch for {key}")
        capture = doc["inventory"]["reference_utc_ns"]
        if row["capture_start_utc_ns"] != capture or not (
            row["winning_epoch_utc_ns"] < capture and row["winning_collected_utc_ns"] < capture
        ):
            raise ValueError(f"strict causal timestamp mismatch for {key}")
        local_probes = dict(probes, reference_utc_ns=doc["inventory"]["reference_utc_ns"])
        cat = catalogues[key[0]]
        if cat.count != row["catalogue_count"] or cat.digest != row["catalogue_digest"]:
            raise ValueError(f"strict catalogue reconstruction mismatch for {key[0]}")
        norad, p, v, screening = screen_episode(
            arc, cat, local_probes, row["best_norad"], args.log_margin, config
        )
        short_texts = []
        parsed = parse_element_sets(cat.text)
        records = parse_element_set_records(cat.text)
        by_norad = {n: r.text for n, r in zip(parsed.satellite_numbers, records, strict=True)}
        short_texts = [by_norad[int(n)] for n in norad]
        short_cat = parse_element_sets("\n".join(t.strip() for t in short_texts) + "\n")
        pm, vm, good_m = clock_endpoint_states(
            short_cat, list(range(len(norad))), local_probes["reference_utc_ns"], arc.time_s, -0.5
        )
        pp, vp, good_p = clock_endpoint_states(
            short_cat, list(range(len(norad))), local_probes["reference_utc_ns"], arc.time_s, 0.5
        )
        if list(good_m) != list(range(len(norad))) or list(good_p) != list(range(len(norad))):
            raise ValueError("shortlisted candidate invalid at a clock interpolation endpoint")
        episodes.append(
            Episode(
                key[0],
                key[1],
                row["best_norad"],
                arc.frequency_hz,
                arc.segment,
                arc.training,
                cat.count,
                norad,
                p,
                v,
                pm,
                vm,
                pp,
                vp,
                screening,
            )
        )
        if (index + 1) % 25 == 0:
            print("screened", index + 1, "/", len(parent["assignments"]), flush=True)
    return episodes


def fit_modes(episodes, region, starts, bounds, clock_model, clock_bounds, config):
    evaluations = 0

    def objective(x):
        nonlocal evaluations
        evaluations += 1
        grid = region.points([x[0]], [x[1]])
        clock = x[2] if clock_model == "shared_recorded" else 0.0
        return -sum(
            episode_statistics(ep, grid.ecef_km[0], grid.up[0], clock, config)["train_log_evidence"]
            for ep in episodes
        )

    modes = []
    scipy_bounds = [tuple(bounds[0]), tuple(bounds[1])]
    if clock_model == "shared_recorded":
        scipy_bounds.append(tuple(clock_bounds))
    for label, start in starts:
        x0 = list(np.clip(start, np.asarray(bounds)[:, 0], np.asarray(bounds)[:, 1]))
        if clock_model == "shared_recorded":
            x0.append(float(np.clip(0.0, *clock_bounds)))
        answer = minimize(
            objective,
            x0,
            method="Powell",
            bounds=scipy_bounds,
            options={"xtol": 2e-4, "ftol": 1e-9, "maxiter": 80},
        )
        modes.append(
            {
                "start": label,
                "x_km": answer.x.tolist(),
                "training_negative_log_evidence": float(answer.fun),
                "converged": bool(answer.success),
                "message": str(answer.message),
                "iterations": int(answer.nit),
                "function_evaluations": int(answer.nfev),
            }
        )
        print(clock_model, label, answer.x, answer.fun, answer.success, flush=True)
    modes.sort(key=lambda row: row["training_negative_log_evidence"])
    # Preserve each optimizer result.  Select the reported mode by training
    # evidence only; no coordinate averaging and no held-out selection.
    winner = modes[0]
    x = np.asarray(winner["x_km"])
    grid = region.points([x[0]], [x[1]])
    clock = x[2] if clock_model == "shared_recorded" else 0.0
    train_sum = test_sum = train_count = test_count = heldout_log = 0.0
    unassigned, maximum, entropies = [], [], []
    for episode in episodes:
        stats = episode_statistics(episode, grid.ecef_km[0], grid.up[0], clock, config)
        nt, ne = int(np.sum(episode.training)), int(np.sum(~episode.training))
        train_sum += stats["posterior_train_mse_hz2"] * nt
        test_sum += stats["posterior_heldout_mse_hz2"] * ne
        train_count += nt
        test_count += ne
        heldout_log += stats["heldout_log_predictive"]
        posterior = np.append(stats["candidate_posterior"], stats["unassigned_posterior"])
        positive = posterior > 0
        unassigned.append(stats["unassigned_posterior"])
        maximum.append(float(np.max(stats["candidate_posterior"])))
        entropies.append(float(-np.sum(posterior[positive] * np.log(posterior[positive]))))
    lat, lon = region.coordinates(x[0], x[1])
    return {
        "selection": "all",
        "method": "candidate_identity_mixture",
        "orbit_model": "strict_causal",
        "clock_model": clock_model,
        "weighting": "observation",
        "x_km": x.tolist(),
        "latitude_deg": float(lat),
        "longitude_deg": float(lon),
        "altitude_m": 0.0,
        "training_rms_hz": float(np.sqrt(train_sum / train_count)),
        "evaluation_rms_hz": float(np.sqrt(test_sum / test_count)),
        "heldout_log_predictive": heldout_log,
        "observations": train_count + test_count,
        "episodes": len(episodes),
        "converged": bool(winner["converged"]),
        "clock_s": clock,
        "candidate_posterior": {
            "mean_unassigned": float(np.mean(unassigned)),
            "episodes_unassigned_over_half": int(np.sum(np.asarray(unassigned) > 0.5)),
            "median_max_candidate": float(np.median(maximum)),
            "median_entropy_nats": float(np.median(entropies)),
        },
        "modes": modes,
        "total_objective_evaluations": evaluations,
    }


def full_tail_check(episodes, catalogues, evidence_root, region, model, config):
    """Evaluate omitted catalogue likelihood at a fitted mode without refitting."""
    x = model["x_km"]
    grid = region.points([x[0]], [x[1]])
    clock = model["clock_s"]
    fractions = []
    docs = {}
    for index, episode in enumerate(episodes):
        if episode.session_id not in docs:
            docs[episode.session_id] = json.loads(
                (evidence_root / (episode.session_id + ".json")).read_text()
            )
        doc = docs[episode.session_id]
        arc = dict(load_observations(doc, 0))[episode.episode_id]
        cat = parse_element_sets(catalogues[episode.session_id].text)
        p, v, valid = state_arrays(
            cat,
            list(range(len(cat.satellite_numbers))),
            doc["inventory"]["reference_utc_ns"],
            arc.time_s,
            clock_s=clock,
        )
        predicted = doppler(p, v, grid.ecef_km[0])
        visible = visibility(p, grid.ecef_km[0], grid.up[0], arc.training)
        stats = mixture_statistics(
            arc.frequency_hz[None] - predicted,
            arc.frequency_hz,
            arc.segment,
            arc.training,
            len(cat.satellite_numbers),
            visible=visible,
            config=config,
        )
        valid_norad = np.asarray(cat.satellite_numbers)[valid]
        kept = np.isin(valid_norad, episode.candidate_norad)
        ll = stats["candidate_train_log_likelihood"]
        full = logsumexp(ll[np.isfinite(ll)]) if np.any(np.isfinite(ll)) else -np.inf
        short = logsumexp(ll[kept & np.isfinite(ll)]) if np.any(kept & np.isfinite(ll)) else -np.inf
        fraction = 0.0 if not np.isfinite(full) else max(0.0, 1 - np.exp(short - full))
        fractions.append(fraction)
        if (index + 1) % 50 == 0:
            print("tail checked", index + 1, "/", len(episodes), flush=True)
    values = np.asarray(fractions)
    return {
        "episodes": len(values),
        "maximum_omitted_signal_fraction": float(np.max(values)),
        "p99_omitted_signal_fraction": float(np.quantile(values, 0.99)),
        "episodes_above_1e-6": int(np.sum(values > 1e-6)),
        "episodes_above_1e-4": int(np.sum(values > 1e-4)),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--strict", type=Path, required=True)
    p.add_argument("--reranking", type=Path, required=True)
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--log-margin", type=float, default=25.0)
    a = p.parse_args()
    if a.output.exists():
        raise ValueError("fresh output required")
    parent_path = a.run / "inference.json"
    parent = json.loads(parent_path.read_text())
    strict_path = a.strict / "strict-inference.json"
    strict = json.loads(strict_path.read_text())
    strict_states_path = a.strict / "strict-states.npz"
    strict_states = dict(np.load(strict_states_path))
    reranking = json.loads(a.reranking.read_text())
    if not reranking.get("strictly_causal") or reranking.get("offline_noncausal"):
        raise ValueError("strictly causal reranking required")
    if reranking["parent_digest"] != digest(parent_path):
        raise ValueError("parent digest mismatch")
    rows = reranking["rows"]
    root = a.evidence / "evidence"
    captures = {
        sid: json.loads((root / (sid + ".json")).read_text())["inventory"]["reference_utc_ns"]
        for sid in {r["session_id"] for r in rows}
    }
    catalogues = causal_catalogues(a.archive, reranking, captures)
    region = Region(**parent["region"])
    raw_points = [
        ("parent_initial", parent["initial"]),
        *[(f"parent_model_{i}", m["x_km"][:2]) for i, m in enumerate(parent["models"])],
        *[(f"strict_model_{i}", m["x_km"][:2]) for i, m in enumerate(strict["models"])],
    ]
    centre = np.asarray(
        next(
            m for m in strict["models"] if m["selection"] == "all" and m["clock_model"] == "fixed"
        )["x_km"][:2]
    )
    for radius in (100.0, 300.0):
        displacements = [
            ("east", [radius, 0]),
            ("west", [-radius, 0]),
            ("north", [0, radius]),
            ("south", [0, -radius]),
        ]
        for axis, delta in displacements:
            raw_points.append((f"strict_fixed_{axis}_{int(radius)}km", centre + delta))
    unique = {}
    for label, point in raw_points:
        point = np.asarray(point, dtype=float)
        unique.setdefault(tuple(np.round(point, 6)), (label, point))
    labels, points = zip(*unique.values(), strict=True)
    grid = region.points(np.asarray(points)[:, 0], np.asarray(points)[:, 1])
    probes = {"labels": labels, "ecef": grid.ecef_km, "up": grid.up}
    config = MixtureConfig()
    evidence_hashes = {}
    episodes = build_episodes(
        a, parent, strict, reranking, catalogues, probes, config, strict_states, evidence_hashes
    )
    screening = {
        "episodes": len(episodes),
        "catalogue_size_min": min(e.catalogue_size for e in episodes),
        "catalogue_size_max": max(e.catalogue_size for e in episodes),
        "shortlist_size_min": min(len(e.candidate_norad) for e in episodes),
        "shortlist_size_median": float(np.median([len(e.candidate_norad) for e in episodes])),
        "shortlist_size_max": max(len(e.candidate_norad) for e in episodes),
        "probe_maximum_omitted_signal_fraction": float(
            max(
                check["omitted_signal_fraction"]
                for episode in episodes
                for check in episode.screening["probe_tail_checks"]
            )
        ),
        "probes": [
            {"label": label, "x_km": point.tolist()}
            for label, point in zip(labels, points, strict=True)
        ],
    }
    span = 500.0
    bounds = np.array(
        [
            [
                max(-region.width_km / 2, centre[0] - span),
                min(region.width_km / 2, centre[0] + span),
            ],
            [
                max(-region.height_km / 2, centre[1] - span),
                min(region.height_km / 2, centre[1] + span),
            ],
        ]
    )
    starts = [(label, point) for label, point in zip(labels, points, strict=True)]
    # Four broad truth-blind starts are enough to test local convergence while
    # retaining the complete probe set for candidate support.
    start_indices = sorted({0, len(starts) - 1, len(starts) - 3, len(starts) - 5})
    starts = [starts[i] for i in start_indices]
    shared = next(
        m
        for m in strict["models"]
        if m["selection"] == "all" and m["clock_model"] == "shared_recorded"
    )
    clock_bounds = shared["clock_bounds_s"][0]
    models = []
    for clock_model in ["fixed", "shared_recorded"]:
        model = fit_modes(episodes, region, starts, bounds, clock_model, clock_bounds, config)
        model["tail_check"] = full_tail_check(episodes, catalogues, root, region, model, config)
        if model["tail_check"]["episodes_above_1e-4"]:
            raise ValueError("candidate truncation tail exceeded declared bound at fitted mode")
        models.append(model)
    variants = {"strict_causal_identity_mixture": models}
    baseline = [
        m
        for m in strict["models"]
        if m["selection"] == "all" and m["clock_model"] in {"fixed", "shared_recorded"}
    ]
    out = {
        "complete": True,
        "strictly_causal": True,
        "evaluation_location_used": False,
        "known_site_candidate_fields_used": False,
        "heldout_used_for_fitting_or_identity_selection": False,
        "satellite_identities_verified": False,
        "position_scope": "local conditional refinement of truth-blind wide modes",
        "region": parent["region"],
        "local_bounds_km": bounds.tolist(),
        "likelihood": {
            "signal_sigma_hz": config.signal_sigma_hz,
            "unassigned_sigma_hz": config.unassigned_sigma_hz,
            "signal_prior": config.signal_prior,
            "candidate_prior": "signal_prior / full strictly causal catalogue size",
            "source_offsets": "per-segment arithmetic mean profiled on training only, then frozen",
            "robust_loss": "pseudo-Huber with the fixed-ID baseline transform",
            "covariance_model": "simple iid per-observation scale after profiled offsets",
            "calibration": (
                "uncalibrated composite likelihood; posterior weights are not confidence"
            ),
        },
        "tail_scope": (
            "exact full-catalogue checks at truth-blind screening probes and fitted local modes; "
            "not a global-search certificate"
        ),
        "screening": screening,
        "models": [*baseline, *models],
        "mixture_variants": variants,
        "source_hashes": {
            str(parent_path): digest(parent_path),
            str(strict_path): digest(strict_path),
            str(a.reranking): digest(a.reranking),
            str(strict_states_path): digest(strict_states_path),
            **evidence_hashes,
        },
    }
    write_json(a.output, out)


if __name__ == "__main__":
    main()
