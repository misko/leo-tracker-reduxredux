"""Carrier recovery benchmark using disjoint inferred-T-state and test regions."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
PRIOR = BASE.parent / "2026_09_29_ds10_signal_extension/local"
sys.path.insert(0, str(BASE.parent / "2026_09_29_all_track_symbols"))
from decode_tracks import SEED, codebook, slots  # noqa: E402


def disagreement(z, prediction):
    return ((z.real >= 0) != (prediction >= 0)).sum(axis=0), np.full(z.shape[1], len(z))


def main():
    source = BASE / "local/rows.json"
    rows = [r for r in json.loads(source.read_text()) if r["rate"] == 10000000]
    support_path = BASE / "local/bandwidth-extension/summary.json"
    support = json.loads(support_path.read_text())["support"]
    bindings = json.loads((PRIOR / "word-comparison.json").read_text())["source_sha256"]
    words = np.array([[1 if b == "1" else -1 for b in word]
                      for word in codebook(list(map(int, SEED)))])
    receipts, sources, frame_rows = {}, {}, []
    counts = {edge: np.zeros((2, 2, len(bins)), dtype=int) for edge, bins in support.items()}
    for r in rows:
        receipt = PRIOR / "decoded" / r["unit"] / "results.json"
        if r["unit"] not in receipts:
            digest = hashlib.sha256(receipt.read_bytes()).hexdigest()
            assert bindings[str(receipt)] == "sha256:" + digest
            sources[str(receipt)] = digest
            receipts[r["unit"]] = {v["track_id"]: v
                                   for v in json.loads(receipt.read_text())["rows"]}
        record = receipts[r["unit"]][r["track_id"]]
        path = Path(r["source_artifact"])
        assert hashlib.sha256(path.read_bytes()).hexdigest() == r["source_artifact_sha256"]
        assert record["artifact_sha256"] == r["source_artifact_sha256"]
        phases = {w["frame"]: w["known_phase"] for w in record["words"]
                  if w["accepted"] and w["known_phase"] is not None}
        with np.load(path) as data:
            bins = np.array(support[r["edge"]])
            ids = np.searchsorted(data["bins"], bins)
            assert np.array_equal(data["bins"][ids], bins)
            meta = json.loads(str(data["metadata"]))
            for half, f in enumerate(meta["evaluation_frames"]):
                if f not in phases:
                    continue
                # Word fit/validation ends at symbol257; score only 258–289.
                expected = words[phases[f]][slots(bins, np.arange(258, 290))]
                errors, n = disagreement(data["z"][f, 256:288][:, ids], expected)
                counts[r["edge"]][half, 0] += errors
                counts[r["edge"]][half, 1] += n
                frame_rows.append(dict(id=r["id"], unit=r["unit"], frame=f,
                                       half=half, phase=phases[f],
                                       edge=r["edge"], errors=errors.tolist(), count=n.tolist()))
    summaries = []
    for edge, c in counts.items():
        bins = np.array(support[edge])
        core = np.isin(bins, [486, 487, 496, 497] if edge == "upper" else [526, 527, 536, 537])
        train_error = c[0, 0] / np.maximum(c[0, 1], 1)
        held_error = c[1, 0] / np.maximum(c[1, 1], 1)
        grouped = {}
        for row in frame_rows:
            if row["edge"] == edge and row["half"] == 1:
                error = np.array(row["errors"]) / np.array(row["count"])
                grouped.setdefault(row["unit"], []).append(error[~core].mean() - error[core].mean())
        rng = np.random.default_rng(300981)
        groups = list(grouped.values())
        bootstrap = [np.mean([v for k in rng.integers(len(groups), size=len(groups))
                              for v in groups[k]]) for _ in range(999)]
        summaries.append(dict(edge=edge, bins=bins.tolist(), held_recording_groups=len(groups),
                              extra_minus_core_cluster_ci=np.quantile(
                                  bootstrap, [.025, .975]).tolist(),
                              training_error=train_error.tolist(), held_error=held_error.tolist(),
                              training_counts=c[0, 1].tolist(), held_counts=c[1, 1].tolist(),
                              training_reliability=np.clip(1 - 2 * train_error, 0, 1).tolist(),
                              core_held_error=float(c[1, 0, core].sum() / c[1, 1, core].sum()),
                              extra_held_error=float(c[1, 0, ~core].sum() / c[1, 1, ~core].sum())))
    result = dict(edges=summaries, frames=frame_rows, source_sha256=sources,
                  metadata_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  support_sha256=hashlib.sha256(support_path.read_bytes()).hexdigest(),
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitation="Inferred state from accepted symbols194–257; evaluate disjoint "
                  "258–289 only. Train weights on first reserved frame, assess second. Selection "
                  "conditions on accepted state and may favor cleaner frames. Tail disagreement "
                  "is not independently verified BER or proof of early-header reliability.")
    (BASE / "local/carrier-reliability.json").write_text(json.dumps(result, indent=2) + "\n")
    for r in summaries:
        print(r["edge"], "held frames", r["held_counts"][0] // 32,
              "core", r["core_held_error"], "extra", r["extra_held_error"],
              "carrier range", min(r["held_error"]), max(r["held_error"]))


if __name__ == "__main__":
    main()
