"""Audit newest causal element epochs for frozen assigned satellite IDs.

Archive collection time and element epoch are different authorities. This
read-only audit does not choose an orbit using RF residuals or receiver position.
"""

import argparse
import json
from pathlib import Path

from replay_regional_doppler import digest, write_json

from leo.sky.propagation import parse_element_set_records, parse_element_sets


def newest_causal(rows, measurement_ns):
    eligible = [
        r
        for r in rows
        if r["collected_utc_ns"] < measurement_ns and r["epoch_utc_ns"] < measurement_ns
    ]
    if not eligible:
        raise ValueError("no causal element")
    return max(eligible, key=lambda r: (r["epoch_utc_ns"], r["collected_utc_ns"], r["digest"]))


def main():
    from leo.operations.tle_archive import TleArchiveReader

    p = argparse.ArgumentParser(description=__doc__)
    for key in ["archive", "evidence", "assignments", "output"]:
        p.add_argument("--" + key, type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise ValueError("fresh output required")
    rows = json.loads(a.assignments.read_text())["assignments"]
    docs = {
        r["session_id"]: json.loads(
            (a.evidence / "evidence" / (r["session_id"] + ".json")).read_text()
        )["inventory"]
        for r in rows
    }
    first = min(d["reference_utc_ns"] for d in docs.values())
    last = max(d["reference_utc_ns"] for d in docs.values())
    wanted = {r["norad"] for r in rows}
    archive = TleArchiveReader(a.archive)
    snapshots = [
        s
        for s in archive.list_snapshots()
        if first - 7 * 86400 * 10**9 <= s.collected_utc_ns < last
    ]
    cached, candidates = {}, {n: [] for n in wanted}
    for i, snapshot in enumerate(snapshots):
        if snapshot.digest not in cached:
            records = [
                r
                for r in parse_element_set_records(archive.read(snapshot))
                if r.satellite_number in wanted
            ]
            cached[snapshot.digest] = [
                (r, parse_element_sets(r.text).element_epoch_utc_ns()[0]) for r in records
            ]
        for record, epoch in cached[snapshot.digest]:
            candidates[record.satellite_number].append(
                dict(
                    epoch_utc_ns=epoch,
                    collected_utc_ns=snapshot.collected_utc_ns,
                    digest=snapshot.digest,
                    provider=snapshot.provider,
                    text=record.text,
                )
            )
        if i % 20 == 0:
            print("read", i + 1, "of", len(snapshots), "snapshots", flush=True)
    output = dict(
        assignments_digest=digest(a.assignments),
        evaluation_location_used=False,
        selection="maximum causal element epoch; then collection time and digest",
        lookback_days=7,
        archive_snapshot_count=len(snapshots),
        rows=[],
    )
    nominal = {}
    for row in rows:
        meta = docs[row["session_id"]]
        path = a.evidence / "evidence" / meta["tle_file"]
        if path not in nominal:
            if digest(path) != meta["tle_digest"]:
                raise ValueError("nominal TLE digest mismatch")
            cat = parse_element_sets(path.read_text())
            nominal[path] = dict(
                zip(cat.satellite_numbers, cat.element_epoch_utc_ns(), strict=True)
            )
        selected = newest_causal(candidates[row["norad"]], meta["reference_utc_ns"])
        old = nominal[path][row["norad"]]
        output["rows"].append(
            dict(
                session_id=row["session_id"],
                episode_id=row["episode_id"],
                norad=row["norad"],
                measurement_utc_ns=meta["reference_utc_ns"],
                nominal_epoch_utc_ns=old,
                nominal_tle_digest=meta["tle_digest"],
                selected=selected,
                strictly_newer_epoch=selected["epoch_utc_ns"] > old,
            )
        )
    write_json(a.output, output)
    print(
        "newer elements",
        sum(r["strictly_newer_epoch"] for r in output["rows"]),
        "of",
        len(rows),
        flush=True,
    )


if __name__ == "__main__":
    main()
