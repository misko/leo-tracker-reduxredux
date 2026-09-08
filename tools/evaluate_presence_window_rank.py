#!/usr/bin/env python3
"""Rank complete archived dwells without opening RF or treating a screen as GLRT.

Previously examined six-window evidence is development data for this new
algorithm. References are used only after ranking, never to select a window.
"""

from __future__ import annotations

import argparse
import json
import struct
from collections import defaultdict
from pathlib import Path

import numpy as np

from leo.analysis.starlink.templates import qin_edge_pilot_frame
from tools.evaluate_native_presence_budgets import associated
from tools.native_presence import build_window_ranker
from tools.presence_window_rank import NativeWindowRank
from tools.qualify_native_presence import digest, write_json


def load_dwells(directory):
    inputs = json.loads((directory / "inputs.json").read_text())
    evidence = json.loads((directory / "results.json").read_text())
    if not 6 <= len(inputs) <= 1536 or len(inputs) != len(evidence):
        raise ValueError("bounded paired six-window inventory required")
    by_file = {row["probe"]: row for row in evidence}
    if len(by_file) != len(evidence) or set(by_file) != {r["file"] for r in inputs}:
        raise ValueError("paired evidence inventory mismatch")
    groups = defaultdict(list)
    for row in inputs:
        p = row["provenance"]
        if row["file"] != Path(row["file"]).name or p["rx"] != 1:
            raise ValueError("single selected RX and local probe filenames required")
        groups[(p["session_id"], p["visit"])].append(row)
    for key, rows in sorted(groups.items()):
        rows.sort(key=lambda r: r["provenance"]["probe_offset_ms"])
        if [r["provenance"]["probe_offset_ms"] for r in rows] != list(range(0, 120, 20)):
            raise ValueError("complete nonduplicate six-window tiling required")
        first = rows[0]
        rate, edge, counter = first["rate_hz"], first["edge"], int(first["device_counter"])
        if (
            rate not in (2500000, 5000000)
            or edge not in ("lower", "upper")
            or not 0 <= counter < 2**64 - rate * 120 // 1000
        ):
            raise ValueError("invalid dwell geometry")
        exact = np.asarray(qin_edge_pilot_frame(rate, edge), dtype="<c16")
        control = np.asarray(qin_edge_pilot_frame(rate, edge, symbol_roll=17), dtype="<c16")
        blocks, outcomes = [], []
        for index, row in enumerate(rows):
            file = directory / row["file"]
            outcome = by_file[row["file"]]
            numerical = outcome["result"]
            positive = [c for c in row["oracle_candidates"] if c["margin"] >= 0.025]
            detected = [
                c
                for c in numerical["candidates"]
                if c["fractional_complete"] and c["margin"] >= 0.025
            ]
            matched = any(
                associated(
                    a,
                    b,
                    rate,
                    {"maximum_cfo_difference_hz": 8000, "maximum_circular_epoch_difference_us": 2},
                )
                for a in detected
                for b in positive
            )
            if (
                row["rate_hz"] != rate
                or row["edge"] != edge
                or row["provenance"]["channel"] != first["provenance"]["channel"]
                or row["provenance"]["manifest_sha256"] != first["provenance"]["manifest_sha256"]
                or int(row["device_counter"]) != counter + index * rate // 50
                or digest(file) != row["sha256"]
                or outcome["provenance"] != row["provenance"]
                or numerical["rate_hz"] != rate
                or numerical["edge"] != int(edge == "upper")
                or numerical["format"] != 2
                or numerical["device_counter"] != row["device_counter"]
                or outcome["reference_positive"] != bool(positive)
                or outcome["detected"] != bool(detected)
                or outcome["matched_reference"] != matched
            ):
                raise ValueError("probe identity, continuity, or hash mismatch")
            data = file.read_bytes()
            expected = struct.pack(
                "<4sIIIIQ",
                b"LPR1",
                rate,
                int(edge == "upper"),
                rate // 50,
                2,
                counter + index * rate // 50,
            )
            header = expected + exact.tobytes() + control.tobytes()
            if len(data) != len(header) + rate // 50 * 4 or not data.startswith(header):
                raise ValueError("probe header/templates differ from recorded configuration")
            blocks.append(np.frombuffer(data, "<i2", offset=len(header)).reshape(-1, 2))
            outcomes.append(outcome)
        yield (
            {
                "session": key[0],
                "visit": key[1],
                "rate_hz": rate,
                "edge": edge,
                "counter": str(counter),
                "rx": 1,
                "channel": first["provenance"]["channel"],
                "source_files": [r["file"] for r in rows],
                "source_sha256": [r["sha256"] for r in rows],
                "reference_positive": [bool(r["reference_positive"]) for r in outcomes],
                "associated": [bool(r["matched_reference"]) for r in outcomes],
                "native_flagged": [bool(r["detected"]) for r in outcomes],
            },
            np.concatenate(blocks),
        )


