"""Export only RF evidence and causal orbit authority for a fresh wide search."""

import argparse
import json
import shutil
from pathlib import Path

from replay_regional_doppler import digest, load_observations, write_json


def prepare(source, output):
    output.mkdir(parents=True, exist_ok=False)
    (output / "evidence").mkdir()
    inventory = json.loads((source / "inventory.json").read_text())
    rows = []
    for original in inventory["scans"]:
        if not original["included"]:
            continue
        path = source / "evidence" / (original["session_id"] + ".json")
        document = json.loads(path.read_text())
        meta = {
            k: document["inventory"][k]
            for k in [
                "session_id",
                "reference_utc_ns",
                "tle_file",
                "tle_digest",
                "tle_collected_ns",
            ]
        }
        meta.update(partition="randomized", known_site_candidate_fields_used=False)
        series = [
            {
                k: s[k]
                for k in [
                    "tracklet_id",
                    "channel",
                    "edge",
                    "actual_rf_hz",
                    "t_s",
                    "y_hz",
                    "candidate_ids",
                ]
            }
            for s in document["series"]
        ]
        episodes = [
            {k: e[k] for k in ["episode_id", "members", "channel"]} for e in document["episodes"]
        ]
        exported = dict(inventory=meta, series=series, episodes=episodes)
        load_observations(exported, 0)  # validate no duplicated source observations
        tle = source / "evidence" / meta["tle_file"]
        if (
            digest(tle) != meta["tle_digest"]
            or meta["tle_collected_ns"] >= meta["reference_utc_ns"]
        ):
            raise ValueError("invalid causal TLE authority")
        shutil.copyfile(tle, output / "evidence" / tle.name)
        write_json(output / "evidence" / path.name, exported)
        rows.append(
            dict(**meta, included=True, episode_count=len(episodes), source_digest=digest(path))
        )
    write_json(
        output / "inventory.json",
        dict(
            scans=rows,
            prior_matched_norads_used=False,
            partition="randomized",
            source_inventory_digest=digest(source / "inventory.json"),
        ),
    )
    print(f"Exported {len(rows)} scans, {sum(r['episode_count'] for r in rows)} RF episodes")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    prepare(a.source, a.output)
