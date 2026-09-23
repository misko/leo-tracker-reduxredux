#!/usr/bin/env python3
"""Frozen fixed-cone cross-validation over the 12 TRAIN scans."""
import hashlib, importlib.util, json, os, sys, time
from pathlib import Path
import numpy as np

ROOT = Path(__file__).parents[2]
HERE = Path(__file__).parent
CONE = ROOT / "reports/2026_09_23_train_pointing_cone/run.py"
SOURCE_LOCATIONS = ROOT / "reports/2026_09_23_train_pointing_cone/locations.json"
METADATA = Path("/tmp/leo-train-rx-metadata.json")
SEED = 20260923
WIDTHS = (10, 15, 20, 30)
MAPPINGS = ((0, 1), (1, 0))

def digest(path): return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod
    spec.loader.exec_module(mod); return mod

def fold_map(ids):
    unique = np.asarray(sorted(set(ids)))
    rng = np.random.default_rng(SEED); shuffled = unique[rng.permutation(len(unique))]
    return {value: index % 5 for index, value in enumerate(shuffled)}

def shuffled_labels(labels, strata, permutation):
    rng = np.random.default_rng(SEED + 1000 + permutation)
    out = labels.copy(); unchanged = 0
    for key in sorted(set(strata)):
        ix = np.flatnonzero(strata == key)
        if len(ix) < 2 or len(set(labels[ix])) < 2: unchanged += 1
        else: out[ix] = labels[ix][rng.permutation(len(ix))]
    return out, unchanged, int(np.count_nonzero(out != labels))

def select_orientation(coverage, weights, train):
    scores = coverage[:, train] @ weights[train]
    return int(np.argmax(scores)), float(np.max(scores))

def score_cell(cone, midpoint, endpoints, labels, weights, identities, strata, folds, control_count=20):
    fold_ids = np.asarray([folds[x["candidate_id"]] for x in identities])
    orientations = cone.orientation_grid(15)
    axes = cone.axes_batched(orientations)
    angle = np.degrees(np.arccos(np.clip(np.einsum("oac,tc->oat", axes, midpoint), -1, 1))).astype(np.float32)
    label_sets = [("actual", -1, labels, 0, 0)]
    for p in range(control_count):
        shuffled, unchanged, moved = shuffled_labels(labels, strata, p)
        label_sets.append(("shuffle", p, shuffled, unchanged, moved))
    rows = []
    tracks = np.arange(len(labels))
    for kind, permutation, assigned, unchanged, moved in label_sets:
        for mapping in MAPPINGS:
            selected = angle[:, np.asarray(mapping)[assigned], tracks]
            for fold in range(5):
                held = fold_ids == fold; train = ~held
                if not held.any() or not train.any(): raise ValueError(f"empty fold {fold}")
                for width in WIDTHS:
                    coverage = selected <= width
                    oi, fit_duration = select_orientation(coverage, weights, train)
                    held_duration = float(np.sum(weights[held]))
                    held_inside = float(np.sum(weights[held] * coverage[oi, held]))
                    mount = axes[oi, np.asarray(mapping)[assigned]]
                    endpoint_angle = np.degrees(np.arccos(np.clip(np.einsum("tec,tc->te", endpoints, mount), -1, 1)))
                    sampled_whole = coverage[oi] & np.all(endpoint_angle <= width, axis=1)
                    sampled_whole_inside = float(np.sum(weights[held] * sampled_whole[held]))
                    rows.append({
                        "kind": kind, "permutation": permutation, "mapping": list(mapping),
                        "fold": fold, "width_deg": width,
                        "orientation": [int(x) for x in orientations[oi]],
                        "fit_inside_duration_s": fit_duration,
                        "fit_duration_s": float(np.sum(weights[train])),
                        "held_inside_duration_s": held_inside,
                        "held_duration_s": held_duration,
                        "held_coverage": held_inside / held_duration,
                        "held_sampled_whole_inside_duration_s": sampled_whole_inside,
                        "held_sampled_whole_coverage": sampled_whole_inside / held_duration,
                        "held_track_count": int(np.sum(held)),
                        "held_norad_count": len(set(identities[i]["candidate_id"] for i in np.flatnonzero(held))),
                        "unchanged_strata": unchanged, "moved_labels": moved,
                    })
    return rows, len(orientations)

