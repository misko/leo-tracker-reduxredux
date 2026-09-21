"""Conditionally reassociate and fit every recovered leading RF tracklet.

The receiver seed is the frozen causal wide-search result, never the evaluation
coordinate.  Each tracklet is independently scored on randomized training RF
against its session's digest-verified, strictly pre-capture catalogue.
"""

import argparse
import json
from pathlib import Path

import numpy as np
from compare_positioning_cohorts import fit
from replay_regional_doppler import digest, load_observations, state_arrays, write_json

from leo.analysis.research.regional_doppler import Region, ScoreConfig, score_states
from leo.sky.propagation import parse_element_sets

SCHEMA = "org.leo.research.extended-tracklet-position-benchmark/v1"
MIN_ELEVATION_DEG = -10.0
PREVIOUS_MIN_OBSERVATIONS = 14
PREVIOUS_MIN_SPAN_S = 7.0


def _catalogue_path(evidence, document):
    path = evidence / document["inventory"]["tle_file"]
    if digest(path) != document["inventory"]["tle_digest"]:
        raise ValueError(f"catalogue digest mismatch: {path}")
    return path


def visible_candidates(catalogue, reference_ns, receiver_ecef_km, times):
    """Generous horizon prefilter evaluated across the complete session span."""
    causal = np.asarray(
        [
            index
            for index, (name, epoch) in enumerate(
                zip(catalogue.names, catalogue.element_epoch_utc_ns(), strict=True)
            )
            if name.startswith("STARLINK") and epoch < reference_ns
        ],
        dtype=int,
    )
    start, stop = float(np.min(times)), float(np.max(times))
    grid = np.unique(np.append(np.arange(start - 15, stop + 30, 15), [start, stop]))
    p, _, valid = state_arrays(catalogue, causal, reference_ns, grid)
    relative = p - receiver_ecef_km
    receiver_up = receiver_ecef_km / np.linalg.norm(receiver_ecef_km)
    sine_elevation = np.sum(relative * receiver_up, axis=-1) / np.linalg.norm(relative, axis=-1)
    visible = valid[np.any(sine_elevation >= np.sin(np.deg2rad(MIN_ELEVATION_DEG)), axis=1)]
    if not len(visible):
        raise ValueError("geometric prefilter removed the complete catalogue")
    return visible, len(causal)


def _legacy_ids(legacy_evidence):
    result = set()
    for path in legacy_evidence.glob("*.json"):
        document = json.loads(path.read_text())
        result.update(
            (document["inventory"]["session_id"], row["tracklet_id"]) for row in document["series"]
        )
    return result


