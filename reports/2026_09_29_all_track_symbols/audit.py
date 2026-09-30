"""Audit coverage and summarize recovered observations without claiming payload."""

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).parent
OUT = BASE / "local"


def main():
    census = json.loads((OUT / "census.json").read_text())
    totals = Counter()
    by_dataset = defaultdict(Counter)
    by_rate = defaultdict(Counter)
    missing, errors, bindings = [], [], {}
    missing_windows, outside_hamming, distinct_words = [], Counter(), set()
    outside_polarity_hamming = Counter()
    for capture in census["captures"]:
        p = OUT / "decoded" / capture["unit"] / "results.json"
        if not p.exists():
            missing.append(capture["unit"])
            continue
        bindings[capture["unit"]] = hashlib.sha256(p.read_bytes()).hexdigest()
        d = json.loads(p.read_text())
        assert len(d["rows"]) == len(capture["tracks"])
        expected = {t["track_id"] for t in capture["tracks"]}
        assert len(expected) == len(capture["tracks"])
        assert {r["track_id"] for r in d["rows"]} == expected
        counts = Counter(recordings=1)
        wp = p.with_name("windows.json")
        windows = {}
        if wp.exists():
            wd = json.loads(wp.read_text())
            assert wd["source_sha256"] == bindings[capture["unit"]]
            windows = {r["index"]: r["windows"] for r in wd["rows"]}
        else:
            missing_windows.append(capture["unit"])
        for row in d["rows"]:
            counts["tracks"] += 1
            counts[row["status"]] += 1
            for w in windows.get(row["index"], []):
                counts["wholeframe_windows"] += 1
                counts["wholeframe_accepted"] += w["accepted"]
                counts["wholeframe_known"] += w["known_phase"] is not None
                if w["accepted"]:
                    distinct_words.add(w["word"])
                    counts["wholeframe_accepted_in_qualified_tracks"] += (
                        row["status"] == "qualified"
                    )
                    if w["known_phase"] is None:
                        counts["wholeframe_outside_known"] += 1
                        outside_hamming[w["nearest_known_hamming"]] += 1
                        outside_polarity_hamming[
                            w.get("nearest_known_hamming_allowing_inversion")
                        ] += 1
                        counts["wholeframe_exact_complements"] += (
                            w.get("complement_known_phase") is not None
                        )
            if "artifact" not in row:
                errors.append(dict(unit=capture["unit"], **row))
                continue
            shape = row["shape"]
            counts["recovered_tracks"] += 1
            counts["complex_observations"] += shape[0] * shape[1] * shape[2]
            counts["data_observations"] += (
                shape[0] * shape[1] * (shape[2] - len(row["receiver_metadata"]["pilot_bins"]))
            )
            counts["qualified_evaluation_frames"] += len(row["qualified_frames"])
            counts["word_windows"] += len(row["words"])
            counts["accepted_words"] += sum(w["accepted"] for w in row["words"])
            counts["known_words"] += sum(w["known_phase"] is not None for w in row["words"])
            if row["status"] == "qualified":
                counts["known_words_in_qualified_tracks"] += sum(
                    w["known_phase"] is not None for w in row["words"]
                )
                counts["qualified_tracks_with_known_words"] += any(
                    w["known_phase"] is not None for w in row["words"]
                )
        totals.update(counts)
        by_dataset[capture["dataset"]].update(counts)
        by_rate[str(capture["rate"])].update(counts)
    versions = {}
    paths = [
        *BASE.glob("*.py"),
        BASE.parent / "2026_09_28_ds7_ds8_correspondence/native_rate_decode.py",
        BASE.parent / "2026_09_27_ds7_header/tcodes.py",
        BASE.parent / "2026_09_27_ds7_header/analyze.py",
        BASE.parent / "2026_09_27_ds7_header/recover.py",
    ]
    for p in paths:
        versions[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    result = dict(
        expected_recordings=len(census["captures"]),
        expected_tracks=census["tracks"],
        complete=not missing and totals["tracks"] == census["tracks"],
        counts=dict(totals),
        by_dataset=dict(by_dataset),
        by_rate=dict(by_rate),
        missing_recordings=missing,
        errors=errors,
        missing_window_recordings=missing_windows,
        distinct_accepted_words=len(distinct_words),
        outside_known_hamming=dict(outside_hamming),
        outside_known_hamming_allowing_inversion=dict(outside_polarity_hamming),
        receipts_sha256=bindings,
        sources_sha256=versions,
        runtime="/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python",
        limitation="Census coverage of pilot-selected four-frame excerpts, not complete "
        "visits or continuous tracks. Single-receiver word candidates, not FEC messages.",
    )
    (OUT / "audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: v
                for k, v in result.items()
                if k not in ("receipts_sha256", "sources_sha256", "errors")
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
