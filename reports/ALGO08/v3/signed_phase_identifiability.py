"""Reconstruct fixed-support signed phase endpoints and same-profile grid geometry."""

import argparse
from hashlib import sha256
import json
from math import asin, cos, dist, hypot, inf, isclose, isfinite, nextafter, radians, sin, sqrt
from pathlib import Path
import re
import subprocess
import zlib


ROOT = Path(__file__).resolve().parents[3]
REVISION = "188aae607aa3f47ff0801ea626cc08d594d844ec"
ARCHIVE = "reports/ALGO08/v3/measurements/"
REFERENCE_SHA = "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5"
RECENT = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124/cases/DS30-0049")
ARMS = ("c0", "fitted_c")
MAX_BYTES = 12_000_000
SCALE = 5.991464547107979
GIT = ["git", "-c", f"safe.directory={ROOT}", "-C", str(ROOT)]
CASE = re.compile(r"DS30-\d{4}")
FIELDS = ("latlon", "east_north_km", "objective", "rf_rms_hz", "curved_points", "linear_points",
          "failed_curved", "failed_linear", "final_phase_change_s")


def hash_bytes(body):
    return sha256(body).hexdigest()


def canonical(doc):
    return "sha256:" + hash_bytes(json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                           allow_nan=False).encode())


def read(path):
    return json.loads(path.read_bytes())


def case_hint(label):
    found = CASE.findall(label)
    if len(set(found)) == 1:
        return found[0]
    narrow = set(re.findall(r"(?<!\d)0\d{3}(?!\d)", label))
    return "DS30-" + narrow.pop() if len(narrow) == 1 else None


def trace_paths(doc, keys=(), case=None):
    if isinstance(doc, list):
        for index, row in enumerate(doc):
            yield from trace_paths(row, (*keys, index), case)
    if not isinstance(doc, dict):
        return
    case = next((doc[k] for k in ("case", "case_id", "dataset_label", "recording")
                 if isinstance(doc.get(k), str) and CASE.fullmatch(doc[k])), case)
    if isinstance(doc.get("signed"), dict) and "signed_total_clocks" in doc:
        yield case, keys, doc
        return
    for key, value in doc.items():
        yield from trace_paths(value, (*keys, key), key if CASE.fullmatch(key) else case)


def numeric_arms(arms):
    if not isinstance(arms, dict) or set(arms) != set(ARMS):
        return None
    if any(any(k not in row for k in FIELDS) for row in arms.values()):
        return None
    return {arm: {k: arms[arm][k] for k in FIELDS} for arm in ARMS}


def checkpoint(attempt):
    signed = attempt["signed"]
    repair = attempt.get("repair") or {}
    alternative = attempt.get("conditional_repair_fallback") or {}
    if alternative.get("status") == "qualified_for_standard_evidence":
        origin, ordinary = "conditional refit", alternative.get("finish")
    elif repair.get("status") == "complete":
        origin, ordinary = "accepted repair", repair.get("finish")
    elif attempt.get("pair_passes") is True:
        origin, ordinary = "initial accepted pair", attempt.get("finish")
    else:
        origin, ordinary = None, None
    before, after = numeric_arms(ordinary), numeric_arms(signed.get("finish"))
    comparison = None
    if signed.get("status") == "accepted" and before is not None and after is not None:
        if all(before[a]["curved_points"] > 0 and not before[a]["failed_curved"] and not before[a]["failed_linear"]
               and not after[a]["failed_curved"] and not after[a]["failed_linear"]
               and all(before[a][name] == after[a][name] for name in ("curved_points", "linear_points")) for a in ARMS):
            comparison = {a: dict(move_km=dist(before[a]["east_north_km"], after[a]["east_north_km"]),
                                  reported_cross_prior_score_difference=after[a]["objective"]-before[a]["objective"],
                                  signed_minus_ordinary_rf_rms_hz=after[a]["rf_rms_hz"]-before[a]["rf_rms_hz"]) for a in ARMS}
    return dict(origin=origin, before=before, after=after, comparison=comparison,
                qualifies=signed.get("selection", {}).get("qualified"), signed_status=signed.get("status"),
                terminal=attempt.get("decision"), exterior=attempt.get("exterior"),
                postfit_repair=(attempt.get("local_future_repair") or {}).get("decision"),
                clocks={name: attempt[name] for name in ("signed_total_clocks", "signed_refit_clocks",
                                                         "signed_qualify_clocks", "exterior_clocks") if name in attempt})


