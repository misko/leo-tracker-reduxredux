"""Freeze the new 24-hour cohort by time/availability, never positioning error."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_tle_position import AdaptiveTlePositionStoreV2

OUT = Path(__file__).resolve().parent
END = datetime(2026, 9, 23, 15, 15, tzinfo=timezone.utc)
END_NS = int(END.timestamp()*1e9)
START_NS = END_NS - 86400*10**9


def main():
    previous = json.loads((OUT.parent / "2026_09_23_sixteen_scan_position_resolution/selection.json").read_text())
    original = set(previous["session_ids"])
    iq = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    try:
        candidates = [sid for timestamp, sid in iq.publication_index()
                      if START_NS-600*10**9 <= timestamp <= END_NS+600*10**9]
    finally:
        iq.close()

    def inspect(sid):
        try:
            with urlopen("http://127.0.0.1:8090/api/v3/scanner/adaptive-sessions/"+sid, timeout=60) as response:
                capture = json.load(response)["capture"]
            stamp = int(datetime.fromisoformat(capture["captured_at"]).timestamp()*1e9)
            if not START_NS <= stamp < END_NS:
                return dict(session_id=sid, state="outside_capture_start_window")
            row = dict(session_id=sid, captured_at=capture["captured_at"],
                       sample_rate_hz=capture["sample_rate_hz"], edge=capture.get("selected_edge"))
            if sid in original:
                return dict(row, state="excluded_original_development_scan")
            status = AdaptiveTlePositionStoreV2(Path("/srv/bulk/leo")).status(sid)
            if status.manifest is None:
                return dict(row, state="position_evidence_unavailable")
            doc = status.manifest.document
            tracks = doc.diagnostics.get("track_evidence", [])
            if not tracks:
                return dict(row, state="no_eligible_track_evidence")
            return dict(row, state="eligible", tracks=len(tracks),
                observations=sum(len(t["times_s"]) for t in tracks),
                training=sum(sum(t["training_mask"]) for t in tracks),
                evidence_digest=hashlib.sha256(json.dumps(tracks,sort_keys=True,separators=(",",":")).encode()).hexdigest(),
                input_manifest_sha256=doc.input_manifest_sha256,
                analysis_manifest_sha256=doc.analysis_manifest_sha256)
        except Exception as error:
            return dict(session_id=sid,state="unavailable",reason=f"{type(error).__name__}: {error}")
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(inspect, candidates))
    rows.sort(key=lambda row:(row.get("captured_at", ""),row["session_id"]))
    eligible = [r for r in rows if r["state"] == "eligible"]
    groups = []
    for start in range(0,len(eligible),16):
        chunk = eligible[start:start+16]
        groups.append(dict(group_id=f"block_{len(groups)+1:02d}",
            session_ids=[r["session_id"] for r in chunk], scan_count=len(chunk),
            complete_16_scan_block=len(chunk)==16, start=chunk[0]["captured_at"],end=chunk[-1]["captured_at"]))
    result=dict(window_start=datetime.fromtimestamp(START_NS/1e9,timezone.utc).isoformat(),
        window_end=END.isoformat(), eligibility="Capture start in frozen half-open24h window; original16 excluded; existing nonempty public V2 track evidence",
        grouping="All eligible scans chronological, nonoverlapping chunks16; last partial retained separately; gaps do not imply continuous IQ",
        known_position_used_for_selection=False, original_excluded_ids=sorted(original),
        counts={state:sum(r["state"]==state for r in rows) for state in sorted({r["state"] for r in rows})},
        eligible_session_ids=[r["session_id"] for r in eligible],groups=groups,scans=rows)
    (OUT/"inventory.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"counts":result["counts"],"groups":groups},indent=2))


if __name__ == "__main__": main()
