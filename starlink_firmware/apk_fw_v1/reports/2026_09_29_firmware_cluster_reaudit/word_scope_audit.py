"""Separate qualified-track state evidence from all accepted-window counts."""

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
SOURCE = (BASE.parents[3] / "reports") / "2026_09_29_ds10_signal_extension/local"


def state_counts(windows):
    frames = defaultdict(list)
    for w in windows:
        if w["known_phase"] is not None:
            frames[w["frame"]].append(w["known_phase"])
    result = Counter(multiwindow_frames=0, multiwindow_single_state=0,
                     two_frame_tracks=0, two_frame_state_changed=0)
    consistent = []
    for values in frames.values():
        if len(values) >= 2:
            result["multiwindow_frames"] += 1
            result["multiwindow_single_state"] += len(set(values)) == 1
        if len(set(values)) == 1:
            consistent.append(values[0])
    if len(consistent) == 2:
        result["two_frame_tracks"] += 1
        result["two_frame_state_changed"] += consistent[0] != consistent[1]
    return result


def main():
    structure_path = SOURCE / "word-structure.json"
    qualified_path = SOURCE / "qualified-tracks.json"
    comparison_path = SOURCE / "word-comparison.json"
    model_path = BASE.parents[3] / "reports/2026_09_28_sequence_semantics/local/phase_model.json"
    structure = json.loads(structure_path.read_text())
    qualified = {r["id"] for r in json.loads(qualified_path.read_text())}
    totals = defaultdict(Counter)
    filtered = defaultdict(Counter)
    for name, digest in structure["source_sha256"].items():
        path = Path(name)
        raw = path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == digest.removeprefix("sha256:")
        unit = path.parent.name
        dataset = unit.split("-")[0]
        for row in json.loads(raw)["rows"]:
            counts = state_counts(row["windows"])
            totals[dataset].update(counts)
            if f"{unit}-T{row['index']:04d}" in qualified:
                filtered[dataset].update(counts)
    assert dict(totals) == structure["counts"]
    words = json.loads(model_path.read_text())["generated_words"]
    comparison = json.loads(comparison_path.read_text())
    novelty_counts = defaultdict(Counter)
    for row in comparison["novelty"]:
        distance = min(sum(a != b for a, b in zip(row["word"], w, strict=True)) for w in words)
        assert distance == row["nearest_known_hamming"]
        novelty_counts[f"{row['dataset']}:{row['status']}"][distance] += 1
    result = dict(all_accepted_track_counts=dict(totals),
                  qualified_track_counts=dict(filtered),
                  unmatched_windows_by_dataset_quality_and_distance=dict(novelty_counts),
                  verified_window_receipts=len(structure["source_sha256"]),
                  source_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in (structure_path, qualified_path,
                                           comparison_path, model_path)},
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitation="Existing 350 decode receipts, no new IQ decoding. Counts "
                  "are track/frame/window units and may duplicate physical observations. "
                  "Qualified list precedes later one-entry physical deduplication. "
                  "Generator matches are T-state evidence, not payload or identity. "
                  "Unmatched words are not automatically new fields or proven errors.")
    (BASE / "local/word-scope-audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k.endswith("counts")
                      or k.startswith("unmatched")}, indent=2))


if __name__ == "__main__":
    main()
