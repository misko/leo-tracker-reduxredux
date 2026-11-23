"""Count the I/Q retention and archived members implied by a second sparse search."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path

from aperture_trial import BENCH, DENSE, inputs, read, write
from primary_owner_census import canonical_owners, pinned_aperture
from rf_block_trial import schedule


def footprint(members, requested):
    matched = set()
    touched = held_bytes = compressed_bytes = decoded_bytes = 0
    for compressed, windows in members:
        selected = requested.intersection(windows)
        if not selected:
            continue
        if selected & matched:
            raise ValueError("Repeated requested opportunity")
        matched.update(selected)
        touched += 1
        compressed_bytes += compressed
        decoded_bytes += sum(windows.values())
        held_bytes += sum(windows[v] for v in selected)
    if matched != requested:
        raise ValueError("Requested visit absent from the authenticated inventory")
    return dict(stereo_visits=len(matched), held_iq_bytes=held_bytes, touched_members=touched,
                member_compressed_bytes=compressed_bytes, member_decoded_bytes=decoded_bytes)


def run(output, visit_ledger):
    from first_third_ingress import chunk_rows
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import FastSegmentSource

    packets = pinned_aperture()
    archive = visit_ledger.read_bytes()
    forecasts = json.loads(gzip.decompress(archive))
    data = {}
    for name, root in (("DS30-0008", DENSE.parent / "baseline"),
                       ("south-containing", BENCH / "exact-curved-lookahead-south-inside/candidate")):
        native, _, _, expected, identity = inputs(name)
        source = native["source"]
        inventory = read(root / "fast-scan-inputs" / (source["session_id"] + ".json"))
        if canonical_digest(inventory) != source["input_manifest_sha256"]:
            raise ValueError("Native packet and stored inventory disagree")
        members, window_count = [], 0
        for entry in inventory["segments"]:
            segment = FastSegmentSource(entry)
            for chunk in segment.reader.manifest.chunks:
                windows = {}
                for row in chunk_rows(segment, chunk):
                    visit = row.acquisition["global_visit"]
                    if visit != window_count:
                        raise ValueError("Nonconsecutive authenticated RF opportunity")
                    windows[visit] = row.payload_bytes
                    window_count += 1
                members.append((chunk.compressed_bytes, windows))
        if window_count != inventory["window_count"]:
            raise ValueError("Incomplete segment manifest")
        probes = source["probes"]
        _, paid, _ = schedule(probes)
        held = {r["visit_index"] for r in probes} - paid
        owners = canonical_owners(native, packets[name]["full"], identity, expected)
        needed = {probes[i]["visit_index"] for arm in owners.values() for i in arm} & held
        data[name] = dict(identity=identity, inventory_sha256=canonical_digest(inventory),
                          all_members=footprint(members, set(range(window_count))),
                          unpaid=footprint(members, held), unpaid_with_full_owner=footprint(members, needed))
        queries = forecasts[name]
        if queries["identity"] != identity:
            raise ValueError("Forecast and recording refer to different inputs")
        actual = {}
        for arm, rules in queries["visits"].items():
            actual[arm] = {}
            for rule, visits in rules.items():
                proposed = set(visits["proposed"])
                if len(proposed) != len(visits["proposed"]) or proposed - held:
                    raise ValueError("Expected unique proposals only on unpaid stereo visits")
                actual[arm][rule] = footprint(members, proposed)
        data[name].update(forecast=actual, forecast_visit_digest=canonical_digest(queries),
                          forecast_archive_sha256=sha256(archive).hexdigest())
    write(output, data)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    cli.add_argument("--visit-ledger", type=Path,
                     default=Path(__file__).parent / "measurements/sparse-rf-visits.json.gz")
    run(**vars(cli.parse_args()))
