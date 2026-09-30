"""Longer calibration/evaluation of a matched cross-session candidate pair."""

import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from extend import OUT, PRIOR, sha, write  # noqa: E402

sys.path.insert(0, str(PRIOR))


def run(job):
    import decode_tracks

    capture, index = job
    subset = dict(capture, tracks=[capture["tracks"][index]])
    decode_tracks.OUT = OUT / "extended-repeat"
    return decode_tracks.process_capture(subset, 14)


if __name__ == "__main__":
    census = json.loads((OUT / "census.json").read_text())
    jobs = []
    for unit, index in [("DS9-F099", 44), ("DS10-F034", 50)]:
        capture = next(c for c in census["captures"] if c["unit"] == unit)
        jobs.append((capture, index))
    write(OUT / "extended-repeat/plan.json", dict(
        candidates=[dict(unit=c["unit"], original_index=i,
                         track_id=c["tracks"][i]["track_id"]) for c, i in jobs],
        norad_id=63854, method_sha256=sha(Path(__file__)),
        selection="Promising cross-session exact-sequence-bound candidate: same upper edge, "
        "channel 1, RX1, 7.5MS/s; four-frame minimum pilot .529 vs .487. "
        "Revisit the same 20ms excerpts with 14 frames, no correlation-based selection. "
        "Both orbit labels remain conditional and do not beat all stored controls.",
    ))
    with ProcessPoolExecutor(max_workers=2) as pool:
        for result in pool.map(run, jobs):
            print(json.dumps(result), flush=True)
