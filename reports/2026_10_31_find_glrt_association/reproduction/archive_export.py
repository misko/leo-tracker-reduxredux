"""Read-only archive export. Output JSON on stdout; never mutate the archive."""
import argparse
import hashlib
import json
from pathlib import Path
from sgp4.api import Satrec
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_set_records


def select_first(records, end_ns, horizon_ns):
    """Time-selected first available post-epoch record, never fit-selected."""
    chosen = {}
    for record in sorted(records, key=lambda r: (r['collected_utc_ns'], r['epoch_utc_ns'], r['hash'])):
        if end_ns < record['epoch_utc_ns'] <= horizon_ns and end_ns < record['collected_utc_ns'] <= horizon_ns:
            chosen.setdefault(str(record['norad']), record)
    return chosen


def main(args):
    sources = json.loads(args.targets.read_text())
    scans = {}
    for row in sources:
        inv = json.loads(Path(row['inventory_path']).read_text())
        native = Path(inv['job']['root']) / inv['job']['case']
        receipt = json.loads((native / 'receipt.json').read_text())
        obs = json.loads((native / 'observations.json').read_text())
        origin = receipt['origin_utc_ns']
        end = origin + int(max(o['time_s'] for o in obs) * 1e9)
        scans[row['case']] = dict(origin_utc_ns=origin, end_utc_ns=end, horizon_utc_ns=end + int(48 * 3600e9))
    archive = TleArchiveReader(args.archive)
    snapshots = [s for s in archive.list_snapshots('space-track')
                 if any(v['end_utc_ns'] < s.collected_utc_ns <= v['horizon_utc_ns'] for v in scans.values())]
    records = []
    for snap in snapshots:
        for record in parse_element_set_records(archive.read(snap)):
            lines = [l for l in record.text.splitlines() if l.startswith(('1 ', '2 '))]
            sat = Satrec.twoline2rv(*lines)
            epoch = round((sat.jdsatepoch - 2440587.5) * 86400e9 + sat.jdsatepochF * 86400e9)
            records.append(dict(norad=record.satellite_number, lines=lines, epoch_utc_ns=epoch,
                                collected_utc_ns=snap.collected_utc_ns, snapshot_digest=snap.digest,
                                hash=hashlib.sha256(('\n'.join(lines) + '\n').encode()).hexdigest()))
    for v in scans.values():
        v['elements'] = select_first(records, v['end_utc_ns'], v['horizon_utc_ns'])
    print(json.dumps(dict(selection='first archived availability with element epoch after scan end, within 48 hours',
                         snapshots=len(snapshots), scans=scans), allow_nan=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--targets', type=Path, required=True)
    p.add_argument('--archive', type=Path, default=Path('/var/lib/leo/tle'))
    main(p.parse_args())
