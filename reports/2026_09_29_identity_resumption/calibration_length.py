"""Fixed four-frame replay to audit recovery's frame-count sensitivity."""

import hashlib
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
OUT = BASE / "local/calibration-length"
sys.path.insert(0, str(BASE))
from long_track_excerpts import recover  # noqa: E402


def common_evaluation(a, b):
    return sorted(set(a["evaluation_frames"]) & set(b["evaluation_frames"]))


def main():
    from leo.storage.adaptive_hop import AdaptiveHopIqStore

    OUT.mkdir(exist_ok=True)
    if (OUT / "result.json").exists():
        raise SystemExit("Existing result retained")
    paths = [BASE / "local/simultaneous/recovery.json"] + [
        BASE / f"local/simultaneous5/pair-{k}/recovery.json" for k in range(4)]
    jobs, bindings = [], {}
    for path in paths:
        bindings[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        jobs.append(json.loads(path.read_text())["rows"][0])
    long_path = BASE / "local/long-track/recovery.json"
    bindings[str(long_path)] = hashlib.sha256(long_path.read_bytes()).hexdigest()
    long_rows = json.loads(long_path.read_text())["rows"]
    jobs.extend([long_rows[0], long_rows[-1]])
    census_path = BASE.parent / "2026_09_29_ds10_signal_extension/local/census.json"
    captures = {c["unit"]: c for c in json.loads(census_path.read_text())["captures"]}
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    results = []
    try:
        with tempfile.TemporaryDirectory(dir=OUT) as td:
            for index, r in enumerate(jobs):
                unit = r["id"].rsplit("-T", 1)[0]
                source = r["source"]
                p = source["probe"]
                with store.reader(captures[unit]["session"]) as reader:
                    _, values = reader.read_visit_ci16(r["visit"])
                rate = source["sample_rate_hz"]
                begin = round(p["probe_start_ms"] * rate / 1000)
                excerpt = values[begin:begin + round(.020 * rate), p["receiver_id"], :].copy()
                assert hashlib.sha256(excerpt.tobytes()).hexdigest() == source["excerpt_sha256"]
                np.save(Path(td) / "stream.npy", excerpt)
                bins, z, meta = recover(source, Path(td), 4, all_supported_bins=True)
                path = OUT / f"case-{index}.npz"
                np.savez_compressed(path, bins=bins, z=z, metadata=json.dumps(meta))
                old_path = Path(r["artifact"])
                assert hashlib.sha256(old_path.read_bytes()).hexdigest() == r["artifact_sha256"]
                with np.load(old_path) as data:
                    previous = json.loads(str(data["metadata"]))
                common = common_evaluation(meta, previous)
                qualified = [f for f in meta["evaluation_frames"]
                             if meta["diagnostics"][f]["held_pilot_coherence"] > .5]
                result = dict(id=r["id"], visit=r["visit"], qualified4=qualified,
                    qualified15=r["qualified"], common_frames=common,
                    coherence4=[meta["diagnostics"][f]["held_pilot_coherence"] for f in common],
                    coherence15=[previous["diagnostics"][f]["held_pilot_coherence"]
                                 for f in common],
                    original_artifact_sha256=r["artifact_sha256"],
                    artifact=str(path),
                    artifact_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    excerpt_sha256=source["excerpt_sha256"])
                results.append(result)
                print(result["id"], result["visit"], "four-frame qualified", len(qualified),
                      "common", result["coherence4"], result["coherence15"], flush=True)
    finally:
        store.close()
    (OUT / "result.json").write_text(json.dumps(dict(rows=results, source_sha256=bindings,
        method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        limitation="One fixed first candidate/excerpt per pair and two successful controls. "
        "Not an exhaustive frame-count search. Only common evaluation frames compare directly."),
        indent=2) + "\n")


if __name__ == "__main__":
    main()
