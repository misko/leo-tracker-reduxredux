"""Join independent orbital labels with receiver-validated decoded patterns."""

import csv
import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent / "local"


def family(word):
    if len(word) != 60 or set(word) - {"0", "1"}:
        raise ValueError("A family requires all 60 observed bits")
    inverted = word.translate(str.maketrans("01", "10"))
    return min(w[i:] + w[:i] for w in (word, inverted) for i in range(60))


def utc(ns):
    return datetime.fromtimestamp(ns / 1e9, UTC).isoformat()


def same_acquisition(label, export):
    if label.get("probe") != export["probe"]:
        return False
    return {k: v for k, v in label["candidate"].items() if k != "candidate_rank"} == {
        k: v for k, v in export["candidate"].items() if k != "candidate_rank"
    }


def main():
    old = ROOT / "reports/2026_09_27_ds7_header/local"
    prior = ROOT / "reports/2026_09_27_ds7_satellite_annotations/local"
    links = json.loads((prior / "recovered-signal-track-links.json").read_text())
    folders = [old / "best-upper", old / "holdout-upper"] + sorted(
        p for p in OUT.iterdir() if p.is_dir() and (p / "tcodes.json").exists()
    )
    groups, bits = [], []
    for folder in folders:
        inventory = json.loads((folder / "inventory.json").read_text())
        exports = inventory["exports"]
        sid = exports[0]["session_id"]
        visit = exports[0]["probe"]["visit_index"]
        edge = exports[0]["probe"]["edge"]
        labels = (
            json.loads((folder / "labels.json").read_text())
            if (folder / "labels.json").exists()
            else [r for r in links if r["session_id"] == sid and r["visit"] == visit]
        )
        # Cached acquisition sometimes publishes identical numerical solutions
        # at different candidate ranks. Join only exact probe + solution equality;
        # equal time or CFO alone is insufficient.
        track_path = OUT / (sid + "-tracks.json")
        if track_path.exists():
            for label in json.loads(track_path.read_text()):
                for e in exports:
                    if same_acquisition(label, e) and label not in labels:
                        labels.append(
                            dict(
                                label,
                                binding="identical probe and numerical "
                                "acquisition solution; duplicate rank ignored",
                            )
                        )
        qualified = [
            r
            for r in labels
            if r.get("status") in {"likely_conditional", "conditional_doppler_label"}
        ]
        ids = sorted({r["norad_id"] for r in qualified})
        satellite = ids[0] if len(ids) == 1 else None
        decoded = json.loads((folder / "tcodes.json").read_text())
        rows = decoded["results"]
        mapping_verified = edge == "upper"
        if edge == "lower" and decoded.get("convention", "").startswith("T[(n - 16*i) mod 60]"):
            reference = json.loads((OUT / "ut-lower-reference-check.json").read_text())
            mapping_verified = len(reference) == 13 and all(
                r["lower_simple_prediction"] > 0.99 for r in reference
            )
        codes = [r for r in rows if r["repeated_code_candidate"] and mapping_verified]
        archive = np.load(folder / "recovery-soft-symbols.npz")
        signatures, split_signatures = [], []
        for e in exports:
            z = archive[e["name"] + "_deviations"][:, 2, :].real
            signatures.append("".join("1" if v >= 0 else "0" for v in z.mean(axis=0)))
            split_signatures.extend(
                "".join("1" if v >= 0 else "0" for v in part.mean(axis=0))
                for part in np.array_split(z, 2)
            )
        header_stable = len(set(signatures + split_signatures)) == 1
        groups.append(
            dict(
                group=folder.name,
                dataset="DS7" if folder.parent == old else inventory.get("dataset", "DS8"),
                session_id=sid,
                visit=visit,
                edge=edge,
                norad_id=satellite,
                labels=labels,
                qualified_codes=len(codes),
                attempted_frames=len(rows),
                unique_families=len({family(r["combined_word"]) for r in codes}),
                header_symbol4_rx_words=signatures,
                header_symbol4_split_words=split_signatures,
                header_symbol4_stable=header_stable,
                result_sha256=hashlib.sha256((folder / "tcodes.json").read_bytes()).hexdigest(),
            )
        )
        for row in codes:
            bits.append(
                dict(
                    group=folder.name,
                    dataset=groups[-1]["dataset"],
                    session_id=sid,
                    visit=visit,
                    frame=row["frame"],
                    norad_id=satellite,
                    raw_bits=row["combined_word"],
                    family=family(row["combined_word"]),
                    rx_agreement=row["receiver_bit_agreement"],
                    heldout_correlation=row["rx1_heldout_correlation"],
                )
            )
    ds7 = [
        r
        for r in json.loads((prior / "track-annotations.json").read_text())
        if r["status"] == "likely_conditional"
    ]
    ds8all = [r for p in sorted(OUT.glob("*-tracks.json")) for r in json.loads(p.read_text())]
    ds8 = [r for r in ds8all if r.get("status") == "conditional_doppler_label"]
    shared = sorted({r["norad_id"] for r in ds7} & {r["norad_id"] for r in ds8})
    repeats = []
    for norad in shared:
        a, b = ([r for r in data if r["norad_id"] == norad] for data in (ds7, ds8))
        repeats.append(
            dict(
                norad_id=norad,
                name=a[0]["satellite_name"],
                ds7_tracks=len(a),
                ds8_tracks=len(b),
                ds7_sessions=sorted({r["session_id"] for r in a}),
                ds8_sessions=sorted({r["session_id"] for r in b}),
                ds7_start=min(r["start_utc"] for r in a),
                ds8_start=utc(min(r["start_utc_ns"] for r in b)),
                ds7_validation_rms_hz=[r["validation_rms_hz"] for r in a],
                ds8_validation_rms_hz=[r["validation_rms_hz"] for r in b],
                ds7_azimuth_deg=[r["azimuth_mid_deg"] for r in a],
                ds8_azimuth_deg=[r["azimuth_mid_deg"] for r in b],
            )
        )
    code_labels = defaultdict(set)
    code_groups = defaultdict(set)
    raw_labels = defaultdict(set)
    for bit in bits:
        code_groups[bit["family"]].add(bit["group"])
        if bit["norad_id"] is not None:
            code_labels[bit["family"]].add(bit["norad_id"])
            raw_labels[bit["raw_bits"]].add(bit["norad_id"])
    collisions = [
        dict(family=k, norad_ids=sorted(v), groups=sorted(code_groups[k]))
        for k, v in code_labels.items()
        if len(v) > 1
    ]
    ds7families = {r["family"] for r in bits if r["dataset"] == "DS7"}
    original_ds7families = {
        r["family"] for r in bits if r["group"] in {"best-upper", "holdout-upper"}
    }
    ds8bits = [r for r in bits if r["dataset"] == "DS8"]
    result = dict(
        groups=groups,
        ds8_tracks_surveyed=len(ds8all),
        ds8_conditional_tracks=len(ds8),
        cross_dataset_repeat_candidates=repeats,
        total_qualified_codewords=len(bits),
        unique_families=len(code_groups),
        ds8_codewords=len(ds8bits),
        ds8_codewords_in_ds7_families=sum(r["family"] in ds7families for r in ds8bits),
        ds8_codewords_in_original_ds7_families=sum(
            r["family"] in original_ds7families for r in ds8bits
        ),
        exact_cross_identity_words=[
            dict(raw_bits=k, norad_ids=sorted(v)) for k, v in raw_labels.items() if len(v) > 1
        ],
        cross_identity_family_collisions=collisions,
    )
    (OUT / "joint-results.json").write_text(json.dumps(result, indent=2) + "\n")
    with (OUT / "decoded-bits.csv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=list(bits[0]))
        writer.writeheader()
        writer.writerows(bits)
    (OUT / "repeat-candidates.json").write_text(json.dumps(repeats, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "groups"}, indent=2))
    for r in groups:
        print(
            r["group"],
            r["norad_id"],
            r["qualified_codes"],
            r["unique_families"],
            r["header_symbol4_stable"],
            r["header_symbol4_rx_words"],
        )


if __name__ == "__main__":
    main()
