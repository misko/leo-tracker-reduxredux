"""Post-seal state summaries; configured position is never a selection input."""

import numpy as np
import qualify as source
import score_pilot
from leo.analysis.regional_position_score import coordinates, zero_sum_basis
from leo.contracts.regional_position import RegionalPrior


def distance_km(latitude, longitude, reference):
    a, b = np.radians([latitude, longitude])
    ra, rb = np.radians([reference["latitude_deg"], reference["longitude_deg"]])
    hav = np.sin((a - ra) / 2) ** 2 + np.cos(a) * np.cos(ra) * np.sin((b - rb) / 2) ** 2
    return float(2 * 6371.0088 * np.arcsin(np.sqrt(hav)))


def summarize():
    here = source.HERE
    directory = here / "inference_results"
    outcomes = list(score_pilot.sealed_rows(directory, "outcomes_seal.json", "outcomes"))
    predictions = {
        r["case"]: r["path"]
        for r in score_pilot.sealed_rows(directory, "predictions_seal.json", "predictions")
    }
    # Configured coordinates enter only after all four endpoint/prediction seals.
    reference_path = here.parents[2] / "deploy/station/gauss-r20-lt3d-004b-20261001-v1.json"
    reference = source.read(reference_path)
    terminal = source.read(source.ATTEMPT / "output/terminal.json")
    derivation = source.read(source.ATTEMPT / "derivation.json")
    recording = source.read(source.ATTEMPT / "training-input.json")["source"]
    if recording["radio_id"] != reference["radio_serial"]:
        raise ValueError("Configured radio identity differs")
    if (
        not reference["valid_from_utc_ns"]
        <= derivation["origin_utc_ns"]
        < reference["valid_until_utc_ns"]
    ):
        raise ValueError("Configured reference interval differs")
    prior = RegionalPrior(**terminal["provenance"]["prior"])
    center_path = source.ATTEMPT / "output/stages/shape-all.json"
    center = np.asarray(source.read(center_path)["result"]["winner"]["theta"][:2])
    rows = []
    for item in outcomes:
        outcome = source.read(item["path"])
        v = np.asarray(outcome["result"]["vector"])
        n = np.asarray(outcome["result"]["nuisance"])
        seed_v = np.asarray(outcome["original_seed"]["vector"])
        seed_n = np.asarray(outcome["original_seed"]["nuisance"])
        with np.load(predictions[item["case"]], allow_pickle=False) as p:
            q, numbers = p["detection_probability"], p["number"]
        relative = zero_sum_basis(len(numbers)) @ v[8:]
        lat, lon = coordinates(prior, v[:2])
        rows.append(
            dict(
                case=item["case"],
                latitude_deg=lat,
                longitude_deg=lon,
                configured_reference_distance_km=distance_km(lat, lon, reference),
                east_north_km=v[:2],
                movement_from_complete_seed_km=float(np.linalg.norm(v[:2] - seed_v[:2])),
                strict_audit=outcome["independent_endpoint_status"],
                inside_broad250km_disk=bool(np.linalg.norm(v[:2]) <= 250 + 1e-9),
                old_production_center_distance_km=float(np.linalg.norm(v[:2] - center)),
                inside_old_production25km_disk=bool(np.linalg.norm(v[:2] - center) <= 25 + 1e-9),
                common_timing_s=float(v[7]),
                relative_timing_s=relative,
                total_timing_s=v[7] + relative,
                relative_timing_rms_s=float(np.sqrt(np.mean(relative**2))),
                candidate_numbers=numbers,
                q=q,
                q_sum=float(q.sum()),
                absolute_band_offsets_hz=n[-2:],
                band_update_from_complete_seed_hz=n[-2:] - seed_n[-2:],
                fitted_c=float(v[6]),
                cost=outcome["cost"],
            )
        )
    source.save(
        here / "state_diagnostics.json",
        dict(
            rows=rows,
            reference_sha256=source.digest(reference_path),
            reference_evidence=reference["position_evidence"],
            reference_usage="After all four outcome/prediction seals; no seeding/selection",
            production_center_authority=dict(
                path=str(center_path), sha256=source.digest(center_path)
            ),
            qualifier_sha256=source.digest(here / "qualification.json"),
            outcomes_seal_sha256=source.digest(directory / "outcomes_seal.json"),
            predictions_seal_sha256=source.digest(directory / "predictions_seal.json"),
            no_new_objectives=True,
            fits=0,
        ),
    )


if __name__ == "__main__":
    summarize()
