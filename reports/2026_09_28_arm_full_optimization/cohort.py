"""Metadata-balanced saved-IQ full-search cohort runner and sealed-baseline audit."""

import argparse
import hashlib
import json
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
INPUTS = Path("/var/tmp/leo-ds7-large-arm-20260928")
BASELINE = HERE.parent / "2026_09_28_ds7_large_arm/baseline-01/rows.jsonl"
ORACLE = Path("/var/tmp/leo-arm-full-search-oracle-allrates")
RATES = (2500000, 5000000, 7500000, 10000000)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def select(rows, *, all_sealed=False):
    if all_sealed:
        return list(rows)
    chosen = []
    for rate in RATES:
        group = [r for r in rows if r["rate_hz"] == rate]
        for edge in ("lower", "upper"):
            chosen.extend([r for r in group if r["target"]["edge"] == edge][:8])
        if sum(r["rate_hz"] == rate for r in chosen) != 16:
            raise ValueError("insufficient edge-balanced metadata")
    return chosen


def templates():
    d = json.loads((ORACLE / "oracle.json").read_text())
    out = {}
    for case in d["cases"]:
        out[(case["context"]["rate_hz"], case["context"]["target"]["edge"])] = case["templates"]
    return out


def baseline():
    out = {}
    for line in BASELINE.read_text().splitlines():
        r = json.loads(line)
        c = r["context"]
        if r["method"] == "original" and r["repeat"] == 0 and r["status"] == "ok":
            out[(c["session_id"], c["visit_index"])] = r["result"]["probes"]
    return out


def compare(native, reference):
    bad = []
    hits = [0, 0, 0]
    seen = set()
    for row in native:
        key = (row["receiver_id"], row["probe_index"])
        expected = reference.get(key)
        if key in seen:
            bad.append({"key": key, "error": "duplicate_native_window"})
            continue
        seen.add(key)
        if expected is None:
            bad.append({"key": key, "error": "unexpected_native_window"})
            continue
        actual = row["candidates"]
        wanted = expected["candidates"]
        hp = [x for x in wanted if x["margin"] >= 0.025]
        hn = [x for x in actual if x["margin"] >= 0.025]
        hits[0] += len(hp)
        hits[1] += len(hn)
        unmatched = set(range(len(hn)))
        for p in hp:
            q = next(
                (
                    i
                    for i in unmatched
                    if abs(hn[i]["epoch"] - p["epoch_sample"]) <= 2
                    and abs(hn[i]["tracking_cfo_hz"] - p["tracking_cfo_hz"]) <= 8000
                ),
                None,
            )
            if q is not None:
                unmatched.remove(q)
                hits[2] += 1
        if len(actual) != len(wanted):
            bad.append({"key": key, "error": "candidate_count"})
            continue
        for a, b in zip(actual, wanted, strict=True):
            fields = (
                ("epoch", "epoch_sample", 0),
                ("acquired_cfo_hz", "acquired_cfo_hz", 2e-6),
                ("tracking_cfo_hz", "tracking_cfo_hz", 2e-6),
                ("exact_score", "exact_score", 2e-9),
                ("control_score", "control_score", 2e-9),
                ("margin", "margin", 2e-9),
            )
            if any(abs(a[x] - b[y]) > tol for x, y, tol in fields):
                bad.append({"key": key, "error": "ordered_field"})
                break
    for key, expected in reference.items():
        if key not in seen:
            bad.append({"key": key, "error": "missing_native_window"})
            hits[0] += sum(x["margin"] >= 0.025 for x in expected["candidates"])
    return {
        "errors": bad,
        "reference_positive": hits[0],
        "native_positive": hits[1],
        "matched_positive": hits[2],
    }


def worker(row, binary, temp, ts, base):
    if sha(INPUTS / row["file"]) != row["sha256"]:
        raise ValueError("input hash")
    iq = np.load(INPUTS / row["file"], allow_pickle=False)
    raw = temp / (row["file"] + ".ci16")
    np.asarray(iq, dtype="<i2").tofile(raw)
    t = ts[(row["rate_hz"], row["target"]["edge"])]
    for item in t.values():
        if sha(ORACLE / item["file"]) != item["sha256"]:
            raise ValueError("template hash")
    try:
        proc = subprocess.run(
            [
                str(binary),
                str(row["rate_hz"]),
                str(ORACLE / t["exact"]["file"]),
                str(ORACLE / t["control"]["file"]),
                str(raw),
            ],
            text=True,
            capture_output=True,
        )
    finally:
        raw.unlink(missing_ok=True)
    lines = [json.loads(x) for x in proc.stdout.splitlines()]
    ref = {
        (p["receiver_id"], p["probe_index"]): p
        for p in base[(row["session_id"], row["visit_index"])]
    }
    return {
        "context": row,
        "returncode": proc.returncode,
        "stderr": proc.stderr,
        "rows": lines,
        "audit": compare(lines, ref)
        if proc.returncode == 0 and len(lines) == 22
        else {"errors": [{"error": "runner_failure"}]},
    }


def run(binary, output, workers=4, all_sealed=False):
    if not 1 <= workers <= 8:
        raise ValueError("workers must be 1..8")
    receipt = json.loads((INPUTS / "inputs.json").read_text())
    rows = select(receipt["rows"], all_sealed=all_sealed)
    ts = templates()
    base = baseline()
    output.mkdir()
    manifest = {
        "schema": "arm-full-optimization-cohort/v1",
        "selected": rows,
        "input_sha256": sha(INPUTS / "inputs.json"),
        "baseline_sha256": sha(BASELINE),
        "binary_sha256": sha(binary),
        "all_sealed": all_sealed,
        "planned_dwells": len(rows),
        "planned_windows": len(rows) * 22,
        "complete": False,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    with (
        tempfile.TemporaryDirectory(prefix="leo-cohort-", dir=output) as name,
        (output / "rows.jsonl").open("x") as f,
        ThreadPoolExecutor(max_workers=workers) as pool,
    ):
        futures = [pool.submit(worker, row, binary, Path(name), ts, base) for row in rows]
        for future in as_completed(futures):
            try:
                value = future.result()
            except Exception as error:
                value = {
                    "context": rows[futures.index(future)],
                    "returncode": None,
                    "stdout": "",
                    "stderr": "",
                    "rows": [],
                    "audit": {"errors": [{"error": repr(error)}]},
                }
            f.write(json.dumps(value) + "\n")
            f.flush()
    manifest["complete"] = True
    manifest["processed_dwells"] = len(rows)
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--binary", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--all-sealed", action="store_true")
    a = p.parse_args()
    run(a.binary, a.output, a.workers, a.all_sealed)
