"""Read-only archive adapter: earliest post-scan epochs, without RF selection."""

import argparse
import json
from pathlib import Path
from sgp4.exporter import export_tle
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets


def select_post_versions(records, numbers, end, hours=48):
    chosen = {}
    for row in records:
        n = row['norad']
        if n not in numbers or not end < row['collected_utc_ns'] <= end + hours * 3600_000_000_000:
            continue
        if not end < row['element_epoch_utc_ns'] <= end + hours * 3600_000_000_000:
            continue
        key = (row['element_epoch_utc_ns'], row['collected_utc_ns'])
        if n not in chosen or key < (chosen[n]['element_epoch_utc_ns'], chosen[n]['collected_utc_ns']):
            chosen[n] = row
    return chosen


def main(directory):
    receipt = json.loads((directory / 'receipt.json').read_text())
    nominal = json.loads((directory / 'nominal_elements.json').read_text())
    numbers = set(map(int, nominal));end = receipt['origin_utc_ns'] + 300_000_000_000
    reader = TleArchiveReader(Path('/var/lib/leo/tle'))
    snapshots = [s for s in reader.list_snapshots('space-track') if end < s.collected_utc_ns <= end + 48 * 3600_000_000_000]
    unique = {}
    for s in snapshots:unique.setdefault(s.sha256, s)
    def records():
        for snapshot in unique.values():
            cat = parse_element_sets(reader.read(snapshot))
            for n, name, sat, epoch in zip(cat.satellite_numbers, cat.names, cat.satellites, cat.element_epoch_utc_ns(), strict=True):
                if n in numbers:
                    yield dict(norad=n, name=name, lines=export_tle(sat), element_epoch_utc_ns=epoch,
                        collected_utc_ns=snapshot.collected_utc_ns, snapshot_digest=snapshot.digest)
    chosen = select_post_versions(records(), numbers, end)
    print(json.dumps(dict(case=directory.name, origin_utc_ns=receipt['origin_utc_ns'], end_utc_ns=end,
        selection='earliest epoch after scan, earliest collection tie-break; fixed 48h window',
        diagnostic_future_TLE_only=True, same_causal_candidate_inventory=True, GPS_or_RF_used=False,
        snapshot_count=len(snapshots), unique_payloads=len(unique), versions=chosen,
        missing=sorted(numbers-set(chosen)))))


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--directory',required=True,type=Path)
    main(parser.parse_args().directory)
