#!/usr/bin/env python3
import hashlib
import json
import math
import sys


if len(sys.argv) != 4:
    raise SystemExit(
        "usage: compare_recomputed_partitions.py ORACLE-TRACKS.json GRAPH.tsv PIPELINE.tracks.tsv"
    )


def digest(value):
    payload = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


oracle = json.load(open(sys.argv[1], encoding="utf-8"))
graph = {}
with open(sys.argv[2], encoding="utf-8") as source:
    metadata = source.readline().rstrip("\n").split("\t")
    if len(metadata) != 4 or metadata[0] != "META":
        raise RuntimeError("invalid graph metadata")
    if not source.readline().startswith("candidate_id\t"):
        raise RuntimeError("invalid graph header")
    for line in source:
        row = line.rstrip("\n").split("\t")
        if len(row) != 8 or row[0] in graph:
            raise RuntimeError("invalid graph row")
        graph[row[0]] = {
            "start": int(row[1]),
            "center": int(row[2]),
            "end": int(row[3]),
            "moments": [float(item) for item in row[4:8]],
        }

actual = {}
current = None
with open(sys.argv[3], encoding="utf-8") as source:
    for line in source:
        row = line.rstrip("\n").split("\t")
        if row[0] == "TRACK":
            if len(row) != 6 or row[2] in actual:
                raise RuntimeError("invalid pipeline track")
            current = {
                "support_digest": row[3],
                "partition_seed": row[4],
                "count": int(row[5]),
                "observation_ids": [],
                "mask": [],
            }
            actual[row[2]] = current
        elif row[0] == "POINT":
            if current is None or len(row) != 6:
                raise RuntimeError("invalid pipeline point")
            current["observation_ids"].append(row[2])
            current["mask"].append(int(row[5]))
        else:
            raise RuntimeError("invalid pipeline evidence record")

dwell = digest(
    {
        "algorithm_version": "persistent-hop-normalized-hough-episode-graph-v1",
        "input_manifest_digest": oracle["input_manifest_sha256"],
        "session_id": oracle["session_id"],
    }
)
protocol = digest(
    {
        "algorithm": "scanner-shared-tracking-v12",
        "catalogue": "exclude-labelled-debris-and-sgp4-failures-before-response-v1",
        "group_limit": 4,
        "observer": {"mode": "fixed", "salt": "cf510316-fixed-partition-v1"},
        "selection": "eligible-first-longest-support-v1",
        "trajectory": oracle["config_digest"],
        "utc_qualification_limit_ns": 2_000_000_000,
    }
)

shared = support_exact = seed_exact = ids_exact = mask_exact = 0
for track in oracle["tracks"]:
    tracklet_id = track["tracklet_id"]
    if tracklet_id not in actual:
        continue
    shared += 1
    episode = digest({"dwell_id": dwell, "tracklet_id": tracklet_id})
    observations = []
    for point in track["points"]:
        support = graph[point["candidate_id"]]
        observation_id = digest(
            {
                "algorithm_version": "persistent-hop-normalized-hough-episode-graph-v1",
                "candidate_id": point["candidate_id"],
                "canonical_rf_hz": 11_200_000_000.0,
                "relative_alias_index": point["relative_alias_index"],
                "tracklet_id": tracklet_id,
            }
        )
        observations.append(
            {
                "episode_id": episode,
                "factorial_support_moments_s": support["moments"],
                "observation_id": observation_id,
                "schema_version": 1,
                "support_center_utc_ns": support["center"],
                "support_end_utc_ns": support["end"],
                "support_start_utc_ns": support["start"],
            }
        )
    observations.sort(key=lambda item: (item["support_center_utc_ns"], item["observation_id"]))
    observation_ids = [item["observation_id"] for item in observations]
    support_digest = digest(
        {
            "algorithm_version": "catalogue-prediction-support-v1",
            "episode_ids": [episode],
            "observations": observations,
            "response_fields_excluded": True,
            "schema_version": 1,
        }
    )
    partition_seed = digest(
        {
            "policy": "persistent-hop-fixed-orbit-randomized-residual-v1",
            "response_free_support_digest": support_digest,
            "selection_protocol_digest": protocol,
        }
    )
    ranking = sorted(
        (
            digest(
                {
                    "observation_id": observation_id,
                    "partition_policy": "deterministic-randomized-observation-v1",
                    "split_seed": partition_seed,
                }
            ),
            index,
        )
        for index, observation_id in enumerate(observation_ids)
    )
    training_count = min(max(2, math.floor(len(observation_ids) * 0.6)), len(observation_ids) - 1)
    mask = [0] * len(observation_ids)
    for _, index in ranking[:training_count]:
        mask[index] = 1

    found = actual[tracklet_id]
    support_exact += found["support_digest"] == support_digest
    seed_exact += found["partition_seed"] == partition_seed
    ids_exact += found["observation_ids"] == observation_ids
    mask_exact += found["mask"] == mask
    if found["count"] != len(observation_ids):
        raise RuntimeError("pipeline observation count differs")

result = {
    "oracle_tracks": len(oracle["tracks"]),
    "pipeline_tracks": len(actual),
    "membership_identical_tracks": shared,
    "exact_support_digests": support_exact,
    "exact_partition_seeds": seed_exact,
    "exact_observation_id_vectors": ids_exact,
    "exact_training_masks": mask_exact,
    "open_duplicate_rank_identity_ties": len(oracle["tracks"]) - shared,
}
if result != {
    "oracle_tracks": 64,
    "pipeline_tracks": 64,
    "membership_identical_tracks": 58,
    "exact_support_digests": 58,
    "exact_partition_seeds": 58,
    "exact_observation_id_vectors": 58,
    "exact_training_masks": 58,
    "open_duplicate_rank_identity_ties": 6,
}:
    raise RuntimeError(f"recomputed partition comparison differs: {result}")
print(json.dumps(result, sort_keys=True, separators=(",", ":")))