def summarize(rows):
    result = {}
    for bins in sorted({r["bins"] for r in rows}):
        result[str(bins)] = {}
        for rate in sorted({r["rate_hz"] for r in rows}):
            subset = [r for r in rows if r["bins"] == bins and r["rate_hz"] == rate]
            result[str(bins)][str(rate)] = {
                "visits": len(subset),
                "reference_positive_visits": sum(any(r["reference_positive"]) for r in subset),
                "all_six_associated_visits": sum(any(r["associated"]) for r in subset),
                "first_window_associated_visits": sum(r["associated"][0] for r in subset),
                "top_k": {
                    str(k): {
                        "reference_covered": sum(
                            any(r["reference_positive"][i] for i in r["order"][:k]) for r in subset
                        ),
                        "associated": sum(
                            any(r["associated"][i] for i in r["order"][:k]) for r in subset
                        ),
                        "flagged_without_association": sum(
                            any(r["native_flagged"][i] for i in r["order"][:k])
                            and not any(r["associated"][i] for i in r["order"][:k])
                            for r in subset
                        ),
                    }
                    for k in (1, 2, 3)
                },
                "desktop_screen_cpu_p50_p99_max_ms": np.percentile(
                    [r["total_cpu_ms"] for r in subset], [50, 99, 100]
                ).tolist(),
            }
    return result


def prepare_smoke(directory: Path, output: Path):
    """First two visits per rate/edge, independent of scores; saved-IQ only."""
    directory, output = directory.resolve(), output.resolve()
    if any(
        output.is_relative_to(p) for p in (directory, Path("/mnt/qnap01"), Path("/srv/bulk/leo"))
    ):
        raise ValueError("output must be separate from corpus/archive")
    output.mkdir(parents=True, exist_ok=False)
    counts, rows = defaultdict(int), []
    for metadata, iq in load_dwells(directory):
        rate, edge = metadata["rate_hz"], metadata["edge"]
        key = (rate, edge)
        if counts[key] == 2:
            continue
        counts[key] += 1
        path = output / f"{metadata['session']}-{metadata['visit']}.rank"
        with path.open("xb") as stream:
            stream.write(
                struct.pack(
                    "<4sIIIIQ",
                    b"LRK1",
                    rate,
                    int(edge == "upper"),
                    len(iq),
                    2,
                    int(metadata["counter"]),
                )
            )
            stream.write(np.asarray(qin_edge_pilot_frame(rate, edge), dtype="<c16").tobytes())
            stream.write(iq.astype("<i2").tobytes())
        rows.append({**metadata, "file": path.name, "sha256": digest(path)})
    if len(rows) != 8 or set(counts.values()) != {2}:
        raise ValueError("both rates and edges need two visits")
    write_json(output / "inputs.json", rows)
    return rows


def evaluate(directory: Path, output: Path):
    directory, output = directory.resolve(), output.resolve()
    if (
        output.is_relative_to(directory)
        or output.is_relative_to(Path("/mnt/qnap01"))
        or output.is_relative_to(Path("/srv/bulk/leo"))
    ):
        raise ValueError("output must be separate from corpus/archive")
    output.mkdir(parents=True, exist_ok=False)
    library = build_window_ranker(output / "rank.so", cflags=("-fcx-limited-range",))
    rows = []
    workspaces = {}
    try:
        for metadata, iq in load_dwells(directory):
            for bins in (512, 1024, 2048, 4096, 8192):
                key = (metadata["rate_hz"], metadata["edge"], bins)
                if key not in workspaces:
                    workspaces[key] = NativeWindowRank(library, *key)
                rank = workspaces[key].run(iq)
                rows.append(
                    {
                        **metadata,
                        "bins": bins,
                        "scores": list(rank.scores),
                        "order": list(rank.order),
                        "projected_epoch_samples": list(rank.projected_epoch_samples),
                        **{
                            name: getattr(rank, name)
                            for name in (
                                "fold_cpu_ms",
                                "correlation_cpu_ms",
                                "total_cpu_ms",
                                "total_wall_ms",
                            )
                        },
                    }
                )
    finally:
        for native in workspaces.values():
            native.close()
    write_json(output / "results.json", rows)
    write_json(
        output / "summary.json",
        {
            "schema": "org.leo.research.presence-window-rank/v1",
            "status": "development_experiment_not_a_classifier_or_untouched_holdout",
            "inputs_sha256": digest(directory / "inputs.json"),
            "prior_results_sha256": digest(directory / "results.json"),
            "binary_sha256": digest(library),
            "ranking_used_reference": False,
            "confirmation": (
                "previously recorded frozen fractional GLRT output for the selected window; "
                "no live ARM or combined-runtime claim"
            ),
            "results": summarize(rows),
        },
    )
    print(json.dumps(summarize(rows), indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    evaluate(args.directory, args.output)


if __name__ == "__main__":
    main()
