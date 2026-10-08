"""Reserve a random whole-recording split without opening analysis outcomes."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from leo.storage.adaptive_hop import AdaptiveHopIqStore

HERE = Path(__file__).resolve().parent


def main():
    output = HERE / "newer-random-split.json"
    if output.exists():
        raise FileExistsError(output)
    window = ["2026-10-08T18:30:00+00:00", "2026-10-08T20:00:00+00:00"]
    start, end = [int(datetime.fromisoformat(t).timestamp() * 1e9) for t in window]
    source = HERE.parent / "2026_10_08_position_error_iter12/membership-audit.json"
    reserved = HERE.parent / "2026_10_08_position_error_iter08/newer-validation.json"
    previous = (
        json.loads(source.read_text())["members"] + json.loads(reserved.read_text())["captures"]
    )
    old_ids = {r["session_id"] for r in previous}
    old_iq = {r["uncompressed_sha256"] for r in previous}
    rows, excluded = [], []
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    try:
        for ns, sid in sorted(store.history_index()):
            if not start <= ns < end:
                continue
            capture = store.inspect(sid)
            manifest = capture.manifest
            if manifest.finalized_utc_ns > end:
                excluded.append(dict(session_id=sid, reason="publication after cutoff"))
                continue
            assert sid not in old_ids and manifest.uncompressed_sha256 not in old_iq
            rows.append(
                dict(
                    label=f"FRESH-{len(rows) + 1:03d}",
                    session_id=sid,
                    capture_start_utc_ns=ns,
                    published_finalized_utc_ns=manifest.finalized_utc_ns,
                    recording_manifest_sha256=capture.manifest_sha256,
                    uncompressed_sha256=manifest.uncompressed_sha256,
                    sample_rate_hz=manifest.receipt.plan.geometry.sample_rate_hz,
                )
            )
    finally:
        store.close()
    assert len(rows) >= 3
    assert len({r["uncompressed_sha256"] for r in rows}) == len(rows)
    seed = 2026100818
    order = np.random.Generator(np.random.PCG64(seed)).permutation(len(rows)).tolist()
    validation_count = int(np.ceil(2 * len(rows) / 3))
    validation = set(order[:validation_count])
    for index, row in enumerate(rows):
        row["group"] = "validation" if index in validation else "development"
    output.write_text(
        json.dumps(
            dict(
                frozen_at=datetime.now(UTC).isoformat(),
                capture_start_window_utc=window,
                seed=seed,
                generator="numpy.PCG64",
                permutation=order,
                captures=rows,
                excluded=excluded,
                group_unit=(
                    "Whole recording; both receivers, all RF channels and all windows stay together"
                ),
                membership=(
                    "All published recordings in fixed window finalized by cutoff; "
                    "no analysis-readiness or position-error gate"
                ),
                development_count=len(rows) - validation_count,
                validation_count=validation_count,
                constraints=(
                    "No outcomes opened. Freeze candidate and acceptance criteria before validation. "
                    "Fit any cross-recording preprocessing on development only. "
                    "Small later sampling frame limits generalization."
                ),
                preserved_chronological_cohort_sha256=hashlib.sha256(
                    reserved.read_bytes()
                ).hexdigest(),
                consumed_membership_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            ),
            indent=2,
        )
        + "\n"
    )
    print(
        "Frozen",
        len(rows),
        "recordings:",
        len(rows) - validation_count,
        "development /",
        validation_count,
        "validation",
        flush=True,
    )


if __name__ == "__main__":
    main()
