"""Bounded Model C native-CFO/history research on sealed DS21 development data."""

import argparse
import json
import time
from pathlib import Path

import numpy as np
from ds20_channel_corpus import digest
from ds21_common import OUTPUT, immutable, load_case
from joint_association_native import native_branch_inputs

from leo.analysis.channel_group_calibration import GroupCalibrationObjective, fit_group_calibration
from leo.analysis.frozen_group_calibration import freeze_group_calibration
from leo.analysis.hard60_score import likelihood as wrapped_likelihood
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.joint_association_sparse import SparseNativeJointObjective
from leo.analysis.regional_position_score import ALIAS_HZ
from leo.application.channel_group_refinement import carried_seed
from leo.application.hard60_runner import HARD60_SCORE


def objective(case, source, observations, waveform_rows=()):
    ids = {row["candidate_id"] for row in waveform_rows}
    # Filter measured rows by view through actual projected native identities.
    from leo.application.scanner_trajectory import project_scanner_candidates

    view_ids = {
        p.candidate_id
        for p in project_scanner_candidates(source)
        if p.source_group_id in observations.window_ids
    }
    waveform_rows = [row for row in waveform_rows if row["candidate_id"] in view_ids & ids]
    evidence, families, labels = native_branch_inputs(
        source, observations, waveform_rows=waveform_rows
    )
    base = SparseNativeJointObjective(
        observations,
        case["bank"],
        case["prior"],
        HARD60_SCORE,
        sample_rate_hz=case["source"].sample_rate_hz,
        branch_evidence=evidence,
        family_keys=families,
        maximum_gap_s=case["source"].probe_ms / 1000 * 1.25,
    )
    model = GroupCalibrationObjective(base, observations.channel >= 5)
    return model, dict(
        native_branch_labels=labels,
        native_candidates=int(evidence.available.sum()),
        measured_waveform_candidates=int(evidence.waveform_measured.sum()),
        missing_waveform_candidates=int((evidence.available & ~evidence.waveform_measured).sum()),
        continuity_families=len(base.families),
        temporal_edges=sum(len(f) - 1 for f in base.families),
        sampling_period_hz=base.sample_rate_hz,
    )


def held_prediction(case, source, observations, training_model, fit):
    model, metadata = objective(case, source, observations)
    correction = freeze_group_calibration(training_model, fit)
    v = np.asarray(fit["vector"])
    shifts = v[7] + training_model.basis @ v[8:]
    prediction, visible = [], []
    for obs in model.base.branch_observations:
        values = predict_orbits(case["bank"], obs, case["prior"], v[:2], shifts, derivatives=False)
        prediction.append(
            values[0]
            + correction.predict(obs.times_s, obs.rf_hz, obs.receiver, obs.channel >= 5)[:, None]
        )
        visible.append(values[1])
    terms, _ = model.base.likelihood(np.stack(prediction, axis=2), np.stack(visible, axis=2))
    return dict(
        windows=len(observations.window_ids),
        nll=terms.nll,
        nll_per_window=terms.nll / len(observations.window_ids),
        signal_windows=float(terms.responsibilities.sum()),
        clutter_windows=float(terms.clutter_probability.sum()),
        window_ids=observations.window_ids,
        metadata=metadata,
        held_fitting="none; training correction function, position and timing frozen",
    )


def physical_receiver_branches(model, seed):
    """Choose one receiver-wide ambiguity integer from confident training rows.

    This initializes the native-frequency objective; it supplies no new identity
    truth. Groups share the same receiver integer, and both c arms share it.
    """
    obs = model.observations
    vector = np.asarray(seed["vector"])
    shifts = vector[7] + model.basis @ vector[8:]
    prediction, visible, _, _ = predict_orbits(model.bank, obs, model.prior, vector[:2], shifts)
    prediction += model.correction(vector, seed["nuisance"])[:, None]
    terms = wrapped_likelihood(obs.measured_hz, prediction, visible, HARD60_SCORE)
    selected = terms.responsibilities.argmax(axis=1)
    confidence = terms.responsibilities[np.arange(len(selected)), selected]
    raw = obs.measured_hz - prediction[np.arange(len(selected)), selected]
    integers = np.floor(raw / ALIAS_HZ + 0.5).astype(int)
    result = []
    for receiver in (0, 1):
        mask = (obs.receiver == receiver) & (confidence > 0.5)
        values, counts = np.unique(integers[mask], return_counts=True)
        mode = int(values[counts.argmax()]) if len(values) else 0
        result.append(
            dict(
                receiver=receiver,
                integer=mode,
                confident_windows=int(mask.sum()),
                modal_fraction=float(counts.max() / mask.sum()) if mask.any() else None,
            )
        )
    return result


