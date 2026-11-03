"""Reconstruct prior per-satellite causal catalogues, matching original hashes."""

import hashlib
import json
from pathlib import Path

from audit_causal_orbit_disagreement import previous_versions
from sgp4.exporter import export_tle

from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets


def run():
    root = Path(__file__).resolve().parents[1]
    reader = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshots = reader.list_snapshots("space-track")
    cache = {}
    result = {}
    for number in range(1, 6):
        case = f"DSX01-S0{number}"
        directory = (
            root
            / (
                "reports/2026_10_17_dsx01_polynomial_satellite_dive/frozen_inputs"
                if number == 1
                else "reports/2026_10_17_robust_curve_reassociation/frozen_inputs"
            )
            / case
        )
        receipt = json.loads((directory / "receipt.json").read_text())
        selected = directory / "selected.tle"
        if number == 1:
            selected = (
                root
                / "reports/2026_10_17_noise_gated_position/frozen_inputs/DSX01-S01/selected.tle"
            )
        if hashlib.sha256(selected.read_bytes()).hexdigest() != receipt["latest_tle_sha256"]:
            raise ValueError("latest selected catalogue changed")
        current = parse_element_sets(selected.read_text())
        latest = dict(zip(current.satellite_numbers, current.element_epoch_utc_ns(), strict=True))
        cutoff = receipt["cutoff_utc_ns"]
        unique = {
            s.sha256: s
            for s in snapshots
            if cutoff - 172800_000_000_000 <= s.collected_utc_ns <= cutoff
        }
        records = []
        for digest, snapshot in unique.items():
            if digest not in cache:
                cache[digest] = parse_element_sets(reader.read(snapshot))
            cat = cache[digest]
            for name, n, sat, epoch in zip(
                cat.names,
                cat.satellite_numbers,
                cat.satellites,
                cat.element_epoch_utc_ns(),
                strict=True,
            ):
                if n in latest:
                    records.append(
                        dict(
                            norad=n,
                            satellite=sat,
                            name=name,
                            epoch=epoch,
                            collected=snapshot.collected_utc_ns,
                            digest=snapshot.digest,
                        )
                    )
        old = previous_versions(latest, records, cutoff)
        text = "".join(
            f"0 {old[n]['name']}\n{a}\n{b}\n"
            for n in sorted(old)
            for a, b in [export_tle(old[n]["satellite"])]
        )
        digest = hashlib.sha256(text.encode()).hexdigest()
        if digest != receipt["previous_tle_sha256"]:
            raise ValueError(f"prior catalogue does not reproduce original bytes for {case}")
        result[case] = dict(
            catalogue_sha256=digest,
            cutoff_utc_ns=receipt["cutoff_utc_ns"],
            previous_satellites=len(old),
            maximum_collection_utc_ns=max(v["collected"] for v in old.values()),
            sources={
                str(n): dict(
                    epoch_utc_ns=v["epoch"], collected_utc_ns=v["collected"], digest=v["digest"]
                )
                for n, v in old.items()
            },
            text=text,
        )
    return result


if __name__ == "__main__":
    print(json.dumps(run()))
