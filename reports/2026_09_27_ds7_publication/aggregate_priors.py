"""Snapshot existing DS7 prior results, or rebuild tables from that snapshot.

Fetch mode takes the original DS7 manifest path; no analysis is launched.
Default mode is offline and rebuilds the tables from saved evidence.
"""
import argparse
import csv
import hashlib
import json
import math
import statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
OUT = HERE / "prior-aggregation"


def get(path):
    with urlopen("http://127.0.0.1:8090" + path, timeout=30) as response:
        return json.load(response)


def compact(result):
    """Keep selected results and provenance, excluding large numerical diagnostics."""
    manifest = result.get("manifest")
    if manifest:
        document = manifest["document"]
        diagnostics = document.get("diagnostics", {})
        document["diagnostics"] = {k: diagnostics[k] for k in
                                   ("configuration", "reference_evaluation_only") if k in diagnostics}
        result["snapshot_note"] = (
            "Document excerpt: numerical diagnostics omitted. document_sha256 identifies "
            "the original complete source document, not this excerpt."
        )
    return result


def snapshot(manifest):
    OUT.mkdir(exist_ok=False)
    raw = manifest.read_bytes()
    membership = json.loads(raw)["captures"]
    wanted = {c["session_id"] for c in membership}
    assert len(wanted) == 88
    capture_metadata = {}
    cursor = 0
    for _ in range(100):
        page = get(f"/api/v2/scanner/adaptive-sessions?cursor={cursor}&limit=20")
        for item in page["items"]:
            if item["session_id"] in wanted:
                capture_metadata[item["session_id"]] = item
        if set(capture_metadata) == wanted:
            break
        cursor = page.get("next_cursor")
        if cursor is None:
            break
    assert set(capture_metadata) == wanted, "Incomplete DS7 capture metadata"

    def fetch(capture):
        sid = capture["session_id"]
        try:
            result = get(f"/api/v1/scanner/tracking/{sid}/adaptive-tle-position-v2")
        except Exception as error:
            result = {"state": "fetch_failed", "error": str(error)}
        return {"membership": capture, "capture": capture_metadata[sid], "result": compact(result)}

    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(fetch, membership))
    payload = {"captured_utc": datetime.now(timezone.utc).isoformat(),
               "membership_sha256": hashlib.sha256(raw).hexdigest(),
               "membership_source": "reports/2026_09_27_ds7_post_ds6/manifest.json",
               "records": records}
    (OUT / "snapshot.json").write_text(json.dumps(payload, indent=2) + "\n")


