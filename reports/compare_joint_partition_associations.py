"""Compare frozen identity mixtures without consulting a receiver reference position."""

import argparse
import hashlib
import itertools
import json
from pathlib import Path


def load_result(path):
    raw = path.read_bytes()
    checksum = hashlib.sha256(raw).hexdigest()
    if checksum != path.with_name("result.sha256").read_text().strip():
        raise ValueError("result checksum mismatch")
    result = json.loads(raw)
    if (result.get("position_truth_used") is not False
            or result.get("complete") is not True
            or result.get("selected", {}).get("converged") is not True):
        raise ValueError("complete converged blind result required")
    return result, "sha256:" + checksum


def indexed_tracks(result):
    tracks = {}
    for row in result["tracks"]:
        key = (row["session_id"], row["episode_id"])
        if key in tracks:
            raise ValueError("duplicate episode")
        tracks[key] = row
    return tracks


def leader(row):
    candidate = max(row["candidates"], key=lambda c: c["weight"], default=None)
    if candidate is None:
        return None, 0.0
    return candidate["norad"], candidate["weight"]


def compare(left, right):
    a, b = indexed_tracks(left), indexed_tracks(right)
    shared = sorted(a.keys() & b.keys())
    if not shared:
        raise ValueError("no common episodes")
    changed = []
    strong = 0
    strong_agree = 0
    for key in shared:
        an, aw = leader(a[key])
        bn, bw = leader(b[key])
        both_strong = aw >= 0.9 and bw >= 0.9
        strong += both_strong
        strong_agree += both_strong and an == bn
        if an != bn:
            changed.append({"session_id": key[0], "episode_id": key[1],
                            "left_norad": an, "left_weight": aw,
                            "right_norad": bn, "right_weight": bw,
                            "left_null": a[key]["null_weight"],
                            "right_null": b[key]["null_weight"]})
    return {"common_episodes": len(shared), "left_only": len(a)-len(shared),
            "right_only": len(b)-len(shared),
            "candidate_leader_agreement": len(shared)-len(changed),
            "both_weight_at_least_0_9": strong,
            "agreement_when_both_weight_at_least_0_9": strong_agree,
            "changed_candidate_leaders": changed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", action="append", nargs=2,
                        metavar=("LABEL", "PATH"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results, bindings = {}, {}
    for label, filename in args.result:
        if label in results:
            raise ValueError("duplicate result label")
        result, checksum = load_result(Path(filename))
        results[label] = result
        bindings[label] = {"path": filename, "sha256": checksum}
    output = {
        "schema": "joint-partition-association-comparison-v1",
        "reference_position_accessed": False,
        "interpretation": "Candidate agreement is stability, not identity ground truth. "
                          "Weights are uncalibrated composite scores. Null mass is separate.",
        "inputs": bindings,
        "summaries": {
            label: {"episodes": len(d["tracks"]),
                    "candidate_weight_at_least_0_9": sum(
                        leader(t)[1] >= 0.9 for t in d["tracks"]),
                    "null_weight_above_0_5": sum(t["null_weight"] > 0.5 for t in d["tracks"])}
            for label, d in results.items()},
        "comparisons": [{"left": a, "right": b, **compare(results[a], results[b])}
                        for a, b in itertools.combinations(results, 2)],
    }
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