def run(label, *, maximum_seconds=500, waveform_path=None):
    started = time.monotonic()
    case = load_case(label)
    variant = "joint-native-neutral-v2" if waveform_path is None else "joint-native-waveform-v2"
    directory = OUTPUT / "local" / variant / label
    terminal = directory / "terminal.json"
    if terminal.exists():
        return json.loads(terminal.read_bytes())
    waveform_rows = []
    if waveform_path is not None:
        waveform = json.loads(waveform_path.read_bytes())
        if waveform["label"] != label or waveform["prepared_sha256"] != (
            case["prepared"]["all"].evidence_sha256
        ):
            raise ValueError("Measured waveform receipt does not bind the native training input")
        waveform_rows = waveform["branch_evidence"]
    protocol = dict(
        model="C",
        policy=variant,
        label=label,
        shared_discovery_sha256=case["protocol_sha256"],
        prepared={view: p.evidence_sha256 for view, p in case["prepared"].items()},
        catalogue_numbers=case["bank"].numbers.tolist(),
        waveform_sha256=None if waveform_path is None else digest(waveform_path),
        sampling_period_hz=case["source"].sample_rate_hz,
        signal_stay=0.95,
        clutter_stay=0.5,
        continuity="receiver/channel/visit/RF; reset retunes and >1.25 native probe durations",
        fit_seconds=20,
        iterations=600,
        starts=3,
        c_arms=["fitted-c", "zero-c"],
        nuisance="receiver affine offsets/drifts; RF c; constant receiver group contrasts",
        receiver_branch_start="Modal confident wrapped all-training integer per RX; shared groups",
        reference_usage="none",
        held_selection="none",
        sources={
            str(path): digest(path)
            for path in (
                Path(__file__),
                Path(__file__).with_name("joint_association_native.py"),
                Path(__file__).parents[1] / "src/leo/analysis/joint_association_graph.py",
                Path(__file__).parents[1] / "src/leo/analysis/joint_association_score.py",
                Path(__file__).parents[1] / "src/leo/analysis/joint_association_sparse.py",
            )
        },
    )
    immutable(directory / "protocol.json", protocol)
    for filename, source_hash in protocol["sources"].items():
        source = Path(filename)
        saved = directory / "source-snapshot" / source.name
        saved.parent.mkdir(parents=True, exist_ok=True)
        if not saved.exists():
            saved.write_bytes(source.read_bytes())
        if digest(saved) != source_hash or digest(source) != source_hash:
            raise ValueError("Joint association source snapshot differs from its sealed protocol")
    all_model, _ = objective(
        case, case["split"].training, case["prepared"]["all"].observations, waveform_rows
    )
    receiver_branches = []
    for row in case["discovery"]["selected"]:
        seed = carried_seed(
            row,
            case["discovery"]["selected"],
            all_model,
            case["prepared"],
            case["full_bank"],
            case["prior"],
            case["nodes"],
            True,
        )
        receiver_branches.append(physical_receiver_branches(all_model, seed))
    immutable(directory / "receiver-branch-starts.json", receiver_branches)
    results = {}
    for view, prepared in case["prepared"].items():
        model, metadata = objective(
            case, case["split"].training, prepared.observations, waveform_rows
        )
        attempts = {arm: [] for arm in protocol["c_arms"]}
        for index, row in enumerate(case["discovery"]["selected"]):
            seed = carried_seed(
                row,
                case["discovery"]["selected"],
                model,
                case["prepared"],
                case["full_bank"],
                case["prior"],
                case["nodes"],
                True,
            )
            for branch in receiver_branches[index]:
                seed["vector"][2 + 2 * branch["receiver"]] += branch["integer"] * ALIAS_HZ
            for arm in attempts:
                path = directory / "attempts" / f"{view}-{index}-{arm}.json"
                if path.exists():
                    cached = json.loads(path.read_bytes())
                    if cached["protocol_sha256"] != digest(directory / "protocol.json"):
                        raise ValueError("Cached joint association fit belongs to another protocol")
                    fit = cached["fit"]
                else:
                    if time.monotonic() - started + protocol["fit_seconds"] >= maximum_seconds:
                        return dict(
                            state="checkpointed",
                            next=str(path),
                            elapsed_s=time.monotonic() - started,
                        )
                    try:
                        fit = fit_group_calibration(
                            model,
                            seed["vector"],
                            seed["nuisance"],
                            arm=arm,
                            seconds=protocol["fit_seconds"],
                            iterations=protocol["iterations"],
                            local_center=seed["vector"][:2],
                            local_radius_km=25,
                        )
                    except (ValueError, TimeoutError) as error:
                        fit = dict(converged=False, reason=str(error))
                    immutable(
                        path, dict(protocol_sha256=digest(directory / "protocol.json"), fit=fit)
                    )
                attempts[arm].append(dict(start=index, fit=fit))
                print(
                    json.dumps(
                        dict(
                            label=label,
                            view=view,
                            arm=arm,
                            start=index,
                            converged=fit["converged"],
                            elapsed_s=time.monotonic() - started,
                        )
                    ),
                    flush=True,
                )
        selected = {}
        for arm, rows in attempts.items():
            valid = [row for row in rows if row["fit"]["converged"]]
            if not valid:
                selected[arm] = dict(state="unavailable", reason="No stationary inference")
                continue
            winner = min(valid, key=lambda row: (row["fit"]["objective"], row["start"]))
            selected[arm] = dict(
                **winner,
                held_prediction=held_prediction(
                    case, case["split"].held, case["held"][view], model, winner["fit"]
                ),
            )
        results[view] = dict(attempts=attempts, selected=selected, metadata=metadata)
    result = dict(
        protocol_sha256=digest(directory / "protocol.json"),
        results=results,
        reference_usage="none",
        elapsed_s=time.monotonic() - started,
    )
    if any(digest(Path(filename)) != sha for filename, sha in protocol["sources"].items()):
        raise ValueError("Joint association source changed before inference seal")
    immutable(terminal, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--maximum-seconds", type=float, default=500)
    parser.add_argument("--waveform-path", type=Path)
    args = parser.parse_args()
    result = run(args.label, maximum_seconds=args.maximum_seconds, waveform_path=args.waveform_path)
    print(
        json.dumps(
            dict(
                label=args.label, state=result.get("state", "sealed"), elapsed_s=result["elapsed_s"]
            )
        )
    )
