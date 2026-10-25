"""Independent immutable-input membership reconstruction; no fitting or GPS."""
import hashlib
import json
from pathlib import Path

import numpy as np

from matched_controls import canonical, cohort, digest, load_baseline, measurement_binding
from probe_ds23_graph_seeded_paths import build

HERE = Path(__file__).resolve().parent


def main():
    cases = {}
    for case in cohort():
        d = load_baseline(case)
        p = build(d, "default", "c0", np.zeros(len(d["means"])))
        owners = {"curved": {}, "predictive": {}}
        for row, i, sl in zip(p.rows, p.members, p.slices, strict=True):
            family = int(row["candidate_index"])
            assert int(row["candidate_norad"]) == int(p.scan.norads[family])
            for local in np.flatnonzero(p.keep[sl]):
                oid = p.scan.tracks[i]["observation_ids"][int(local)]
                assert oid not in owners["curved"]
                owners["curved"][oid] = family
        for entry in d["entries"]:
            track = p.scan.tracks[entry["track_index"]]
            assert entry["observation_ids"] == track["observation_ids"]
            assert entry["points"] == len(track["times"])
            for oid in track["observation_ids"]:
                assert oid not in owners["predictive"]
                owners["predictive"][oid] = int(entry["candidate_index"])
        assert set(owners["curved"]).isdisjoint(owners["predictive"])
        families = sorted(set(owners["curved"].values()) | set(owners["predictive"].values()))
        native = d["scan"].fixed_window_noise
        cases[case] = dict(
            baseline_path=d["baseline_path"], baseline_sha256=d["baseline_sha256"],
            measurement_binding_sha256=measurement_binding(d),
            labels=[int(j) for j in p.labels],
            phase_prior_means_s=d["means"].tolist(),
            powers_sha256=hashlib.sha256(canonical(d["powers"])).hexdigest(),
            noise_sha256=hashlib.sha256(canonical(native)).hexdigest(),
            native_sigma=native["per_observation_noise_sigma_hz"],
            curved_points=len(owners["curved"]), predictive_points=len(owners["predictive"]),
            family_membership=[dict(candidate_index=j, norad=int(p.scan.norads[j]),
                curved_ids=sorted(oid for oid, owner in owners["curved"].items() if owner == j),
                predictive_ids=sorted(oid for oid, owner in owners["predictive"].items() if owner == j))
                for j in families],
        )
        print(case, len(families), len(owners["curved"]), len(owners["predictive"]), flush=True)
    output = HERE / "baseline_membership.json"
    assert not output.exists(), "Version new audits; preserve previous evidence"
    output.write_text(json.dumps(dict(status="passed", GPS_used=False, no_position_fitting=True,
        source_sha256=digest(Path(__file__)), cases=cases), indent=2) + "\n")


if __name__ == "__main__":
    main()
