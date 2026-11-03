import json
from pathlib import Path

import numpy as np
from matching import ALIAS_HZ, assign_groups, circular_residual, connected_support, robust_line

ROOT = Path(__file__).resolve().parent


def summarize(assignment, data, numbers):
    coherent, segments = connected_support(
        assignment, data["times"], data["channel"], data["receiver"]
    )
    rows = assignment["rows"][coherent]
    for segment in segments:
        indices = np.array(segment["indices"])
        source_rows = assignment["rows"][indices]
        segment["catalog_number"] = int(numbers[segment["satellite_index"]])
        segment["new_source_groups"] = int(np.sum(~data["old_group"][source_rows]))
        segment["rms_hz"] = float(np.sqrt(np.mean(assignment["error_hz"][indices] ** 2)))
    summary = {
        "gate_and_margin_groups": int(assignment["accepted"].sum()),
        "coherent_groups": len(rows),
        "new_groups_outside_all_prior_tracks": int(np.sum(~data["old_group"][rows])),
        "groups_outside_prior_accepted_tracks": int(np.sum(~data["accepted_old_group"][rows])),
        "segments": segments,
    }
    return summary, coherent


def main():
    data = np.load(ROOT / "inputs.npz")
    metadata = json.loads((ROOT / "inputs.json").read_text())
    solution = metadata["solution"]
    times = data["times"]
    offsets = np.zeros(len(times))
    for receiver in (0, 1):
        selected = data["receiver"] == receiver
        parameters = solution["parameters"][str(receiver)]
        offsets[selected] = parameters["intercept_hz_at_150s"] + parameters["slope_hz_s"] * (
            times[selected] - 150
        )
    predictions = data["exact_fraction"] * data["rf"] + offsets
    residual = circular_residual(data["measured"], predictions)
    residual[data["exact_elevation"] < 0] = np.inf
    assignment = assign_groups(residual, data["group"])
    summary, coherent = summarize(assignment, data, data["selected_numbers"])
    target_index = int(np.flatnonzero(data["selected_numbers"] == 66891)[0])
    target_residual = residual[target_index].copy()
    target_residual[(data["channel"] != 1) | (data["receiver"] != 0)] = np.inf
    target_assignment = assign_groups(target_residual[None, :], data["group"])
    target_summary, target_coherent = summarize(target_assignment, data, np.array([66891]))
    target_summary["interpretation"] = (
        "Nonexclusive 66891 curve support on CH1/RX0; competing satellites are not rejected here"
    )
    all_prediction = (
        np.stack([np.interp(times, data["nodes"], fraction) for fraction in data["fractions"]])
        * data["rf"]
        + offsets
    )
    all_elevation = np.stack(
        [np.interp(times, data["nodes"], elevation) for elevation in data["elevations"]]
    )
    all_residual = circular_residual(data["measured"], all_prediction)
    all_residual[all_elevation < 0] = np.inf
    all_assignment = assign_groups(all_residual, data["group"])
    all_summary, all_coherent = summarize(all_assignment, data, data["numbers"])
    generator = np.random.default_rng(20261002)
    controls = []
    for _trial in range(20):
        shifts = generator.uniform(10000, ALIAS_HZ - 10000, (len(predictions), 1))
        control_residual = circular_residual(data["measured"], predictions + shifts)
        control_residual[data["exact_elevation"] < 0] = np.inf
        control_assignment = assign_groups(control_residual, data["group"])
        control_summary, _ = summarize(control_assignment, data, data["selected_numbers"])
        controls.append({key: value for key, value in control_summary.items() if key != "segments"})
    refinements = {}
    for receiver in (0, 1):
        group_indices = np.flatnonzero(
            coherent & (data["receiver"][assignment["rows"]] == receiver)
        )
        rows = assignment["rows"][group_indices]
        satellite_indices = assignment["satellites"][group_indices]
        observation_times = times[rows] - 150
        initial = solution["parameters"][str(receiver)]
        values = assignment["error_hz"][group_indices] + offsets[rows]
        training = (np.floor(times[rows] / 10).astype(int) % 3) != 2
        _, inverse, counts = np.unique(
            satellite_indices[training], return_inverse=True, return_counts=True
        )
        intercept, slope = robust_line(
            observation_times[training],
            values[training],
            1 / counts[inverse],
            (initial["intercept_hz_at_150s"], initial["slope_hz_s"]),
        )
        previous_errors = assignment["error_hz"][group_indices]
        updated_errors = values - intercept - slope * observation_times
        refinements[str(receiver)] = {
            "intercept_hz_at_150s": intercept,
            "slope_hz_s": slope,
            "training_groups": int(training.sum()),
            "evaluation_groups": int((~training).sum()),
            "evaluation_rms_before_hz": float(np.sqrt(np.mean(previous_errors[~training] ** 2))),
            "evaluation_rms_after_hz": float(np.sqrt(np.mean(updated_errors[~training] ** 2))),
        }
    result = {
        "session_id": metadata["session_id"],
        "protocol": {
            "gate_hz": 1000,
            "runner_separation_hz": 250,
            "max_gap_s": 4,
            "minimum_groups": 8,
            "minimum_span_s": 10,
            "position_frozen": True,
            "primary_offsets_frozen": True,
            "one_candidate_per_source_group": True,
            "controls": "20 per-satellite random constant frequency shifts, frozen parameters",
            "refinement": (
                "one RX-line-only polish on frozen selected-family assignments; 10s blocks; "
                "no reassignment; evaluation is selection-conditioned, not independent"
            ),
        },
        "selected_family": summary,
        "all_catalogue": all_summary,
        "target_66891_ch1_rx0": target_summary,
        "controls": controls,
        "raw_line_refinement": refinements,
    }
    (ROOT / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    np.savez_compressed(
        ROOT / "assignments.npz",
        **assignment,
        coherent=coherent,
        all_rows=all_assignment["rows"],
        all_satellites=all_assignment["satellites"],
        all_coherent=all_coherent,
        target_rows=target_assignment["rows"],
        target_error_hz=target_assignment["error_hz"],
        target_coherent=target_coherent,
    )
    print(
        json.dumps(
            {
                "selected_family": {
                    key: value for key, value in summary.items() if key != "segments"
                },
                "all_catalogue": {
                    key: value for key, value in all_summary.items() if key != "segments"
                },
                "control_coherent_range": [
                    min(row["coherent_groups"] for row in controls),
                    max(row["coherent_groups"] for row in controls),
                ],
                "refinement": refinements,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
