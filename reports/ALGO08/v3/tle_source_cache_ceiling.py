"""Price a persistent source index before adding any persistent cache format."""

import argparse
from collections import Counter
from dataclasses import dataclass
import gc
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from aperture_trial import configuration, write
from dense_geographic_trial import elapsed, host, now


HERE = Path(__file__).resolve().parent
ROOT = Path("/srv/bulk/leo-dev/ds30-full-20261121")
LIBRARY = Path("/opt/leo-algo08/algo08v3/payload/_leo_tle_records.so")
LIBRARY_PIN = "4bdfbfd2440253a624ac2eab3886be48639e9668f58566e2f5edeffc50de469d"
CASES = {
    "DS30-0008": ("a9ced88711b3a8174e47f7a337e2d5a497642c81eb4a7b5c877c2402d607f77a",
                  "b141b4f803a24730c4c3aa0bd8b649f13ccda28b0667b50fcbeefb2e9746cea1"),
    "DS30-0016": ("c781d10abe126bdc40d75a6e202d09a7542e92ef932a535f42700fe95d9ac38c",
                  "c167f3c3d833cfe21fdb0baf2d05ab30cd8e4673ec8ef4b4f6fbda9f56474110"),
    "DS30-0057": ("5e8608f4e5a19b7b8ef44965344749002499b42b370230ec7e361c6966c7be51",
                  "2eb40f7db2442805c09943231995eae377ce7b05306f6fe22f6206f30d902366"),
}
HOUR = 3_600_000_000_000


@dataclass(frozen=True)
class Costs:
    records: int
    eligible_records: int
    all_records_causal: bool
    parse_cpu_s: float


def admissible(snapshot, cutoff, hours):
    return 0 <= cutoff - snapshot.collected_utc_ns <= hours * HOUR


def oldest_by_content(snapshots):
    """Mirror exactly the 72 h history source stamp on repeated contents."""
    first = {}
    for snapshot in sorted(snapshots):
        first.setdefault(snapshot.sha256, snapshot)
    return tuple(first.values())


def budget(costs, earlier_digests, earlier_causal):
    repeated = {key: row for key, row in costs.items() if key in earlier_digests}
    reusable = {key: row for key, row in repeated.items() if key in earlier_causal and row.all_records_causal}
    return dict(repeated_bodies=len(repeated), reusable_bodies=len(reusable),
                unique_bodies=len(costs), repeated_body_records=sum(row.records for row in repeated.values()),
                reusable_body_records=sum(row.records for row in reusable.values()),
                total_rows=sum(row.records for row in costs.values()),
                causal_rows=sum(row.eligible_records for row in costs.values()),
                all_native_parse_cpu_s=sum(row.parse_cpu_s for row in costs.values()),
                free_repeated_native_parse_cpu_s=sum(row.parse_cpu_s for row in reusable.values()))


def checked(path, expected):
    data = path.read_bytes()
    if sha256(data).hexdigest() != expected:
        raise ValueError(f"Unrecognized held source {path.name}")
    return json.loads(data)


def source(case):
    from leo.operations.tle_archive import TleArchiveReader

    root = ROOT / "snapshot" / "inputs" / case
    binding_pin, request_pin = CASES[case]
    binding = checked(ROOT / "bindings" / f"{case}.json", binding_pin)
    request = checked(root / "request.json", request_pin)
    reader = TleArchiveReader(root / "tle")
    snapshots = reader.list_snapshots("space-track")
    cutoff = binding["orbit_cutoff_ns"]
    if (case != binding["case"]["id"]
            or request["job"]["native_input"]["sha256"] != "sha256:" + binding["case"]["native"]["sha256"]
            or {s.path.name: s.sha256 for s in snapshots} != request["causal_snapshots"]
            or not all(admissible(s, cutoff, 72) for s in snapshots)):
        raise ValueError("Capture cutoff or complete snapshot inventory differs from the sealed request")
    return reader, cutoff, snapshots


