"""Export histories for every regional candidate from pre-cutoff archive bytes.

No fitted association list, receiver position, or following-TLE diagnostic is
opened. Each historical epoch retains its earliest causal archive occurrence.
"""

import json
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from dsx01_inference_audit import ROOT, validate_history
from sgp4.exporter import export_tle

from leo.operations.tle_archive import TleArchiveError, TleArchiveReader
from leo.sky.propagation import parse_element_sets


def run():
    reader = TleArchiveReader(Path("/var/lib/leo/tle"))
    try:
        snapshots = reader.list_snapshots("space-track")
    except TleArchiveError:
        return from_verified_exports()
    cache = {}
    for k in range(1, 6):
        case = f"DSX01-S0{k}"
        stem = (
            "2026_10_17_dsx01_polynomial_satellite_dive"
            if k == 1
            else "2026_10_17_robust_curve_reassociation"
        )
        folder = ROOT / "reports" / stem / "frozen_inputs" / case
        receipt = json.loads((folder / "receipt.json").read_text())
        with np.load(folder / "bank.npz") as bank:
            numbers = set(map(int, bank["norad"]))
        cutoff = receipt["cutoff_utc_ns"]
        records = {n: {} for n in numbers}
        sources = []
        for snapshot in snapshots:
            if not cutoff - 172800_000_000_000 <= snapshot.collected_utc_ns <= cutoff:
                continue
            if snapshot.sha256 not in cache:
                catalogue = parse_element_sets(reader.read(snapshot))
                cache[snapshot.sha256] = [
                    (name, n, int(epoch), export_tle(sat))
                    for name, n, sat, epoch in zip(
                        catalogue.names,
                        catalogue.satellite_numbers,
                        catalogue.satellites,
                        catalogue.element_epoch_utc_ns(),
                        strict=True,
                    )
                    if "STARLINK" in name.upper()
                ]
            sources.append(
                dict(
                    path=str(snapshot.path),
                    collected_utc_ns=snapshot.collected_utc_ns,
                    digest=snapshot.digest,
                )
            )
            for name, n, epoch, lines in cache[snapshot.sha256]:
                if n not in numbers or not cutoff - 172800_000_000_000 <= epoch <= cutoff:
                    continue
                records[n].setdefault(
                    epoch,
                    dict(
                        name=name,
                        lines=lines,
                        epoch=epoch,
                        collected_utc_ns=snapshot.collected_utc_ns,
                        snapshot_digest=snapshot.digest,
                    ),
                )
        histories = {str(n): [v for _, v in sorted(r.items())] for n, r in sorted(records.items())}
        count = validate_history(histories, cutoff)
        path = ROOT / "reports/2026_10_18_dsx01_clean_region" / case / "causal_history.json"
        payload = dict(
            origin_utc_ns=receipt["origin_utc_ns"],
            cutoff_utc_ns=cutoff,
            past_versions=histories,
            source_snapshots=sources,
            candidate_count=len(numbers),
            record_count=count,
            association_whitelist_used=False,
            diagnostic_or_future_TLE_source_read=False,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and json.loads(path.read_text()) != json.loads(json.dumps(payload)):
            raise ValueError("preserve existing causal-history export")
        write(path, payload)
        print(case, len(numbers), count, len(sources), flush=True)


def from_verified_exports():
    """Use all available causal catalogue records, never an association subset.

    This has incomplete historical depth. Earlier scan exports contain orbital
    records only; no earlier radio/calibration/location estimate is transferred.
    """
    latest_path = ROOT / "reports/2026_10_18_dsx01_retention_localization/causal_tles.json"
    latest = json.loads(latest_path.read_text())
    for k in range(1, 6):
        case = f"DSX01-S0{k}"
        stem = (
            "2026_10_17_dsx01_polynomial_satellite_dive"
            if k == 1
            else "2026_10_17_robust_curve_reassociation"
        )
        folder = ROOT / "reports" / stem / "frozen_inputs" / case
        receipt = json.loads((folder / "receipt.json").read_text())
        with np.load(folder / "bank.npz") as bank:
            numbers = set(map(int, bank["norad"]))
        cutoff = receipt["cutoff_utc_ns"]
        records = {n: {} for n in numbers}
        sources = [str(latest_path)]
        for source_case, data in latest.items():
            if data["cutoff_utc_ns"] > cutoff:
                continue
            for number, record in data["satellites"].items():
                n = int(number)
                p = record["provenance"]
                if n in numbers and max(p["collected_utc_ns"], p["element_epoch_utc_ns"]) <= cutoff:
                    row = dict(
                        name=p["name"],
                        lines=record["lines"],
                        epoch=p["element_epoch_utc_ns"],
                        collected_utc_ns=p["collected_utc_ns"],
                        snapshot_digest=p["snapshot_digest"],
                    )
                    records[n][row["epoch"]] = row
            prior = ROOT / "reports/2026_10_18_dsx01_orbit_uncertainty/causal_inputs" / source_case
            meta = json.loads((prior / "previous_receipt.json").read_text())
            cat = parse_element_sets((prior / "previous.tle").read_text())
            sources += [str(prior / "previous.tle"), str(prior / "previous_receipt.json")]
            for name, n, sat in zip(cat.names, cat.satellite_numbers, cat.satellites, strict=True):
                p = meta["sources"][str(n)]
                if n in numbers and max(p["collected_utc_ns"], p["epoch_utc_ns"]) <= cutoff:
                    records[n].setdefault(
                        p["epoch_utc_ns"],
                        dict(
                            name=name,
                            lines=export_tle(sat),
                            epoch=p["epoch_utc_ns"],
                            collected_utc_ns=p["collected_utc_ns"],
                            snapshot_digest=p["digest"],
                        ),
                    )
        histories = {str(n): [v for _, v in sorted(r.items())] for n, r in sorted(records.items())}
        count = validate_history(histories, cutoff)
        path = ROOT / "reports/2026_10_18_dsx01_clean_region" / case / "causal_history.json"
        payload = dict(
            origin_utc_ns=receipt["origin_utc_ns"],
            cutoff_utc_ns=cutoff,
            past_versions=histories,
            source_exports=sources,
            candidate_count=len(numbers),
            record_count=count,
            association_whitelist_used=False,
            diagnostic_or_future_TLE_source_read=False,
            source_limitation=(
                "raw archive unreadable; available verified causal catalogues only; "
                "incomplete historical depth"
            ),
            earlier_scan_radio_or_position_used=False,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and json.loads(path.read_text()) != json.loads(json.dumps(payload)):
            raise ValueError("preserve existing causal-history export")
        write(path, payload)
        print(case, len(numbers), count, payload["source_limitation"], flush=True)


if __name__ == "__main__":
    run()
