"""Attribute the free-versus-known-site loss gap without changing fitted states."""

from __future__ import annotations

import json

import numpy as np
from finite_set_fit import assert_snapshot_unchanged, snapshot_files
from finite_set_likelihood import circular_residual, prepare_finite_set_likelihood
from prepare_scans import ROOT, load_scan
from rough_smoke import serializable
from soft_likelihood import SoftLikelihood
from timing_model import TimingObjective


def group_metadata(data, prepared):
    first = np.array([rows[0] for rows in prepared.group_row_indices], dtype=int)
    for name in ("receiver", "channel", "times"):
        values = np.asarray(getattr(data, name))
        for rows in prepared.group_row_indices:
            if np.any(values[rows] != values[rows[0]]):
                raise ValueError(f"group-inconsistent {name}")
    return {name: np.asarray(getattr(data, name))[first] for name in
            ("receiver", "channel", "times")}


def gap_bins(gap, metadata):
    time_bins = np.floor(metadata["times"] / 30).astype(int)
    output = []
    keys = np.column_stack((metadata["receiver"], metadata["channel"], time_bins))
    for receiver, channel, time_bin in np.unique(keys, axis=0):
        selected = np.all(keys == [receiver, channel, time_bin], axis=1)
        output.append({"receiver": int(receiver), "channel": int(channel),
                       "start_s": int(time_bin * 30), "groups": int(selected.sum()),
                       "free_advantage_nll": float(np.sum(gap[selected]))})
    return output


def weighted_residual_summary(residual, weights):
    total = float(np.sum(weights))
    if total <= 0:
        return {"support": 0., "mean_hz": None, "rms_hz": None}
    return {"support": total, "mean_hz": float(weights @ residual / total),
            "rms_hz": float(np.sqrt(weights @ residual**2 / total))}


