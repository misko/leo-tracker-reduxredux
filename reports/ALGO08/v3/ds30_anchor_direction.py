"""Read two archived, fixed-support conditional position surfaces per case."""

import hashlib
import json
from math import cos, floor, hypot, isfinite, radians
from pathlib import Path

from leo.contracts.position_grid import ARMS, validate


CROSS = Path("/tmp/leo-v3-0049-saved-cross-proof02")
ANCHORS = Path("/dev/shm/leo-v3-anchor-only-0049-01")
FIELD = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124/cases/DS30-0086")
TRANSLATED = Path("/tmp/leo-v3-field-offer-0086-01")
SCALE = 5.991


def digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def canonical(value):
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                             allow_nan=False).encode())


def read(path, pin=None):
    body = path.read_bytes()
    if pin is not None and digest(body) != "sha256:" + pin.removeprefix("sha256:"):
        raise ValueError(f"Changed archived product {path}")
    return json.loads(body)


def publication(root, receipt, native, owners, figure, grid_pin, authority):
    run = receipt["run_id"]
    folder = root / "fast-scan-standard-v2" / run / "final-error-v7"
    envelope = read(folder / "position-grid.json", grid_pin)
    manifest = read(folder / "manifest.json")
    grid = validate(envelope["document"], manifest)
    terminal = read(root / "fast-scan-automatic-work" / run / "terminal.json", receipt["terminal_sha256"])
    binding = grid["binding"]
    if ({"run_id": run, "terminal_sha256": receipt["terminal_sha256"], "input_sha256": native,
         "owner_sha256": owners, "position_png_sha256": figure} !=
            {key: binding[key] for key in ("run_id", "terminal_sha256", "input_sha256",
                                           "owner_sha256", "position_png_sha256")}
            or envelope["sha256"] != canonical(grid) or manifest["raw_authority"] != authority
            or grid["region_center"] != receipt["region"]["center"]
            or grid["box_width_km"] != receipt["region"]["width_km"]
            or terminal["region"] != receipt["region"] or terminal["native_sha256"] != native
            or terminal["decision"] != "ok" or receipt["decision"] != "complete"
            or terminal["session_id"] != receipt["session_id"]
            or grid["endpoint_latlon"] != {arm: terminal["arms"][arm]["latlon"] for arm in ARMS}
            or grid["endpoint_objective_replay"] != manifest["objective_replay"]
            or any(abs(delta) > 1e-4 or not isfinite(delta)
                   for delta in grid["endpoint_objective_replay"].values())
            or not grid["complete"] or grid["nuisance_model"] not in (
                "unchanged published marginal likelihood",
                "unchanged marginal likelihood, research permuted native posterior factor")):
        raise ValueError(f"Grid does not bind its archived science at {root}")
    evidence = dict(root=str(root), grid_file_sha256="sha256:" + grid_pin.removeprefix("sha256:"),
                    grid_document_sha256=envelope["sha256"], binding=binding, offer=receipt["region"],
                    terminal_endpoint_replay=grid["endpoint_objective_replay"], raw_authority=authority,
                    nuisance_model=grid["nuisance_model"],
                    counts={arm: {key: manifest["arms"][arm][key] for key in
                                  ("associated_points", "tracks", "satellites")} for arm in ARMS},
                    total_points=grid["evaluated_points"])
    return grid, evidence


def from_crossover(crossover, mode, grid_pin):
    cell = crossover["cells"][mode]
    worker = read(CROSS / mode / "crossover-worker.json", crossover["owner_row_source_sha256"][mode])
    if worker["waveform_reads"] != 0 or worker["receipt"]["terminal_sha256"] != cell["terminal_sha256"]:
        raise ValueError("Saved crossover does not bind the scored control")
    owners = {arm: cell["arms"][arm]["owner_sha256"] for arm in ARMS}
    if owners != {arm: canonical({row[0]: row[1] for row in worker["ordered_owners"][arm]}) for arm in ARMS}:
        raise ValueError("Crossover owner rows changed")
    return publication(CROSS / mode, worker["receipt"], cell["native_sha256"], owners,
                       cell["figures"]["position"][0], grid_pin, crossover["raw_metadata"]["raw_authority_sha256"])


def scientific_grid(grid):
    return {key: val for key, val in grid.items() if key not in ("binding", "elapsed_seconds")}


def basic_points(grid, arm):
    points = {tuple(row["latlon"]): row["scores"][arm] for row in grid["points"]
              if row["scores"][arm] is not None}
    origin = points[tuple(grid["endpoint_latlon"][arm])]
    return {position: score-origin for position, score in points.items()}


