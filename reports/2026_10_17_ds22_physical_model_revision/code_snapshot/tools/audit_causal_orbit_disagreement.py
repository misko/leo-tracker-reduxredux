"""Compare latest and previous distinct causal TLE epochs, never future elements.

Disagreement is a sensitivity diagnostic, not measured ephemeris error. The
association experiment continues to use the original latest causal elements.
"""

import argparse
import hashlib
import json
from pathlib import Path

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import write

from leo.operations.tle_archive import TleArchiveReader
from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km, look_angles
from leo.sky.propagation import ElementSetCatalogue, parse_element_sets


def previous_versions(latest, records, cutoff):
    previous = {}
    for row in records:
        n = row["norad"]
        if (
            n not in latest
            or row["collected"] > cutoff
            or not cutoff - 172800_000_000_000 <= row["epoch"] < latest[n]
        ):
            continue
        key = (row["epoch"], row["collected"], row["digest"])
        if n not in previous or key > previous[n][0]:
            previous[n] = key, row
    return {n: entry[1] for n, entry in previous.items()}


def run(inputs, output):
    output.mkdir(parents=True, exist_ok=False)
    receipt = json.loads((inputs / "receipt.json").read_text())
    cutoff = receipt["cutoff_utc_ns"]
    current = parse_element_sets((inputs / "selected.tle").read_text())
    latest = dict(zip(current.satellite_numbers, current.element_epoch_utc_ns(), strict=True))
    reader = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshots = {
        s.sha256: s
        for s in reader.list_snapshots("space-track")
        if cutoff - 172800_000_000_000 <= s.collected_utc_ns <= cutoff
    }
    candidates = []
    for snapshot in snapshots.values():
        catalogue = parse_element_sets(reader.read(snapshot))
        for name, number, satellite, epoch in zip(
            catalogue.names,
            catalogue.satellite_numbers,
            catalogue.satellites,
            catalogue.element_epoch_utc_ns(),
            strict=True,
        ):
            if number in latest:
                candidates.append(
                    dict(
                        norad=number,
                        satellite=satellite,
                        epoch=epoch,
                        collected=snapshot.collected_utc_ns,
                        digest=snapshot.digest,
                        name=name,
                    )
                )
    previous = previous_versions(latest, candidates, cutoff)
    numbers = sorted(previous)
    indexes = {n: i for i, n in enumerate(current.satellite_numbers)}
    new = ElementSetCatalogue(
        tuple(current.names[indexes[n]] for n in numbers),
        tuple(numbers),
        tuple(current.satellites[indexes[n]] for n in numbers),
    )
    old = ElementSetCatalogue(
        tuple(previous[n]["name"] for n in numbers),
        tuple(numbers),
        tuple(previous[n]["satellite"] for n in numbers),
    )
    times = np.linspace(0, 300, 13)
    p_new, v_new, ok_new = matching.ecef_states(new, receipt["origin_utc_ns"], times)
    p_old, v_old, ok_old = matching.ecef_states(old, receipt["origin_utc_ns"], times)
    site = geodetic_to_ecef_km(*receipt["regional_center"], 0.0)
    rotation = ecef_to_enu_matrix(*receipt["regional_center"])
    _, _, _, rate_new = look_angles(p_new, v_new, site, rotation)
    _, _, _, rate_old = look_angles(p_old, v_old, site, rotation)
    delta_frequency = -11.5e9 * (rate_new - rate_old) / 299792.458
    design = np.column_stack([np.ones(len(times)), times - 150])
    coefficients = np.linalg.lstsq(design, delta_frequency.T, rcond=None)[0]
    shape = delta_frequency - (design @ coefficients).T
    rows = []
    for i, n in enumerate(numbers):
        if not ok_new[i] or not ok_old[i]:
            rows.append(dict(norad=n, status="propagation_unusable"))
            continue
        rows.append(
            dict(
                norad=n,
                status="compared",
                latest_epoch_utc_ns=latest[n],
                previous_epoch_utc_ns=previous[n]["epoch"],
                previous_collection_utc_ns=previous[n]["collected"],
                previous_digest=previous[n]["digest"],
                median_position_difference_km=float(
                    np.median(np.linalg.norm(p_new[i] - p_old[i], axis=1))
                ),
                maximum_velocity_difference_m_s=float(
                    1000 * np.max(np.linalg.norm(v_new[i] - v_old[i], axis=1))
                ),
                frequency_difference_rms_hz=float(np.sqrt(np.mean(delta_frequency[i] ** 2))),
                frequency_difference_slope_hz_s=float(coefficients[1, i]),
                frequency_difference_affine_removed_rms_hz=float(np.sqrt(np.mean(shape[i] ** 2))),
            )
        )
    write(output / "results.json", rows)
    write(
        output / "protocol.json",
        dict(
            source_id=receipt["source_id"],
            cutoff_utc_ns=cutoff,
            original_bank_sha256=receipt["bank_sha256"],
            latest_tle_sha256=hashlib.sha256((inputs / "selected.tle").read_bytes()).hexdigest(),
            archive_unique_payloads=len(snapshots),
            all_archive_collections_causal=True,
            no_future_elements=True,
            latest_candidates=len(latest),
            compared_candidates=len(previous),
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            interpretation=(
                "successive causal prediction disagreement, not truth error; "
                "no candidate or observation changed"
            ),
            evaluation_site=receipt["regional_center"],
            rf_hz=11.5e9,
            times_s=times.tolist(),
        ),
    )
    from sgp4.exporter import export_tle

    (output / "previous.tle").write_text(
        "".join(
            f"0 {name}\n{a}\n{b}\n"
            for name, sat in zip(old.names, old.satellites, strict=True)
            for a, b in [export_tle(sat)]
        )
    )
    print(json.dumps(dict(source_id=receipt["source_id"], compared=len(previous))), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--inputs", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    q = Path("/mnt/qnap01")
    if a.output.resolve() == q or q in a.output.resolve().parents:
        p.error("QNAP is read-only")
    run(a.inputs, a.output)
