"""Audit the saved DS30-0397 corner-phase support recovery."""

import argparse
import ast
from dataclasses import dataclass
from hashlib import sha256
import json
from math import ceil, isfinite
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
PAYLOAD = Path("/opt/leo-algo08/algo08v3/payload")
VARIANTS = Path("tools/pipeline_eval/variants")
CASE = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124/cases/DS30-0397")
PAIR = "e67d43e06027c8d38daa3bf794a48aba108197b353ce5fee9e69d02b01b05f3d"
REQUEST = "4141acf7ff8e49d621c2f194d34bf4a3daa6bbcf9077ba3668f3b9b6ba2a88a8"
TRACE = "2b2c08ae3926f1f20fce12cf4bdce96e36dfc7ef38b7bca25b53800529270442"
LIVE = "9e9674b3a5550a43463e40364ad6d0946b2f3d7c824801d0b2a83979c11ec03e"
WITNESS = "bee40f5e3ef4ff4cf6925be121e916775092ff37b90f3c0a057db80c2224c9af"
REFERENCE = "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5"
OLD_CORNER = "37e894e5ff4a9d78356ccd876b5538fcdcf76d9a3b2faf99dccaead31d963464"
REPAIRED_CORNER = "14be68cd3af6906dbe0df64841e6a756e93caf234ad11b553bd1d8937fc2e18f"
PROJECTOR = "873b856dd081269234f9af8415e7c1abaa00afb27c991dad43ab24e0764dd668"
SPARSE = "e381e0807e47a10091ffd9c9d1d8c0d43aa531a5e4c81acda53ddbfa922ef021"
BUILD = "30cc3b044040f2519677d67abfde731f83693612744d2236d1ba71bb5a31e4ab"
OUTSIDE = "orbit phase interpolation never extrapolates"
ARMS = ("c0", "fitted_c")


def digest(body):
    return "sha256:" + sha256(body).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()


def checked(body, pin):
    if digest(body) != "sha256:" + pin.removeprefix("sha256:"):
        raise ValueError("Sealed DS30-0397 evidence differs from its reviewed digest")
    return body


def document(path, pin=None):
    if path.resolve(strict=True) != path:
        raise ValueError("Use a direct recorded publication path")
    raw = path.read_bytes()
    return json.loads(raw if pin is None else checked(raw, pin))


def git_blob(revision, path):
    return subprocess.check_output(["git", "-c", f"safe.directory={ROOT}", "-C", str(ROOT), "show", f"{revision}:{path}"])


def timing(native):
    anchor, source = (native[x] for x in ("clock_anchor", "source"))
    before, after = (anchor[name]["realtime_ns"] for name in ("before", "after"))
    times = [(row["valid_start_counter"] - anchor["sample_counter"]) / source["sample_rate_hz"]
             + source["probe_ms"] * .0005 for row in source["probes"]
             if any(factor["passed_fractional_margin_gate"] is True for factor in row["candidates"])]
    if not times or min(times) < 0 or after < before:
        raise ValueError("Malformed sealed probe chronology")
    return dict(cutoff_ns=before, after_ns=after, origin_ns=(before + after)//2,
                winning_range_s=[min(times), max(times)], native_probes=len(source["probes"]),
                signed_winners=len(times), capture_duration_s=(native["last_sample_counter"]-anchor["sample_counter"])
                / source["sample_rate_hz"])


def left_extension(added, latest_possible_track_s):
    if not added or added != list(range(int(added[0]), -17)) or added[0] < -31:
        raise ValueError("Expected a strictly left, contiguous phase-support extension")
    return dict(nominal_right_s_upper=ceil(max(300, latest_possible_track_s)) + 17,
                lower_stencil_query_s_bin=[added[0], added[0]+1],
                nominal_left_s=-17, effective_left_s=added[0])


def selected_definitions(body, names, variables):
    tree = ast.parse(body)
    selected = [node for node in tree.body if getattr(node, "name", None) in names]
    if {node.name for node in selected} != set(names):
        raise ValueError("Pinned demonstration definitions are incomplete")
    exec(compile(ast.Module(body=selected, type_ignores=[]), "<pinned phase support>", "exec"), variables)
    return variables


