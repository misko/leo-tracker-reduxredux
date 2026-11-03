"""Read-only causal GP revision coverage; emits metadata, not provider bytes."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent


def select(refs, cutoff, strict=True):
    eligible = [
        r
        for r in refs
        if r.collected_utc_ns < cutoff or (not strict and r.collected_utc_ns == cutoff)
    ]
    return max(eligible, key=lambda r: (r.collected_utc_ns, r.sha256)) if eligible else None


def epoch_ns(line):
    year = int(line[18:20])
    year += 1900 if year >= 57 else 2000
    day = Decimal(line[20:32])
    date = datetime(year, 1, 1, tzinfo=UTC) + timedelta(days=int(day) - 1)
    return int(date.timestamp()) * 10**9 + int((day - int(day)) * 86400 * 10**9)


def main():
    import inspect

    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_set_records

    reader = TleArchiveReader(Path("/var/lib/leo/tle"))
    refs = reader.list_snapshots("space-track")
    cache, snapshots, rows, hashes = {}, {}, [], {}

    def records(ref):
        if ref is None:
            return {}
        key = str(ref.path)
        if key not in cache:
            parsed = parse_element_set_records(reader.read(ref))
            mapping = {}
            for r in parsed:
                if r.satellite_number in mapping:
                    raise ValueError("duplicate catalogue number")
                mapping[r.satellite_number] = dict(
                    epoch_ns=epoch_ns(r.first_line),
                    element_sha256=hashlib.sha256(
                        (r.first_line + "\n" + r.second_line + "\n").encode()
                    ).hexdigest(),
                )
            cache[key] = mapping
            snapshots[key] = dict(
                collected_utc_ns=ref.collected_utc_ns,
                sha256=ref.sha256,
                provider=ref.provider,
                objects=len(mapping),
            )
        return cache[key]

    root = HERE.parent.parent
    prior_path = HERE.parent / "2026_09_29_candidate_rx_transfer/results.json"
    prior = json.loads(prior_path.read_text())
    for path, digest in prior["hashes"].items():
        assert hashlib.sha256((root / path).read_bytes()).hexdigest() == digest
    paths = sorted(
        (HERE.parent / "2026_09_29_donor_residual_transfer/runs").glob("DS*_*_8/result.json")
    )
    for path in paths:
        data = json.loads(path.read_text())
        for c in data["cases"]:
            latest = select(refs, c["start_utc_ns"] - 505_000_000_000)
            assert latest is not None
            refs_by_age = {
                "latest": latest,
                **{
                    f"older_{h}h": select(refs, latest.collected_utc_ns - h * 3600 * 10**9, False)
                    for h in (6, 24)
                },
            }
            row = {k: c[k] for k in ("unit_id", "session_id", "track_id", "number", "start_utc_ns")}
            row["products"] = {}
            for label, ref in refs_by_age.items():
                r = records(ref).get(c["number"])
                row["products"][label] = dict(
                    snapshot=str(ref.path) if ref else None,
                    record=r,
                    element_age_hours=(c["start_utc_ns"] - r["epoch_ns"]) / 3.6e12 if r else None,
                )
            rows.append(row)
    assert len(paths) == 9 and len(rows) == 3983
    for path in paths + [HERE / "inventory.py", HERE / "PROTOCOL.md", prior_path]:
        hashes[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    runtime = {}
    for obj in (TleArchiveReader, parse_element_set_records):
        path = Path(inspect.getfile(obj))
        runtime[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    print(
        json.dumps(dict(hashes=hashes, runtime=runtime, snapshots=snapshots, rows=rows), indent=2)
    )


if __name__ == "__main__":
    main()
