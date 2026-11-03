"""Read-only causal TLE export for the five predeclared DSX01 scan cutoffs."""

import json
from pathlib import Path

from sgp4.exporter import export_tle

from leo.operations.causal_tle_catalogue import causal_catalogue
from leo.operations.tle_archive import TleArchiveReader


def run():
    root = Path(__file__).resolve().parents[1]
    reader = TleArchiveReader(Path("/var/lib/leo/tle"))
    output = {}
    for i in range(1, 6):
        case = f"DSX01-S{i:02d}"
        bank = (
            root
            / (
                "reports/2026_10_17_dsx01_polynomial_satellite_dive/frozen_inputs"
                if i == 1
                else "reports/2026_10_17_robust_curve_reassociation/frozen_inputs"
            )
            / case
        )
        receipt = json.loads((bank / "receipt.json").read_text())
        catalogue = causal_catalogue(reader, receipt["cutoff_utc_ns"])
        output[case] = dict(
            cutoff_utc_ns=receipt["cutoff_utc_ns"],
            origin_utc_ns=receipt["origin_utc_ns"],
            satellites={
                str(n): dict(lines=export_tle(s), provenance=p)
                for n, s, p in zip(
                    catalogue.catalogue.satellite_numbers,
                    catalogue.catalogue.satellites,
                    catalogue.provenance,
                    strict=True,
                )
            },
        )
    print(json.dumps(output))


if __name__ == "__main__":
    run()