def demonstration(projector, repaired):
    """Exercise the original checked stencil on synthetic states, outside any fit."""
    import numpy as np

    scope = selected_definitions(projector, ("Stencil", "prepare"), dict(np=np, dataclass=dataclass))
    guard = selected_definitions(repaired, ("support_knots", "splice_bank"),
                                 dict(np=np, PHASE_LIMIT_S=30., DERIVATIVE_STEP_S=.05, NOMINAL_PAD_S=17.))
    nominal, times, phases = np.arange(-17., 318.), np.array([.01]), np.array([-25.5])

    def states(t):
        return np.broadcast_to(t[None, :, None], (1, len(t), 3)).copy(), np.ones((1, len(t), 3))

    p, v = states(nominal)
    bank = dict(time_s=nominal, position_km=p, velocity_km_s=v)
    try:
        scope["prepare"](bank, times, phases)
    except ValueError as error:
        if str(error) != OUTSIDE:
            raise
    else:
        raise ValueError("The installed kernel unexpectedly extrapolated the demonstration")
    extra = guard["support_knots"](nominal, times, phases, derivative_step_s=.05)
    augmented = guard["splice_bank"](bank, extra, *states(extra))
    stencil = scope["prepare"](augmented, times, phases)
    requested = times + (phases[:, None] + np.array([0., .05, -.05]))[..., None]
    grid = augmented["time_s"]
    observed = grid[stencil.index] + stencil.fraction * (grid[stencil.index+1]-grid[stencil.index])
    if not np.array_equal(requested, observed) or not np.array_equal(p, augmented["position_km"][:, len(extra):]):
        raise ValueError("Extending support changed the reconstructed query or its prior bank")
    return dict(synthetic_only=True, strict_nominal_rejection=True, added_knots_s=extra.tolist(),
                exact_query_reconstruction=True, example_queries_s=requested.ravel().tolist())


