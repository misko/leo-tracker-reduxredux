"""Compare frozen-association residuals across archived orbit updates, without truth."""

import argparse
import json
from pathlib import Path

import numpy as np
from replay_regional_doppler import digest, load_observations, state_arrays, write_json

from leo.sky.propagation import parse_element_sets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["run", "replay", "audit", "evidence", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("fresh output required")
    parent = json.loads((args.run / "inference.json").read_text())
    replay = json.loads(args.replay.read_text())
    audit = json.loads(args.audit.read_text())
    expected = digest(args.run / "inference.json")
    if replay["parent_digest"] != expected or audit["assignments_digest"] != expected:
        raise ValueError("parent mismatch")
    data = dict(np.load(args.run / "states.npz"))
    old = parent["models"][0]["segment_training_rms"]
    new = replay["models"][0]["segment_training_rms"]
    rows = []
    for i, (assignment, orbit) in enumerate(zip(parent["assignments"], audit["rows"], strict=True)):
        if any(assignment[k] != orbit[k] for k in ["session_id", "episode_id", "norad"]):
            raise ValueError("assignment mismatch")
        mask = data["episode"] == i
        segments = np.unique(data["segment"][mask])
        doc = json.loads(
            (args.evidence / "evidence" / (assignment["session_id"] + ".json")).read_text()
        )
        arc = dict(load_observations(doc, 0))[assignment["episode_id"]]
        if not np.array_equal(arc.frequency_hz, data["y"][mask]):
            raise ValueError("observation mismatch")
        p, v, valid = state_arrays(
            parse_element_sets(orbit["selected"]["text"]),
            [0],
            orbit["measurement_utc_ns"],
            arc.time_s,
        )
        if len(valid) != 1:
            raise ValueError("invalid orbit")
        rows.append(
            dict(
                **assignment,
                selected=assignment in parent["selected_assignments"],
                observations=int(mask.sum()),
                original_max_segment_training_rms_hz=max(old[str(s)] for s in segments),
                updated_max_segment_training_rms_hz=max(new[str(s)] for s in segments),
                median_orbit_displacement_km=float(
                    np.median(np.linalg.norm(p[0] - data["p"][mask], axis=1))
                ),
                nominal_age_h=(orbit["measurement_utc_ns"] - orbit["nominal_epoch_utc_ns"])
                / 3.6e12,
                updated_signed_age_h=(
                    orbit["measurement_utc_ns"] - orbit["selected"]["epoch_utc_ns"]
                )
                / 3.6e12,
            )
        )
    rows.sort(key=lambda r: r["updated_max_segment_training_rms_hz"], reverse=True)
    write_json(
        args.output,
        dict(
            evaluation_location_used=False,
            parent_digest=expected,
            replay_digest=digest(args.replay),
            audit_digest=digest(args.audit),
            rows=rows,
        ),
    )
    for r in rows[:8]:
        print(json.dumps(r), flush=True)


if __name__ == "__main__":
    main()
