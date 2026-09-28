"""Count separate candidate encounters without counting receiver replicas as passes."""

import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent / "local"


def encounters(rows, gap_s=600):
    episodes = []
    for row in sorted(rows, key=lambda r: r["start_s"]):
        if not episodes or row["start_s"] > episodes[-1]["end_s"] + gap_s:
            episodes.append(dict(start_s=row["start_s"], end_s=row["end_s"], rows=[row]))
        else:
            episodes[-1]["end_s"] = max(episodes[-1]["end_s"], row["end_s"])
            episodes[-1]["rows"].append(row)
    return episodes


def utc(seconds):
    return datetime.fromtimestamp(seconds, UTC).isoformat()


def main():
    prior = ROOT / "reports/2026_09_27_ds7_satellite_annotations/local/track-annotations.json"
    paths = [prior, *sorted(OUT.glob("*-tracks.json"))]
    rows = []
    for path in paths:
        for row in json.loads(path.read_text()):
            if row.get("status") not in {"likely_conditional", "conditional_doppler_label"}:
                continue
            is_ds7 = path == prior
            rows.append(
                dict(
                    row,
                    dataset="DS7" if is_ds7 else "DS8",
                    name=row.get("satellite_name", row.get("candidate_name")),
                    start_s=datetime.fromisoformat(row["start_utc"]).timestamp()
                    if is_ds7
                    else row["start_utc_ns"] / 1e9,
                    end_s=datetime.fromisoformat(row["end_utc"]).timestamp()
                    if is_ds7
                    else row["end_utc_ns"] / 1e9,
                )
            )
    assert len({(r["dataset"], r["session_id"], r["track_id"]) for r in rows}) == len(rows)
    by_id = defaultdict(list)
    for row in rows:
        by_id[row["norad_id"]].append(row)
    ranking = []
    for norad, group in by_id.items():
        episodes = encounters(group)
        ranking.append(
            dict(
                norad_id=norad,
                name=group[0]["name"],
                encounters=len(episodes),
                tracks=len(group),
                recordings=len({r["session_id"] for r in group}),
                datasets=sorted({r["dataset"] for r in group}),
                sensitivity={str(gap): len(encounters(group, gap)) for gap in (300, 1200)},
                observations=[
                    dict(
                        start_utc=utc(e["start_s"]),
                        end_utc=utc(e["end_s"]),
                        tracks=len(e["rows"]),
                        receivers=sorted({r["receiver_id"] for r in e["rows"]}),
                        sessions=sorted({r["session_id"] for r in e["rows"]}),
                        validation_rms_hz=[r["validation_rms_hz"] for r in e["rows"]],
                        azimuth_deg=[r["azimuth_mid_deg"] for r in e["rows"]],
                        elevation_deg=[r["elevation_mid_deg"] for r in e["rows"]],
                    )
                    for e in episodes
                ],
            )
        )
    ranking.sort(key=lambda r: (-r["encounters"], -r["tracks"], r["norad_id"]))
    with (OUT / "decoded-bits.csv").open() as stream:
        bits = [r for r in csv.DictReader(stream) if r["norad_id"] == "59199"]
    a, b = ([r for r in bits if r["dataset"] == dataset] for dataset in ("DS7", "DS8"))
    aw, bw = ({r["raw_bits"] for r in group} for group in (a, b))
    af, bf = ({r["family"] for r in group} for group in (a, b))
    comparison = dict(
        norad_id=59199,
        ds7_observations=len(a),
        ds8_observations=len(b),
        ds7_unique_words=len(aw),
        ds8_unique_words=len(bw),
        ds7_families=len(af),
        ds8_families=len(bf),
        shared_exact_words=sorted(aw & bw),
        shared_families=sorted(af & bf),
        ds7_word_occurrences_shared=sum(r["raw_bits"] in bw for r in a),
        ds8_word_occurrences_shared=sum(r["raw_bits"] in aw for r in b),
        family_jaccard=len(af & bf) / len(af | bf),
    )
    result = dict(
        policy="Conditional labels only. Merge overlapping intervals and gaps <=600 s "
        "across receivers, RF channels and recordings. Descriptive encounter count, "
        "not independently confirmed orbital passes. Rank encounters, then tracks.",
        coverage="All 5142 DS7 annotations and 245 DS8 tracks from four recordings; "
        "not all DS8 recordings",
        qualifying_tracks=len(rows),
        identities=len(ranking),
        encounter_histogram=dict(Counter(r["encounters"] for r in ranking)),
        input_hashes={
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in paths + [OUT / "decoded-bits.csv"]
        },
        ranked_by_encounters=ranking,
        ranked_by_tracks=sorted(ranking, key=lambda r: (-r["tracks"], r["norad_id"])),
        decoded_repeat_comparison=comparison,
    )
    (OUT / "pass-frequency-comparison.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            dict(
                qualifying_tracks=len(rows),
                identities=len(ranking),
                histogram=result["encounter_histogram"],
                top=ranking[:2],
                comparison=comparison,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
