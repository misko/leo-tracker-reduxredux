"""Read-only final-reassociation history bank; original archive/epoch ordering."""

from sgp4.api import Satrec

from leo.sky.propagation import parse_element_set_records


def collect_versions(reader, cutoff):
    snapshots = [
        s
        for s in reader.list_snapshots("space-track")
        if cutoff - int(72 * 3.6e12) <= s.collected_utc_ns <= cutoff
    ]
    versions = {}
    for snapshot in snapshots:
        for record in parse_element_set_records(reader.read(snapshot)):
            lines = [line for line in record.text.splitlines() if line.startswith(("1 ", "2 "))]
            if len(lines) != 2:
                continue
            satellite = Satrec.twoline2rv(*lines)
            epoch = int(round((satellite.jdsatepoch - 2440587.5 + satellite.jdsatepochF) * 86400e9))
            if epoch > cutoff:
                continue
            rows = versions.setdefault(str(record.satellite_number), {})
            rows.setdefault(
                epoch,
                dict(
                    lines=lines,
                    epoch_utc_ns=epoch,
                    collected_utc_ns=snapshot.collected_utc_ns,
                    digest=snapshot.digest,
                ),
            )
    return dict(
        cutoff_utc_ns=cutoff,
        snapshot_count=len(snapshots),
        versions={
            n: sorted(rows.values(), key=lambda r: -r["epoch_utc_ns"])
            for n, rows in versions.items()
        },
    )
