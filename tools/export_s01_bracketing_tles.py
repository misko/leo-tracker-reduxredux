"""Read-only archive adapter; export past and post-observation element sets.

Run as the archive's existing service user. Output contains public TLE data and
provenance only; no credential/configuration access or archive writes.
"""

import json
from pathlib import Path

from sgp4.exporter import export_tle

from leo.operations.causal_tle_catalogue import causal_catalogue
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets

ANCHOR = 1792167342609909833
END = ANCHOR + 300_000_000_000


def run():
    reader = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshots = reader.list_snapshots("space-track")
    causal = causal_catalogue(reader, 1792167342484895460)
    past = {}
    for n, name, sat, provenance in zip(causal.catalogue.satellite_numbers,
                                       causal.catalogue.names, causal.catalogue.satellites,
                                       causal.provenance, strict=True):
        past[n] = dict(norad=n, name=name, lines=export_tle(sat), **{
            k: v for k, v in provenance.items() if k not in ("norad", "name")})
    after = [s for s in snapshots if END < s.collected_utc_ns <= END + 48 * 3600_000_000_000]
    unique = {}
    for s in after:
        unique.setdefault(s.sha256, s)
    future, first_snapshot = {}, {}
    for snapshot in sorted(unique.values()):
        cat = parse_element_sets(reader.read(snapshot))
        for n, name, sat, epoch in zip(cat.satellite_numbers, cat.names, cat.satellites,
                                       cat.element_epoch_utc_ns(), strict=True):
            if n not in past:
                continue
            row = dict(norad=n, name=name, lines=export_tle(sat),
                       element_epoch_utc_ns=epoch, collected_utc_ns=snapshot.collected_utc_ns,
                       snapshot_digest=snapshot.digest, provider=snapshot.provider)
            if snapshot == after[0]:
                first_snapshot[n] = row
            if END < epoch <= END + 48 * 3600_000_000_000:
                key = (epoch, snapshot.collected_utc_ns)
                if n not in future or key < (future[n]["element_epoch_utc_ns"],
                                             future[n]["collected_utc_ns"]):
                    future[n] = row
    print(json.dumps(dict(anchor_utc_ns=ANCHOR, observation_end_utc_ns=END,
                          selection=(
                              "earliest epoch after scan; earliest collection breaks ties; "
                              "48-hour window chosen without looking at the radio fit"),
                          past=past, first_post_collection=first_snapshot,
                          first_future_epoch=future,
                          post_collections=len(after), unique_post_payloads=len(unique))))


if __name__ == "__main__":
    run()