def percentile(values, fraction):
    values = sorted(values)
    index = (len(values) - 1) * fraction
    low, high = math.floor(index), math.ceil(index)
    return values[low] + (values[high] - values[low]) * (index - low)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch-manifest", type=Path)
    args = parser.parse_args()
    if args.fetch_manifest:
        snapshot(args.fetch_manifest)
    payload = json.loads((OUT / "snapshot.json").read_text())
    rows = []
    for record in payload["records"]:
        member, capture, result = record["membership"], record["capture"], record["result"]
        assert member["session_id"] == capture["session_id"]
        assert member["manifest_sha256"] == capture["input_manifest_sha256"]
        assert member["sample_rate_hz"] == capture["sample_rate_hz"]
        document = (result.get("manifest") or {}).get("document", {})
        if document:
            assert document["session_id"] == member["session_id"]
            assert document["input_manifest_sha256"] == member["manifest_sha256"]
        priors = {p["name"]: p for p in document.get("priors", [])}
        row = {"session_id": member["session_id"], "dwell_ms": capture["active_dwell_ms"],
               "valid_visit_ms": capture["valid_visit_ms"],
               "sample_rate_msps": capture["sample_rate_hz"] / 1e6,
               "nominal_capture_seconds": capture["nominal_duration_seconds"],
               "publication_state": result.get("state")}
        for name in ("reno", "sacramento"):
            prior = priors.get(name, {})
            error = (prior.get("selected") or {}).get("horizontal_error_m")
            assert error is None or (math.isfinite(error) and error >= 0)
            available = result.get("state") == "complete" and error is not None
            row[name + "_error_km"] = error / 1000 if available else None
            row[name + "_search_complete"] = prior.get("search_complete", False)
            row[name + "_stop_reason"] = prior.get("stop_reason")
        rows.append(row)
    assert len(rows) == len({r["session_id"] for r in rows}) == 88
    with (OUT / "individual.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    groups = sorted({(r["dwell_ms"], r["sample_rate_msps"]) for r in rows})
    summaries = []
    for dwell, rate in groups + [(None, None)]:
        selected = [r for r in rows if dwell is None or (r["dwell_ms"], r["sample_rate_msps"]) == (dwell, rate)]
        summary = {"dwell_ms": dwell, "sample_rate_msps": rate, "recordings": len(selected)}
        for name in ("reno", "sacramento"):
            values = [r[name + "_error_km"] for r in selected if r[name + "_error_km"] is not None]
            summary[name] = {"available": len(values),
                             "search_complete": sum(r[name + "_search_complete"] for r in selected),
                             "mean_km": statistics.mean(values) if values else None,
                             "median_km": statistics.median(values) if values else None,
                             "p90_km": percentile(values, .9) if values else None,
                             "below_1km": sum(v < 1 for v in values)}
        summaries.append(summary)
    (OUT / "summary.json").write_text(json.dumps(summaries, indent=2) + "\n")
    lines = ["# DS7 error by dwell time and sample rate", "",
             "Rows aggregate individual published selected-position errors; they are not pooled location fits.",
             "Reno and Sacramento name search priors applied to the same recordings, not collection sites.",
             "Dwell groups use `active_dwell_ms` (120, 240, or 360 ms), not `valid_visit_ms` (120 ms for all 88). Each recording has a nominal duration of 300 seconds.", "",
             "Correction: the initial published table incorrectly grouped by `valid_visit_ms` and therefore collapsed the three active-dwell settings. This version uses the same frozen API snapshot and errors, regrouped by active dwell and sample rate. The overall 88-recording metrics are unchanged.", "",
             "| Active dwell (ms) | Rate (MS/s) | N | Reno available | Reno median (km) | Reno mean (km) | Reno P90 (km) | Sac available | Sac median (km) | Sac mean (km) | Sac P90 (km) |",
             "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    def fmt(value):
        return f"{value:.2f}" if value is not None else "—"
    for s in summaries:
        cells = [str(s["dwell_ms"]) if s["dwell_ms"] is not None else "All",
                 f'{s["sample_rate_msps"]:g}' if s["sample_rate_msps"] is not None else "All", str(s["recordings"])]
        for name in ("reno", "sacramento"):
            p = s[name]
            cells += [f'{p["available"]}/{s["recordings"]}'] + [fmt(p[k]) for k in ("median_km", "mean_km", "p90_km")]
        lines.append("| " + " | ".join(cells) + " |")
    lines += ["", "P90 uses linear interpolation on sorted per-recording errors; each recording has equal weight.",
              "Missing outputs remain in the N denominator and are excluded from error summaries.", "",
              "| Prior | Search complete / 88 | Below 1 km / 88 |", "|---|---:|---:|"]
    for name in ("reno", "sacramento"):
        p = summaries[-1][name]
        lines.append(f'| {name.title()} | {p["search_complete"]}/88 | {p["below_1km"]}/88 |')
    stops = {name: sorted({str(r[name + "_stop_reason"]) for r in rows}) for name in ("reno", "sacramento")}
    lines += ["", f"Recorded stopping reasons: `{json.dumps(stops, sort_keys=True)}`.", "",
              "These budget-limited prior searches are a different estimator from the report's 677 m full88 joint fit.",
              "Availability means a published selected estimate exists; it does not imply exhaustive search or a qualified fix.",
              "DS7 contains 31 recordings at 120 ms, 25 at 240 ms, and 32 at 360 ms active dwell. `valid_visit_ms` is a separate metadata field and is 120 ms throughout.",
              "The evaluation-only reference is 37.84903264307456, -122.4856541910174 (unsurveyed).",
              "This is descriptive single-site evidence, not a causal comparison of sample rates or dwell durations.", "",
              f'Snapshot UTC: {payload["captured_utc"]}. DS7 manifest SHA-256: `{payload["membership_sha256"]}`.', "",
              "[Per-recording CSV](individual.csv) · [Summary JSON](summary.json) · [Frozen API excerpts](snapshot.json)",
              "", "API excerpts retain source document hashes, input bindings, search configuration, selected results and the evaluation reference; large numerical diagnostics are omitted. Original document hashes identify the full source documents, not the excerpts.",
              "", "Regenerate offline with `python ../aggregate_priors.py` from this directory."]
    (OUT / "README.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
