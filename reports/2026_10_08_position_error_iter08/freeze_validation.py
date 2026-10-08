"""Reserve later published recordings without opening localization outcomes."""

import json
from datetime import UTC, datetime
from pathlib import Path

from leo.storage.adaptive_hop import AdaptiveHopIqStore

HERE = Path(__file__).resolve().parent


def main():
    output = HERE / "newer-validation.json"
    if output.exists():
        raise FileExistsError(output)
    window = ["2026-10-08T16:50:00+00:00", "2026-10-08T18:30:00+00:00"]
    start, end = [int(datetime.fromisoformat(t).timestamp() * 1e9) for t in window]
    old = json.loads(
        (HERE.parent / "2026_10_08_position_error_iter01/ds17-manifest.json").read_text()
    )
    newer = json.loads(
        (HERE.parent / "2026_10_08_position_error_iter05/newer-recordings.json").read_text()
    )
    previous = old["captures"] + newer["captures"]
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
                    label=f"LATER-{len(rows) + 1:03}",
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
                capture_start_window_utc=window,
                captures=rows,
                excluded=excluded,
                membership="All published recordings in fixed capture window, published by cutoff; no localization or analysis-readiness admission gate; unpublished/spooled recordings outside this cohort",
                role="Reserved later validation; no outcomes opened and no RF collection launched",
            ),
            indent=2,
        )
        + "\n"
    )
    print("Frozen", len(rows), "later recordings; excluded", len(excluded))


if __name__ == "__main__":
    main()