def associate(evidence, legacy_evidence, parent):
    model = parent["models"][0]
    region = Region(**parent["region"])
    receiver = region.points([model["x_km"][0]], [model["x_km"][1]], 0).ecef_km[0]
    legacy = _legacy_ids(legacy_evidence)
    matched = {(row["session_id"], row["episode_id"]) for row in parent["assignments"]}
    arrays = {
        key: []
        for key in [
            "y",
            "segment",
            "training",
            "p",
            "v",
            "episode",
            "norad",
            "session",
            "time",
            "p-0.5",
            "v-0.5",
            "p0.5",
            "v0.5",
        ]
    }
    catalogue_cache = {}
    rows = []
    paths = sorted(evidence.glob("*.json"))
    for session_index, path in enumerate(paths):
        document = json.loads(path.read_text())
        inventory = document["inventory"]
        reference_ns = int(inventory["reference_utc_ns"])
        if int(inventory["tle_collected_ns"]) >= reference_ns:
            raise ValueError(f"catalogue was not collected before capture: {path}")
        cat_path = _catalogue_path(evidence, document)
        if str(cat_path) not in catalogue_cache:
            catalogue_cache[str(cat_path)] = parse_element_sets(cat_path.read_text())
        catalogue = catalogue_cache[str(cat_path)]
        arcs = load_observations(document, 0, individual=True)
        all_times = np.concatenate([arc.time_s for _, arc in arcs])
        selected, causal_count = visible_candidates(catalogue, reference_ns, receiver, all_times)
        states = {}
        valid_reference = None
        for shift in [0.0, -0.5, 0.5]:
            p, v, valid = state_arrays(catalogue, selected, reference_ns, all_times, clock_s=shift)
            if valid_reference is None:
                valid_reference = valid
            elif not np.array_equal(valid, valid_reference):
                raise ValueError("valid candidate set changed across clock stencil")
            states[shift] = (p, v)
        cursor = 0
        for episode_id, arc in arcs:
            count = len(arc.time_s)
            section = slice(cursor, cursor + count)
            cursor += count
            p, v = states[0.0][0][:, section], states[0.0][1][:, section]
            score = score_states(
                arc,
                p,
                v,
                region.points([model["x_km"][0]], [model["x_km"][1]]),
                len(valid_reference),
                ScoreConfig(),
            )
            winner = int(score["best_index"][0])
            if winner < 0:
                raise ValueError(f"no candidate assignment: {inventory['session_id']} {episode_id}")
            norad = int(catalogue.satellite_numbers[valid_reference[winner]])
            episode_index = len(rows)
            values = {
                "y": arc.frequency_hz,
                "segment": np.full(count, episode_index),
                "training": arc.training,
                "p": p[winner],
                "v": v[winner],
                "episode": np.full(count, episode_index),
                "norad": np.full(count, norad),
                "session": np.full(count, session_index),
                "time": arc.time_s,
                "p-0.5": states[-0.5][0][winner, section],
                "v-0.5": states[-0.5][1][winner, section],
                "p0.5": states[0.5][0][winner, section],
                "v0.5": states[0.5][1][winner, section],
            }
            for key, value in values.items():
                arrays[key].extend(value)
            key = (inventory["session_id"], episode_id)
            rows.append(
                {
                    "episode_index": episode_index,
                    "session_id": key[0],
                    "episode_id": key[1],
                    "norad": norad,
                    "observations": count,
                    "span_s": float(np.ptp(arc.time_s)),
                    "in_matched_622": key in matched,
                    "in_previous_export": key in legacy,
                    "passes_previous_length_gate": bool(
                        count >= PREVIOUS_MIN_OBSERVATIONS
                        and np.ptp(arc.time_s) >= PREVIOUS_MIN_SPAN_S
                    ),
                    "catalogue_candidates_before_geometry": causal_count,
                    "catalogue_candidates_after_geometry": len(valid_reference),
                    "training_best_rms_hz": float(score["best_train_rms_hz"][0]),
                    "heldout_best_rms_hz": float(score["best_test_rms_hz"][0]),
                    "training_log_bayes_factor": float(score["train_logbf"][0]),
                    "heldout_log_bayes_factor": float(score["heldout_logbf"][0]),
                    "signal_weight": float(score["signal_weight"][0]),
                }
            )
        print(session_index + 1, "/", len(paths), "tracklets", len(rows), flush=True)
    data = {key: np.asarray(value) for key, value in arrays.items()}
    _, data["pass_group"] = np.unique(
        np.column_stack([data["session"], data["norad"]]), axis=0, return_inverse=True
    )
    return data, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--legacy-evidence", type=Path, required=True)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--strict-inference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    states_path = args.output.with_suffix(".npz")
    if args.output.exists() or states_path.exists():
        raise ValueError("fresh output required")
    parent_path = args.parent / "inference.json" if args.parent.is_dir() else args.parent
    parent = json.loads(parent_path.read_text())
    strict = json.loads(args.strict_inference.read_text())
    shared = next(
        row
        for row in strict["models"]
        if row["selection"] == "all" and row["clock_model"] == "shared_recorded"
    )
    data, rows = associate(args.evidence, args.legacy_evidence, parent)
    cohorts = {
        "matched_622": [row["episode_index"] for row in rows if row["in_matched_622"]],
        "previous_export_684": [row["episode_index"] for row in rows if row["in_previous_export"]],
        "all_gate_length": [
            row["episode_index"] for row in rows if row["passes_previous_length_gate"]
        ],
        "all_leading_tracklets": [row["episode_index"] for row in rows],
    }
    region = Region(**parent["region"])
    models = []
    for cohort, episodes in cohorts.items():
        mask = np.isin(data["episode"], episodes)
        for weighting in ["observation", "pass"]:
            result = fit(
                data,
                region,
                parent["initial"],
                weighting,
                True,
                subset=mask,
                fit_clock=True,
                clock_bounds={0: shared["clock_bounds_s"][0]},
            )
            models.append(
                {
                    "method": "operational_catalogue_hard_association",
                    "cohort": cohort,
                    "selection": "all",
                    "clock_model": "shared_recorded",
                    **result,
                }
            )
            print(cohort, weighting, result["evaluation_rms_hz"], flush=True)
    output = {
        "schema": SCHEMA,
        "strictly_causal": True,
        "evaluation_location_used": False,
        "heldout_used_for_fitting_or_identity_selection": False,
        "conditional_association_position": {
            "source": "frozen causal wide-search model zero",
            "latitude_deg": parent["models"][0]["latitude_deg"],
            "longitude_deg": parent["models"][0]["longitude_deg"],
        },
        "catalogue_policy": (
            "Session operational catalogue with collection and element epoch strictly before "
            "capture; not the freshest-per-satellite archived composite."
        ),
        "geometry_prefilter_minimum_elevation_deg": MIN_ELEVATION_DEG,
        "identity_interpretation": (
            "Training-only hard best candidates conditional on the frozen seed; short-track "
            "identities are candidates, not independently validated labels."
        ),
        "source_hashes": {
            str(parent_path): digest(parent_path),
            str(args.strict_inference): digest(args.strict_inference),
        },
        "cohorts": {name: len(values) for name, values in cohorts.items()},
        "models": models,
        "tracks": rows,
    }
    np.savez_compressed(states_path, **data)
    output["states_digest"] = digest(states_path)
    write_json(args.output, output)


if __name__ == "__main__":
    main()
