"""Freeze metadata-only chronological DS8/DS9 transfer membership."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def select(manifest, count=8):
    rows = manifest["captures"]
    if len({r["session_id"] for r in rows}) != len(rows):
        raise ValueError("duplicate session")
    ordered = sorted(rows, key=lambda r: (r["capture_start_utc_ns"], r["session_id"]))
    if len(ordered) < count:
        raise ValueError("insufficient manifest membership")
    return [
        {
            "unit_id": f"{manifest['dataset_id']}-{i:03d}",
            "dataset_id": manifest["dataset_id"],
            "session_id": row["session_id"],
            "manifest_sha256": row["manifest_sha256"],
            "capture_start_utc_ns": row["capture_start_utc_ns"],
            "sample_rate_hz": row["sample_rate_hz"],
            "mint_analysis_evidence_sha256": row.get("analysis_evidence_sha256"),
        }
        for i, row in enumerate(ordered[:count], 1)
    ]


def main():
    captures, sources = [], []
    for name in ("2026_09_28_ds8_post_ds7", "2026_09_28_ds9_post_ds8"):
        path = ROOT / "reports" / name / "manifest.json"
        manifest = json.loads(path.read_text())
        captures.extend(select(manifest))
        sources.append(
            {
                "dataset_id": manifest["dataset_id"],
                "path": str(path.relative_to(ROOT)),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "recordings": len(manifest["captures"]),
            }
        )
    assert len({r["session_id"] for r in captures}) == 16
    plan = {
        "schema": "ds89-baseline-transfer-plan/v1",
        "sources": sources,
        "selection": (
            "first8 by capture_start_utc_ns then session_id; no analysis/performance filter"
        ),
        "captures": captures,
    }
    with (HERE / "plan.json").open("x") as stream:
        json.dump(plan, stream, indent=2)
    print(json.dumps({"selected": len(captures), "sources": sources}, indent=2))


if __name__ == "__main__":
    main()
