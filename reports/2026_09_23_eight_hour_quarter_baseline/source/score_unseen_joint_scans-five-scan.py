#!/usr/bin/env python3
"""Exact Doppler-shape prediction on whole scans excluded from a frozen fit.

Research adapter only. Receiver position and shared rates are never optimized.
New catalogue objects use the causal mean (zero residual rate); orbit-parameter
uncertainty is not integrated. Reported weights are composite, not calibrated.
"""

import argparse
import json
from pathlib import Path

import numpy as np
from build_shared_orbit_rate_cache import digest, load_module, validate_sidecar

from leo.analysis.research.heldout_scan_shape import score_unseen_shape
from leo.analysis.research.regional_doppler import (
    LIGHT_KM_S,
    REFERENCE_RF_HZ,
    Region,
    ScoreConfig,
)
from leo.sky.propagation import parse_element_sets


def validate_frozen_fit(fit, exact, fit_digest, sessions):
    if (
        fit.get("converged") is not True
        or fit.get("truth_accessed") is not False
        or fit.get("complete_cohort") is not True
        or exact.get("truth_accessed") is not False
        or exact.get("fit_digest") != fit_digest
        or exact.get("score_agreement") is not True
        or exact.get("shared_prior_count") != 1
    ):
        raise ValueError("converged blind fit and matching qualified exact replay required")
    training = fit.get("sessions", [])
    if not training or not sessions or len(sessions) != len(set(sessions)):
        raise ValueError("nonempty unique scan cohorts required")
    if set(training).intersection(sessions):
        raise ValueError("whole-scan holdout overlaps training scans")


def run(args):
    if args.output.exists():
        raise FileExistsError(args.output)
    fit = json.loads(args.fit.read_text())
    exact = json.loads(args.exact.read_text())
    inventory_path = args.evidence / "inventory.json"
    inventory = json.loads(inventory_path.read_text())
    if inventory.get("known_position_used") is not False or inventory.get(
        "prior_matched_norads_used"
    ):
        raise ValueError("blind evidence required")
    scans = [r for r in inventory["scans"] if r["included"]]
    validate_frozen_fit(fit, exact, digest(args.fit), [r["session_id"] for r in scans])
    config = ScoreConfig(**fit.get("score_config", {}))
    east, north = fit["east_north_km"]
    point = Region(**fit["region"]).points([east], [north])
    receiver, up = point.ecef_km[0], point.up[0]
    rates = {int(r["norad"]): float(r["rate_s_h"]) for r in fit["rates"]}
    if len(rates) != len(fit["rates"]) or not all(np.isfinite(v) for v in rates.values()):
        raise ValueError("unique finite frozen rates required")
    replay = load_module(Path(__file__).parents[1] / "replay_regional_doppler.py", "unseen_replay")
    loader = load_module(
        Path(__file__).with_name("replay_five_block_regional.py"), "unseen_loader"
    ).FiveBlockLoader()
    args.output.mkdir(parents=True)
    result = {
        "schema": "unseen-joint-scan-shape/v1",
        "complete": False,
        "truth_accessed": False,
        "parameters_refitted": False,
        "fit_digest": digest(args.fit),
        "exact_digest": digest(args.exact),
        "inventory_digest": digest(inventory_path),
        "source_digest": digest(Path(__file__)),
        "score_config": config.__dict__,
        "training_sessions": fit["sessions"],
        "scans": [],
        "interpretation": "frozen-parameter composite Doppler-shape prediction",
        "orbit_uncertainty_integrated": False,
        "unseen_norad_policy": "causal mean with zero residual rate",
    }
    for scan in scans:
        session = scan["session_id"]
        source = args.evidence / "evidence" / f"{session}.json"
        document = json.loads(source.read_text())
        authority = document["inventory"]
        name = authority["tle_file"]
        if Path(name).name != name:
            raise ValueError("catalogue must be a local basename")
        tle = source.parent / name
        reference = int(authority["reference_utc_ns"])
        if (
            reference != scan["reference_utc_ns"]
            or authority["tle_collected_ns"] >= reference
            or digest(tle) != authority["tle_digest"]
        ):
            raise ValueError("catalogue or capture authority mismatch")
        side_path = args.sidecars / f"{session}.json"
        side = json.loads(side_path.read_text())
        rows = validate_sidecar(side, session, reference, digest(tle))
        catalogue = parse_element_sets(tle.read_text())
        indices = [
            i
            for i, (name, epoch) in enumerate(
                zip(catalogue.names, catalogue.element_epoch_utc_ns(), strict=True)
            )
            if name.startswith("STARLINK") and epoch < reference
        ]
        norads = np.asarray(catalogue.satellite_numbers)[indices]
        episodes = []
        for episode_id, arc in loader(document, max_per_partition=0):
            prediction = np.zeros((len(indices), len(arc.time_s)))
            visible = np.zeros(len(indices), dtype=bool)
            failed = []
            for j, (index, norad) in enumerate(zip(indices, norads, strict=True)):
                row = rows[int(norad)]
                phase = row["nominal_phase_s"] + rates.get(int(norad), 0.0) * row["causal_age_h"]
                p, v, valid = replay.state_arrays(
                    catalogue, [index], reference, arc.time_s, orbit_time_s=phase
                )
                if len(valid) != 1:
                    failed.append(int(norad))
                    continue
                delta = p[0] - receiver
                distance = np.linalg.norm(delta, axis=-1)
                prediction[j] = (
                    -REFERENCE_RF_HZ / LIGHT_KM_S * np.sum(delta * v[0], axis=-1) / distance
                )
                visible[j] = np.all(
                    np.sum(delta * up, axis=-1) / distance
                    >= np.sin(np.deg2rad(config.minimum_elevation_deg))
                )
            score = score_unseen_shape(
                arc.frequency_hz, prediction, arc.segment, visible, len(indices), config
            )
            weights = score.pop("candidate_weights")
            top = np.argsort(weights)[-10:][::-1]
            score.update(
                episode_id=episode_id,
                observations=len(arc.time_s),
                propagation_exclusions=failed,
                top_candidates=[
                    {"norad": int(norads[j]), "weight": float(weights[j])} for j in top
                ],
                remaining_signal_weight=float(np.sum(weights) - np.sum(weights[top])),
            )
            episodes.append(score)
        record = {
            "session_id": session,
            "evidence_digest": digest(source),
            "sidecar_digest": digest(side_path),
            "catalogue_digest": digest(tle),
            "catalogue_size": len(indices),
            "unseen_rate_norads": [int(n) for n in norads if int(n) not in rates],
            "episodes": episodes,
            "log_predictive": sum(e["log_predictive"] for e in episodes),
        }
        (args.output / f"{session}.json").write_text(
            json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n"
        )
        result["scans"].append(
            {
                "session_id": session,
                "digest": digest(args.output / f"{session}.json"),
                "log_predictive": record["log_predictive"],
            }
        )
        (args.output / "result.json").write_text(
            json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
        )
    result["complete"] = True
    result["log_predictive"] = sum(r["log_predictive"] for r in result["scans"])
    (args.output / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("fit", "exact", "evidence", "sidecars", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
