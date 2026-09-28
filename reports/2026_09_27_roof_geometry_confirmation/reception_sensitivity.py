"""Predeclared reception-row dependence sensitivities for confirmation.

This module only transforms already-built reception inputs. It does not read
recordings, search outputs, coordinates, or outcome files.
"""

from __future__ import annotations

from collections import Counter
from typing import Mapping, Sequence


def deduplicate_matched_physical_pairs(
    reception: Mapping[str, Sequence[Mapping[str, object]]],
    endpoint_receipt: Sequence[Mapping[str, object]],
) -> tuple[dict[str, list[dict[str, object]]], dict[str, object]]:
    """Keep one row per matched physical pair, RX0 preferred deterministically.

    Unmatched rows are never removed. Every input track key is retained even if
    its resulting reception list is empty. Input mappings and rows are not
    mutated.
    """
    receipt_by_anchor: dict[str, Mapping[str, object]] = {}
    for item in endpoint_receipt:
        anchor = str(item["anchor_key"])
        if anchor in receipt_by_anchor:
            raise ValueError("duplicate anchor in endpoint receipt")
        receipt_by_anchor[anchor] = item

    occurrences: dict[str, list[tuple[str, int, str, str]]] = {}
    copied: dict[str, list[dict[str, object]]] = {}
    input_rows = 0
    unmatched_rows = 0
    matched_without_pair = 0
    for track_id, rows in reception.items():
        track = str(track_id)
        copied[track] = []
        for index, source in enumerate(rows):
            row = dict(source)
            copied[track].append(row)
            input_rows += 1
            anchor = str(row["anchor_key"])
            receipt = receipt_by_anchor.get(anchor)
            if receipt is None or str(receipt["track_id"]) != track:
                raise ValueError("reception row lacks matching endpoint receipt")
            matched = row.get("matched")
            if not isinstance(matched, bool):
                raise ValueError("matched must be boolean")
            if not matched:
                unmatched_rows += 1
                continue
            pair = row.get("physical_pair_key")
            if pair is None:
                matched_without_pair += 1
                continue
            receiver = str(receipt["receiver_id"])
            if receiver not in {"rx0", "rx1"}:
                raise ValueError("receiver_id must be rx0 or rx1")
            occurrences.setdefault(str(pair), []).append((track, index, receiver, anchor))

    keep: set[tuple[str, int]] = set()
    duplicate_pairs = 0
    for values in occurrences.values():
        ordered = sorted(values, key=lambda value: (
            0 if value[2] == "rx0" else 1, value[3], value[0], value[1]
        ))
        keep.add((ordered[0][0], ordered[0][1]))
        duplicate_pairs += int(len(ordered) > 1)

    output = {track: [] for track in copied}
    removed_by_track: Counter[str] = Counter()
    removed = 0
    for track, rows in copied.items():
        for index, row in enumerate(rows):
            pair = row.get("physical_pair_key")
            if not row["matched"] or pair is None or (track, index) in keep:
                output[track].append(row)
            else:
                removed += 1
                removed_by_track[track] += 1

    accounting = {
        "rule": "one matched row per physical_pair_key; RX0 preferred, then anchor_key lexical",
        "input_tracks": len(copied),
        "input_rows": input_rows,
        "output_rows": input_rows - removed,
        "removed_duplicate_matched_rows": removed,
        "duplicate_physical_pairs": duplicate_pairs,
        "unmatched_rows_preserved": unmatched_rows,
        "matched_rows_without_pair_preserved": matched_without_pair,
        "tracks_empty_after_deduplication": sorted(
            track for track, rows in output.items() if not rows
        ),
        "removed_by_track": dict(sorted(removed_by_track.items())),
    }
    return output, accounting
