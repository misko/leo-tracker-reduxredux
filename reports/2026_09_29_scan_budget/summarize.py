import collections
import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PREVIOUS = HERE.parent / "2026_09_29_time_balanced_scans"


def distance(point, reference):
    p, q = np.radians(point), np.radians(reference)
    a = (
        np.sin((p[0] - q[0]) / 2) ** 2
        + np.cos(p[0]) * np.cos(q[0]) * np.sin((p[1] - q[1]) / 2) ** 2
    )
    return float(2 * 6371008.8 * np.arcsin(np.sqrt(a)))


def verify(doc):
    for name, digest in doc["hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name


def main():
    reference = json.loads(
        (HERE.parent / "2026_09_29_unassociated_trend/summary.json").read_text()
    )["reference"]
    manifest = json.loads((HERE / "manifest.json").read_text())
    verify(manifest)
    rows, missing, hashes = [], [], {}
    table = [
        "| Set | Qualified | Error m | Start span h | Tracks | Held log score |",
        "|---|:---:|---:|---:|---:|---:|",
    ]
    for unit in manifest["sets"]:
        if unit["count"] == 8:
            path = PREVIOUS / f"grid_{unit['dataset']}_balanced_{unit['fold']}.json"
            primary = json.loads(
                (PREVIOUS / f"{unit['dataset']}_balanced_{unit['fold']}.json").read_text()
            )
            verify(primary)
        else:
            path = HERE / f"{unit['unit']}.json"
        if not path.exists():
            missing.append(unit["unit"])
            table.append(f"| {unit['unit']} | NO OUTPUT | — | — | — | — |")
            continue
        row = json.loads(path.read_text())
        verify(row)
        hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        assert row["sessions"] == [r["session_id"] for r in unit["scans"]]
        row.update(
            unit=unit["unit"],
            count=unit["count"],
            fold=unit["fold"],
            qualified=row["selected"] is not None,
        )
        row["error_m"] = (
            distance(row["selected"]["estimate_deg"], reference) if row["qualified"] else None
        )
        rows.append(row)
        if row["qualified"]:
            table.append(
                f"| {row['unit']} | yes | {row['error_m']:.2f} "
                f"| {row['start_span_hours']:.3f} | {row['tracks']} "
                f"| {row['selected']['held_score']:.3f} |"
            )
        else:
            table.append(
                f"| {row['unit']} | NO | — | {row['start_span_hours']:.3f} | {row['tracks']} | — |"
            )
    aggregates = []
    for ds in ("DS7", "DS8", "DS9"):
        reference_rows = [r for r in rows if r["dataset"] == ds and r["count"] == 8]
        expected = collections.Counter(s for r in reference_rows for s in r["sessions"])
        baseline_held = sum(r["selected"]["held_score"] for r in reference_rows)
        for count, number, multiplicity in ((8, 3, 1), (12, 2, 1), (16, 3, 2), (24, 1, 1)):
            selected = [r for r in rows if r["dataset"] == ds and r["count"] == count]
            complete = len(selected) == number and all(r["qualified"] for r in selected)
            aggregate = dict(dataset=ds, count=count, complete=complete)
            if complete:
                coverage = collections.Counter(s for r in selected for s in r["sessions"])
                assert coverage == {k: v * multiplicity for k, v in expected.items()}
                assert sum(r["observations"] for r in selected) == multiplicity * sum(
                    r["observations"] for r in reference_rows
                )
                normalized = sum(r["selected"]["held_score"] for r in selected) / multiplicity
                aggregate.update(
                    sets=number,
                    median_error_m=float(np.median([r["error_m"] for r in selected])),
                    subkm=sum(r["error_m"] < 1000 for r in selected),
                    normalized_held_score=normalized,
                    held_gain_vs_eight=normalized - baseline_held,
                    min_span_h=min(r["start_span_hours"] for r in selected),
                    max_span_h=max(r["start_span_hours"] for r in selected),
                )
            aggregates.append(aggregate)
    (HERE / "TABLE.md").write_text("\n".join(table) + "\n")
    (HERE / "summary.json").write_text(
        json.dumps(
            dict(
                reference=reference,
                prior_center_error_m=distance(
                    manifest["config"]["geographic_prior_center_deg"], reference
                ),
                rows=rows,
                missing=missing,
                aggregates=aggregates,
                hashes=hashes,
            ),
            indent=2,
        )
        + "\n"
    )
    print(json.dumps(dict(missing=missing, aggregates=aggregates), indent=2))


if __name__ == "__main__":
    main()
