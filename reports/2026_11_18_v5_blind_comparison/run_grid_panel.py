"""Replay the unchanged regional prototype on the original v5 roof recordings."""

import argparse
import hashlib
import importlib
import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from tempfile import TemporaryDirectory

study = importlib.import_module("reports.2026_11_18_blind_regional_receiver.run_study")
HERE = Path(__file__).resolve().parent
ARCHIVE = Path("/srv/bulk/leo-dev/accuracy-repair-20261115/ds26-four-configs-twice-001")
GRAPHS = Path("/srv/bulk/leo/research/algo07v3-20261104/tracks001/candidate")
OUTPUT = HERE / "prototype"


def displaced(point, bearing, km):
    lat, lon = map(math.radians, point)
    angle = km / 6371.0088
    y = math.asin(math.sin(lat) * math.cos(angle)
                  + math.cos(lat) * math.sin(angle) * math.cos(bearing))
    x = lon + math.atan2(math.sin(bearing) * math.sin(angle) * math.cos(lat),
                         math.cos(angle) - math.sin(lat) * math.sin(y))
    return [math.degrees(y), (math.degrees(x) + 180) % 360 - 180]


def offers(center, case):
    seed = hashlib.sha256(("v5-grid-comparison-v1/" + case).encode()).digest()
    orientation = 2 * math.pi * int.from_bytes(seed[:8]) / 2**64
    true = {"id": "original", "center": center}
    distractors = [{"id": f"r{i}",
                    "center": displaced(center, orientation + math.radians(offset), km)}
                   for i, (offset, km) in enumerate([(0, 45), (105, 65), (230, 250)])]
    multiple = [true, *distractors]
    multiple.sort(key=lambda r: hashlib.sha256(seed + r["id"].encode()).digest())
    return {"one": [true], "four": multiple}


def ds26_inputs(member):
    case = member["dataset_label"]
    path = GRAPHS / (case + ".json")
    raw = path.read_bytes()
    graph_sha = study.sha(raw)
    checked = study.read(GRAPHS / (case + "-receipt.json"))
    assert checked["dataset_label"] == case and graph_sha == checked["output_sha256"]
    doc = json.loads(raw)
    meta = doc["metadata"]
    cutoff = meta["causal_cutoff_utc_ns"]
    assert cutoff == member["cutoff_utc_ns"] and meta["run_id"] == member["run_id"]
    native = Path(member["frozen_native_path"])
    assert "sha256:" + study.sha(native.read_bytes()) == member["input_sha256"]
    entries = [(int(k.split("-")[0]), k, v) for k, v in member["causal_snapshots"].items()]
    ns, name, digest = max(row for row in entries if row[0] < cutoff)
    cat = native.parent / "tle/archive/space-track" / name
    assert study.sha(cat.read_bytes()) == digest.removeprefix("sha256:")
    obs = {"anchor_utc_ns": meta["anchor_utc_ns"], "cutoff_utc_ns": cutoff,
           "duration_s": meta["duration_s"], "catalog_timestamp_ns": ns,
           "tracks": [{k: r[k] for k in ("times", "values", "receiver", "channel", "rf_hz")}
                      for r in doc["tracks"]]}
    return study.packed(obs), cat, dict(native=member["input_sha256"], graph=graph_sha)


def ds29_inputs(record):
    public = study.ROOT / "public_recorded"
    obs = (public / "observations" / (record["observation_sha256"] + ".json")).read_bytes()
    cat = public / "orbits" / (record["catalogue_sha256"] + ".tle")
    assert study.sha(obs) == record["observation_sha256"]
    assert study.sha(cat.read_bytes()) == cat.stem
    return obs, cat, dict(native=record["native_sha256"])


def replay(member, center, digest):
    case = member["dataset_label"]
    dest = OUTPUT / (case + ".json")
    on_ds26 = case.startswith("DS26-")
    choices = offers(center, case)
    if not on_ds26:
        choices.pop("four")  # Use the actual locked offers for the four-region DS29 results.
    if dest.exists():
        old = study.read(dest)
        assert old["engine_sha256"] == digest and old["offers"] == choices
        return
    answer = dict(case=case, engine_sha256=digest, offers=choices)
    if on_ds26 and member["availability"] != "available":
        study.save(dest, dict(answer, status="input_unavailable", reason=member["availability"]))
        return
    obs, cat, provenance = (ds26_inputs if on_ds26 else ds29_inputs)(member)
    obs_sha, cat_sha = study.sha(obs), study.sha(cat.read_bytes())
    predictions = {}
    with TemporaryDirectory() as directory:
        query_file = Path(directory) / "query.json"
        obs_file = Path(directory) / "observation.json"
        obs_file.write_bytes(obs)
        for mode, regions in choices.items():
            query = dict(id=case, observation=obs_sha, catalog=cat_sha, regions=regions)
            query_file.write_bytes(study.packed(query))
            paths = {"query.json": query_file, "observation.json": obs_file, "orbits.tle": cat}
            predictions[mode] = study.dispatch(paths, "primary")
    study.save(dest, dict(answer, status="evaluated", observation=obs_sha, catalog=cat_sha,
                          provenance=provenance, predictions=predictions))


def main():
    arg = argparse.ArgumentParser(description=__doc__)
    arg.add_argument("--jobs", type=int, default=6)
    args = arg.parse_args()
    digest = study.freeze()
    cohort = study.read(ARCHIVE / "plans/science.json")["cohorts"]["DS26"]
    center = cohort["template"]["search_center"]
    ds29 = study.read(study.ROOT / "recorded_private/provenance.json")["observations"]
    OUTPUT.mkdir(exist_ok=True)
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        pending = [pool.submit(replay, m, center, digest) for m in [*ds29, *cohort["members"]]]
        for i, future in enumerate(as_completed(pending), 1):
            future.result()
            if i % 20 == 0 or i == len(pending):
                print(f"{i}/{len(pending)} recordings processed", flush=True)
    assert study.freeze() == digest


if __name__ == "__main__":
    main()