def local(point, grid):
    lat, lon = grid["region_center"]
    return ((point[1]-lon)*111.32*cos(radians(lat)), (point[0]-lat)*111.0)


def stencil(points, x, y, step, dx, dy):
    cells = {(i, j): points.get((x+i*step, y+j*step)) for i in (-1, 0, 1) for j in (-1, 0, 1)}
    if any(value is None for value in cells.values()):
        return None
    base = cells[0, 0]
    ee = (cells[1, 0] + cells[-1, 0] - 2*base)/step**2
    nn = (cells[0, 1] + cells[0, -1] - 2*base)/step**2
    en = (cells[1, 1] - cells[-1, 1] - cells[1, -1] + cells[-1, -1])/(4*step**2)
    spread = hypot(ee-nn, 2*en)
    eigen = [(ee+nn-spread)/2, (ee+nn+spread)/2]
    quadratic = (ee*dx**2 + 2*en*dx*dy + nn*dy**2)/2
    return dict(step_km=step, principal_curvatures=eigen,
                directional_curvature=None if dx == dy == 0 else 2*quadratic/(dx**2+dy**2),
                quadratic_delta=quadratic if eigen[0] > 0 else None)


def enclosing_cell(points, x, y, dx, dy, step, radius):
    i, j = dx/step, dy/step
    if max(abs(i), abs(j)) > radius:
        return None
    lower_i, lower_j = min(floor(i), radius-1), min(floor(j), radius-1)
    a, b = i-lower_i, j-lower_j
    lower = [(lower_i, lower_j), (lower_i+1, lower_j), (lower_i, lower_j+1), (lower_i+1, lower_j+1)]
    corners = [points.get((x+k*step, y+l*step)) for k, l in lower]
    if any(score is None for score in corners):
        return None
    base = points[x, y]
    deltas = [score-base for score in corners]
    weights = ((1-a)*(1-b), a*(1-b), (1-a)*b, a*b)
    return dict(corner_deltas=deltas, bilinear_delta=sum(d*w for d, w in zip(deltas, weights, strict=True)))


def cross_section(grid, other, arm, geographic_points):
    x, y = grid["endpoints"][arm]
    target = tuple(other["endpoint_latlon"][arm])
    u, v = (other["endpoints"][arm] if grid["region_center"] == other["region_center"]
            else local(target, grid))
    dx, dy = (u-x, v-y)
    points = {(row["east_km"], row["north_km"]): row["scores"][arm] for row in grid["points"]}
    radius = grid["local_size"] // 2
    step = grid["local_half_width_km"]/radius
    terms = [stencil(points, x, y, h, dx, dy) for h in (0.5, 1.0)]
    within_local = max(abs(dx), abs(dy)) <= grid["local_half_width_km"]
    exact = geographic_points.get(target)
    estimate = enclosing_cell(points, x, y, dx, dy, step, radius) if within_local and exact is None else None
    return dict(displacement_km=hypot(dx, dy), direction=None if dx == dy == 0 else [dx/hypot(dx, dy), dy/hypot(dx, dy)],
                sampled_minimum_delta=min(geographic_points.values()),
                opposing_endpoint_in_offer=max(abs(u), abs(v)) <= grid["box_width_km"]/2,
                opposing_endpoint_in_local_patch=within_local,
                exact_cross_delta=exact, local_cross=estimate, curvatures=terms)


def pair_geometry(first, second, arm):
    a, b = basic_points(first, arm), basic_points(second, arm)
    common = a.keys() & b.keys()
    best = min(common, key=lambda coord: (max(a[coord], b[coord]), coord), default=None)
    overlap = [coord for coord in common if max(a[coord], b[coord]) <= SCALE]
    return dict(shared_samples=len(common), shared_within_scale=len(overlap),
                best_common_deltas=None if best is None else [a[best], b[best]],
                first=cross_section(first, second, arm, a), second=cross_section(second, first, arm, b))


