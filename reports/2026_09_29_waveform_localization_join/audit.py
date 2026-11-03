"""Exact provenance join of waveform census and fixed localization posterior."""

import hashlib
import json
from collections import Counter
from pathlib import Path
from statistics import median

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CENSUS = HERE.parent / "2026_09_29_all_track_symbols"


def selected_partition(track, visit):
    indexes = [i for i, v in enumerate(track["visits"]) if v == visit]
    if not indexes:
        raise ValueError("selected visit absent from exact track")
    states = {bool(track["training_mask"][i]) for i in indexes}
    if len(states) != 1:
        raise ValueError("whole-visit partition inconsistent")
    return "training" if states.pop() else "held"


def main():
    paths = [
        CENSUS / "local/census.json",
        CENSUS / "decode_tracks.py",
        HERE / "audit.py",
        HERE / "PROTOCOL.md",
        HERE.parent / "2026_09_29_donor_residual_transfer/plan.json",
    ]
    census = json.loads(paths[0].read_text())
    captures = {c["session"]: c for c in census["captures"]}
    plan = json.loads(paths[-1].read_text())
    rows = []
    for u in plan["units"]:
        if u["role"] != "target":
            continue
        posterior_path = ROOT / u["posterior"]
        paths.append(posterior_path)
        post = {
            (r["session_id"], r["track_id"]): r
            for r in json.loads(posterior_path.read_text())["rows"]
        }
        residual_path = (
            HERE.parent / "2026_09_29_donor_residual_transfer/runs" / u["unit_id"] / "result.json"
        )
        paths.append(residual_path)
        residuals = {
            (c["session_id"], c["track_id"]): c
            for c in json.loads(residual_path.read_text())["cases"]
        }
        for entry in u["group"]["inputs"]:
            a = next(a for a in entry["artifacts"] if a["kind"] == "observations")
            p = Path(a["path"])
            paths.append(p)
            assert "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest() == a["sha256"]
            obs = json.loads(p.read_text())
            session = entry["session_id"]
            capture = captures.get(session)
            decoded = {}
            if capture:
                assert capture["capture_manifest"] == entry["manifest_sha256"]
                assert capture["source_sha256"] == a["sha256"]
                dp = CENSUS / "local/decoded" / capture["unit"] / "results.json"
                paths.append(dp)
                data = json.loads(dp.read_text())
                binding = hashlib.sha256(
                    json.dumps(
                        dict(
                            capture=capture,
                            frames=data["frames_requested"],
                            script_sha=hashlib.sha256(
                                (CENSUS / "decode_tracks.py").read_bytes()
                            ).hexdigest(),
                        ),
                        sort_keys=True,
                    ).encode()
                ).hexdigest()
                assert binding == data["binding"]
                decoded = {r["track_id"]: r for r in data["rows"]}
            for t in obs["tracks"]:
                pr = post.get((session, t["track_id"]))
                if pr is None:
                    continue
                row = dict(
                    unit_id=u["unit_id"],
                    session_id=session,
                    track_id=t["track_id"],
                    sample_rate_hz=obs["sample_rate_hz"],
                    responsibility=pr["signal_responsibility"],
                    strong=pr["signal_responsibility"] * max(pr["weights_given_signal"]) >= 0.5,
                    status="not_in_census",
                    selected_partition=None,
                    residual_error_hz=None,
                )
                d = decoded.get(t["track_id"])
                if capture and d is None:
                    row["status"] = "track_missing_from_census"
                if d:
                    assert d["exact_track_binding"]
                    row["status"] = d["status"]
                    row["selected_partition"] = selected_partition(t, d["visit"])
                    row["selected_visit"] = d["visit"]
                    row["pilot_coherences"] = [
                        d["receiver_metadata"]["diagnostics"][f]["held_pilot_coherence"]
                        for f in d["receiver_metadata"]["evaluation_frames"]
                    ]
                    assert (row["status"] == "qualified") == all(
                        v > 0.5 for v in row["pilot_coherences"]
                    )
                c = residuals.get((session, t["track_id"]))
                if c:
                    e = np.asarray(c["residual"])
                    m = np.asarray(c["mask"], bool)
                    row["residual_error_hz"] = float(np.median(abs(e[~m] - e[m].mean())))
                rows.append(row)
    assert len(rows) == 4328
    summary = {}
    for ds in ("all", "DS7", "DS8", "DS9"):
        selected = [r for r in rows if ds == "all" or r["unit_id"].startswith(ds)]
        by_status = {}
        for status in sorted({r["status"] for r in selected}):
            group = [r for r in selected if r["status"] == status]
            errors = [r["residual_error_hz"] for r in group if r["residual_error_hz"] is not None]
            by_status[status] = dict(
                tracks=len(group),
                strong=sum(r["strong"] for r in group),
                median_signal_responsibility=median(r["responsibility"] for r in group),
                selected_partition=dict(Counter(r["selected_partition"] for r in group)),
                residual_cases=len(errors),
                median_held_residual_hz=median(errors) if errors else None,
            )
        summary[ds] = by_status
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    (HERE / "results.json").write_text(
        json.dumps(dict(hashes=hashes, rows=rows, summary=summary), indent=2) + "\n"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
