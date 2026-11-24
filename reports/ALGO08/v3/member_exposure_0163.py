"""Map original DS30-0163 signed member boundaries to recorded stereo visits."""

import argparse
from collections import defaultdict
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
from time import perf_counter

from guarded_stage_idle import IdleAdmission


READY = Path("/dev/shm/leo-v3-ds30-0163-ready01")
REQUEST = "654bb406870bd97ac6b1854f312b0dae54e8405d6fda81c2ee135c61e41fcae9"
INVENTORY = "d30888ead13433a1194dec7286e2a71af3d4d78876733eadd8becc06c7121ddd"
NATIVE = "f026bb3822ad7a946979a091c55b06d11d7c675e667c564f7d984e9f38fb2651"


def read_checked(path, pin, limit):
    with os.fdopen(os.open(path, os.O_NOFOLLOW | os.O_RDONLY | os.O_NONBLOCK), "rb") as f:
        info = os.fstat(f.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
            raise ValueError("Unexpected metadata file size or type")
        buf = f.read(limit + 1)
        if len(buf) != info.st_size or sha256(buf).hexdigest() != pin.removeprefix("sha256:"):
            raise ValueError("Source digest mismatch")
    return buf


def stage(target):
    req = json.loads(read_checked(READY / "request.json", REQUEST, 32768))
    inv = json.loads(read_checked(READY / "inventory.json", INVENTORY, 32768))
    if req["case"] != "DS30-0163" or req["inventory"] != "sha256:" + INVENTORY:
        raise ValueError("Wrong sample enrollment")
    target.mkdir(mode=0o755, exist_ok=True)
    gate = IdleAdmission(Path("/sys/dev/block/252:5/stat"), perf_counter() + 120, lambda **event: None)
    with Path("/tmp/leo-algo08v2-2x-bench/gauss.lock").open("rb") as lock:
        for i, (s, (name, pin)) in enumerate(zip(inv["segments"], req["manifests"], strict=True)):
            if (s["scope"] != f"segment-{i:08d}" or name != str(Path(s["path"]) / "manifest.json")
                    or pin != s["manifest_digest"] or Path(s["path"]).parent != Path(req["recording"])):
                raise ValueError("Unexpected signed segment identity")
            out = target / (s["scope"] + ".json")
            if out.exists():
                read_checked(out, pin, 32768)
                continue
            with gate.slot(lock):
                data = read_checked(name, pin, 32768)
            temp = out.with_suffix(".part")
            with temp.open("xb") as f:
                f.write(data)
            temp.rename(out)


def schedule(inventory, manifests):
    visits = []
    members = []
    for seg, doc in zip(inventory["segments"], manifests, strict=True):
        if doc["session_id"] != Path(seg["path"]).name or not doc["chunks"]:
            raise ValueError("Unexpected segment manifest")
        cursor = 0
        for i, member in enumerate(doc["chunks"]):
            count = member["window_count"]
            if (member["chunk_index"] != i or member["first_sequence"] != cursor or count <= 0
                    or member["compressed_bytes"] <= 0):
                raise ValueError("Member partition has a gap or an invalid extent")
            ordinal = len(members)
            members.append(dict(ordinal=ordinal, segment=seg["scope"], local_index=i,
                                first_visit=len(visits), visits=count, compressed_bytes=member["compressed_bytes"],
                                compressed_sha256=member["compressed_sha256"]))
            visits.extend([ordinal] * count)
            cursor += count
        if cursor != seg["windows"] or cursor != doc["window_count"]:
            raise ValueError("Manifest counts disagree")
    if len(visits) != inventory["window_count"]:
        raise ValueError("Recording is incomplete")
    return visits, members


def summarize_streams(visits, source):
    lanes = defaultdict(list)
    channel_visits = defaultdict(set)
    for probe in source["probes"]:
        i = probe["visit_index"]
        radio = probe["receiver_id"]
        if not 0 <= i < len(visits) or radio not in (0, 1) or radio in channel_visits[i]:
            raise ValueError("Probe outside signed stereo roster or duplicated")
        lanes[probe["receiver_id"], probe["channel"], probe["actual_rf_hz"]].append(
            (i, probe["valid_start_counter"], bool(probe["candidates"])))
        channel_visits[i].add(radio)
    if not channel_visits or any(radios != {0, 1} for radios in channel_visits.values()):
        raise ValueError("Incomplete stereo opportunities")
    streams = []
    for (radio, channel, rf), rows in sorted(lanes.items()):
        kept = [row for row in rows if visits[row[0]] % 2 == 0]
        counters = [r[1] for r in rows]
        if counters != sorted(set(counters)):
            raise ValueError("Nonchronological stream records")
        def longest_gap(items):
            return max(((b[1] - a[1]) / source["sample_rate_hz"] for a, b in zip(items, items[1:])),
                       default=None)
        streams.append(dict(radio=radio, channel=channel, rf=rf, opportunities=len(rows), retained=len(kept),
                            nonempty=sum(r[2] for r in rows), retained_nonempty=sum(r[2] for r in kept),
                            longest_original_gap_s=longest_gap(rows), longest_retained_gap_s=longest_gap(kept)))
    return len(channel_visits), streams


def measure(target):
    inv = json.loads(read_checked(READY / "inventory.json", INVENTORY, 32768))
    docs = [json.loads(read_checked(target / (s["scope"] + ".json"), s["manifest_digest"], 32768))
            for s in inv["segments"]]
    visits, members = schedule(inv, docs)
    source = json.loads(read_checked(READY / "native.json", NATIVE, 8_000_000))["source"]
    admitted, streams = summarize_streams(visits, source)
    return dict(case="DS30-0163", inventory_sha256=INVENTORY, native_sha256=NATIVE, members=members,
                issued=len(visits), admitted=admitted, streams=streams,
                rule="retain even zero-based member ordinal across signed chronological segments")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["stage", "measure"])
    parser.add_argument("local_manifests", type=Path)
    args = parser.parse_args()
    if args.action == "stage":
        stage(args.local_manifests)
    else:
        print(json.dumps(measure(args.local_manifests), indent=2, allow_nan=False))
