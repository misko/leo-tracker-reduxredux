"""Apply existing fixed-window paired word checks to a cached DS9 visit."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from firmware_seed_search import SEED
from phase_model import codebook
from window_audit import fixed_windows, summarize

BASE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="middle")
    tag = parser.parse_args().tag
    source = BASE / f"local/DS9-{tag}-soft.npz"
    archive = np.load(source)
    metadata = [json.loads(str(archive[f"metadata{i}"])) for i in range(2)]
    frames = sorted(set(metadata[0]["evaluation_frames"]) & set(metadata[1]["evaluation_frames"]))
    frames = [
        f
        for f in frames
        if min(m["diagnostics"][f]["held_pilot_coherence"] for m in metadata) > 0.5
    ]
    rows = fixed_windows(
        archive["bins0"], archive["bins1"], archive["z0"], archive["z1"], frames, 0.25
    )
    lookup = {word: phase for phase, word in enumerate(codebook(list(map(int, SEED))))}
    for row in rows:
        row["phase"] = lookup.get(row["word"]) if row["accepted"] else None
    summary = summarize(rows)
    summary["known_generator_windows"] = sum(r["accepted"] and r["phase"] is not None for r in rows)
    summary["accepted_outside_generator"] = sum(r["accepted"] and r["phase"] is None for r in rows)
    summary["phases"] = sorted({r["phase"] for r in rows if r["phase"] is not None})
    result = dict(
        summary=summary,
        frames=frames,
        rows=rows,
        input_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        limitation="Existing exploratory fixed-window gates. Both receiver words "
        "must agree exactly with full slot coverage and scores >0.25. Generator "
        "lookup occurs afterward. No shuffled-code gate, FEC/header semantics, "
        "or independent boundary-to-phase validation.",
    )
    name = "ds9_word_audit" if tag == "middle" else f"ds9_{tag}_word_audit"
    (BASE / f"local/{name}.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
