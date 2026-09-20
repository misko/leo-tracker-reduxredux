"""Retrospective full-catalogue check of flagged frozen associations, no truth input."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from replay_regional_doppler import digest, load_observations, state_arrays, write_json

from leo.analysis.research.regional_doppler import Region, ScoreConfig, score_states
from leo.sky.propagation import parse_element_set_records, parse_element_sets


def flagged(row):
    """Exploratory signal-only audit trigger, not an exclusion rule."""
    return row["updated_max_segment_training_rms_hz"] > 1000 or (
        row["selected"]
        and row["original_max_segment_training_rms_hz"] < 100
        and row["updated_max_segment_training_rms_hz"] > 300
    )


def main():
    from leo.operations.tle_archive import TleArchiveReader

    p = argparse.ArgumentParser(description=__doc__)
    for key in ["archive", "run", "replay", "residual-audit", "evidence", "output"]:
        p.add_argument("--" + key, type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise ValueError("fresh output required")
    parent = json.loads((a.run / "inference.json").read_text())
    replay = json.loads(a.replay.read_text())
    residual = json.loads(a.residual_audit.read_text())
    if any(x["parent_digest"] != digest(a.run / "inference.json") for x in [replay, residual]):
        raise ValueError("parent mismatch")
    # Signal-only exploratory trigger; never an automatic exclusion policy.
    flags = [r for r in residual["rows"] if flagged(r)]
    docs = {
        r["session_id"]: json.loads(
            (a.evidence / "evidence" / (r["session_id"] + ".json")).read_text()
        )
        for r in flags
    }
    times = {sid: d["inventory"]["reference_utc_ns"] for sid, d in docs.items()}
    best = {sid: {} for sid in docs}
    archive = TleArchiveReader(a.archive)
    snapshots = [
        s
        for s in archive.list_snapshots()
        if min(times.values()) - 7 * 86400e9
        <= s.collected_utc_ns
        <= max(times.values()) + 7 * 86400e9
    ]
    for index, s in enumerate(snapshots):
        text = archive.read(s)
        cat = parse_element_sets(text)
        records = parse_element_set_records(text)
        epochs = cat.element_epoch_utc_ns()
        if len(records) != len(epochs):
            raise ValueError("catalogue order mismatch")
        for record, epoch, name, norad in zip(
            records, epochs, cat.names, cat.satellite_numbers, strict=True
        ):
            if record.satellite_number != norad:
                raise ValueError("NORAD order mismatch")
            if not name.startswith("STARLINK"):
                continue
            for sid, t in times.items():
                key = (abs(epoch - t), s.collected_utc_ns, s.digest)
                if norad not in best[sid] or key < best[sid][norad][0]:
                    best[sid][norad] = (key, record.text)
        if index % 20 == 0:
            print("archive", index + 1, len(snapshots), flush=True)
    region = Region(**parent["region"])
    # Predetermined model definition, not selected by evaluation error.
    model = next(m for m in replay["models"] if m["selection"] == "all" and not m["clock_fitted"])
    grid = region.points([model["x_km"][0]], [model["x_km"][1]])
    results = []
    for row in flags:
        sid = row["session_id"]
        arc = dict(load_observations(docs[sid], 0))[row["episode_id"]]
        cat = parse_element_sets(
            "\n".join(v[1].strip() for k, v in sorted(best[sid].items())) + "\n"
        )
        pos, vel, ids = state_arrays(
            cat, list(range(len(cat.satellite_numbers))), times[sid], arc.time_s
        )
        score = score_states(arc, pos, vel, grid, len(cat.satellite_numbers), ScoreConfig())
        winner = int(score["best_index"][0])
        result = dict(
            **row,
            catalogue_count=len(cat.satellite_numbers),
            valid_count=len(ids),
            best_norad=int(cat.satellite_numbers[ids[winner]]) if winner >= 0 else None,
            score={k: np.asarray(v).tolist() for k, v in score.items()},
            catalogue_digest=hashlib.sha256(
                ("\n".join(v[1].strip() for k, v in sorted(best[sid].items())) + "\n").encode()
            ).hexdigest(),
        )
        results.append(result)
        print(sid, row["norad"], "->", result["best_norad"], flush=True)
    write_json(
        a.output,
        dict(
            offline_noncausal=True,
            evaluation_location_used=False,
            parent_digest=digest(a.run / "inference.json"),
            replay_digest=digest(a.replay),
            residual_audit_digest=digest(a.residual_audit),
            snapshot_digests=[s.digest for s in snapshots],
            model="all-fixed-clock nearest-epoch replay",
            rows=results,
        ),
    )


if __name__ == "__main__":
    main()
