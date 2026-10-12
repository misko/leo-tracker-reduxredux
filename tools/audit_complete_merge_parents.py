"""Profile every authoritative component parent at an existing bootstrap point.

This diagnostic reads frozen inputs and public checkpoint ports. It does not
change prior numerical products, proposal policies, or reference coordinates.
"""

import json
from pathlib import Path

import numpy as np
from band_calibrated_merge_study import LOCAL, REPORT
from continuous_merge_positions import load_prepared
from continuous_merge_study import plain, sha, write
from global_band_merge_study import verify

from leo.analysis.hard60_score import predict_orbits
from leo.analysis.lnb_band_calibration import calibrated_band_observations
from leo.analysis.persistent_hop_trajectory import reconstruct_persistent_hop_trajectories
from leo.analysis.regional_position_bootstrap import bootstrap_position
from leo.application.hard60_b7 import SharedPoints
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.contracts.digests import canonical_digest
from leo.contracts.regional_position import PositionOrbitBank, RegionalPrior
from leo.contracts.scanner_tracking import TrackingCandidate, TrackingInput, TrackingProbe
from leo.scanner.persistent_hop import Feature103DualRxTimingV3, PersistentHopUtcTimingAuthorityV1
from leo.storage.regional_position_checkpoints import RegionalCheckpointStore


def main():
    sid = "fast-43ce59233fe914e1d273ee584efcd405"
    case = LOCAL / "DS20" / sid / "global-transfer"
    protocol_path = case / "protocol.json"
    protocol = json.loads(protocol_path.read_bytes())
    verify(protocol)
    old = Path(protocol["original_case"])
    prepared = load_prepared(old / "baseline.json")
    source = json.loads((old / "source.json").read_bytes())
    timing_type = {1: PersistentHopUtcTimingAuthorityV1, 3: Feature103DualRxTimingV3}[
        source["timing"]["schema_version"]
    ]
    source["timing"] = timing_type.model_validate(source["timing"])
    source["probes"] = tuple(
        TrackingProbe(**{**p, "candidates": tuple(TrackingCandidate(**c) for c in p["candidates"])})
        for p in source["probes"]
    )
    candidates = {c.candidate_id: c for c in project_scanner_candidates(TrackingInput(**source))}
    trajectory = reconstruct_persistent_hop_trajectories(
        tuple(candidates[c] for c in prepared.candidate_ids)
    )
    lookup = {identity: i for i, identity in enumerate(prepared.candidate_ids)}
    tracks = {
        t.tracklet_id: tuple(lookup[p.candidate_id] for p in t.points) for t in trajectory.tracklets
    }
    components = json.loads((old / "census.json").read_bytes())["variants"]["replace-guard"][
        "components"
    ]
    terminal = json.loads((case / "cal-original/terminal.json").read_bytes())
    point_key = next(f for f in terminal["result"]["finals"] if f["arm"] == "fitted-c")["basin"]
    point = tuple(float(v) for v in point_key.split(":")[1:])
    cached = {}
    for mode in ("cal-original", "cal-joined"):
        binding = canonical_digest({"experiment": protocol, "mode": mode})
        receipt = SharedPoints(RegionalCheckpointStore(case / mode, sid, binding)).get(
            canonical_digest({}) + ":" + point_key
        )
        if not receipt or receipt["reason"] or receipt["result"] is None:
            raise ValueError("selected checkpoint unavailable")
        cached[mode] = receipt["result"]["bootstrap"]
    pool = list(prepared.bootstrap_tracks)
    for component in components:
        pool.extend(tracks[identity] for identity in component["member_ids"])
    pool.extend(tuple(m["rows"]) for m in cached["cal-joined"]["matches"])
    pool = tuple(dict.fromkeys(pool))
    with np.load(protocol["bank_path"]) as z:
        bank = PositionOrbitBank(**{key: z[key] for key in z.files})
    results = []
    for calibration in (False, True):
        observations, _ = calibrated_band_observations(
            prepared.observations,
            protocol["fixed_band_offsets_hz"] if calibration else (0.0, 0.0),
        )
        fit = bootstrap_position(
            observations,
            bank,
            RegionalPrior(),
            point,
            pool,
            maximum_seconds=120,
            orbit_predictor=predict_orbits,
        )
        matches = {tuple(m.rows): m for m in fit.matches}
        selected = set(prepared.bootstrap_tracks)
        for component in components:
            parents = []
            component_rows = set()
            for identity in component["member_ids"]:
                rows = tracks[identity]
                component_rows.update(rows)
                match = matches.get(rows)
                parents.append(
                    {
                        "tracklet_id": identity,
                        "rows": rows,
                        "selected_original": rows in selected,
                        "channel": int(observations.channel[rows[0]]),
                        "receiver": int(observations.receiver[rows[0]]),
                        "time_range_s": [
                            float(observations.times_s[rows[0]]),
                            float(observations.times_s[rows[-1]]),
                        ],
                        "match": plain(match),
                        "catalogue_number": (
                            int(bank.numbers[match.satellite_index]) if match else None
                        ),
                    }
                )
            joined = [
                m
                for m in cached["cal-joined"]["matches"]
                if set(m["rows"]) <= component_rows
                and sum(bool(set(m["rows"]) & set(p["rows"])) for p in parents) > 1
            ]
            results.append(
                {
                    "calibrated": calibration,
                    "lane": component["lane"],
                    "parents": parents,
                    "joined_matches_at_cached_calibrated_point": joined,
                    "profiled_joined_matches": [
                        plain(matches.get(tuple(m["rows"]))) for m in joined
                    ],
                }
            )
    write(
        REPORT / "refinement/complete-parent-audit.json",
        {
            "session_id": sid,
            "protocol_sha256": sha(protocol_path),
            "script_sha256": sha(Path(__file__)),
            "point": point_key,
            "pool_tracks": len(pool),
            "reference_usage": "none; point selected from existing calibrated original output",
            "scope": (
                "Same point, full initial bank, shape sampler and timing search; raw/calibrated "
                "profiles of every contributing original parent, including those outside the "
                "selected quota. No inference policy or existing products changed."
            ),
            "rows": results,
        },
    )
    for row in results:
        print(
            json.dumps(
                {
                    "calibrated": row["calibrated"],
                    "lane": row["lane"],
                    "parents": [
                        {k: p[k] for k in ("selected_original", "catalogue_number", "time_range_s")}
                        | {
                            "length": len(p["rows"]),
                            "shape_rms_hz": (p["match"] or {}).get("shape_rms_hz"),
                        }
                        for p in row["parents"]
                    ],
                    "joined": [
                        {
                            "length": len(m["rows"]),
                            "catalogue_number": int(bank.numbers[m["satellite_index"]]),
                            "shape_rms_hz": m["shape_rms_hz"],
                        }
                        for m in row["profiled_joined_matches"]
                        if m
                    ],
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
