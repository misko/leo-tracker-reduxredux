"""Freeze published newer recordings using metadata only, before position outcomes."""

import json
from datetime import UTC, datetime
from pathlib import Path

from leo.storage.adaptive_hop import AdaptiveHopIqStore

HERE = Path(__file__).resolve().parent


def main():
    output = HERE / "newer-recordings.json"
    if output.exists():
        raise FileExistsError(output)
    start = int(datetime.fromisoformat("2026-10-08T14:36:56+00:00").timestamp() * 1e9)
    end = int(datetime.fromisoformat("2026-10-08T16:50:00+00:00").timestamp() * 1e9)
    old = json.loads(
        (HERE.parent / "2026_10_08_position_error_iter01/ds17-manifest.json").read_text()
    )
    previous = {r["session_id"] for r in old["captures"]}
    rows, excluded = [], []
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    try:
        for ns, sid in sorted(store.history_index()):
            if not start <= ns < end:
                continue
            capture = store.inspect(sid)
            manifest = capture.manifest
            if manifest.finalized_utc_ns > end:
                excluded.append(dict(session_id=sid, reason="published after fixed cutoff"))
                continue
            assert sid not in previous
            rows.append(
                dict(
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
    assert len({r["uncompressed_sha256"] for r in rows}) == len(rows)
    output.write_text(
        json.dumps(
            dict(
                frozen_at=datetime.now(UTC).isoformat(),
                capture_start_window_utc=["2026-10-08T14:36:56+00:00", "2026-10-08T16:50:00+00:00"],
                membership=(
                    "All recordings published by cutoff in capture window; "
                    "metadata-only admission, "
                    "no analysis-readiness or position-error gate. Unpublished/spooled recordings "
                    "are outside this published replication cohort."
                ),
                role="Separate newer-data replication; no new RF acquisition",
                captures=rows,
                excluded=excluded,
            ),
            indent=2,
        )
        + "\n"
    )
    print("Frozen newer published recordings:", len(rows))


if __name__ == "__main__":
    main()
