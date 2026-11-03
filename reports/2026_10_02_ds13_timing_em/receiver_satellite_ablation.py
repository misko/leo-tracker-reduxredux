"""Bounded, reference-informed diagnostic ablations, not benchmark contenders."""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from finite_set_fit import assert_snapshot_unchanged, snapshot_files
from finite_set_likelihood import prepare_finite_set_likelihood
from joint_inputs import _coordinates, _ecef
from prepare_scans import ROOT, load_scan
from rough_smoke import serializable
from soft_likelihood import SoftLikelihood
from soft_solvers import fit_soft

REMOVED_CATALOGUE = {"scan-fw-911c4e5db9243281": 58484, "scan-fw-ffa1cc19d8d7c09f": 65745}


class ReceiverSubset:
    def __init__(self, source, receiver):
        self.source = source
        mask = np.asarray(source.receiver) == receiver
        if not np.any(mask):
            raise ValueError("receiver has no rows")
        for name in ("times", "measured", "rf", "receiver", "channel", "group", "margin"):
            setattr(self, name, np.asarray(getattr(source, name))[mask].copy())

    def __getattr__(self, name):
        return getattr(self.source, name)


def detection_probabilities(numbers, omitted=None):
    probabilities = np.full(len(numbers), 0.8 / len(numbers))
    if omitted is not None:
        chosen = np.asarray(numbers) == omitted
        if chosen.sum() != 1:
            raise ValueError("omitted catalogue number must occur once")
        probabilities[chosen] = 0.
    return probabilities


def run_case(cell):
    session, variant = cell
    output = ROOT / "receiver-satellite-ablation" / f"{session}-{variant}.json"
    if output.exists():
        raise FileExistsError(output)
    parent_path = ROOT / "runs-continuation" / session / "medium" / "fit.json"
    reference_path = ROOT / "scans" / session / "evaluation.json"
    attribution_path = ROOT / "wrong-solution-attribution" / session / "attribution.json"
    parent = json.loads(parent_path.read_text())
    hashes = {**parent["source_hashes"], **snapshot_files(
        [__file__, parent_path, reference_path, attribution_path])}
    assert_snapshot_unchanged(hashes)
    _, data = load_scan(session)
    satellites = np.asarray(parent["fit"]["satellite_indices"], dtype=int)
    numbers = data.numbers[satellites]
    omitted = None
    if variant in ("rx0", "rx1"):
        data = ReceiverSubset(data, int(variant[-1]))
    elif variant == "omit":
        omitted = REMOVED_CATALOGUE[session]
    else:
        raise ValueError("unknown ablation")
    likelihood = SoftLikelihood(prepare_finite_set_likelihood(data.measured, data.group),
                                detection_probabilities(numbers, omitted))
    fitted = fit_soft(data, parent["fit"]["parameters"], satellites, likelihood,
                      200., budget_s=30.)
    reference = json.loads(reference_path.read_text())["reference_site"]
    location = _ecef(*_coordinates(np.asarray(fitted["parameters"])[:2]))
    truth = _ecef(reference["latitude_deg"], reference["longitude_deg"])
    original = _ecef(*_coordinates(np.asarray(parent["fit"]["parameters"])[:2]))
    result = {"schema": "ds13-receiver-satellite-ablation/v1", "session": session,
              "variant": variant, "omitted_catalog_number": omitted, "fit": fitted,
              "position_error_km": float(np.linalg.norm(location - truth)),
              "displacement_from_parent_km": float(np.linalg.norm(location - original)),
              "observation_count": len(data.times), "source_hashes": hashes,
              "reference_informed_diagnostic": True,
              "scope": "Receiver split or emitter deletion, selected after reference-informed "
                       "attribution. Not validation or a proposed satellite-exclusion policy. "
                       "Deletion sets detection probability to zero without deleting observations, "
                       "changing other probabilities, timing priors, parameter vector or gauge. "
                       "Absolute objectives are not compared between ablation models."}
    assert_snapshot_unchanged(hashes)
    output.parent.mkdir(exist_ok=True)
    with output.open("x") as stream:
        json.dump(serializable(result), stream, indent=2, allow_nan=False)
    return {key: result[key] for key in ("session", "variant", "omitted_catalog_number",
                                        "position_error_km", "displacement_from_parent_km")} | {
        "success": fitted["success"], "status": fitted["status"], "elapsed_s": fitted["elapsed_s"]}


if __name__ == "__main__":
    cells = [(session, variant) for variant in ("rx0", "rx1", "omit")
             for session in REMOVED_CATALOGUE]
    with ProcessPoolExecutor(max_workers=2) as executor:
        for result in executor.map(run_case, cells):
            print(json.dumps(result), flush=True)
