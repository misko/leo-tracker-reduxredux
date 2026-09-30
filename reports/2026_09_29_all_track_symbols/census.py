"""Freeze the >=5 MS/s, >3-second public-track census without reading raw IQ."""

import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).parent
OUT = BASE / "local"


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def eligible(track, rate):
    return rate >= 5_000_000 and max(track["times_s"]) - min(track["times_s"]) > 3


def main():
    OUT.mkdir(exist_ok=True)
    authority = ROOT / "reports/2026_09_28_full_manifest_inputs"
    plan = json.loads((authority / "plan.json").read_text())
    captures = []
    for row in plan["captures"]:
        if row["sample_rate_hz"] < 5_000_000:
            continue
        mp = ROOT / row["dataset_manifest_path"]
        assert digest(mp) == row["dataset_sha256"]
        member = next(
            c
            for c in json.loads(mp.read_text())["captures"]
            if c["session_id"] == row["session_id"]
        )
        assert member["manifest_sha256"] == row["manifest_sha256"]
        artifacts = (row.get("reused_input") or {}).get("artifacts", [])
        source = next((a for a in artifacts if a["kind"] == "observations"), None)
        p = (
            Path(source["path"])
            if source
            else authority / "exports" / row["unit_id"] / "observations.json"
        )
        sha = digest(p)
        if source:
            assert sha == source["sha256"]
        d = json.loads(p.read_text())
        assert d["manifest_sha256"] == row["manifest_sha256"]
        assert d["sample_rate_hz"] == row["sample_rate_hz"]
        tracks = []
        for t in d["tracks"]:
            if not eligible(t, row["sample_rate_hz"]):
                continue
            assert len(t["visits"]) == len(t["times_s"]) == len(t["measured_hz"])
            tracks.append(dict(**t, span_s=max(t["times_s"]) - min(t["times_s"])))
        captures.append(
            dict(
                unit=row["unit_id"],
                dataset=row["dataset_id"],
                session=row["session_id"],
                rate=row["sample_rate_hz"],
                capture_manifest=row["manifest_sha256"],
                analysis_manifest=d["analysis_manifest_sha256"],
                start_utc_ns=d["start_utc_ns"],
                source=str(p),
                source_sha256=sha,
                tracks=tracks,
            )
        )
    output = dict(
        captures=captures,
        counts=dict(Counter(c["dataset"] for c in captures)),
        tracks=sum(len(c["tracks"]) for c in captures),
        policy="All frozen DS7/DS8/DS9 captures >=5MS/s, public exported tracks "
        "with span strictly >3s. Existing track builder also requires support>=6. "
        "Receiver tracks are distinct observations, not unique satellites. "
        "Span includes scan gaps; not continuous dwell. Excerpt census planned; "
        "not every visit or every raw sample decoded.",
    )
    (OUT / "census.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({k: v for k, v in output.items() if k != "captures"}, indent=2))


if __name__ == "__main__":
    main()