def audit(case, earlier_digests, earlier_causal, earlier_pairs):
    from leo.contracts.digests import canonical_digest
    from leo.operations.causal_tle_catalogue import causal_catalogue
    from tools.pipeline_eval.variants import algo08_causal_reuse as reuse
    from tools.pipeline_eval.variants.experimental.preparation_gc import defer_collection
    from tools.pipeline_eval.variants.experimental.tle_records import batch_records

    reader, cutoff, snapshots = source(case)
    io, initialization = Counter(), Counter()
    calls = {}
    active = None
    original_read = reader.read
    original_rv = reuse.Satrec.twoline2rv

    def verified(snapshot):
        nonlocal active
        if not admissible(snapshot, cutoff, 72):
            raise ValueError("A source read would cross the signed capture cutoff")
        stamp = now()
        text = original_read(snapshot)
        io.update(elapsed(stamp))
        io.update(reads=1, bytes=snapshot.byte_size)
        active = snapshot.sha256
        return text

    def reconstruct(*lines):
        stamp = now()
        record = original_rv(*lines)
        initialization.update(elapsed(stamp))
        initialization["calls"] += 1
        return record

    with batch_records(LIBRARY) as native:
        original_parse = reuse.parse_element_set_records

        def observed(text):
            if active is None or active in calls:
                raise ValueError("Expected a first parse of a verified source body")
            stamp = now()
            records = original_parse(text)
            timing = elapsed(stamp)
            calls[active] = text, len(records), timing["cpu_s"]
            return records

        @defer_collection
        def prepare():
            if gc.isenabled():
                raise ValueError("Expected the installed deferred-collection scope")
            parser = reuse.CausalPreparationParser()
            causal = causal_catalogue(reader, cutoff, element_parser=parser)
            for snapshot in oldest_by_content(snapshots):
                parser(reader.read(snapshot))
            return parser, causal

        with (patch.object(reader, "read", verified), patch.object(reuse, "parse_element_set_records", observed),
              patch.object(reuse, "Satrec", SimpleNamespace(twoline2rv=reconstruct))):
            stamp = now()
            parser, causal = prepare()
            stage = elapsed(stamp)
    if native["fallback"] or parser.stats["fallback_calls"] or len(calls) != len(oldest_by_content(snapshots)):
        raise ValueError("Installed native and within-solve parser must cover every source")
    if any(not (0 <= cutoff-r["collected_utc_ns"] <= 48 * HOUR
                and 0 <= cutoff-r["element_epoch_utc_ns"] <= 48 * HOUR) for r in causal.provenance):
        raise ValueError("Noncausal newest catalogue member")

    counts = {}
    for key, (text, records, timing) in calls.items():
        epochs = parser.catalogues[text].epochs
        if len(epochs) != records:
            raise ValueError("The verified snapshot did not reconstruct every original record")
        n = sum(epoch <= cutoff for epoch in epochs)
        counts[key] = Costs(records, n, n == records, timing)
    # Retain only digests of exact past line pairs for overlap accounting.
    current_pairs = {sha256((first+"\n"+second).encode("ascii")).digest()
                     for (first, second), (_, _, epoch) in parser.elements.items() if epoch <= cutoff}
    measurements = budget(counts, earlier_digests, earlier_causal)
    measurements.update(unique_causal_line_pairs=len(current_pairs),
                        repeated_causal_line_pairs=len(current_pairs & earlier_pairs),
                        noncausal_at_cutoff_bodies=sum(not row.all_records_causal for row in counts.values()),
                        ideal_reuse_source_cpu_s=stage["cpu_s"]-measurements["free_repeated_native_parse_cpu_s"])
    earlier_digests.update(counts)
    earlier_causal.update(k for k, row in counts.items() if row.all_records_causal)
    earlier_pairs.update(current_pairs)
    return dict(case=case, cutoff_utc_ns=cutoff, archive=str(reader.root),
                inventory_digest=canonical_digest({s.path.name:s.sha256 for s in snapshots}),
                snapshots48=sum(admissible(s, cutoff, 48) for s in snapshots), snapshots72=len(snapshots),
                stock_causal_orbits=len(causal.catalogue), source_cpu_s=stage["cpu_s"], elapsed_s=stage["elapsed_s"],
                verified_reads=dict(io), native=native, scan_parser=parser.stats, source_counts=measurements,
                sgp4_initialization=dict(initialization),
                stock_catalogue_provenance_sha256=canonical_digest(causal.provenance))


def run(output):
    machine = host()
    _, specification = configuration()
    if (sha256(LIBRARY.read_bytes()).hexdigest() != LIBRARY_PIN
            or specification.get("defer_preparation_gc") is not True):
        raise ValueError("Expected installed native record validation and deferred preparation GC")
    digests, causal, pairs = set(), set(), set()
    rows = [audit(case, digests, causal, pairs) for case in CASES]
    if [r["cutoff_utc_ns"] for r in rows] != sorted(r["cutoff_utc_ns"] for r in rows):
        raise ValueError("Reuses must precede the requested cutoff")
    write(output, dict(host=machine, native_library_sha256=LIBRARY_PIN, deferred_preparation_gc=True,
                       capture_source_pins=CASES, runs=rows,
                       persistent_cache_created=False, no_source_writes=True,
                       pins={name:sha256((HERE / name).read_bytes()).hexdigest()
                             for name in ("tle-source-cache-ceiling-protocol.md", "tle_source_cache_ceiling.py")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output)