def run(session):
    output = ROOT / "wrong-solution-attribution" / session
    if output.exists():
        raise FileExistsError(output)
    source, data = load_scan(session)
    seed_path = ROOT / "scans" / session / "seed.json"
    seed = json.loads(seed_path.read_text())
    free_path = ROOT / "runs-continuation" / session / "medium" / "fit.json"
    oracle_path = ROOT / "oracle-diagnostic" / f"{session}-warm.json"
    free_record, oracle_record = (json.loads(path.read_text()) for path in
                                  (free_path, oracle_path))
    inherited = {**free_record["source_hashes"], **oracle_record["source_hashes"]}
    assert_snapshot_unchanged(inherited)
    hashes = {**inherited, **snapshot_files([__file__, seed_path, free_path, oracle_path])}
    satellites = np.asarray(seed["satellites"], dtype=int)
    prepared = prepare_finite_set_likelihood(data.measured, data.group)
    probability = 0.8 / len(satellites)
    states = {}
    for name, record in (("free", free_record), ("oracle", oracle_record)):
        likelihood = SoftLikelihood(prepared, probability)
        objective = TimingObjective(data, seed["initial"], satellites, likelihood, 200.)
        vector = np.asarray(record["fit"]["vector"])
        value, gradient = objective.evaluate(vector)
        prediction, visibility, jacobian = objective.predict(vector, with_jacobian=True)
        if not np.isclose(value, record["fit"]["objective"], rtol=0, atol=1e-6):
            raise ValueError("sealed fit did not reproduce")
        states[name] = {"value": value, "gradient": gradient, "objective": objective,
                        "prediction": prediction, "visibility": visibility,
                        "jacobian": jacobian, "likelihood": likelihood.last_result,
                        "residual": circular_residual(data.measured[:, None], prediction)}
    free, oracle = states["free"], states["oracle"]
    group_gap = free["likelihood"]["log_likelihood"] - oracle["likelihood"]["log_likelihood"]
    metadata = group_metadata(data, prepared)
    total_data_gap = float(group_gap.sum())
    satellite_rows = []
    for column, satellite in enumerate(satellites):
        keep = np.arange(len(satellites)) != column
        omitted = {}
        for name, state in states.items():
            value = prepared.evaluate(
                state["prediction"][:, keep], state["visibility"][:, keep], sigma_hz=200.,
                detection_probability=probability, clutter_rate=2.,
            )
            omitted[name] = value["total_log_likelihood"]
        masked_gradient = np.zeros_like(oracle["prediction"])
        masked_gradient[:, column] = -oracle["likelihood"]["prediction_gradient"][:, column]
        position_gradient = oracle["jacobian"].transpose_multiply(masked_gradient.ravel())[:2]
        row = {"catalog_number": int(data.numbers[satellite]), "satellite_index": int(satellite),
               "position_gradient_at_oracle": position_gradient,
               "fixed_state_component_removal_gap_change": total_data_gap - (
                   omitted["free"] - omitted["oracle"]),
               "total_timing_s": {name: record["fit"]["total_shifts_s"][column]
                                  for name, record in (("free", free_record),
                                                       ("oracle", oracle_record))}}
        for name, state in states.items():
            weights = state["likelihood"]["row_association_probability"][:, column]
            row[name] = weighted_residual_summary(state["residual"][:, column], weights)
            row[name]["confident_rows"] = int(np.sum(weights >= 0.8))
            row[name]["per_receiver"] = {}
            for receiver in (0, 1):
                chosen = data.receiver == receiver
                row[name]["per_receiver"][str(receiver)] = weighted_residual_summary(
                    state["residual"][chosen, column], weights[chosen])
        satellite_rows.append(row)
    summed = np.sum([row["position_gradient_at_oracle"] for row in satellite_rows], axis=0)
    np.testing.assert_allclose(summed, oracle["gradient"][:2], atol=1e-8)
    track_rows = []
    for track in seed["rough"]["assignments"]:
        column = np.flatnonzero(satellites == track["satellite_index"])[0]
        rows = np.flatnonzero(np.isin(data.original_rows, track["rows"]))
        row = {"track_index": track["track_index"], "catalog_number": track["catalog_number"],
               "receiver": track["receiver"], "span_s": track["span_s"],
               "track_source_rows": len(track["rows"]), "exact_representative_overlap": len(rows)}
        for name, state in states.items():
            weights = state["likelihood"]["row_association_probability"][rows, column]
            row[name] = {"mean_association": float(weights.mean()) if len(rows) else None,
                         "confident_rows": int(np.sum(weights >= 0.8)),
                         "median_absolute_residual_hz": float(np.median(
                             np.abs(state["residual"][rows, column]))) if len(rows) else None}
        track_rows.append(row)
    bins = gap_bins(group_gap, metadata)
    np.testing.assert_allclose(sum(row["free_advantage_nll"] for row in bins), total_data_gap)
    result = {"schema": "ds13-wrong-solution-attribution/v1", "session": session,
              "reference_used": True, "source_hashes": hashes,
              "scope": "Fixed-parameter comparisons, not leave-one-satellite-out refits. "
                       "Component removal retains original per-satellite detection probability; "
                       "its gap changes overlap and are not additive. Oracle is a local profile.",
              "free_objective": free["value"], "oracle_objective": oracle["value"],
              "data_gap": total_data_gap,
              "prior_gap": oracle["value"] - free["value"] - total_data_gap,
              "free_position_gradient_at_oracle": oracle["gradient"][:2],
              "satellites": satellite_rows, "seed_track_agreement": track_rows,
              "receiver_channel_time_bins": bins,
              "positive_gap_groups": int(np.sum(group_gap > 0)),
              "negative_gap_groups": int(np.sum(group_gap < 0)),
              "strong_winner_changed_rows": int(np.sum(
                  (free["likelihood"]["row_association_probability"].max(axis=1) >= 0.8)
                  & (oracle["likelihood"]["row_association_probability"].max(axis=1) >= 0.8)
                  & (free["likelihood"]["row_association_probability"].argmax(axis=1)
                     != oracle["likelihood"]["row_association_probability"].argmax(axis=1))))}
    assert_snapshot_unchanged(hashes)
    output.mkdir(parents=True, exist_ok=False)
    with (output / "attribution.json").open("x") as stream:
        json.dump(serializable(result), stream, indent=2, allow_nan=False)
    np.savez_compressed(output / "evidence.npz", times=data.times, receiver=data.receiver,
                        channel=data.channel, measured=data.measured, group=data.group,
                        catalog_numbers=data.numbers[satellites],
                        free_prediction=free["prediction"], oracle_prediction=oracle["prediction"],
                        free_posterior=free["likelihood"]["row_association_probability"],
                        oracle_posterior=oracle["likelihood"]["row_association_probability"],
                        group_gap=group_gap, **{f"group_{key}": value
                                              for key, value in metadata.items()})
    return {"session": session, "data_gap": total_data_gap,
            "largest_components": sorted(satellite_rows, key=lambda row:
                                         -row["fixed_state_component_removal_gap_change"])[:4]}


if __name__ == "__main__":
    for session in json.loads((ROOT / "protocol-soft.json").read_text())["sessions"]:
        print(json.dumps(serializable(run(session))), flush=True)
