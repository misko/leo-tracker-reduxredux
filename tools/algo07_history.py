"""Read-only causal history export and private numerical lookup for ALGO07."""
from pathlib import Path
from algo03_shadow_worker import read, write


def collect_versions(cutoff, *, reader):
    """Preserve the frozen archive ordering and genuine-earlier-epoch rule.

    Deduplicating equal epochs keeps the first encountered archive receipt,
    exactly as the original per-request collector did. No later collection is
    admitted, even if it contains an old element epoch.
    """
    from sgp4.api import Satrec
    from leo.sky.propagation import parse_element_set_records
    snapshots = [s for s in reader.list_snapshots('space-track')
                 if cutoff-int(72*3.6e12) <= s.collected_utc_ns <= cutoff]
    versions = {}
    for snapshot in snapshots:
        for record in parse_element_set_records(reader.read(snapshot)):
            lines = [line for line in record.text.splitlines() if line.startswith(('1 ', '2 '))]
            if len(lines) != 2:
                continue
            satellite = Satrec.twoline2rv(*lines)
            epoch = int(round((satellite.jdsatepoch-2440587.5+satellite.jdsatepochF)*86400e9))
            if epoch > cutoff:
                continue
            rows = versions.setdefault(str(record.satellite_number), {})
            rows.setdefault(epoch, dict(lines=lines, epoch_utc_ns=epoch,
                collected_utc_ns=snapshot.collected_utc_ns, digest=snapshot.digest))
    return dict(cutoff_utc_ns=cutoff, snapshot_count=len(snapshots),
                versions={n:sorted(rows.values(), key=lambda r:-r['epoch_utc_ns']) for n,rows in versions.items()})


def export_history(path, cutoff, *, reader):
    value = collect_versions(cutoff, reader=reader)
    write(Path(path), value)
    return value


def collect_private(path, request):
    bank = read(path)
    if request['cutoff'] != bank['cutoff_utc_ns']:
        raise ValueError('Causal history cutoff mismatch')
    chosen = {}
    for norad, latest in request['latest'].items():
        rows = bank['versions'].get(str(norad), [])
        valid = [row for row in rows if latest-row['epoch_utc_ns'] >= 1_000_000_000]
        if valid:
            row = max(valid, key=lambda r:r['epoch_utc_ns'])
            if not request['cutoff']-int(72*3.6e12) <= row['collected_utc_ns'] <= request['cutoff']:
                raise ValueError('Noncausal private history member')
            chosen[str(norad)] = row
    return dict(chosen=chosen, snapshot_count=bank['snapshot_count'])

