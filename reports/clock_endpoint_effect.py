"""Exact endpoint timing sensitivity at a frozen blind position (diagnostic)."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

from leo.analysis.research.formal_orbit import doppler_hz
from leo.analysis.research.regional_doppler import Region
from leo.sky.propagation import parse_element_sets


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("refinement", "evidence", "clock-audit", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    result = json.loads(args.refinement.read_text())
    if result.get("position_truth_used") is not False:
        raise ValueError("blind result required")
    audit = json.loads(args.clock_audit.read_text())
    payload = dict(audit)
    checksum = payload.pop("content_digest")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if "sha256:" + hashlib.sha256(encoded.encode()).hexdigest() != checksum:
        raise ValueError("clock audit digest mismatch")
    clocks = {s["session_id"]: s for s in audit["sessions"]}
    path = Path(__file__).parents[1] / "tools/replay_regional_doppler.py"
    spec = importlib.util.spec_from_file_location("clock_replay", path)
    replay = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(replay)
    region = Region(**result["region"])
    selected = result["selected"]
    receiver = region.points([selected["east_km"]], [selected["north_km"]]).ecef_km[0]
    tracks = {(t["session_id"], t["episode_id"]): t for t in result["tracks"]}
    rows = []
    for session in result["sessions"]:
        path = args.evidence / "evidence" / (session + ".json")
        if digest(path) != clocks[session]["evidence_digest"]:
            raise ValueError("clock evidence binding mismatch")
        document = json.loads(path.read_text())
        metadata = document["inventory"]
        if metadata["reference_utc_ns"] != clocks[session]["reference_utc_ns"]:
            raise ValueError("clock reference mismatch")
        if Path(metadata["tle_file"]).name != metadata["tle_file"]:
            raise ValueError("unsafe TLE basename")
        tle = path.parent / metadata["tle_file"]
        if digest(tle) != metadata["tle_digest"]:
            raise ValueError("TLE digest mismatch")
        catalogue = parse_element_sets(tle.read_text())
        indices = {int(n): i for i, n in enumerate(catalogue.satellite_numbers)}
        for episode, arc in replay.load_observations(document, max_per_partition=0):
            candidate = max(tracks[session, episode]["candidates"], key=lambda c: c["weight"])
            if candidate["weight"] < .9:
                continue
            requested = [indices[candidate["norad"]]]
            predictions = []
            bounds = clocks[session]["allowed_clock_s_relative_to_reference"]
            for clock in (0, *bounds):
                p, v, retained = replay.state_arrays(
                    catalogue, requested, metadata["reference_utc_ns"], arc.time_s, clock_s=clock
                )
                if retained.tolist() != requested:
                    raise ValueError("propagation support changed")
                y = doppler_hz(receiver, p[0], v[0])
                predictions.append(y - np.mean(y[arc.training]))
            rows.append({
                "session_id": session, "episode_id": episode, "norad": candidate["norad"],
                "weight": candidate["weight"], "clock_bounds_s": bounds,
                "endpoint_changes": [
                    {
                        "heldout_rms_hz": float(
                            np.sqrt(np.mean((y-predictions[0])[~arc.training]**2))
                        ),
                        "maximum_absolute_change_hz": float(np.max(np.abs(y-predictions[0]))),
                    }
                    for y in predictions[1:]
                ],
            })
    output = {
        "scope": "exact clock endpoints at frozen blind position and top candidate weight >=.9",
        "not_an_interval_extremum_bound": True, "truth_used": False,
        "refinement_digest": digest(args.refinement), "audit_digest": digest(args.clock_audit),
        "source_digest": digest(Path(__file__)), "rows": rows,
    }
    with args.output.open("x") as stream:
        json.dump(output, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
