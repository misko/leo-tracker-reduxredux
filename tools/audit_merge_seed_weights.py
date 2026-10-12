"""Read matched cached bootstrap seeds to expose sampling and weighting changes."""

import json
from pathlib import Path

import numpy as np
from band_calibrated_merge_study import LOCAL, REPORT
from continuous_merge_study import sha, write
from global_band_merge_study import verify

from leo.application.hard60_b7 import SharedPoints
from leo.contracts.digests import canonical_digest
from leo.storage.regional_position_checkpoints import RegionalCheckpointStore


def main():
    sid = "fast-43ce59233fe914e1d273ee584efcd405"
    case = LOCAL / "DS20" / sid / "global-transfer"
    protocol_path = case / "protocol.json"
    protocol = json.loads(protocol_path.read_bytes())
    verify(protocol)
    original = json.loads((case / "cal-original/terminal.json").read_bytes())
    point = next(f for f in original["result"]["finals"] if f["arm"] == "fitted-c")["basin"]
    rows = []
    for mode in ("cal-original", "cal-joined"):
        binding = canonical_digest({"experiment": protocol, "mode": mode})
        store = RegionalCheckpointStore(case / mode, sid, binding)
        receipt = SharedPoints(store).get(canonical_digest({}) + ":" + point)
        if not receipt or receipt["reason"] or receipt["result"] is None:
            raise ValueError("shared data-selected bootstrap point unavailable")
        seed = receipt["result"]["bootstrap"]
        coarse = receipt["result"]["fits"]["V16"]["fit"]
        matches = seed["matches"]
        support = [len(m["rows"]) for m in matches]
        rows.append(
            {
                "mode": mode,
                "point": point,
                "binding": binding,
                "satellite_indices": seed["satellite_indices"],
                "seed_vector": seed["vector"],
                "matches": len(matches),
                "row_occurrences": sum(support),
                "distinct_rows": len(set(r for m in matches for r in m["rows"])),
                "shape_sample_occurrences": sum(min(12, n) for n in support),
                "nominal_receiver_line_squared_weight": sum(
                    float(np.sqrt(min(n, 100))) for n in support
                ),
                "track_lengths": support,
                "timing_s": [m["timing_s"] for m in matches],
                "coarse_objective": coarse["objective"],
                "coarse_stationary": coarse["converged"],
                "coarse_vector": coarse["vector"],
            }
        )
    write(
        REPORT / "refinement/seed-sampling-and-weight-audit.json",
        {
            "session_id": sid,
            "protocol_sha256": sha(protocol_path),
            "script_sha256": sha(Path(__file__)),
            "rows": rows,
            "same_initial_bank": rows[0]["satellite_indices"] == rows[1]["satellite_indices"],
            "reference_usage": "none; point selected from original calibrated numerical output",
            "scope": (
                "Read-only public checkpoint port. Shape sampling uses 12 per proposal; "
                "nominal receiver-line squared weights sum sqrt(min(track_length,100)), "
                "before robust residual reweighting. No fit or evidence is changed."
            ),
        },
    )
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