def sampled_geometry(grid, before, after, arm):
    """Estimate curvature and displacement on the same signed objective grid."""
    x, y = after["east_north_km"]
    if not grid["complete"] or grid["endpoints"][arm] != [x, y]:
        return None
    n = grid["local_size"] // 2
    if n < 1:
        return None
    h = grid["local_half_width_km"] / n
    if not isfinite(h) or h <= 0:
        return None
    cells = {}
    for row in grid["points"]:
        u, v = (row["east_km"]-x)/h, (row["north_km"]-y)/h
        i, j = round(u), round(v)
        if abs(i) <= n and abs(j) <= n and abs(u-i) < 1e-8 and abs(v-j) < 1e-8:
            score = row["scores"].get(arm)
            if score is not None and isfinite(score):
                cells[i, j] = score
    if len(cells) != (2*n+1)**2 or not isclose(cells[0, 0], after["objective"], abs_tol=1e-8, rel_tol=0):
        return None
    f = cells[0, 0]
    ee = (cells[1, 0]+cells[-1, 0]-2*f)/h**2
    nn = (cells[0, 1]+cells[0, -1]-2*f)/h**2
    en = (cells[1, 1]-cells[1, -1]-cells[-1, 1]+cells[-1, -1])/(4*h**2)
    spread = hypot(ee-nn, 2*en)
    eigen = [(ee+nn-spread)/2, (ee+nn+spread)/2]
    dx, dy = before["east_north_km"][0]-x, before["east_north_km"][1]-y
    u, v = dx/h, dy/h
    interpolated = None
    if max(abs(u), abs(v)) <= n:
        i, j = max(-n, min(int(u // 1), n-1)), max(-n, min(int(v // 1), n-1))
        a, b = u-i, v-j
        interpolated = sum(w*(cells[k, l]-f) for k, l, w in (
            (i, j, (1-a)*(1-b)), (i+1, j, a*(1-b)), (i, j+1, (1-a)*b), (i+1, j+1, a*b)))
    quadratic = (ee*dx**2+2*en*dx*dy+nn*dy**2)/2 if eigen[0] > 0 else None
    return dict(step_km=h, hessian_score_per_km2=[[ee, en], [en, nn]], eigenvalues=eigen,
                quadratic_score_delta=quadratic, bilinear_score_delta=interpolated,
                nominal_two_dimensional_scale=SCALE, in_local_grid=interpolated is not None)


def bound_arms(arms, width):
    half = width/2
    points = {arm: max(abs(v) for v in row["east_north_km"]) for arm, row in arms.items()}
    if any(not isfinite(edge) or edge > half for edge in points.values()):
        return None
    return [arm for arm in ARMS if points[arm] >= nextafter(half, -inf)]


def add_grid(record, signed_grid):
    if record["comparison"] is None or signed_grid.get("endpoints") is None:
        return
    values = {arm: sampled_geometry(signed_grid, record["before"][arm], record["after"][arm], arm) for arm in ARMS}
    if any(value is None for value in values.values()):
        return
    width = signed_grid["box_width_km"]
    record.update(geometry=values, width_km=width, ordinary_bound_arms=bound_arms(record["before"], width),
                  signed_bound_arms=bound_arms(record["after"], width))


def verified_grid(base):
    for folder in (base, base/"candidate", base/"routed"/"candidate"):
        for path in folder.glob("fast-scan-standard-*/*/*/position-grid.json"):
            for holder in (folder, base, base.parent, base.parent.parent):
                if not path.is_relative_to(holder):
                    continue
                receipt = holder / "prediction-seal.json"
                if receipt.is_file() and read(receipt).get(str(path.relative_to(holder))) == hash_bytes(path.read_bytes()):
                    body = read(path)
                    if canonical(body["document"]) == body["sha256"]:
                        yield body["document"], str(path), hash_bytes(receipt.read_bytes())


def record_document(body, name, kind, *, grid_options=()):
    if b'"signed_total_clocks"' not in body:
        return []
    digest = hash_bytes(body)
    rows = []
    for case, keys, attempt in trace_paths(json.loads(body), case=case_hint(name)):
        result = checkpoint(attempt)
        if case is None and not any("south" in str(k) or "north" in str(k) or "india" in str(k) for k in keys):
            continue
        result.update(case=case, source=name, source_kind=kind, source_sha256=digest, trace=keys)
        for grid, origin, seal in grid_options:
            add_grid(result, grid)
            if "geometry" in result:
                result.update(grid_source=origin, grid_seal_sha256=seal)
                break
        rows.append(result)
    return rows


def tracked():
    entries = subprocess.check_output([*GIT, "ls-tree", "-r", "-l", REVISION, "--", ARCHIVE], text=True)
    rows, cap, inspected = [], 0, 0
    with subprocess.Popen([*GIT, "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE) as blobs:
        for line in entries.splitlines():
            info, name = line.split("\t", 1)
            _, kind, oid, size = info.split()
            if kind != "blob" or not name.endswith((".json", ".json.gz")):
                continue
            if int(size) > MAX_BYTES:
                cap += 1
                continue
            blobs.stdin.write(oid.encode()+b"\n")
            blobs.stdin.flush()
            _, _, size = blobs.stdout.readline().split()
            body = blobs.stdout.read(int(size))
            if blobs.stdout.read(1) != b"\n":
                raise ValueError("Truncated Git receipt")
            if name.endswith(".gz"):
                body = zlib.decompressobj(31).decompress(body, MAX_BYTES+1)
            if len(body) > MAX_BYTES:
                cap += 1
                continue
            inspected += 1
            rows.extend(record_document(body, name.removeprefix(ARCHIVE), "tracked receipt"))
    return rows, dict(inspected=inspected, above_byte_cap=cap)


def resident():
    stage = Path("/dev/shm")
    rows, files = [], 0
    for path in sorted(stage.glob("leo-v3-*/**/risk-route.json")):
        relative = path.relative_to(stage)
        if "reports" in relative.parts or not path.resolve().is_relative_to(stage) or path.stat().st_size > MAX_BYTES:
            continue
        files += 1
        base = stage / relative.parts[0]
        rows.extend(record_document(path.read_bytes(), str(relative), "tmpfs route",
                                    grid_options=tuple(verified_grid(base))))
    return rows, files


def recent():
    pair = read(RECENT / "pair.json")
    folder = RECENT / "successor/attempt-000002"
    attempt_path = folder / "result.json"
    attempt = read(attempt_path)
    if (not pair["verified_pair"] or not pair["same_lease"]
            or pair["attempt_result_sha256"]["successor"] != "sha256:"+hash_bytes(attempt_path.read_bytes())):
        raise ValueError("The 0049 paired result changed")
    publication = folder / "publication"
    witness = publication / "exact-named-raw-witness.json"
    (grid_path,) = publication.glob("fast-scan-standard-*/*/*/position-grid.json")
    envelope = read(grid_path)
    grid = envelope["document"]
    if (canonical(grid) != envelope["sha256"] or canonical(
            {k: v for k, v in grid.items() if k not in ("binding", "elapsed_seconds")}) !=
            attempt["evidence"]["scientific_digests"]["grid"]):
        raise ValueError("The complete signed profile grid does not bind to the paired result")
    return record_document(witness.read_bytes(), f"DS30-0049/{witness.name}", "paired original raw",
                           grid_options=((grid, str(grid_path), pair["attempt_result_sha256"]["successor"]),))


def predict():
    archival, coverage = tracked()
    staged, count = resident()
    return dict(schema="leo.research.signed-phase-identifiability.v1", revision=REVISION,
                coverage=coverage | {"tmpfs_route_files": count}, rows=archival+staged+recent(),
                solver_workers=0, reference_coordinates_read=0)


def distance_km(a, b):
    x, y = map(radians, a)
    p, q = map(radians, b)
    return 12742.0176 * asin(sqrt(sin((x-p)/2)**2+cos(x)*cos(p)*sin((y-q)/2)**2))


def refresh_history(history):
    """Count actual center and side evaluations once the terminal position is reached."""
    terminal = history[-1]["position"]
    start = next(i for i in range(len(history)) if all(step["position"] == terminal for step in history[i:]))
    tail = history[start+1:]
    return dict(rounds=history, terminal_position_first_round=start+1,
                objective_calls=sum(row["evaluations"] for row in history),
                stationary_three_call_rounds=sum(row["evaluations"] == 3 for row in tail),
                side_calls_at_unchanged_endpoint=sum(2 for row in tail if row["evaluations"] == 3),
                late_phase_unchanged=all(row["phase_change_s"] == 0 for row in tail) if tail else None)


def refreshes():
    sources = {
        "DS30-0049": RECENT / "successor/attempt-000002/publication/exact-named-raw-witness.json",
        "DS30-0169": Path("/dev/shm/leo-v3-clean-saved-0169-initial01/routed/risk-route.json"),
        "DS30-0173": Path("/dev/shm/leo-v3-0173-composed-saved-result01/routed/risk-route.json"),
        "DS30-0255": Path("/dev/shm/leo-v3-conditional-repair-0255-result01/routed/risk-route.json"),
        "DS30-0359": Path("/dev/shm/leo-v3-0359-composed-saved-result01/routed/risk-route.json"),
        "DS30-0419": Path("/dev/shm/leo-v3-nomination-handoff-0419-local01/routed/risk-route.json"),
    }
    rows = {}
    for case, path in sources.items():
        body = path.read_bytes()
        data = json.loads(body)
        route = data["ports"]["history_risk"] if "ports" in data else data["solves"][0]
        (attempt,) = route["lean_attempts"]
        rows[case] = dict(source=str(path), source_sha256=hash_bytes(body),
                          elapsed=attempt["named_survivor_fit"], arms={
                              arm: refresh_history(route["lean_final_fit"]["arms"][arm]["fit"]["history"])
                              for arm in ARMS})
    return dict(rows=rows, actual_solver_workers=0)


def score(prediction, pin):
    body = prediction.read_bytes()
    if hash_bytes(body) != pin:
        raise ValueError("Prediction changed before opening the survey")
    data = subprocess.check_output([*GIT, "show", "2d0ad2dfd:reports/2026_11_21_ds30_full/reference-audit.json"])
    if hash_bytes(data) != REFERENCE_SHA:
        raise ValueError("The survey input changed")
    references = {row["dataset_label"]: [row["reference"][key] for key in ("latitude_deg", "longitude_deg")]
                  for row in json.loads(data)["cases"] if row["authority_eligible"] and row["sealed_metadata_digests_verified"]}
    prediction = json.loads(body)
    results = []
    for index, row in enumerate(prediction["rows"]):
        if row["comparison"] is None or row["case"] not in references:
            continue
        location = references[row["case"]]
        arms = {arm: {key+"_horizontal_error_m": 1000*distance_km(row[key][arm]["latlon"], location)
                      for key in ("before", "after")} for arm in ARMS}
        for record in arms.values():
            record["signed_minus_ordinary_horizontal_m"] = record["after_horizontal_error_m"]-record["before_horizontal_error_m"]
        results.append(dict(row_index=index, case=row["case"], arms=arms))
    return dict(predictions_sha256=pin, reference_sha256=REFERENCE_SHA, results=results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("predict", "score", "refreshes"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--prediction", type=Path)
    parser.add_argument("--prediction-sha256")
    args = parser.parse_args()
    answer = {"predict": predict, "refreshes": refreshes,
              "score": lambda: score(args.prediction, args.prediction_sha256)}[args.mode]()
    with args.output.open("x") as out:
        json.dump(answer, out, indent=2, sort_keys=True, allow_nan=False)
        out.write("\n")
