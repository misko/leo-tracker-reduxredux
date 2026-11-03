"""Freeze a balanced panel and export response-free causal orbit evidence."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
AUTHORITIES = {
    "DS9": ROOT / "reports/2026_09_28_ds9_post_ds8/manifest.json",
    "DS10": ROOT / "reports/2026_09_29_ds10_post_ds9/local/manifest.json",
    "DS11": ROOT / "reports/2026_09_30_ds11_post_ds10/local/manifest.json",
}
COUNTS = {"DS9": 11, "DS10": 11, "DS11": 10}
PYTHON = "/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python"

def digest(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")

def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

def selected_indices(size, count):
    if count < 2 or size < count:
        raise ValueError("invalid quantile count")
    return [i * (size - 1) // (count - 1) for i in range(count)]

def freeze():
    selection = {"schema": "sacramento-model-panel/v1", "counts": COUNTS,
                 "selected": {}, "authorities": {}, "created_utc": datetime.now(timezone.utc).isoformat()}
    for dataset, path in AUTHORITIES.items():
        captures = sorted(json.loads(path.read_text())["captures"], key=lambda r: (r["capture_start_utc_ns"], r["session_id"]))
        selection["authorities"][dataset] = {"path": str(path), "sha256": digest(path), "count": len(captures)}
        selection["selected"][dataset] = [captures[i] | {"selection_index": i, "unit_id": f"{dataset}-F{i+1:03d}"}
                                           for i in selected_indices(len(captures), COUNTS[dataset])]
    write_new(HERE / "selection.json", selection)
    adapter = module(ROOT / "reports/2026_09_30_gaussian_sum_single_scan/evidence.py", "evidence_adapter")
    paths = sorted(set(ROOT.glob("reports/*/exports/*/observations.json")) |
                   set(ROOT.glob("reports/*/evidence/sources/*.observations.json")))
    by_session = {}
    for path in paths:
        try:
            with path.open() as stream:
                head = stream.read(1000)
            match = re.search(r'"session_id"\s*:\s*"([^"]+)"', head)
            if match:
                by_session.setdefault(match[1], []).append(path)
        except OSError:
            continue
    inventory = []
    for dataset, rows in selection["selected"].items():
        for row in rows:
            accepted, errors = [], []
            for path in by_session.get(row["session_id"], []):
                try:
                    bundle = adapter.load_observation_export(path, row)
                    accepted.append((path, bundle))
                except Exception as exc:
                    errors.append({"path": str(path), "error": str(exc)})
            item = {"unit_id": row["unit_id"], "session_id": row["session_id"], "dataset": dataset,
                    "status": "ready" if accepted else "needs_export", "rejected": errors}
            if accepted:
                path, bundle = accepted[0]
                write_new(HERE / "evidence" / f"{row['unit_id']}.json", bundle)
                item.update(source=str(path), sha256=digest(path), tracks=len(bundle["tracks"]))
            inventory.append(item)
    write_new(HERE / "inventory.json", {"selection_sha256": digest(HERE / "selection.json"), "rows": inventory})
    print(json.dumps({"selected": len(inventory), "ready": sum(r["status"] == "ready" for r in inventory)}), flush=True)

def units():
    selection = json.loads((HERE / "selection.json").read_text())
    return [row for rows in selection["selected"].values() for row in rows]

def ensure_source(unit):
    path = HERE / "evidence" / f"{unit}.json"
    if path.exists():
        return json.loads(path.read_text())
    row = next(r for r in units() if r["unit_id"] == unit)
    exporter = module(ROOT / "tools/ds7_export_baseline.py", "baseline_exporter")
    output = HERE / "evidence/sources" / f"{unit}.observations.json"
    exporter.export(row, output, Path("/srv/bulk/leo"), Path("/var/lib/leo/tle"))
    adapter = module(ROOT / "reports/2026_09_30_gaussian_sum_single_scan/evidence.py", "evidence_adapter")
    bundle = adapter.load_observation_export(output, row)
    write_new(path, bundle)
    return bundle

def journal():
    output = HERE / "tle-publications.jsonl"
    if output.exists():
        return
    result = subprocess.run(["sudo", "-n", "journalctl", "-u", "leo-tle-collection.service",
                             "--since", "2026-09-20", "--until", "2026-09-30 02:00:00", "-o", "json", "--no-pager"],
                            check=True, capture_output=True, text=True, timeout=60)
    with output.open("x") as stream:
        stream.write(result.stdout)

def publication_times(path):
    times = {}
    for line in Path(path).read_text().splitlines():
        try:
            doc = json.loads(line)
            message = json.loads(doc["MESSAGE"])
            ns = int(doc["__REALTIME_TIMESTAMP"]) * 1000
        except (KeyError, ValueError, TypeError):
            continue
        if message.get("event") != "tle_collection":
            continue
        for row in message.get("providers", []):
            if row.get("status") == "published" and row.get("digest"):
                key = row["provider"], row["digest"]
                times.setdefault(key, []).append(ns)
    return times

def orbit_export(unit):
    import numpy as np
    from leo.operations.tle_archive import TleArchiveReader
    from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
    from leo.sky.propagation import parse_element_set_records, parse_element_sets, propagate_grid
    from leo.sky.sampling import SamplingGrid
    from leo.sky.frames import greenwich_mean_sidereal_time_rad, julian_day_from_utc_ns, teme_to_ecef
    began = time.monotonic()
    bundle = ensure_source(unit)
    source_path = Path(bundle["source"]["path"])
    if digest(source_path) != bundle["source"]["sha256"]:
        raise ValueError("source hash mismatch")
    source = json.loads(source_path.read_text())
    capture = next(r for r in units() if r["unit_id"] == unit)
    cutoff = min(int(source["start_utc_ns"]), int(capture.get("capture_start_earliest_utc_ns", capture["capture_start_utc_ns"])))
    reader = TleArchiveReader(Path("/var/lib/leo/tle"))
    publications = publication_times(HERE / "tle-publications.jsonl")
    eligible = []
    for ref in reader.list_snapshots():
        if ref.collected_utc_ns >= cutoff:
            continue
        matches = [t for t in publications.get((ref.provider, ref.digest), [])
                   if max(ref.collected_utc_ns, ref.path.stat().st_mtime_ns) <= t < cutoff]
        if matches:
            eligible.append((ref, min(matches)))
    if not eligible:
        raise ValueError("no completion-proven causal catalogue")
    # Public provider snapshots are complete catalogues. Freeze latest complete
    # snapshot per provider, then newest element epoch per object across them.
    latest = [max((r for r in eligible if r[0].provider == provider), key=lambda r: (r[0].collected_utc_ns, r[0].digest))
              for provider in sorted({r[0].provider for r in eligible})]
    choices, proofs = {}, []
    for ref, published_ns in latest:
        payload, _ = exclude_labelled_starlink_debris(reader.read(ref))
        records = list(parse_element_set_records(payload))
        epochs = parse_element_sets(payload).element_epoch_utc_ns()
        proofs.append({"path": str(ref.path), "sha256": ref.digest, "provider": ref.provider,
                       "collected_utc_ns": ref.collected_utc_ns, "mtime_ns": ref.path.stat().st_mtime_ns,
                       "published_utc_ns": published_ns, "cutoff_utc_ns": cutoff})
        for record, epoch in zip(records, epochs, strict=True):
            key = int(epoch), ref.collected_utc_ns, ref.digest
            if record.satellite_number not in choices or key > choices[record.satellite_number][0]:
                choices[record.satellite_number] = key, record
    ordered = [choices[n][1] for n in sorted(choices)]
    payload = "".join(f"0 {r.name}\n{r.first_line}\n{r.second_line}\n" for r in ordered)
    cat = parse_element_sets(payload)
    ts = [t for row in source["tracks"] for t in row["times_s"]]
    knots = np.arange(math.floor((min(ts)-15)/5)*5, math.ceil((max(ts)+15)/5)*5+2.5, 5.)
    def propagate(times):
        ns = np.array([source["start_utc_ns"] + round(t*1e9) for t in times], dtype=np.int64)
        state = propagate_grid(cat, SamplingGrid(tuple(map(int, ns)), 0, 1.), np.arange(len(ordered)))
        jd, frac = julian_day_from_utc_ns(ns)
        pos, vel = teme_to_ecef(state.position_teme_km, state.velocity_teme_km_s, greenwich_mean_sidereal_time_rad(jd, frac))
        valid = (state.error_code == 0).all(axis=1) & np.isfinite(pos).all(axis=(1,2)) & np.isfinite(vel).all(axis=(1,2))
        valid &= np.linalg.norm(pos, axis=-1).min(axis=1) > 6498.137
        return pos, vel, valid
    pos, vel, valid = propagate(knots)
    midpos, midvel, midvalid = propagate(knots[:-1]+2.5)
    valid &= midvalid
    out = Path("/srv/bulk/leo/research/sacramento_model_comparison") / f"{unit}-orbits.npz"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        raise FileExistsError(out)
    ids = np.asarray(cat.satellite_numbers)
    np.savez(out, satellite_ids=ids[valid], knot_times_s=knots,
             positions_ecef_km=pos[valid], velocities_ecef_km_s=vel[valid])
    cubic = (-vel[:, :-3] + 9*vel[:, 1:-2] + 9*vel[:, 2:-1] - vel[:, 3:])/16
    meta = {"schema": "gaussian-sum-response-free-orbits/v1", "session_id": source["session_id"],
            "observation_sha256": digest(source_path), "tle": {"causal": True, "sources": proofs,
                "publication_log_sha256": digest(HERE / "tle-publications.jsonl")},
            "policy": "Full newest-element union of latest completion-proven complete provider snapshots; labelled debris excluded; no measured-response or geographic shortlist",
            "catalogue_count": len(ordered), "propagated_count": int(valid.sum()),
            "propagation_rejected_norad_ids": ids[~valid].tolist(), "catalogue_gap": bool((~valid).any()),
            "state_file": str(out), "state_sha256": digest(out), "start_utc_ns": source["start_utc_ns"],
            "knot_start_s": float(knots[0]), "knot_stop_s": float(knots[-1]), "knot_step_s": 5.,
            "cubic_velocity_midpoint_max_error_km_s": float(np.linalg.norm(cubic[valid]-midvel[valid,1:-1],axis=-1).max()),
            "elapsed_seconds": time.monotonic()-began}
    write_new(HERE / "evidence" / f"{unit}-orbits.json", meta)
    print(json.dumps({"unit": unit, "status": "ready", "satellites": int(valid.sum()), "seconds": meta["elapsed_seconds"]}), flush=True)

def batch(start, count):
    groups = list(json.loads((HERE / "selection.json").read_text())["selected"].values())
    ordered = [g[i]["unit_id"] for i in range(max(map(len,groups))) for g in groups if i < len(g)]
    for unit in ordered[start:start+count]:
        receipt = HERE / "preparation" / f"{unit}.json"
        if receipt.exists():
            continue
        cmd = ["sudo", "-n", "env", "OPENBLAS_NUM_THREADS=1", "OMP_NUM_THREADS=1", PYTHON, str(Path(__file__).resolve()), "orbit", unit]
        began = time.monotonic()
        try:
            result = subprocess.run(cmd, text=True, capture_output=True, timeout=180)
            item = {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
        except subprocess.TimeoutExpired:
            item = {"returncode": 124, "stderr": "preparation timeout"}
        item.update(unit=unit, seconds=time.monotonic()-began, command=cmd)
        write_new(receipt, item)
        print(json.dumps(item), flush=True)

if __name__ == "__main__":
    command = sys.argv[1]
    if command == "freeze": freeze()
    elif command == "journal": journal()
    elif command == "orbit": orbit_export(sys.argv[2])
    elif command == "batch": batch(int(sys.argv[2]), int(sys.argv[3]))
    else: raise ValueError(command)
