"""Read-only 14-frame re-analysis of the 72 exactly bound DS8 candidate tracks."""

import hashlib
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import decode_tracks  # noqa: E402

OUT = BASE / "local/ds8-fourteen-frames"


def run_capture(capture):
    # A separate output root preserves every original four-frame artifact.
    decode_tracks.OUT = OUT
    return decode_tracks.process_capture(capture, frames=14)


def main():
    binding_path = BASE / "local/bound-ds8-labels/summary.json"
    census_path = BASE / "local/census.json"
    binding = json.loads(binding_path.read_text())
    census = json.loads(census_path.read_text())
    selected = {(r["session"], r["track_id"]): r for r in binding["bound"]}
    captures = []
    mapping = []
    for capture in census["captures"]:
        keep = [t for t in capture["tracks"] if (capture["session"], t["track_id"]) in selected]
        if not keep:
            continue
        captures.append(dict(capture, tracks=keep))
        for new_index, track in enumerate(keep):
            label = selected[capture["session"], track["track_id"]]
            mapping.append(
                dict(
                    unit=capture["unit"],
                    new_index=new_index,
                    original_id=label["id"],
                    track_id=track["track_id"],
                    old_status=label["decode_status"],
                    norad_id=label["norad_id"],
                    satellite_name=label["satellite_name"],
                )
            )
    assert len(mapping) == len(selected) == 72
    OUT.mkdir(exist_ok=True)
    plan = dict(
        captures=captures,
        mapping=mapping,
        frames=14,
        source_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [binding_path, census_path, Path(__file__), Path(decode_tracks.__file__)]
        },
    )
    (OUT / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    with ProcessPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(run_capture, c) for c in captures]
        for future in as_completed(jobs):
            print(json.dumps(future.result()), flush=True)


if __name__ == "__main__":
    main()
