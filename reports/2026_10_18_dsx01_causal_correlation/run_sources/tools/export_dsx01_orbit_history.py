"""Read-only past element histories and explicitly separate following-version diagnostics."""

import json
from pathlib import Path

from sgp4.exporter import export_tle

from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets


def run():
    root = Path(__file__).resolve().parents[1]
    definitions = {}
    wanted = set()
    for number in range(1, 6):
        case = f"DSX01-S0{number}"
        bank = (
            root
            / (
                "reports/2026_10_17_dsx01_polynomial_satellite_dive/frozen_inputs"
                if number == 1
                else "reports/2026_10_17_robust_curve_reassociation/frozen_inputs"
            )
            / case
        )
        receipt = json.loads((bank / "receipt.json").read_text())
        source = root / "reports/2026_10_18_dsx01_nomination_iteration/seeds_32" / case
        numbers = {
            r["candidate_norad"]
            for p in source.glob("*_center.json")
            for r in json.loads(p.read_text())["rows"]
        }
        selected = (
            root / "reports/2026_10_17_noise_gated_position/frozen_inputs/DSX01-S01/selected.tle"
            if number == 1
            else bank / "selected.tle"
        )
        cat = parse_element_sets(selected.read_text())
        latest = {
            n: dict(name=name, lines=export_tle(sat), epoch=int(epoch))
            for n, name, sat, epoch in zip(
                cat.satellite_numbers,
                cat.names,
                cat.satellites,
                cat.element_epoch_utc_ns(),
                strict=True,
            )
            if n in numbers
        }
        definitions[case] = dict(receipt=receipt, latest=latest)
        wanted.update(numbers)
    reader = TleArchiveReader(Path("/var/lib/leo/tle"))
    refs = reader.list_snapshots("space-track")
    earliest = (
        min(d["receipt"]["cutoff_utc_ns"] for d in definitions.values()) - 48 * 3600_000_000_000
    )
    latest = (
        max(d["receipt"]["origin_utc_ns"] for d in definitions.values())
        + 300_000_000_000
        + 24 * 3600_000_000_000
    )
    refs = [r for r in refs if earliest <= r.collected_utc_ns <= latest]
    unique = {r.sha256: r for r in refs}
    parsed = {}
    for digest, ref in unique.items():
        cat = parse_element_sets(reader.read(ref))
        parsed[digest] = {
            n: dict(name=name, lines=export_tle(sat), epoch=int(epoch))
            for n, name, sat, epoch in zip(
                cat.satellite_numbers,
                cat.names,
                cat.satellites,
                cat.element_epoch_utc_ns(),
                strict=True,
            )
            if n in wanted
        }
    result = {}
    for case, definition in definitions.items():
        receipt = definition["receipt"]
        cut = receipt["cutoff_utc_ns"]
        end = receipt["origin_utc_ns"] + 300_000_000_000
        histories = {n: {} for n in definition["latest"]}
        following = {}
        for ref in refs:
            for n, row in parsed[ref.sha256].items():
                if n not in histories:
                    continue
                current = definition["latest"][n]
                record = dict(
                    row, collected_utc_ns=ref.collected_utc_ns, snapshot_digest=ref.digest
                )
                if (
                    cut - 48 * 3600_000_000_000 <= ref.collected_utc_ns <= cut
                    and row["epoch"] <= current["epoch"]
                ):
                    histories[n][row["epoch"]] = record
                if (
                    end < ref.collected_utc_ns <= end + 24 * 3600_000_000_000
                    and row["epoch"] > current["epoch"]
                ):
                    following.setdefault(n, record)
        result[case] = dict(
            cutoff_utc_ns=cut,
            origin_utc_ns=receipt["origin_utc_ns"],
            following_versions_are_diagnostic_only_never_causal_inference=True,
            candidates={
                n: dict(
                    latest_causal=current,
                    past_versions=[histories[n][epoch] for epoch in sorted(histories[n])[-4:]],
                    first_following_newer_version=following.get(n),
                )
                for n, current in definition["latest"].items()
            },
        )
    return result


if __name__ == "__main__":
    print(json.dumps(run()))
