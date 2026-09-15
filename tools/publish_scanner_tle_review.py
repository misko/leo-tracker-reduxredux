"""Assemble per-recording candidate review pages from completed research screens."""

import argparse
import csv
import gzip
import hashlib
import json
import math
import shutil
from collections import Counter
from pathlib import Path


def candidate_comparisons(track):
    """Compare a frozen training leader with retained alternatives on equal support."""
    field = track["fields"]["0"]
    training = field.get("top_training", [])
    if not training:
        return []
    leader = training[0]
    candidates = {c["catalog_number"]: c for c in training}
    candidates.update({c["catalog_number"]: c for c in field["top_heldout"]})
    ranks = {c["catalog_number"]: i + 1 for i, c in enumerate(training)}
    held_ranks = {c["catalog_number"]: i + 1 for i, c in enumerate(field["top_heldout"])}
    rows = []
    for number, c in candidates.items():
        train_gain = c["training_rms_hz"] - leader["training_rms_hz"]
        held_gain = c["heldout_rms_hz"] - leader["heldout_rms_hz"]
        rows.append(
            {
                "catalog_number": number,
                "name": c["name"],
                "training_rank": ranks.get(number),
                "heldout_rank": held_ranks.get(number),
                "training_rms_hz": c["training_rms_hz"],
                "heldout_rms_hz": c["heldout_rms_hz"],
                "leader_training_gain_hz": train_gain,
                "leader_heldout_gain_hz": held_gain,
                "leader_heldout_gain_percent": (
                    100 * held_gain / c["heldout_rms_hz"] if c["heldout_rms_hz"] > 0 else None
                ),
                "tau_s": c["tau_s"],
            }
        )
    return rows


def comparison_page(record):
    sid = record["session_id"]
    lines = [
        f"# Candidate RMS comparisons: {sid}",
        f"Recorded **{record['capture_start_utc']}**, RX0, 10 MS/s.",
        f"[Recording assessment and plots]({sid}.md).",
        "Each track has its own training-selected leader; there is no single satellite "
        "assignment for the whole recording. Lower RMS is better. The same observations "
        "and chronological split are used for all candidates within a track.",
        "Gain = alternative RMS − training-leader RMS. Positive gain favors the leader; "
        "negative heldout gain means the alternative predicts better. Percent gain uses "
        "the alternative RMS as denominator; it is not identification confidence. "
        "Tau and carrier offset were selected on training data and remain frozen on heldout.",
        "The archived screen retained the top five training candidates and top five "
        "heldout candidates, whose union is listed below. Candidate counts describe the "
        "full scored population; names/scores outside these retained lists were not "
        "archived. A blank rank means outside that top-five list. Catalogue exclusions "
        "and control results are in the linked recording assessment and evidence.",
    ]
    flat = []
    for track in record["screen"]["tracks"]:
        rows = candidate_comparisons(track)
        if not rows:
            continue
        field = track["fields"]["0"]
        leader = field["top_training"][0]
        alternatives = [
            c for c in field["top_heldout"] if c["catalog_number"] != leader["catalog_number"]
        ]
        best_other = min(alternatives, key=lambda c: c["heldout_rms_hz"], default=None)
        lines.extend(
            [
                f"## CH{track['channel']} {track['edge']}, "
                f"{track['time_s'][0]:.2f}–{track['time_s'][-1]:.2f} s",
                f"Track `{track['tracklet_id']}`; {track['observations']} observations; "
                f"{field['candidate_count']} nominal-time satellites scored. "
                f"Training leader: **{leader['name']} (NORAD {leader['catalog_number']})**; "
                f"heldout rank {field['winner_heldout_rank']} in the full scored population.",
            ]
        )
        if best_other:
            gain = best_other["heldout_rms_hz"] - leader["heldout_rms_hz"]
            lines.append(
                f"Against the best other heldout candidate, {best_other['name']} "
                f"(NORAD {best_other['catalog_number']}): leader heldout RMS "
                f"**{leader['heldout_rms_hz']:.2f} Hz** versus "
                f"**{best_other['heldout_rms_hz']:.2f} Hz**; "
                f"gain **{gain:+.2f} Hz**. This alternative is selected on heldout data "
                "for diagnosis, not used to refit the leader."
            )
        lines.extend(
            [
                "| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | "
                "Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |\n"
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n"
                + "\n".join(
                    f"| {r['name']} | {r['catalog_number']} | {r['training_rank'] or '—'} | "
                    f"{r['heldout_rank'] or '—'} | {r['training_rms_hz']:.2f} | "
                    f"{r['heldout_rms_hz']:.2f} | "
                    f"{r['leader_training_gain_hz']:+.2f} | {r['leader_heldout_gain_hz']:+.2f} | "
                    + (
                        f"{r['leader_heldout_gain_percent']:+.2f}"
                        if r["leader_heldout_gain_percent"] is not None
                        else "undefined"
                    )
                    + f" | {r['tau_s']:+.0f} |"
                    for r in rows
                )
            ]
        )
        for row in rows:
            flat.append(
                {
                    "session_id": sid,
                    "tracklet_id": track["tracklet_id"],
                    "channel": track["channel"],
                    "edge": track["edge"],
                    "candidate_count": field["candidate_count"],
                    "training_leader_norad": leader["catalog_number"],
                    **row,
                }
            )
    return "\n\n".join(lines) + "\n", flat


