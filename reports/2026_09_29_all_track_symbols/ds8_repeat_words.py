"""Independent per-receiver whole-word check for two conditional DS8 revisits."""

import hashlib
import json
from pathlib import Path

import numpy as np
from decode_tracks import word_candidate

BASE = Path(__file__).parent


def main():
    rows, hashes = [], {}
    for visit in (17, 74):
        folder = BASE / f"local/paired-ds8-DS8-F017-v{visit}"
        receipt_path = folder / "summary.json"
        path = folder / f"DS8-F017-v{visit}-data-soft.npz"
        receipt = json.loads(receipt_path.read_text())
        assert hashlib.sha256(path.read_bytes()).hexdigest() == receipt["header"]["sha256"]
        data = np.load(path)
        frames = []
        for f in receipt["qualified_frames"]:
            words = [word_candidate(data[f"z{rx}"][f], data[f"bins{rx}"], f) for rx in (0, 1)]
            frames.append(
                dict(
                    frame=f,
                    rx0=words[0],
                    rx1=words[1],
                    both_accepted_same_word=all(w["accepted"] for w in words)
                    and words[0]["word"] == words[1]["word"],
                )
            )
        rows.append(
            dict(visit=visit, prior_aliases=receipt["prior_inventory_aliases"], rows=frames)
        )
        hashes.update(
            {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in [receipt_path, path]}
        )
    census_path = BASE / "local/census.json"
    capture = next(
        c for c in json.loads(census_path.read_text())["captures"] if c["unit"] == "DS8-F017"
    )
    times = []
    for visit in (17, 74):
        values = [
            t
            for track in capture["tracks"]
            for v, t in zip(track["visits"], track["times_s"], strict=True)
            if v == visit
        ]
        times.append(float(np.mean(values)))
    hashes[str(census_path)] = hashlib.sha256(census_path.read_bytes()).hexdigest()
    result = dict(
        method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        input_sha256=hashes,
        support_center_separation_s=times[1] - times[0],
        visits=rows,
    )
    out = BASE / "local/paired-ds8-DS8-F017-v74/paired-word-check.json"
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            dict(
                separation_s=times[1] - times[0],
                paired_words=sum(r["both_accepted_same_word"] for v in rows for r in v["rows"]),
            )
        )
    )


if __name__ == "__main__":
    main()
