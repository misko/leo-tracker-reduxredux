"""Read-only inventory of recent capture and automatic positioning receipts.

Print a compact JSON snapshot. No service changes, new capture, or fitting.
Run with read access to the published local store and its analysis modules.
"""

import hashlib
import json
import math
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path("/srv/bulk/leo")


def utc(ns):
    return datetime.fromtimestamp(ns / 1e9, UTC).isoformat()


def distance(lat, lon, ref):
    a, b, c, d = map(math.radians, (lat, lon, *ref))
    h = math.sin((a - c) / 2) ** 2 + math.cos(a) * math.cos(c) * math.sin((b - d) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(min(1, h)))


def main():
    from leo.analysis.regional_position_score import coordinates
    from leo.contracts.regional_position import RegionalPrior
    from leo.storage.regional_position import RegionalPositionStore

    now = time.time_ns()
    cutoff = now - 6 * 3600 * 10**9
    captures = {}
    sources = {}
    regional = []

    def read(path):
        raw = path.read_bytes()
        sources[str(path)] = "sha256:" + hashlib.sha256(raw).hexdigest()
        return json.loads(raw)

    def capture(name):
        path = ROOT / "scanner-adaptive-recordings" / name / "manifest.json"
        if not path.exists():
            return None
        sealed = read(path)
        r = sealed["manifest"]
        t = r.get("timing", {})
        start = t.get("first_sample_estimate_utc_ns", r["created_utc_ns"])
        return dict(
            session=name,
            start_ns=start,
            start_utc=utc(start),
            sample_rate_hz=t.get("sample_rate_hz"),
            manifest_sha256=sealed["sha256"],
            timing_bracket_ms=t.get("first_sample_bracket_width_ns", 0) / 1e6,
            capture_duration_s=(t.get("terminal_realtime_ns", start) - start) / 1e9,
            finalized_utc=utc(r["finalized_utc_ns"]),
            capture_to_publication_s=(r["finalized_utc_ns"] - start) / 1e9,
        )

    for path in (ROOT / "scanner-adaptive-recordings").glob("*/manifest.json"):
        if path.stat().st_mtime_ns < cutoff:
            continue
        row = capture(path.parent.name)
        if row and row["start_ns"] >= cutoff:
            captures[row["session"]] = row
    store = RegionalPositionStore(ROOT)
    for directory in sorted((ROOT / "scanner-regional-position-v1").iterdir()):
        status = store.status(directory.name)
        if status.manifest is None:
            continue
        doc = status.manifest.document.model_dump(mode="json")
        path = directory / "document.json"
        read(path)
        for name in ("T1AT", "V16"):
            assert store.artifact(directory.name, name) is not None
        c = captures.get(directory.name) or capture(directory.name)
        assert c and c["manifest_sha256"] == doc["input_manifest_sha256"]
        d = doc["diagnostics"]
        bank = d.get("bank", {})
        row = dict(
            c,
            windows=doc["windows"],
            configuration=doc["configuration"],
            configuration_sha256=doc["configuration_sha256"],
            checkpoint_binding=d.get("checkpoint_binding"),
            completed_utc=utc(path.stat().st_mtime_ns),
            capture_to_regional_minutes=(path.stat().st_mtime_ns - c["start_ns"]) / 60e9,
            snapshot_age_hours=(c["start_ns"] - d.get("snapshot_collected_utc_ns", c["start_ns"]))
            / 3.6e12,
            retained_satellites=len(bank.get("retained_numbers", [])),
            invalid_satellites=bank.get("invalid_numbers", []),
            failures=d.get("regional_failures", []),
            reference=[doc["reference_latitude_deg"], doc["reference_longitude_deg"]],
            methods=[],
        )
        finals = d.get("final_starts", [])
        for m in doc["methods"]:
            mr = dict(
                name=m["name"],
                point_count=len(m["points"]),
                converged_points=sum(p["converged"] for p in m["points"]),
                unscored_points=sum(p["objective"] is None for p in m["points"]),
                stop=m["search_stop_reason"],
                deferred_cells=m["deferred_cells"],
                arms=[],
            )
            for arm in m["arms"]:
                selected = arm["selected"]
                starts = []
                for f in finals:
                    if f["method"] != m["name"] or f["arm"] != arm["name"] or f["fit"] is None:
                        continue
                    fit = f["fit"]
                    lat, lon = coordinates(RegionalPrior(), fit["vector"][:2])
                    starts.append(
                        dict(
                            basin=f["basin"],
                            start=f["start"],
                            score=fit["objective"] + f["calibration_penalty"],
                            error_m=distance(lat, lon, row["reference"]),
                            converged=fit["converged"],
                            stationarity=fit["stationarity"],
                            stop_reason=fit["stop_reason"],
                            vector=fit["vector"],
                        )
                    )
                mr["arms"].append(
                    dict(
                        name=arm["name"],
                        selected=selected,
                        completed_starts=arm["completed_starts"],
                        reasons=arm["reasons"],
                        starts=starts,
                    )
                )
            row["methods"].append(mr)
        regional.append(row)
    regional_ids = {r["session"] for r in regional}
    for c in captures.values():
        c["regional_complete"] = c["session"] in regional_ids
        work = ROOT / "scanner-regional-position-work-v1" / c["session"]
        c["regional_checkpoints"] = sum(1 for p in work.glob("*/*.json")) if work.exists() else 0
        c["analysis_present"] = (ROOT / "scanner-adaptive-analysis" / c["session"]).exists()
    print(
        json.dumps(
            dict(
                snapshot_utc=utc(now),
                cutoff_utc=utc(cutoff),
                captures=sorted(captures.values(), key=lambda r: r["start_ns"]),
                regional=sorted(regional, key=lambda r: r["start_ns"]),
                source_sha256=sources,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
