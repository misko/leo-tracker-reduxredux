from datetime import datetime, timezone
from hashlib import sha256
import json
from math import cos, radians
from pathlib import Path
from random import Random
from secrets import token_hex
import sys

from extract_tracks import load_hour


LOCAL = Path(__file__).parent
BENCHMARK = Path(sys.argv[1])
PUBLIC = BENCHMARK / "public_field2"
PRIVATE = BENCHMARK / "field2_private"
REFERENCE = (53.39820, -2.34860)
SITE_GROUP = f"s-{token_hex(12)}"
SEED = token_hex(32)
RANDOM = Random(SEED)
CATALOG_TIMESTAMP_NS = int(datetime(2023, 3, 10, 23, 15, 3, tzinfo=timezone.utc).timestamp()) * 10**9


def render(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def digest(content):
    return sha256(content).hexdigest()


def region(near):
    if near:
        north, east = (RANDOM.uniform(-8, 8) for _ in range(2))
    else:
        while True:
            north, east = (RANDOM.uniform(-140, 140) for _ in range(2))
            if 34 <= max(abs(north), abs(east)) <= 140:
                break
    latitude, longitude = REFERENCE
    return {"id": f"r-{token_hex(12)}", "center": [round(latitude + north / 111.26, 8), round(longitude + east / (111.32 * cos(radians(latitude))), 8)]}


def overlaps(left, right):
    lat0, lon0 = left["center"]
    lat1, lon1 = right["center"]
    return abs(lat0 - lat1) * 111.26 <= 25 and abs(lon0 - lon1) * 111.32 * cos(radians(lat0)) <= 25


def offer(present):
    containing = region(True) if present else None
    regions = [containing] if containing else []
    while len(regions) < 4:
        candidate = region(False)
        if any(overlaps(candidate, earlier) for earlier in regions):
            continue
        regions.append(candidate)
    RANDOM.shuffle(regions)
    return containing, regions


def main():
    (PUBLIC / "queries").mkdir(parents=True)
    (PUBLIC / "observations").mkdir()
    (PUBLIC / "orbits").mkdir()
    PRIVATE.mkdir(mode=0o700)
    catalog = (LOCAL / "starlink.tle").read_bytes()
    assert sum(line.startswith(b"1 ") for line in catalog.splitlines()) == 3783
    catalog_sha = digest(catalog)
    (PUBLIC / "orbits" / f"{catalog_sha}.tle").write_bytes(catalog)
    cases = []
    data_receipts = []
    for hour in (3, 4, 5):
        stamp, samples = load_hour(hour)
        anchor = int(stamp.timestamp()) * 10**9
        tracks = json.loads((LOCAL / f"tracks-{hour:02d}.json").read_text())
        assert not tracks and samples.shape == (3600, 1024)
        observation = {
            "anchor_utc_ns": anchor, "cutoff_utc_ns": anchor, "catalog_timestamp_ns": CATALOG_TIMESTAMP_NS,
            "duration_s": 3600.0, "tracks": tracks,
        }
        payload = render(observation)
        observation_sha = digest(payload)
        (PUBLIC / "observations" / f"{observation_sha}.json").write_bytes(payload)
        pair = f"p-{token_hex(12)}"
        for present in (True, False):
            query_id = f"q-{token_hex(12)}"
            containing, regions = offer(present)
            query = {"id": query_id, "observation": observation_sha, "catalog": catalog_sha, "regions": regions}
            (PUBLIC / "queries" / f"{query_id}.json").write_bytes(render(query))
            cases.append({"id": query_id, "pair": pair, "site_group": SITE_GROUP, "source": "field",
                          "condition": "present" if present else "missing", "true_region": containing["id"] if present else None,
                          "latlon": REFERENCE, "difficulty": "sparse"})
        filename = f"Kerberos_230311_{hour:02d}00.csv"
        data_receipts.append({"observation": observation_sha, "source_member": filename, "sha256": digest((LOCAL / filename).read_bytes()),
                              "rows": samples.shape[0], "frequency_bins": samples.shape[1], "accepted_tracks": len(tracks)})
    RANDOM.shuffle(cases)
    (PUBLIC / "manifest.json").write_bytes(render({"queries": [case["id"] for case in cases]}))
    (PRIVATE / "truth.json").write_bytes(render({"cases": cases}))
    (PRIVATE / "source_windows.json").write_bytes(render({"windows": data_receipts, "offer_seed": SEED}))
    for name in ("extract_tracks.py", "fetch_archive.py", "seal.py"):
        (PRIVATE / name).write_bytes((LOCAL / name).read_bytes())
    entries = sorted((str(path.relative_to(PUBLIC)), digest(path.read_bytes())) for path in PUBLIC.rglob("*") if path.is_file())
    public_index = "".join(f"{sha}  {name}\n" for name, sha in entries).encode()
    (BENCHMARK / "field2_public.sha256").write_bytes(public_index)
    print("Public hash-list commitment", digest(public_index), "private truth commitment", digest((PRIVATE / "truth.json").read_bytes()))


if __name__ == "__main__":
    main()
