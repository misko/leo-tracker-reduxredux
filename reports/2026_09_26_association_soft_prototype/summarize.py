"""Print per-method geographic outcomes from the bounded replay JSON."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


CASES = {
    "ddf7aff744cdaa64": "07:50",
    "3228d496423f0b3d": "08:10",
    "dc1153010e57ac76": "08:50",
    "b44838513401b406": "10:10",
    "fadea8b51ac3a4f7": "10:30",
    "d86e8f23c0624bac": "12:50",
}


def summarize(documents: list[dict]) -> str:
    sessions = {}
    for document in documents:
        for row in document["sessions"]:
            sid = row["session_id"]
            if sid in sessions:
                raise ValueError(f"duplicate session: {sid}")
            sessions[sid] = row
    for session in sessions.values():
        for prior, selections in session["selections"].items():
            seeds = []
            for point in session["evaluations"]:
                if point["prior"] != prior:
                    continue
                original = next((s for s in session["published"].values() if abs(s["latitude_deg"] - point["latitude_deg"]) < 1e-8 and abs(s["longitude_deg"] - point["longitude_deg"]) < 1e-8), None)
                if original is not None:
                    seeds.append({"proposal_index": point["proposal_index"], "score_hz": point["scores_hz"]["hard"], "horizontal_error_km": original["horizontal_error_km"]})
            if not seeds:
                raise ValueError("published seeds missing from proposals")
            selections["pooled_seeds"] = min(seeds, key=lambda x: (x["score_hz"], x["proposal_index"]))
    lines = [
        "Errors are kilometres; the same candidate locations are used by all replay methods.",
        "",
    ]
    methods = sorted({m for s in sessions.values() for p in s["selections"].values() for m in p})
    for prior in ("sacramento", "reno"):
        lines.extend([
            f"### {prior.title()}", "",
            "| Case | Published | " + " | ".join(methods) + " |",
            "|---|---:|" + "---:|" * len(methods),
        ])
        ordered = sorted(sessions.values(), key=lambda s: (s["session_id"].removeprefix("scan-fw-") not in CASES, CASES.get(s["session_id"].removeprefix("scan-fw-"), s["session_id"])))
        for session in ordered:
            suffix = session["session_id"].removeprefix("scan-fw-")
            label = CASES.get(suffix, "Control " + suffix[:8])
            values = [session["published"][prior]["horizontal_error_km"]]
            values += [session["selections"][prior][m]["horizontal_error_km"] for m in methods]
            lines.append("| " + label + " | " + " | ".join(f"{x:.2f}" for x in values) + " |")
        lines.append("")
        for group in ("cases", "controls"):
            selected = [s for s in ordered if (s["session_id"].removeprefix("scan-fw-") in CASES) == (group == "cases")]
            if not selected:
                continue
            lines.extend([f"{group.title()} ({len(selected)} scans):", "", "| Method | Median | Mean | Maximum | >100 km | Improved vs hard | Worse vs hard |", "|---|---:|---:|---:|---:|---:|---:|"])
            for method in ["published", *methods]:
                errors = [s["published"][prior]["horizontal_error_km"] if method == "published" else s["selections"][prior][method]["horizontal_error_km"] for s in selected]
                baseline = [s["selections"][prior]["hard"]["horizontal_error_km"] for s in selected]
                improved = sum(x < b - 1e-6 for x, b in zip(errors, baseline, strict=True))
                worse = sum(x > b + 1e-6 for x, b in zip(errors, baseline, strict=True))
                lines.append(f"| {method} | {statistics.median(errors):.2f} | {statistics.mean(errors):.2f} | {max(errors):.2f} | {sum(x > 100 for x in errors)} | {improved} | {worse} |")
            lines.append("")
        lines.extend(["Assignment evidence at each method's selected point:", "", "| Case | Method | Unresolved / tracks | Unresolved duration weight |", "|---|---|---:|---:|"])
        for session in ordered:
            suffix = session["session_id"].removeprefix("scan-fw-")
            label = CASES.get(suffix, "Control " + suffix[:8])
            for method in methods:
                if not method.startswith("reject_m"):
                    continue
                choice = session["selections"][prior][method]
                point = next(p for p in session["evaluations"] if p["prior"] == prior and p["proposal_index"] == choice["proposal_index"])
                threshold = float(method.removeprefix("reject_m"))
                unresolved = [t for t in point["tracks"] if len(t["candidates"]) < 2 or t["margin_hz"] < threshold]
                weight = sum(t["weight_s"] for t in point["tracks"])
                rejected_weight = sum(t["weight_s"] for t in unresolved)
                lines.append(f"| {label} | {method} | {len(unresolved)}/{len(point['tracks'])} | {rejected_weight / weight:.1%} |")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", nargs="+", type=Path)
    args = parser.parse_args()
    print(summarize([json.loads(path.read_text()) for path in args.results]))
