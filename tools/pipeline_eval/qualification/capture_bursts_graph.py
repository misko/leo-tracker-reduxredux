"""Measure the installed Graph stage alone on the already sealed duty inputs."""

import argparse
import json
import sys
from hashlib import file_digest
from pathlib import Path
from time import process_time


def checked(path, digest):
    with path.open("rb") as stream:
        actual = file_digest(stream, "sha256").hexdigest()
    if actual != digest.removeprefix("sha256:"):
        raise ValueError(f"diagnostic input changed: {path}")
    return json.loads(path.read_bytes())


def diagnose(plan, work, ident):
    receiver = Path(plan["receiver"])
    for name in (
        "leo/analysis/localization_v3/tracks.py",
        "leo/analysis/graph_tracklets.py",
        "leo/analysis/polynomial_tracklets.py",
        "tools/pipeline_eval/variants/direct_lifetime_kernels.py",
    ):
        with (receiver / name).open("rb") as stream:
            if file_digest(stream, "sha256").hexdigest() != plan["receiver_files"][name]:
                raise ValueError(f"installed diagnostic source changed: {name}")
    sys.path.insert(0, str(receiver))
    import numpy as np
    from leo.analysis.localization_v3.tracks import prepare_tracks
    from tools.pipeline_eval.variants.direct_lifetime_kernels import prepare_owned

    from leo.analysis.polynomial_tracklets import TrackConfig

    config = plan["authority"][ident]["track_config"]
    config = TrackConfig(**checked(Path(config["path"]), config["sha256"])["config"])
    rows = []
    for row in plan["trials"]:
        if row["id"] != ident:
            continue
        name = row["condition"]
        doc = checked(work / ident / name / "recording/native.json", row["native_sha256"])
        started = process_time()
        prepared = prepare_owned(prepare_tracks, doc, config)
        elapsed = process_time() - started
        tracks = prepared["tracks"]
        spans = np.array([np.ptp(t["times"]) for t in tracks])
        rows.append(
            dict(
                id=ident,
                condition=name,
                native_sha256=row["native_sha256"],
                graph_status=prepared["status"],
                winning_observations=len(prepared["observations"]),
                graph_assigned_observations=prepared["graph_points"],
                tracks=len(tracks),
                track_count_at_least_20s=int(np.count_nonzero(spans >= 20)),
                active_curvature_tracks=len(prepared["curved_indices"]),
                longest_track_s=float(spans.max()) if len(spans) else None,
                graph_cpu_s=elapsed,
            )
        )
    print(json.dumps(rows, allow_nan=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("plan_sha256")
    parser.add_argument("work", type=Path)
    parser.add_argument("case")
    args = parser.parse_args()
    diagnose(checked(args.plan, args.plan_sha256), args.work, args.case)