def audit():
    from tools.pipeline_eval.scoring import distance_km

    pair = document(CASE / "pair.json", PAIR)
    request = document(CASE / "input.json", REQUEST)
    authority = document(CASE / "authority.json", pair["authority_sha256"])
    stock, candidate = (CASE / method / "attempt-000001" for method in ("installed", "successor"))
    original = document(stock / "result.json", pair["attempt_result_sha256"]["installed"])
    result = document(candidate / "result.json", pair["attempt_result_sha256"]["successor"])
    if (not pair["verified_pair"] or pair["generation"] != 1
            or pair["actual_order"] != ["installed", "successor"] or authority != request["authority"]
            or original["raw_identity"] != authority or result["raw_identity"] != authority
            or original["outcome"] != "solver_failed" or result["outcome"] != "complete"):
        raise ValueError("Expected matched original DS30-0397 completion and failure receipts")
    trace = checked((stock / "stderr.log").read_bytes(), TRACE).decode()
    if (trace != original["evidence"]["failure_observation"]["stderr"]
            or trace.count("ValueError: " + OUTSIDE) != 2 or trace.count("algo08_sparse_rank_projection.py") != 2
            or 'in attempt\n' not in trace or 'in explore\n' not in trace
            or list((stock / "publication").glob("fast-scan-automatic-work/*/terminal.json"))):
        raise ValueError("Expected strict rejection during stock rank and its retry before any terminal")
    pub = candidate / "publication"
    acquisition = document(pub / "legacy-original-acquisition.json", LIVE)
    witness = document(pub / "exact-named-raw-witness.json", WITNESS)
    audit = acquisition["acceleration"]["solver"]
    scope, = audit["in_flight"]
    decision = witness["ports"]["history_risk"]["choice"]
    if (audit["original_restart"] or scope["corner_projections_extended"] != 4 or scope["sgp4_calls"] != 4
            or not (scope["new_state_count"] == scope["sgp4_state_count"] == 1116)
            or decision["route"] != "lean" or decision["reason"] != "healthy_samples"
            or witness["ports"]["history_risk"]["inference_calls"] != 1):
        raise ValueError("The verified result followed a different support or inference path")
    native = {}
    clocks = {}
    for base, role, job in ((stock, "installed", original), (candidate, "successor", result)):
        packet, = (base / "publication").glob("fast-scan-automatic-work/*/detections.json")
        native[role] = document(packet, job["native_sha256"])
        clocks[role] = timing(native[role])
    if (native["installed"]["clock_anchor"] != native["successor"]["clock_anchor"]
            or not (clocks["successor"]["cutoff_ns"] == decision["census"]["cutoff_utc_ns"] == authority["causal_cutoff_utc_ns"])
            or clocks["successor"]["origin_ns"] != decision["census"]["origin_utc_ns"]):
        raise ValueError("The actual causal origin does not match the signed clocks")
    if any(doc["source"]["raw_recording_authority_digest"] != authority["raw_authority_sha256"]
           or doc["source"]["input_manifest_sha256"] != authority["inventory_sha256"] for doc in native.values()):
        raise ValueError("The actual detector packets differ from their signed physical source")
    spans = {method: left_extension(scope["added_knots_s"], clock["winning_range_s"][1])
             for method, clock in clocks.items()}
    if spans["successor"]["nominal_right_s_upper"] != 317:
        raise ValueError("Successor winning timestamps do not fit the fixed minimum bank")
    archive = witness["ports"]["verified_tle"]
    timestamps = sorted(int(name.split("-")[0]) for name in archive)
    portable, = witness["ports"]["portable"]["transfers"]
    if (not timestamps or timestamps[-1] >= authority["causal_cutoff_utc_ns"]
            or witness["solver_recipe"]["archive_sha256"] != authority["archive_sha256"]
            or portable["counts"]["sidecar_hit_bodies"]):
        raise ValueError("Catalogued provenance differs from the capture-time cold archive")
    receipt = result["evidence"]["receipt"]
    marker = document(pub / "algo08v3-successor-release.json")
    build = document(CASE.parents[1] / "frozen-build/build.json", BUILD)
    if (marker["build_sha256"] != "sha256:" + BUILD or marker["authority_sha256"] != pair["authority_sha256"]
            or marker["receipt"] != receipt or marker["terminal_sha256"] != receipt["terminal_sha256"]
            or build["sources"][str(VARIANTS / "v5_orbit_domain.py")] != REPAIRED_CORNER):
        raise ValueError("The live support audit does not bind the frozen release marker")
    standard = pub / "fast-scan-standard-v2" / receipt["run_id"] / "final-error-v7"
    terminal = document(pub / "fast-scan-automatic-work" / receipt["run_id"] / "terminal.json", receipt["terminal_sha256"])
    manifest = document(standard / "manifest.json")
    grid = document(standard / "position-grid.json")
    path = document(standard / "position-path.json")
    owners = {arm: digest(encoded({row[0]: row[1] for row in witness["evidence"]["owner_rows"][arm]})) for arm in ARMS}
    binding = dict(terminal_sha256=receipt["terminal_sha256"], owner_sha256=owners, input_sha256=result["native_sha256"])
    position_png, = [item["sha256"] for item in manifest["artifacts"] if item["name"] == "position"]
    binding["position_png_sha256"] = position_png
    for name, envelope in (("grid", grid), ("path", path)):
        doc = envelope["document"]
        scientific = {key: value for key, value in doc.items() if key not in ("binding", "elapsed_seconds")}
        if (digest(encoded(doc)) != envelope["sha256"]
                or digest(encoded(scientific)) != result["evidence"]["scientific_digests"][name]
                or any(doc["binding"][key] != value for key, value in binding.items())):
            raise ValueError("The path or grid is detached from its signed terminal and output")
    grid = grid["document"]
    if (any(not isfinite(point["scores"][arm]) for point in grid["points"] for arm in ARMS)
            or not grid["matched_c_grid"] or not grid["complete"]
            or not (len(grid["points"]) == grid["evaluated_points"] == grid["planned_points"] == 179)
            or terminal["decision"] != "ok" or terminal["orbit_policy"] != "orbit_support"
            or not (len(manifest["artifacts"]) == audit["png_native"]["native"] == 8)):
        raise ValueError("The checked paired-calibration publication is incomplete")
    ref = json.loads(checked(git_blob("2d0ad2dfd", "reports/2026_11_21_ds30_full/reference-audit.json"), REFERENCE))
    surveyed, = (row for row in ref["cases"] if row["dataset_label"] == CASE.name
                 and row["authority_eligible"] and row["sealed_metadata_digests_verified"])
    reference = [surveyed["reference"][key] for key in ("latitude_deg", "longitude_deg")]
    arms = {}
    for arm in ARMS:
        product = manifest["arms"][arm]
        loc = terminal["arms"][arm]["latlon"]
        if (loc != product["endpoint_latlon"] or loc != grid["endpoint_latlon"][arm]
                or owners[arm] != product["owner_sha256"] or grid["endpoint_objective_replay"][arm] != 0):
            raise ValueError("The published arm differs from the standard numerical grid")
        arms[arm] = dict(error_km=distance_km(loc, reference), conditional_rf_rms_hz=terminal["arms"][arm]["rf_rms_hz"],
                         all_owner_rf_rms_hz=product["residual_rms_hz"], owners=product["associated_points"],
                         grid_minimum_index=min(range(179), key=lambda i: grid["points"][i]["scores"][arm]))
    old = checked((PAYLOAD / VARIANTS / "v5_orbit_domain.py").read_bytes(), OLD_CORNER)
    repaired = checked(git_blob("de7873faa", VARIANTS / "v5_orbit_domain.py"), REPAIRED_CORNER)
    projector = checked((PAYLOAD / VARIANTS / "orbit_projector.py").read_bytes(), PROJECTOR)
    sparse = checked((PAYLOAD / VARIANTS / "algo08_sparse_rank_projection.py").read_bytes(), SPARSE)
    if (b'patch.object(scan.ScanLikelihood, "shifted", shifted)' not in old
            or b'patch.object(context, "shifted", shifted)' not in repaired
            or b'patch.object(scan, "shifted", shifted)' not in sparse):
        raise ValueError("The original and repaired dispatch bindings differ from the studied implementation")
    return dict(case=CASE.name, source_pins=dict(stock_corner=OLD_CORNER, repaired_corner=REPAIRED_CORNER, build=BUILD,
                                                sparse_rank=SPARSE, projector=PROJECTOR, reference=REFERENCE),
                authority=authority, observed_support=scope, old_retry_succeeded=False, clocks=clocks,
                successor_bounds=spans["successor"], stock_nominal_right_s_upper=spans["installed"]["nominal_right_s_upper"],
                archive=dict(verified_snapshot_names=len(archive), verified_bytes=sum(archive.values()),
                             verification=witness["ports"]["portable"]["attempts"][0], earliest_ns=timestamps[0],
                             latest_ns=timestamps[-1], portable_body_hits=portable["counts"]["sidecar_hit_bodies"]),
                both_arms=arms, grid=audit["grid"], waveforms_opened=0, tle_bodies_opened=0, solver_runs=0,
                timings=dict(installed_failed_wall_s=original["elapsed_s"], successor_verified_wall_s=result["elapsed_s"]),
                demonstration=demonstration(projector, repaired))


def denied(event, args):
    if event == "open" and isinstance(args[0], (str, bytes)):
        path = Path(os.fsdecode(args[0])).absolute()
        if path.is_relative_to("/srv/bulk") or path.is_relative_to("/mnt/qnap01") or path.name.endswith(".ci16.zst"):
            raise ValueError("The DS30-0397 audit cannot open original data")


if __name__ == "__main__":
    sys.path.append(str(RELEASE / "src"))
    sys.addaudithook(denied)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    with parser.parse_args().output.open("xb") as stream:
        stream.write(encoded(audit()) + b"\n")