def concerns(track):
    """Conservative descriptive checks; never converts a screen to identity."""
    fields = track["fields"]
    if not fields["0"].get("top_training"):
        return ["no nominal candidate"]
    winner = fields["0"]["top_training"][0]
    issues = []
    for key, label in [("top_training", "training"), ("top_heldout", "heldout")]:
        ordered = fields["0"].get(key, [])
        score = "training_rms_hz" if label == "training" else "heldout_rms_hz"
        if len(ordered) > 1 and math.isclose(
            ordered[0][score], ordered[1][score], rel_tol=1e-12, abs_tol=1e-9
        ):
            issues.append(label + " candidate tie")
    held = winner["exact_center_validation"]["heldout_rms_hz"]
    if fields["0"]["winner_heldout_rank"] != 1:
        issues.append("leader changes on heldout")
    if abs(winner["tau_s"]) == 5:
        issues.append("time-shift boundary")
    if winner["exact_center_validation"]["minimum_elevation_deg"] < 0:
        issues.append("below horizon during support")
    if held >= min(n["heldout_rms_hz"] for n in track["radio_polynomials"]):
        issues.append("radio drift fits as well or better")
    for delta in ("-500", "500"):
        if not fields[delta].get("top_training"):
            issues.append("missing wrong-time population")
        elif held >= fields[delta]["top_training"][0]["exact_center_validation"]["heldout_rms_hz"]:
            issues.append(f"{delta}s control fits as well or better")
    return issues


