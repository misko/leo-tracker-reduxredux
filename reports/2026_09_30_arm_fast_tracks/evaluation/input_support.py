"""Oracle-assisted diagnosis only: never supplies hypotheses to a tracker."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
from compare_tracks import read_observations, read_tracks, read_source_map, circular_distance, sha256


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-tracks", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = Path(__file__).resolve().parents[1] / "server-baseline/output"
    ref = read_observations(base / "server-observations.tsv")
    arm = read_observations(base / "arm-observations.tsv")
    sources = read_source_map(base / "server-candidate-map.tsv", ref)
    arm_sources = read_source_map(base / "arm-candidate-map.tsv", arm)
    tracks = read_tracks(args.reference_tracks, ref).tracks
    by_source = defaultdict(list)
    for candidate, obs in arm.items():
        by_source[obs.lane, arm_sources[candidate]].append(obs)
    rows = []
    for track in tracks:
        scale = 11200000000 / track.lane.actual_rf_hz
        spacing = scale / 4.4e-6
        observed = []
        all_times = []
        distances = []
        for point in track.points:
            origin = ref[point.candidate_id]
            all_times.append(origin.center_ns)
            options = by_source[track.lane, sources[point.candidate_id]]
            errors = [circular_distance(
                option.measured_cfo_hz * scale -
                (track.intercept + track.rate * ((option.center_ns-track.reference_ns)*1e-9)),
                spacing) for option in options]
            best = min(errors, default=float("inf"))
            distances.append(best)
            if best <= 2500:
                observed.append(origin.center_ns)
        times = sorted(set(observed))
        duration = (max(all_times)-min(all_times))*1e-9
        rows.append({"reference_index": track.index, "reference_points": len(track.points),
                     "arm_sources_within_2500hz_of_reference_fit": len(times),
                     "fraction_within_2500hz": len(times)/len(track.points),
                     "fraction_within_5000hz": sum(d<=5000 for d in distances)/len(distances),
                     "supported_span_s": (times[-1]-times[0])*1e-9 if times else 0,
                     "reference_span_s": duration,
                     "max_gap_with_endpoints_s": max((b-a)*1e-9 for a,b in zip(
                         [min(all_times)]+times, times+[max(all_times)])),
                     "note": "Reference-conditioned support diagnostic, not recovered tracks."})
    report = {"reference_tracks_sha256": sha256(args.reference_tracks),
              "scope": "oracle-assisted input diagnosis only; detector data unchanged",
              "tracks": rows}
    args.output.write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps({"tracks":len(rows),
                     "at_least_80pct_support":sum(r["fraction_within_2500hz"]>=.8 for r in rows),
                     "at_least_6_points":sum(r["arm_sources_within_2500hz_of_reference_fit"]>=6 for r in rows),
                     "all_gaps_at_most_4s":sum(r["max_gap_with_endpoints_s"]<=4 for r in rows)}))


if __name__ == "__main__":
    main()
