"""Audit the frozen public position evidence without reading IQ or changing it."""
import hashlib
import json
from pathlib import Path

import numpy as np
from matplotlib.figure import Figure
from leo.storage.adaptive_tle_position import AdaptiveTlePositionStoreV2


def main():
    out = Path(__file__).resolve().parent
    source = out.parent / "2026_09_23_sixteen_scan_position_resolution"
    scans = json.loads((source / "scans.json").read_text())
    store = AdaptiveTlePositionStoreV2(Path("/srv/bulk/leo"))
    rows, receipts = [], []
    source_scans = {prior: {} for prior in ("sacramento", "reno")}
    for scan in scans:
        sid = scan["session_id"]
        doc = store.status(sid).manifest.document
        diagnostics = doc.diagnostics
        evidence = diagnostics["track_evidence"]
        for prior in source_scans:
            for score in diagnostics["selected_track_scores"][prior]:
                candidate = score.get("candidate_id")
                if candidate is not None:
                    source_scans[prior].setdefault(str(candidate), set()).add(sid)
        seen = set()
        for track in evidence:
            ids = track["observation_ids"]
            assert len(set(ids)) == len(ids) and not seen.intersection(ids)
            seen.update(ids)
            times = np.asarray(track["times_s"])
            mask = np.asarray(track["training_mask"], dtype=bool)
            assert mask.any() and (~mask).any()
            rows.append(dict(session_id=sid, track_id=track["track_id"],
                             duration_s=float(np.ptp(times)), observations=len(ids),
                             training=int(mask.sum()), evaluation=int((~mask).sum()),
                             rate_hz=scan["rate_hz"], edge=scan["edge"]))
        receipts.append(dict(session_id=sid, tracks=len(evidence), observations=len(seen),
            evidence_sha256=hashlib.sha256(json.dumps(evidence, sort_keys=True,
                separators=(",", ":")).encode()).hexdigest(),
            input_manifest_sha256=doc.input_manifest_sha256,
            analysis_manifest_sha256=doc.analysis_manifest_sha256,
            snapshot_digest=diagnostics.get("snapshot_digest")))
    assert len(rows) == 553 and sum(r["observations"] for r in rows) == 14043
    summary = dict(scans=len(scans), tracks=len(rows),
        observations=sum(r["observations"] for r in rows),
        training=sum(r["training"] for r in rows),
        evaluation=sum(r["evaluation"] for r in rows),
        duration_s_quantiles=np.quantile([r["duration_s"] for r in rows],
                                        [0, .25, .5, .75, 1]).tolist(),
        phase_constraint_status="Frequency-track evidence alone does not contain paired IQ phase, calibrated delay, or cross-dwell phase continuity; no phase-derived position is claimed.",
        validation_status="Saved randomized evaluation rows previously participated in full-catalogue identity/location selection; reuse is conditional sensitivity, not untouched predictive validation.",
        repeated_selected_identity_support={prior: dict(
            distinct_identities=len(sources),
            identities_in_multiple_scans=sum(len(sids)>1 for sids in sources.values()),
            max_scans_per_identity=max(map(len, sources.values())),
            caveat="Selected identity recurrence is conditional evidence, not verified satellite truth.")
            for prior, sources in source_scans.items()})
    (out / "evidence_audit.json").write_text(json.dumps(dict(summary=summary, scans=receipts,
                                                           tracks=rows), indent=2)+"\n")
    fig = Figure(figsize=(12, 4), layout="constrained")
    ax = fig.subplots(1, 3)
    ax[0].hist([r["duration_s"] for r in rows], bins=30, color="#267b9f")
    ax[0].set(xlabel="Track span (s)", ylabel="Tracks", title="All 553 eligible tracks retained")
    ax[1].scatter([r["duration_s"] for r in rows], [r["observations"] for r in rows],
                  s=10, alpha=.5, color="#267b9f")
    ax[1].set(xlabel="Track span (s)", ylabel="Observations", title="Sample count is not independence")
    ax[2].bar(np.arange(16), [r["observations"] for r in receipts], color="#267b9f")
    ax[2].set(xlabel="Chronological scan index (0–15)", ylabel="Observations",
              title="Same data for every method")
    fig.savefig(out / "evidence_profile.png", dpi=160)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
