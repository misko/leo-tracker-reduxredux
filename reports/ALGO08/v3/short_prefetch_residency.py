"""Read-only admission check for the three-member short prefetch comparison."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path

from tools.pipeline_eval.qualification.cache_residency import cache_snapshot, load_query
from reports.ALGO08.v3 import sparse_cold_input as cold


PINNED = {
    "DS30-0008": "a9ced88711b3a8174e47f7a337e2d5a497642c81eb4a7b5c877c2402d607f77a",
    "DS30-0057": "5e8608f4e5a19b7b8ef44965344749002499b42b370230ec7e361c6966c7be51",
    "DS30-0016": "c781d10abe126bdc40d75a6e202d09a7542e92ef932a535f42700fe95d9ac38c",
}


def resident(observation):
    return (observation["observed_members"] == 1 and not observation["unavailable"]
            and observation["observed_file_pages"] > 0
            and observation["cached_pages"] == observation["observed_file_pages"])


def eligible_triples(rows):
    triples = []
    for a, b, c in zip(rows, rows[1:], rows[2:]):
        if (any(row["window_count"] != 64 or not resident(row["payload"]) or not resident(row["index"])
                for row in (a, b, c))
                or b["first_sequence"] != a["first_sequence"]+64
                or c["first_sequence"] != b["first_sequence"]+64):
            continue
        triples.append(a["first_sequence"])
    return triples


def preflight():
    page_size = os.sysconf("SC_PAGE_SIZE")
    cold.verified(cold.CACHE_LIBRARY, cold.CACHE_SHA)
    query = load_query(cold.CACHE_LIBRARY)
    cases = {}
    pressure = Path("/proc/pressure/io")
    before = pressure.read_text().splitlines()
    for case, digest in PINNED.items():
        binding = cold.BINDING.with_name(case+".json")
        expected = json.loads(cold.verified(binding, digest))["case"]["recording"]["segments"]
        manifests = expected[:1] if case == "DS30-0008" else expected
        segments = []
        for pinned in manifests:
            manifest = Path("/srv/bulk") / pinned["path"]
            document = json.loads(cold.verified(manifest, pinned["sha256"]))
            if cold.SOURCE_DIR not in manifest.parent.parents:
                raise ValueError("Unexpected archive location")
            chunks = document["chunks"][:3] if case == "DS30-0008" else document["chunks"]
            rows = []
            for chunk in chunks:
                observations = {}
                for kind, name, size in (("payload", "payload_relative_path", "compressed_bytes"),
                                         ("index", "index_relative_path", "index_bytes")):
                    observation = cache_snapshot([(manifest.parent, chunk[name], chunk[size])], page_size, query)
                    observations[kind] = dict(observation, name=chunk[name], bytes=chunk[size])
                rows.append(dict(chunk_index=chunk["chunk_index"], first_sequence=chunk["first_sequence"],
                                 window_count=chunk["window_count"], **observations))
            segments.append(dict(manifest=pinned, eligible_triple_starts=eligible_triples(rows), members=rows))
        cases[case] = dict(binding_sha256=digest, segments=segments)
    return dict(cases=cases, page_size=page_size, cache_library_sha256=cold.CACHE_SHA,
                io_pressure_before=before, io_pressure_after=pressure.read_text().splitlines(),
                source_sha256=sha256(Path(__file__).read_bytes()).hexdigest())


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.parse_args()
    print(json.dumps(preflight(), indent=2, sort_keys=True, allow_nan=False))