def prepare(cone):
    cells = json.loads((HERE / "locations.json").read_text())["cells"]
    views = [{"group": group, "scan_count": 6, "prior": "reno", "locations": [
        {"role": cell["cell_id"], "latitude_deg": cell["latitude_deg"], "longitude_deg": cell["longitude_deg"]}
        for cell in cells]} for group in ("first_train", "second_train")]
    expanded_text = json.dumps({"views": views}, indent=2, sort_keys=True) + "\n"
    (HERE / "expanded_locations.json").write_text(expanded_text)
    captured = []
    def capture(midpoint, endpoints, receiver_ids, weights, mapping, fractions, **kwargs):
        if tuple(mapping) == (0, 1): captured.append((midpoint.copy(), endpoints.copy(), receiver_ids.copy(), weights.copy()))
        return {str(b): {str(f): {"midpoint_cone_deg": 0.0, "endpoint_cone_deg": 0.0, "tilt_deg": 0, "tilt_azimuth_deg": 0, "yaw_deg": 0} for f in fractions} for b in (0,15,30)}
    generated = HERE / "locations.json"
    original = generated.read_text()
    generated.write_text(expanded_text)
    try:
        cone.profile = capture; cone.HERE = HERE; cone.main()
    finally: generated.write_text(original)
    temp = HERE / "results.json"; prepared = HERE / "prepared_inputs.json"
    temp.replace(prepared); (HERE / "results.sha256").unlink()
    data = json.loads(prepared.read_text())
    data["preparation_note"] = "Geometry profiles are deliberate dummy zeros from interception; identities, candidate selections, metadata/cache bindings, and directions captured in memory are real."
    prepared.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return cells, data, captured

def main(control_count=20):
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    started = time.monotonic(); cone = load(CONE, "fixed_cone_source")
    cells, prepared, captured = prepare(cone)
    metadata = json.loads(METADATA.read_text())["sessions"]
    lanes = {(s["session_id"], t["track_id"]): f'{t["channel"]}/{t["edge"]}/{t["actual_rf_hz"]}/{t["sample_rate_hz"]}' for s in metadata for t in s["tracks"]}
    rows=[]; orientation_count=None
    global_folds = fold_map([identity["candidate_id"] for base in prepared["results"] for identity in base["identities"]])
    for ci, cell in enumerate(cells):
        bases = [prepared["results"][ci], prepared["results"][len(cells)+ci]]
        parts = [captured[ci], captured[len(cells)+ci]]
        midpoint=np.concatenate([x[0] for x in parts]); endpoints=np.concatenate([x[1] for x in parts]); labels=np.concatenate([x[2] for x in parts]); weights=np.concatenate([x[3] for x in parts])
        identities=sum([x["identities"] for x in bases], [])
        if len({x["session_id"] for x in identities}) != 12: raise ValueError("incomplete 12-scan support")
        strata=np.asarray([f'{x["session_id"]}|{lanes[(x["session_id"],x["track_id"])]}' for x in identities])
        cell_rows, orientation_count = score_cell(cone, midpoint, endpoints, labels, weights, identities, strata, global_folds, control_count)
        for row in cell_rows: row.update(cell_id=cell["cell_id"], aliases=cell["aliases"])
        rows.extend(cell_rows); print(f'completed {cell["cell_id"]}', flush=True)
    output={"schema":"train-fixed-cone/v1","seed":SEED,"control_count":control_count,"widths_deg":list(WIDTHS),"orientation_count":orientation_count,"truth_used":False,"held_external_used":False,"elapsed_s":time.monotonic()-started,"rows":rows,"bindings":{"protocol":digest(HERE/"PROTOCOL.md"),"source":digest(__file__),"locations":digest(HERE/"locations.json"),"expanded_locations":digest(HERE/"expanded_locations.json"),"source_locations":digest(SOURCE_LOCATIONS),"cone_source":digest(CONE),"metadata":digest(METADATA),"prepared_inputs":digest(HERE/"prepared_inputs.json")}}
    path=HERE/"results.json"; path.write_text(json.dumps(output,indent=2,sort_keys=True)+"\n")
    (HERE/"results.sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest()+"\n")

if __name__ == "__main__": main()