def publish(source, output):
    output.mkdir(parents=True, exist_ok=True)
    records = sorted(
        (json.loads(p.read_text()) for p in source.glob("scan-hop-*.json")),
        key=lambda r: r["capture_start_utc"],
    )
    if len(records) != 47 or len({r["session_id"] for r in records}) != 47:
        raise ValueError("expected the complete frozen 47-recording cohort")
    counts = Counter()
    summary = []
    all_tracks = []
    all_comparisons = []
    archive = []
    maximum_rms_change = 0.0
    for record in records:
        sid = record["session_id"]
        screen = record.get("screen")
        if screen:
            if "exact_center_validation" not in screen:
                raise ValueError("exact-time validation missing: " + sid)
            for track in screen["tracks"]:
                track["publication_concerns"] = concerns(track)
        data = json.dumps(record, indent=2, allow_nan=False).encode() + b"\n"
        compressed = gzip.compress(data, mtime=0)
        (output / (sid + ".json.gz")).write_bytes(compressed)
        archive.append({"file": sid + ".json.gz", "sha256": hashlib.sha256(compressed).hexdigest()})
        header = f"# {sid}\n\nRecorded **{record['capture_start_utc']}**, RX0, 10 MS/s.\n\n"
        if not screen:
            counts["unavailable"] += 1
            (output / (sid + ".md")).write_text(
                header + "No assignment: " + record.get("error", "missing screen") + "\n"
            )
            summary.append(
                {
                    "session_id": sid,
                    "capture_start_utc": record["capture_start_utc"],
                    "tracks": 0,
                    "descriptive_passes": 0,
                    "candidates": "unavailable",
                    "status": record.get("error", "missing screen"),
                }
            )
            continue
        if "exact_center_validation" not in screen:
            raise ValueError("exact-time validation missing: " + sid)
        page, comparisons = comparison_page(record)
        (output / (sid + "-candidates.md")).write_text(page)
        all_comparisons.extend(comparisons)
        maximum_rms_change = max(
            maximum_rms_change, screen["exact_center_validation"]["maximum_rms_change_hz"]
        )
        counts["screened"] += 1
        counts["tracklets"] += len(screen["tracks"])
        supported = Counter()
        leaders = Counter()
        descriptions = []
        passes = 0
        for t in screen["tracks"]:
            if not t["fields"]["0"].get("top_training"):
                continue
            w = t["fields"]["0"]["top_training"][0]
            number = w["catalog_number"]
            leaders[number] += 1
            issues = concerns(t)
            if not issues:
                supported[number] += 1
                passes += 1
            counts.update(issues)
            all_tracks.append(
                {
                    "session_id": sid,
                    "tracklet_id": t["tracklet_id"],
                    "channel": t["channel"],
                    "edge": t["edge"],
                    "start_s": t["time_s"][0],
                    "end_s": t["time_s"][-1],
                    "span_s": t["span_s"],
                    "leading_norad": number,
                    "training_rms_hz": w["training_rms_hz"],
                    "heldout_rms_hz": w["heldout_rms_hz"],
                    "heldout_rank": t["fields"]["0"]["winner_heldout_rank"],
                    "tau_s": w["tau_s"],
                    "concerns": "; ".join(issues) or "passes descriptive checks; candidate only",
                }
            )
            alternatives = ", ".join(
                str(c["catalog_number"]) for c in t["fields"]["0"]["top_training"][:3]
            )
            descriptions.append(
                f"| CH{t['channel']} {t['edge']} | "
                f"{t['time_s'][0]:.1f}–{t['time_s'][-1]:.1f} | {alternatives} | "
                f"{w['training_rms_hz']:.1f} / {w['heldout_rms_hz']:.1f} | "
                f"{t['fields']['0']['winner_heldout_rank']} | "
                f"{'; '.join(issues) or 'Passes descriptive checks; candidate only'} |"
            )
        counts["descriptive_passes"] += passes
        if passes:
            counts["recordings_with_descriptive_passes"] += 1
        chosen = supported if supported else leaders
        candidate_text = ", ".join(f"{n} ({count} tracklets)" for n, count in chosen.most_common(3))
        status = (
            "Candidates pass descriptive checks; no identification"
            if supported
            else "All leading candidates have diagnostic concerns"
        )
        summary.append(
            {
                "session_id": sid,
                "capture_start_utc": record["capture_start_utc"],
                "tracks": len(screen["tracks"]),
                "descriptive_passes": passes,
                "candidates": candidate_text,
                "status": status,
            }
        )
        png = source / (sid + ".png")
        if png.exists():
            shutil.copyfile(png, output / png.name)
        else:
            raise ValueError("missing per-recording overlay " + sid)
        exclusions = (
            ", ".join(
                f"{e['name']} (NORAD {e['catalog_number']}; SGP4 {e['sgp4_error_codes']})"
                for e in screen["exclusions"]
            )
            or "None"
        )
        audit_note = ""
        audit_path = output / "deep-checks" / (sid + ".json.gz")
        if audit_path.exists():
            audit = json.loads(gzip.decompress(audit_path.read_bytes()))["result"]
            audit_note = (
                "**Stricter audit of one shortlisted track: "
                + ("ABSTAIN" if audit["abstention_recommended"] else "candidate only")
                + f"; leading NORAD {audit['leading_catalog_number']}.** "
                + "; ".join(audit["abstention_reasons"])
                + f". [Full audit](deep-checks/{sid}.json.gz).\n\n"
            )
        detail = (
            header
            + f"**{status}.** Candidates: {candidate_text}.\n\n"
            + audit_note
            + f"[Satellite RMS comparisons and top-1 gains]({sid}-candidates.md).\n\n"
            + "Counts are correlated lane tracklets, "
            "not independent detections or satellite counts. "
            "A recording can contain multiple transmitters; "
            "these are not one-label-per-file assignments.\n\n"
            f"![Six longest eligible tracks and training-selected TLE curves]({sid}.png)\n\n"
            "Solid curves include a per-track constant carrier offset "
            "fitted on the first 60% of observations. "
            "The final 40% is held out. A close curve is not identity evidence by itself.\n\n"
            f"Catalogue: `{screen['snapshot_digest']}`. Orbital-only exclusions: {exclusions}.\n\n"
            "| Lane | Recording seconds | Top 3 training NORADs | "
            "Train / heldout RMS (Hz) | Leader heldout rank | Assessment |\n"
            "|---|---:|---|---:|---:|---|\n"
            + "\n".join(descriptions)
            + f"\n\n[Full candidate, control and measured-CFO evidence]({sid}.json.gz).\n"
        )
        (output / (sid + ".md")).write_text(detail)
    for name, rows in [
        ("recordings.csv", summary),
        ("tracks.csv", all_tracks),
        ("candidate-comparisons.csv", all_comparisons),
    ]:
        with (output / name).open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    metrics = {
        "counts": dict(counts),
        "maximum_exact_validation_rms_change_hz": maximum_rms_change,
        "candidate_only": True,
        "identity_claimed": False,
        "recordings": summary,
    }
    (output / "summary.json").write_text(json.dumps(metrics, indent=2) + "\n")
    (output / "archive-manifest.json").write_text(json.dumps(archive, indent=2) + "\n")
    table = "\n".join(
        f"| {r['capture_start_utc'][11:19]} | [{r['session_id']}]({r['session_id']}.md) | "
        f"{r['tracks']} | {r['descriptive_passes']} | {r['candidates']} |"
        for r in summary
    )
    (output / "README.md").write_text(
        "# Per-recording Starlink TLE candidate review\n\n"
        "Frozen September 14, 2026, 15:28–23:28 UTC cohort: 47 RX0 10 MS/s recordings. "
        "All results are candidate-only; no satellite identity is established.\n\n"
        "Every recording page links its satellite-by-satellite RMS and top-1 gain tables. "
        "[Download all candidate comparisons](candidate-comparisons.csv).\n\n"
        f"{counts['screened']} recordings screened; "
        f"{counts['tracklets']} eligible unique tracklets; "
        f"{counts['descriptive_passes']} tracklets in "
        f"{counts['recordings_with_descriptive_passes']} recordings pass descriptive checks.\n\n"
        "A descriptive pass requires the training leader to remain first on heldout data, "
        "stay above the horizon throughout its measured support, "
        "avoid the ±5 s time-shift boundary, and beat both ±500 s controls "
        "and both linear/quadratic radio-drift controls on heldout RMS. "
        "These checks are not calibrated identity probabilities. "
        "Tracklets across lanes are correlated.\n\n"
        "| UTC start | Recording and detailed assessment | Eligible tracks | Descriptive passes | "
        "Candidates (support counts; otherwise training leaders) |\n"
        "|---|---|---:|---:|---|\n" + table + "\n"
    )
    print(json.dumps(metrics["counts"], indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if (
        args.output.resolve() == Path("/mnt/qnap01")
        or Path("/mnt/qnap01") in args.output.resolve().parents
    ):
        parser.error("QNAP is read-only")
    publish(args.source, args.output)
