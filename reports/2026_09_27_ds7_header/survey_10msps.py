"""Bounded cached-candidate survey; no raw IQ reads or source mutations."""

import dataclasses
import hashlib
import json
import time
from pathlib import Path

from leo.storage.scanner_tracking_source import ScannerTrackingInputStore


def main():
    root = Path(__file__).resolve().parents[2]
    path = root / "reports/2026_09_27_ds7_post_ds6/manifest.json"
    manifest = json.loads(path.read_text())
    out = Path(__file__).parent / "local/survey"
    out.mkdir(exist_ok=True)
    output = out / "cached-candidates.json"
    rows = json.loads(output.read_text())["sessions"] if output.exists() else []
    completed = {r["session_id"] for r in rows}
    store = ScannerTrackingInputStore(Path(manifest["source_bulk_root"]))
    start = time.monotonic()
    for capture in manifest["captures"]:
        sid = capture["session_id"]
        if capture["sample_rate_hz"] != 10000000 or sid in completed:
            continue
        if time.monotonic() - start > 85:
            break
        raw = store.load(sid)
        assert raw.input_manifest_sha256 == capture["manifest_sha256"]
        qualified = [
            (p, c) for p in raw.probes for c in p.candidates if c.passed_fractional_margin_gate
        ]
        ranked = sorted(qualified, key=lambda pc: pc[1].fractional_margin, reverse=True)
        top, seen = [], set()
        for probe, candidate in ranked:
            key = (probe.visit_index, probe.edge)
            if key in seen:
                continue
            seen.add(key)
            top.append(
                dict(
                    probe={k: v for k, v in dataclasses.asdict(probe).items() if k != "candidates"},
                    candidate=dataclasses.asdict(candidate),
                )
            )
            if len(top) == 6:
                break
        row = dict(
            session_id=sid,
            manifest_sha256=raw.input_manifest_sha256,
            analysis_manifest_sha256=raw.analysis_manifest_sha256,
            qualified_candidates=len(qualified),
            top=top,
        )
        rows.append(row)
        output.write_text(
            json.dumps(
                dict(
                    dataset_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    reader_release=manifest["storage_reader_release"],
                    sessions=rows,
                    raw_iq_bytes=0,
                    total_eligible_sessions=19,
                    policy="six highest cached margins from distinct visit/edge pairs per session",
                ),
                indent=2,
            )
            + "\n"
        )
        print(
            sid,
            len(qualified),
            [(p["probe"]["edge"], round(p["candidate"]["fractional_margin"], 4)) for p in top[:2]],
            flush=True,
        )
    store.close()
    print(f"surveyed {len(rows)}/19 sessions", flush=True)


if __name__ == "__main__":
    main()
