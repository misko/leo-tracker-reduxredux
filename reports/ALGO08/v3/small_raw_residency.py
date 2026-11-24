"""Check the full extents of small signed DS30 recordings without reading waveform bytes."""

from hashlib import sha256
import json
import os
from pathlib import Path


def complete(census):
    return bool(census["members"] and census["observed_members"] == census["members"]
                and not census["unavailable"] and census["cached_pages"] == census["observed_file_pages"])


def census():
    from continued_cfo_small_raw import BULK, CASE, ROSTER
    from empty_bootstrap import checked
    from short_raw_diagnostic import CACHE_LIB, CACHE_SHA, cache_residency

    checked(CACHE_LIB, CACHE_SHA)
    query = cache_residency.load_query(CACHE_LIB)
    rows, cases = [], []
    for path in CASE.binding.parent.glob("DS30-*.json"):
        data = path.read_bytes()
        case = json.loads(data)["case"]
        visits = case["recording"]["window_count"]
        if case["id"] != path.stem:
            raise ValueError("Binding case differs from its filename")
        rows.append((visits, path.stem, sha256(data).hexdigest()))
        if 100 <= visits <= 2000:
            cases.append((visits, path.stem, case["recording"]["segments"]))
    digest = sha256(json.dumps(sorted(rows), separators=(",", ":")).encode()).hexdigest()
    if digest != ROSTER or len(rows) != 455:
        raise ValueError("Different signed DS30 roster")
    result = []
    for visits, label, segments in sorted(cases):
        members = {"payload": [], "index": []}
        for segment in segments:
            path = BULK / segment["path"]
            doc = json.loads(checked(path, segment["sha256"]))
            for chunk in doc["chunks"]:
                members["payload"].append((path.parent, chunk["payload_relative_path"], chunk["compressed_bytes"]))
                members["index"].append((path.parent, chunk["index_relative_path"], chunk["index_bytes"]))
        scopes = {k: cache_residency.cache_snapshot(v, os.sysconf("SC_PAGE_SIZE"), query) for k, v in members.items()}
        result.append(dict(case=label, visits=visits, segments=segments,
                           bytes=sum(size for _, _, size in members["payload"]),
                           residency=scopes, fully_resident=all(map(complete, scopes.values()))))
    return dict(roster_sha256=digest, rows=result, payload_bytes_read=0)


if __name__ == "__main__":
    print(json.dumps(census(), indent=2))
