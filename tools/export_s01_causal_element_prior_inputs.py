"""Read-only public archive adapter for past-only orbital-prior sensitivity."""

import json
from pathlib import Path

from sgp4.exporter import export_tle

from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets

ROOT = Path(__file__).resolve().parents[1]
CUTOFF = 1792167342484895460


def run():
    association = json.loads(
        (ROOT / "reports/2026_10_17_s01_phase_sensitivity/c0/association_cap_2.7.json").read_text()
    )
    wanted = {
        r["candidate_norad"] for r in association["association"]["rows"] if r["active_curvature"]
    }
    reader = TleArchiveReader(Path("/var/lib/leo/tle"))
    unique = {}
    for snapshot in reader.list_snapshots("space-track"):
        if CUTOFF - 48 * 3600_000_000_000 <= snapshot.collected_utc_ns <= CUTOFF:
            unique.setdefault(snapshot.sha256, snapshot)
    found = {n: {} for n in wanted}
    for snapshot in unique.values():
        cat = parse_element_sets(reader.read(snapshot))
        for n, name, sat, epoch in zip(
            cat.satellite_numbers,
            cat.names,
            cat.satellites,
            cat.element_epoch_utc_ns(),
            strict=True,
        ):
            if n not in wanted or not CUTOFF - 48 * 3600_000_000_000 <= epoch <= CUTOFF:
                continue
            found[n].setdefault(
                epoch,
                dict(
                    norad=n,
                    name=name,
                    lines=export_tle(sat),
                    element_epoch_utc_ns=epoch,
                    collected_utc_ns=snapshot.collected_utc_ns,
                    snapshot_digest=snapshot.digest,
                ),
            )
    print(
        json.dumps(
            dict(
                cutoff_utc_ns=CUTOFF,
                maximum_age_hours=48,
                unique_payloads=len(unique),
                selection="last four distinct past element epochs per candidate",
                candidates={n: [v[k] for k in sorted(v)[-4:]] for n, v in found.items()},
            )
        )
    )


if __name__ == "__main__":
    run()
