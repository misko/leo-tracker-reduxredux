"""Audit local cached coverage and sign-independent tail quality before transfer."""

import hashlib
import json
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent


def main():
    rows = []
    for path in sorted((BASE / "local").glob("S*-soft.npz")):
        archive = np.load(path)
        metadata = [json.loads(str(archive[f"metadata{i}"])) for i in range(2)]
        frames = sorted(
            set(metadata[0]["evaluation_frames"]) & set(metadata[1]["evaluation_frames"])
        )
        frames = [
            f
            for f in frames
            if min(m["diagnostics"][f]["held_pilot_coherence"] for m in metadata) > 0.5
        ]
        streams = []
        for index in range(2):
            values = archive[f"z{index}"][frames]
            q = values.imag**2 / np.maximum(abs(values) ** 2, 1e-20)
            per_frame_tail = q[:, -10:].mean(axis=(1, 2))
            streams.append(
                dict(
                    carriers=int(values.shape[-1]),
                    tail_mean=None if not frames else float(per_frame_tail.mean()),
                    tails_below_point_one=int((per_frame_tail < 0.1).sum()),
                    per_frame_tail=per_frame_tail.tolist(),
                    symbol_mean=[] if not frames else q.mean(axis=(0, 2)).tolist(),
                )
            )
        rows.append(
            dict(
                signal=path.stem.removesuffix("-soft"),
                frames=frames,
                streams=streams,
                cache_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        )
    result = dict(
        rows=rows,
        source_pattern="local/S*-soft.npz",
        limitation="Nine existing cached paired visits, not exhaustive DS7/DS8 "
        "and not a DS9 analysis. Averaged tail power is a feasibility diagnostic, "
        "not the full-band 502-carrier boundary test; missing carriers cannot "
        "be concatenated into a contiguous full-band boundary.",
    )
    (BASE / "local/local_boundary_feasibility.json").write_text(json.dumps(result, indent=2) + "\n")
    for row in rows:
        print(row["signal"], len(row["frames"]), [r["tail_mean"] for r in row["streams"]])


if __name__ == "__main__":
    main()
