"""Independently bind the original likelihood membership without fitting."""
import hashlib
import json
from pathlib import Path

import numpy as np

from matched_controls import canonical, digest, load_baseline, measurement_binding
from probe_ds23_graph_seeded_paths import build


HERE = Path(__file__).resolve().parent
CASES = ("DS24-0017", "DS24-0095")


def main():
    cases = {}
    for case in CASES:
        d = load_baseline(case)
        p = build(d, "default", "c0", np.zeros(len(d["means"])))
        curved, predictive = {}, {}
        for row, i, sl in zip(p.rows, p.members, p.slices, strict=True):
            track = p.scan.tracks[i]
            family = int(row["candidate_index"])
            assert int(row["candidate_norad"]) == int(p.scan.norads[family])
            for local in np.flatnonzero(p.keep[sl]):
                oid = track["observation_ids"][int(local)]
                assert oid not in curved
                curved[oid] = family
        for entry in d["entries"]:
            track = p.scan.tracks[entry["track_index"]]
            assert entry["observation_ids"] == track["observation_ids"]
            assert entry["points"] == len(track["times"])
            for oid in entry["observation_ids"]:
                assert oid not in predictive
                predictive[oid] = int(entry["candidate_index"])
        assert set(curved).isdisjoint(predictive)
        families = sorted(set(curved.values()) | set(predictive.values()))
        noise = d["scan"].fixed_window_noise
        cases[case] = dict(
            baseline_path=d["baseline_path"], baseline_sha256=d["baseline_sha256"],
            original_measurement_binding_sha256=measurement_binding(d),
            active_curved_points=len(curved), predictive_points=len(predictive),
            inherited_noise_sha256=hashlib.sha256(canonical(noise)).hexdigest(),
            original_powers_sha256=hashlib.sha256(canonical(d["powers"])).hexdigest(),
            original_model=d["model"],
            original_phase_prior_means_s=d["means"].tolist(),
            family_membership=[dict(
                candidate_index=j, norad=int(p.scan.norads[j]),
                curved_observation_ids=sorted(oid for oid, family in curved.items() if family == j),
                predictive_observation_ids=sorted(oid for oid, family in predictive.items() if family == j),
            ) for j in families],
            every_original_likelihood_id_has_one_family=True,
            curved_and_predictive_likelihood_ids_disjoint=True,
        )
    result = dict(source_sha256=digest(Path(__file__)), no_position_fitting=True, GPS_used=False, cases=cases)
    output = HERE / "baseline_membership.json"
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({case: {k: v for k, v in data.items() if k in (
        "active_curved_points", "predictive_points", "original_measurement_binding_sha256",
    )} | {"families": len(data["family_membership"])} for case, data in cases.items()}, indent=2))


if __name__ == "__main__":
    main()