def evaluate():
    cross_pin = "c1fd49b28d0a90370ecf056ac7c0bf90b01af094a9377bfff5c38db39da7b7f3"
    cross = read(CROSS / "final-evidence.json", cross_pin)
    charted, charted_evidence = from_crossover(
        cross, "successor-installed", "32119840f162009193f554dcea821afb183bdac34182197c73cadd455a582a59")
    named, named_evidence = from_crossover(
        cross, "installed-installed", "3122710d132138dde4274176cd2073068c3f77abb881bc662af5ee00727b69b4")
    anchor_pin = "5e6ff5f8f26157d1bb797ccbedab74309387782290727d6aaeade9ea3ef12d9c"
    anchor_seal = read(ANCHORS / "prediction-seal.json", anchor_pin)
    plan = read(ANCHORS / "plan.json", anchor_seal["plan_sha256"])
    anchor_run = read(ANCHORS / "receipt.json", anchor_seal["receipt"])
    witness = read(ANCHORS / "substituted" / "exact-named-raw-witness.json", anchor_run["witness"])["evidence"]
    if (plan["installed_native_sha256"] != charted_evidence["binding"]["input_sha256"]
            or plan["original_archive"] != cross["raw_metadata"]["archive_sha256"]
            or anchor_run["plan_sha256"] != anchor_seal["plan_sha256"]
            or anchor_run["input"] != plan["change"]["derived_native_sha256"]):
        raise ValueError("The anchor intervention and charted control do not share original custody")
    anchor, anchor_evidence = publication(
        ANCHORS / "substituted", anchor_run["receipt"], anchor_run["input"],
        witness["owner_maps"], witness["images"]["position"]["sha256"],
        "059fcc896999ac287b89b4ab36c0bf6cf0a7d245579eecfc09e2562142e8db8e",
        cross["raw_metadata"]["raw_authority_sha256"])
    if (anchor_evidence["offer"] != charted_evidence["offer"]
            or witness["sidecars"]["grid"] != anchor_evidence["grid_document_sha256"]):
        raise ValueError("The anchor output differs from the frozen offer or witnessed grid")
    field_pin = "407765fa47754cc99556143888b286e88f4674ab21836d3f437ac8af4c2ca439"
    pair = read(FIELD / "pair.json", field_pin)
    attempt = FIELD / "successor" / f"attempt-{pair['generation']:06d}"
    recorded = read(attempt / "result.json", pair["attempt_result_sha256"]["successor"])
    field_evidence = recorded["evidence"]
    original_figure = next(row["sha256"] for row in field_evidence["artifacts"] if row["name"] == "position")
    original, original_evidence = publication(
        attempt / "publication", field_evidence["receipt"], recorded["native_sha256"],
        field_evidence["owners"], original_figure, "74a98f34aacc9e5ae104e075130328c2e20b20f35c13a96680c40e38591b277e",
        field_evidence["raw_authority"])
    result_pin = "45ba5b1634f80a4b0f052f89281e44ba16eb4186fc70b79763336fd79120de2d"
    result = read(TRANSLATED / "result.json", result_pin)
    translation = read(TRANSLATED / "prediction-seal.json", result["seal_sha256"])
    east_record = result["alternatives"]["east"]
    (east_grid,) = (key for key in translation if key.startswith("east/") and key.endswith("/position-grid.json"))
    east, east_evidence = publication(TRANSLATED / "east", east_record["receipt"], result["source"]["native_sha256"],
                                      east_record["owner_digests"], east_record["figures"]["position"]["encoded_sha256"],
                                      translation[east_grid], field_evidence["raw_authority"])
    if (not pair["verified_pair"] or not pair["same_lease"] or original_evidence["binding"]["owner_sha256"]
            != east_evidence["binding"]["owner_sha256"] or original_evidence["binding"]["input_sha256"]
            != east_evidence["binding"]["input_sha256"] or east_record["archive_digest"]
            != recorded["raw_identity"]["archive_sha256"] or result["source"]["original_offer_sha256"]
            != recorded["raw_identity"]["region_sha256"].removeprefix("sha256:")
            or field_evidence["scientific_digests"]["grid"] != canonical(scientific_grid(original))
            or east != east_record["grid"]):
        raise ValueError("The translated offer comparison does not bind the original field packet")
    return dict(
        schema="ds30-archived-position-direction-v1", nominal_scale=SCALE,
        ds30_0049=dict(sources=dict(crossover=cross_pin, anchor_prediction=anchor_pin, anchor_witness=anchor_run["witness"]),
                       installed_named=named_evidence, installed_charted=charted_evidence, extra_anchors=anchor_evidence,
                       installed_grid_science_exact=scientific_grid(named) == scientific_grid(charted),
                       arms={arm: pair_geometry(charted, anchor, arm) for arm in ARMS}),
        ds30_0086=dict(sources=dict(field_pair=field_pin, translated_result=result_pin, prediction=result["seal_sha256"]),
                       original=original_evidence, east_containing=east_evidence,
                       arms={arm: pair_geometry(original, east, arm) for arm in ARMS}),
        survey_coordinates_read=0, waveform_reads=0, orbit_body_reads=0, solver_workers=0)


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2, allow_nan=False))
