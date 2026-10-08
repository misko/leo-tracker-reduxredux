"""Reserve new whole-scan random groups without reading positioning outcomes."""

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
    window = ["2026-10-08T20:00:00+00:00", "2026-10-08T21:10:00+00:00"]
    start, end = [int(datetime.fromisoformat(t).timestamp() * 1e9) for t in window]
    membership = HERE.parent / "2026_10_08_position_error_iter12/membership-audit.json"
    recent = HERE.parent / "2026_10_08_position_error_iter20/validation-protocol.json"
    previous = (
        json.loads(membership.read_text())["members"] + json.loads(recent.read_text())["members"]
    )
    old_ids = {row["session_id"] for row in previous}
    old_iq = {row["uncompressed_sha256"] for row in previous}
    assert len(old_ids) == len(old_iq) == 119
    rows, excluded = [], []
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    try:
        for ns, session_id in sorted(store.history_index()):
            if not start <= ns < end:
                continue
            capture = store.inspect(session_id)
            manifest = capture.manifest
            if manifest.finalized_utc_ns > end:
                excluded.append(
                    dict(session_id=session_id, reason="publication after fixed cutoff")
                )
                continue
            assert session_id not in old_ids and manifest.uncompressed_sha256 not in old_iq
            rows.append(
                dict(
                    label=f"RESERVED-{len(rows) + 1:03d}",
                    session_id=session_id,
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
    assert len({row["uncompressed_sha256"] for row in rows}) == len(rows)
    seed = 2026100826
    order = np.random.Generator(np.random.PCG64(seed)).permutation(len(rows)).tolist()
    count = int(np.ceil(2 * len(rows) / 3))
    validation = set(order[:count])
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
                development_count=len(rows) - count,
                validation_count=count,
            membership=(
                "All published recordings in fixed window finalized by cutoff; "
                "no analysis-readiness or error filter"
            ),
                group_unit="Whole recording; both receivers, all channels and all windows together",
            constraints=(
                "No outcomes opened. Freeze qualified candidate and acceptance criteria "
                "before validation. No retuning on validation outcomes. "
                "Small sampling frame limits generalization."
            ),
                source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                consumed_membership_sha256=hashlib.sha256(membership.read_bytes()).hexdigest(),
                newer_consumed_protocol_sha256=hashlib.sha256(recent.read_bytes()).hexdigest(),
            ),
            indent=2,
        )
        + "\n"
    )
    print(f"Reserved {len(rows)}: {len(rows) - count} development / {count} validation", flush=True)


if __name__ == "__main__":
    main()
