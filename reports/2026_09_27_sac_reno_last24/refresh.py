"""Snapshot the latest 24 adaptive captures with both published position results."""
import csv
import json
import statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

BASE = "http://127.0.0.1:8090"

def get(path):
    with urlopen(BASE + path, timeout=60) as response:
        return json.load(response)

def main():
    out = Path(__file__).parent / datetime.now(timezone.utc).strftime("refresh-%H%M%S")
    out.mkdir()
    selected, skipped = [], []
    cursor = 0
    while len(selected) < 24:
        page = get(f"/api/v2/scanner/adaptive-sessions?cursor={cursor}&limit=20")
        (out / f"page-{cursor:04}.json").write_text(json.dumps(page))
        captures = page["items"]
        def fetch(capture):
            return get(f'/api/v1/scanner/tracking/{capture["session_id"]}/adaptive-tle-position-v2')
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(fetch, captures))
        for capture, status in zip(captures, results):
            (out / (capture["session_id"] + ".json")).write_text(json.dumps(status))
            doc = (status.get("manifest") or {}).get("document", {})
            priors = {p["name"]: p for p in doc.get("priors", [])}
            valid = status.get("state") == "complete" and all(
                priors.get(name, {}).get("selected", {}).get("horizontal_error_m") is not None
                for name in ("sacramento", "reno")
            )
            if valid and capture.get("mode") == "adaptive" and capture.get("terminal_state") == "completed":
                selected.append({"capture": capture, "document": doc})
                if len(selected) == 24:
                    break
            else:
                skipped.append(capture["session_id"])
        print(f"Checked through {cursor + len(captures)} captures; selected {len(selected)}", flush=True)
        cursor = page.get("next_cursor")
        if cursor is None:
            break
    (out / "selected.json").write_text(json.dumps(selected))
    (out / "skipped.json").write_text(json.dumps(skipped))
    rows = []
    for item in selected:
        c, d = item["capture"], item["document"]
        p = {v["name"]: v for v in d["priors"]}
        rows.append([c["captured_at"], c["session_id"], c["sample_rate_hz"] / 1e6,
                     p["sacramento"]["selected"]["horizontal_error_m"] / 1000,
                     p["reno"]["selected"]["horizontal_error_m"] / 1000])
    with (out / "errors.csv").open("w") as f:
        writer = csv.writer(f)
        writer.writerow(["capture_utc", "scan_id", "MS/s", "sacramento_error_km", "reno_error_km"])
        writer.writerows(rows)
    lines = ["| Capture UTC | Scan | MS/s | Sacramento (km) | Reno (km) |", "|---|---|---:|---:|---:|"]
    lines += [f"| {r[0]} | {r[1]} | {r[2]:g} | {r[3]:.2f} | {r[4]:.2f} |" for r in rows]
    for col, label in [(3, "Sacramento"), (4, "Reno")]:
        lines.append(f"\n{label}: mean {statistics.mean(r[col] for r in rows):.2f} km; median {statistics.median(r[col] for r in rows):.2f} km.")
    (out / "TABLE.md").write_text("\n".join(lines) + "\n")
    print(out)
    print("\n".join(lines))
    print("Stop reasons:", {p['stop_reason'] for s in selected for p in s['document']['priors']})

if __name__ == "__main__":
    main()
