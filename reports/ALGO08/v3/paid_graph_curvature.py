"""Trace the paid southern packet through the original pre-orbit curvature test."""

import argparse
from pathlib import Path

from aperture_trial import RELEASE, configuration, read, write
from sparse_consensus import paid_visits
from sparse_consensus_trial import bound_inputs


def trace(work):
    configuration()
    import numpy as np
    from leo.analysis.localization_v3.tracks import prepare_tracks
    from leo.analysis.polynomial_tracklets import TrackConfig
    from leo.contracts.digests import canonical_digest

    native, rows, _, _, _, _, identity = bound_inputs("south-containing")
    paid = paid_visits(rows)
    if any(len(r["candidates"]) > 1 for r in rows if r["visit_index"] in paid):
        raise ValueError("This attribution requires unique southern paid factors")
    probes = [dict(r, candidates=[c for c in r["candidates"] if c["passed_fractional_margin_gate"]]
                   if r["visit_index"] in paid else []) for r in rows]
    src = native["source"]
    digest = canonical_digest(["cancellation", src["raw_recording_authority_digest"], identity["ledger"]["detector_sha256"], probes])
    sparse = dict(native, source=dict(src, probes=probes, analysis_manifest_sha256=digest),
                  provenance=dict(native["provenance"], run_id="blind-compact-" + digest[7:39]))
    if canonical_digest(sparse) != read(work / "south-containing-margin.json")["identity"]["native_sha256"]:
        raise ValueError("Sparse attribution differs from the scored solver packet")
    config = TrackConfig(**read(RELEASE / "assets/tracks.json")["config"])
    result = {}
    for label, packet in (("complete", native), ("paid", sparse)):
        prepared = prepare_tracks(packet, config)
        arcs = []
        for track in prepared["tracks"]:
            t, y = track["times"], track["values"]
            x, centered = t - t.mean(), y - y.mean()
            residual = centered - x * (centered @ x) / max(x @ x, 1e-12)
            arcs.append(dict(points=len(t), span_s=float(np.ptp(t)), after_line_rms_hz=float(np.sqrt(np.mean(residual**2)))))
        actual = len(prepared["curved_indices"])
        if actual != sum(a["span_s"] >= 20 and a["after_line_rms_hz"] >= 250 for a in arcs):
            raise ValueError("Recomputed curvature differs from installed gate")
        result[label] = dict(packet_sha256=canonical_digest(packet), points=len(prepared["observations"]),
                             associated_with_graph=prepared["graph_points"], curved=actual, arcs=arcs)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    write(args.output, trace(args.work))
