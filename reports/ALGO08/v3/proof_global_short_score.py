"""Score the already sealed reduced-rank replay against the physical reference."""

import argparse
from hashlib import sha256
from pathlib import Path

from aperture_trial import ARMS, read, write
from dense_quadratic_proxy_score import owner_deltas
from proof_global_short_trial import CONTROL_SHA, checked


REFERENCE_SHA = "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5"


def score(control_path, candidate_path, selection, output):
    from tools.pipeline_eval.scoring import distance_km

    control = checked(control_path, CONTROL_SHA)
    sealed = read(selection)
    candidate = checked(candidate_path, sealed["candidate_sha256"])
    reference = Path(__file__).resolve().parents[2] / "2026_11_21_ds30_full/reference-audit.json"
    row, = [record for record in checked(reference, REFERENCE_SHA)["cases"] if record["dataset_label"] == "DS30-0008"]
    if not row["authority_eligible"]:
        raise ValueError("The physical reference lacks the frozen scoring authority")
    truth = [row["reference"][field] for field in ("latitude_deg", "longitude_deg")]
    proof_owners = {label for probe in candidate["visited_probes"] for label in probe["owners"].values() if label is not None}
    arms = {}
    for arm in ARMS:
        before, after = control["arms"][arm]["latlon"], candidate["arms"][arm]["latlon"]
        owners = control["selected_rows"][arm], candidate["selected_rows"][arm]
        removed = {r[1] for r in owners[0]} - {r[1] for r in owners[1]}
        arms[arm] = dict(control_error_km=distance_km(before, truth), candidate_error_km=distance_km(after, truth),
                         endpoint_shift_km=distance_km(before, after), owners=owner_deltas(*owners),
                         lost_families=sorted(removed), lost_families_present_in_proof=sorted(removed & proof_owners))
    cold = {name: row["attempts"][0]["cold"] for name, row in (("control", control), ("candidate", candidate))}
    write(output, dict(frozen_selection_sha256=sha256(selection.read_bytes()).hexdigest(),
                       reference_sha256=REFERENCE_SHA, scored=arms, proof_union_size=len(proof_owners),
                       cold={name: dict(branch=row["branch"], routing=row["routing"], refined_scores=row["scores"])
                             for name, row in cold.items()}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("control_path", "candidate_path", "selection", "output"):
        parser.add_argument(name, type=Path)
    score(**vars(parser.parse_args()))
