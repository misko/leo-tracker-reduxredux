"""Evaluate the newly completed DS22-137 export without changing the old seal."""

import hashlib
import json
from pathlib import Path

import evaluate_ds22_merged_tracks as graph


def run():
    raw = Path("/tmp/ds22-fast137-existing-tracking.json").read_bytes()
    authority = json.loads(Path("/tmp/ds22-fast137-existing-receipt.json").read_text())
    if hashlib.sha256(raw).hexdigest() != authority["tracking_sha256"]:
        raise ValueError("existing tracking export changed")
    document = json.loads(raw)
    rows, metadata = graph.winners(document)
    config = graph.TrackConfig(**json.loads(graph.CONFIG.read_text())["config"])
    tracks, count = graph.graph_tracks(rows, "DS22-137", config)
    calibration, result = graph.merge_tracks(tracks)
    folder = graph.ROOT / "reports/2026_10_17_ds22_physical_model_revision/fast_recovered/DS22-137"
    folder.mkdir(parents=True, exist_ok=False)
    graph.write(folder / "observations.json", rows)
    graph.write(folder / "tracks.json", tracks)
    graph.write(folder / "merged.json", dict(calibration=calibration, result=result))
    receipt = dict(
        source_id="DS22-137",
        recording_id=authority["recording_id"],
        status="tracks_evaluated",
        metadata=metadata,
        radio_id=document["source"]["radio_id"],
        capture_utc_ns=metadata["anchor_utc_ns"],
        probes=len(document["source"]["probes"]),
        winning_points=len(rows),
        graph_points=count,
        graph_tracks=len(tracks),
        merged_tracks=result["output_tracks"],
        merge_edges=len(result["accepted_edges"]),
        source_snapshot="/tmp/ds22-fast137-existing-tracking.json",
        source_sha256=authority["tracking_sha256"],
        export_authority=authority,
        source_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        satellite_association="not_evaluated",
        position_error_km=None,
    )
    graph.write(folder / "receipt.json", receipt)
    print(
        json.dumps(
            {
                k: receipt[k]
                for k in (
                    "source_id",
                    "winning_points",
                    "graph_points",
                    "graph_tracks",
                    "merged_tracks",
                )
            }
        )
    )


if __name__ == "__main__":
    run()
