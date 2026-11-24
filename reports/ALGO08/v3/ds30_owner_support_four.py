"""Verify the four complete DS30 pairs and reduce their sealed native support."""

import argparse
from collections import defaultdict
from gzip import decompress
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from statistics import median
import subprocess
import sys
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
LEDGER = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124")
PLAN_PIN = "9deecea6ce5237d01d277370f57b2666f3b84ab96bba72fe0b668c7701d0fc99"
REFERENCE_PIN = "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5"
CROSSOVER_PIN = "c1fd49b28d0a90370ecf056ac7c0bf90b01af094a9377bfff5c38db39da7b7f3"
TRACK_SOURCE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/src/leo/analysis/localization_v3/tracks.py")
TRACK_PIN = "db44a947666c2dd7946534f69bf6af72ced63c8af553bb1b089c0fba3d5b7b6f"
PAIRS = {
    "DS30-0019": ("5a5307be75290e5bed14cb42380e47cd9679030a327fdcce2fa1fd2f3c910719",
                  "3f498214c7da8f75a4c88268324bce4a4e4248e3b54146511a724668aa8285f8"),
    "DS30-0049": ("7514497ea681194487e8d85aecf2d739e996abf2b90566d446f81fe38875c36b",
                  "5d338f12159148772b9e5ec31521e55c7867e4fe7c6fd65f28594e69c0ae3b4e"),
    "DS30-0178": ("683cff9ba870beb7f3889566cc94c12c5b9afd1762daa1ad63dc0cacb896f8f1",
                  "55b740527f502b37f9d511853e6004645b6587f11d50a9ce62361e61055a686d"),
    "DS30-0274": ("7e2e78392701820e6a2667adc6ba6f2dfbfec1f7eb1ee5017d50a775b773c28c",
                  "d244488797c86fc24bff964d456e75e6cec1a570b348c04ef1e4a754e6ac097c"),
}
METHODS = ("installed", "successor")
ARMS = ("c0", "fitted_c")


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()


def digest(data):
    return "sha256:" + sha256(data).hexdigest()


def checked(data, pin):
    if digest(data) != "sha256:" + pin.removeprefix("sha256:"):
        raise ValueError("A frozen receipt or source digest changed")
    return data


def document(path, pin=None):
    if path.resolve(strict=True) != path:
        raise ValueError(f"Expected direct receipt path: {path}")
    data = path.read_bytes()
    return json.loads(checked(data, pin) if pin is not None else data)


def git_source(rev, path):
    return subprocess.check_output(["git", "-c", f"safe.directory={ROOT}", "-C", str(ROOT), "show", f"{rev}:{path}"])


def bounds(population, subset, sample):
    """Sharp overlap bounds for a fixed-size unknown subset of a verified universe."""
    if min(subset, sample) < 0 or max(subset, sample) > population:
        raise ValueError("Infeasible owner universe")
    return [max(0, sample - population + subset), min(sample, subset)]


def peaks(native):
    lanes = {}
    session = native["source"]["session_id"]
    for probe in native["source"]["probes"]:
        rx, ch, start = (probe[k] for k in ("receiver_id", "channel", "valid_start_counter"))
        if rx not in (0, 1) or ch not in range(1, 9):
            raise ValueError("Unexpected original receiver or channel")
        key = digest(f"{session}:{rx}:{start}".encode())
        if key in lanes:
            raise ValueError("Repeated signed receiver opportunity")
        eligible = (row for row in probe["candidates"] if row["passed_fractional_margin_gate"] is True)
        best = max(eligible, key=lambda row: (row["fractional_margin"], -row["candidate_rank"]), default=None)
        cfo = None if best is None else best["fractional_tracking_cfo_hz"]
        if cfo is not None and not isfinite(cfo):
            raise ValueError("Accepted CFO must be finite")
        lanes[key] = SimpleNamespace(stream=f"RX{rx + 1}/CH{ch}", signature=(rx, ch, probe["actual_rf_hz"], probe["edge"], start), cfo=cfo)
    return lanes


def owner_map(rows, trusted, own_lanes):
    found = {key: (norad, role) for key, norad, role in rows}
    if (len(found) != len(rows) or len(found) != trusted["associated_points"]
            or not found.keys() <= own_lanes or digest(encoded({k: v[0] for k, v in found.items()})) != trusted["owner_sha256"]):
        raise ValueError("Owner rows do not reproduce published ownership and accepted native support")
    return found


def residuals(before, after, ids):
    return [after[key].cfo - before[key].cfo for key in ids]


def offsets(values):
    absolute = sorted(map(abs, values))
    return dict(n=len(values), median_abs_hz=median(absolute) if absolute else None,
                median_signed_hz=median(values) if values else None,
                exact_cfo=absolute.count(0))


def compare_group(before, after, ids, stock_support, successor_support, installed, successor, installed_count):
    if any(before[k].signature != after[k].signature for k in ids):
        raise ValueError("Native RF opportunity changed")
    a, b = stock_support & ids, successor_support & ids
    result = dict(opportunities=len(ids), installed_accepted=len(a), successor_accepted=len(b),
                  accepted_both=len(a & b), lost_accepted=len(a-b), gained_accepted=len(b-a),
                  accepted_both_cfo=offsets(residuals(before, after, a & b)))
    new = successor.keys() & ids
    pool = new & a
    moves = residuals(before, after, pool)
    owner = dict(successor=len(new), successor_owner_without_installed_factor=len(new-pool),
                 successor_owner_also_installed_accepted=offsets(moves))
    if installed is not None:
        old = installed.keys() & ids
        shared = old & new
        owner.update(availability="exact", installed=len(old), matched=len(shared), lost=len(old-new),
                     gained=len(new-old), retained_cfo=offsets(residuals(before, after, shared)),
                     retained_changed_norad=sum(installed[key][0] != successor[key][0] for key in shared),
                     retained_changed_role=sum(installed[key][1] != successor[key][1] for key in shared))
    else:
        size = len(stock_support)
        shared = bounds(size, len(pool), installed_count)
        absolute = sorted(map(abs, moves))
        required = shared[0]
        owner.update(availability="membership_unavailable", installed=bounds(size, len(a), installed_count),
                     matched=shared, lost=bounds(size, len(a-new), installed_count),
                     gained=[len(new)-shared[1], len(new)-shared[0]],
                     retained_median_abs_hz_bounds=None if not required else
                     [median(absolute[:required]), median(absolute[-required:])])
    return result | dict(owners=owner)


def raw_publication(ledger, case, method, pair, request, row, plan, reference):
    directory = ledger / "cases" / case / method / f"attempt-{pair['generation']:06d}"
    result = document(directory / "result.json", pair["attempt_result_sha256"][method])
    up = directory / "publication"
    receipt = result["evidence"]["receipt"]
    if (result["outcome"] != receipt["decision"] or result["outcome"] != "complete"
            or result["raw_identity"] != request["authority"] or result["generation"] != pair["generation"]
            or row["attempt_result_sha256"] != pair["attempt_result_sha256"][method]
            or row["attempt"] != str((directory / "result.json").relative_to(ledger))
            or row["generation"] != result["generation"] or row["actual_order"] != pair["actual_order"]
            or row["elapsed_s"] != result["elapsed_s"] or not row["verified_pair"]):
        raise ValueError("Independent campaign export and sealed publication disagree")
    native_path, = (up / "fast-scan-automatic-work").glob("*/detections.json")
    standard = up / "fast-scan-standard-v2" / receipt["run_id"] / "final-error-v7"
    native = document(native_path, result["native_sha256"])
    terminal = document(up / "fast-scan-automatic-work" / receipt["run_id"] / "terminal.json", row["terminal_sha256"])
    manifest = document(standard / "manifest.json")
    authority = request["authority"]
    inventory = document(up / "fast-scan-inputs" / (authority["session_id"] + ".json"), authority["inventory_sha256"])
    source, provenance = (native[name] for name in ("source", "provenance"))
    detector_id = provenance["detector_sha256"]
    if method == "installed":
        release = document(up / "algo08v3-release.json")
        stock_build = plan["stock"]
        calibrated_build = stock_build["frozen_specification"]
        if not all(release[key] == stock_build[key] for key in stock_build) or detector_id != "sha256:" + stock_build["detector_sha256"]:
            raise ValueError("Installed science runtime or detector does not match the frozen experiment")
    else:
        release = document(up / "algo08v3-successor-release.json")
        calibrated_build = plan["candidate"]["sha256"]
        if (release["build_sha256"] != calibrated_build or release["authority_sha256"] != pair["authority_sha256"]
                or release["receipt"] != receipt):
            raise ValueError("Successor science runtime or signed input differs from the frozen experiment")
    if (source["session_id"] != authority["session_id"] or len(inventory["segments"]) != reference["segments"]
            or source["input_manifest_sha256"] != authority["inventory_sha256"]
            or source["raw_recording_authority_digest"] != authority["raw_authority_sha256"]
            or row["raw_authority_sha256"] != authority["raw_authority_sha256"]
            or row["authority_sha256"] != pair["authority_sha256"] or row["build_sha256"] != calibrated_build
            or provenance["window_count"] != authority["window_count"]
            or provenance["processed_windows"] != request["expected_admitted"]
            or len(source["probes"]) != request["expected_admitted"] * 2
            or native["clock_anchor"]["before"]["realtime_ns"] != authority["causal_cutoff_utc_ns"]
            or terminal["native_sha256"] != result["native_sha256"] or manifest["input_sha256"] != result["native_sha256"]
            or manifest["terminal_sha256"] != row["terminal_sha256"]
            or terminal["region"] != request["offered_region"]
            or terminal["arms"] != row["arms"] or terminal["arms"] != result["evidence"]["arms"]
            or source["analysis_manifest_sha256"] != digest(encoded(
                ["cancellation", source["raw_recording_authority_digest"], detector_id[7:], source["probes"]]))):
        raise ValueError("Survey identity, verified raw input, ledger, or scientific output disagrees")
    return native, terminal, manifest, up, result


def compare_case(ledger, case, rows, plan, reference, prior):
    from tools.pipeline_eval.scoring import distance_km

    folder = ledger / "cases" / case
    pair = document(folder / "pair.json", PAIRS[case][0])
    request = document(folder / "input.json", PAIRS[case][1])
    authority = document(folder / "authority.json", pair["authority_sha256"])
    if not pair["verified_pair"] or request["authority"] != authority or request["authority_sha256"] != pair["authority_sha256"]:
        raise ValueError("Case is outside the frozen four-pair authority")
    inputs = {method: raw_publication(ledger, case, method, pair, request, rows[case, method], plan, reference)
              for method in METHODS}
    before, after = (peaks(inputs[method][0]) for method in METHODS)
    stock, alternate = (inputs[method][0] for method in METHODS)
    if (before.keys() != after.keys() or stock["delivery_clocks"] != alternate["delivery_clocks"]
            or stock["clock_anchor"] != alternate["clock_anchor"]
            or stock["provenance"]["excluded_windows"] != alternate["provenance"]["excluded_windows"]):
        raise ValueError("The physical aperture opportunities were altered")
    a, b = ({k for k, row in lanes.items() if row.cfo is not None} for lanes in (before, after))
    groups = defaultdict(set)
    for key, item in before.items():
        groups[item.stream].add(key)
    groups["all"] = set(before)
    successor_witness = document(inputs["successor"][3] / "exact-named-raw-witness.json")
    charted_receiver = document(inputs["successor"][3] / "unified-short-bootstrap.json")
    if charted_receiver["native_sha256"] != inputs["successor"][4]["native_sha256"]:
        raise ValueError("Receiver selector belongs to a different scientific publication")
    if prior is not None and any(prior["cells"][f"{m}-{m}"]["terminal_sha256"] != rows[case, m]["terminal_sha256"]
                                 or prior["cells"][f"{m}-{m}"]["native_sha256"] != inputs[m][4]["native_sha256"]
                                 for m in METHODS):
        raise ValueError("The exact stock owner proof belongs to another original pair")
    response = {}
    for arm in ARMS:
        manifests = {m: inputs[m][2]["arms"][arm] for m in METHODS}
        for method in METHODS:
            info, published = inputs[method][4]["evidence"]["owners"][arm], manifests[method]
            if info != published["owner_sha256"] or published["endpoint_latlon"] != inputs[method][1]["arms"][arm]["latlon"]:
                raise ValueError("The terminal and official owner totals are unbound")
        new_owners = owner_map(successor_witness["evidence"]["owner_rows"][arm], manifests["successor"], b)
        old_owners = None if prior is None else owner_map(
            prior["ordered_owner_rows"]["installed-installed"][arm], manifests["installed"], a)
        count = manifests["installed"]["associated_points"]
        support = {stream: compare_group(before, after, ids, a, b, old_owners, new_owners, count)
                   for stream, ids in sorted(groups.items())}
        terminal = {m: inputs[m][1]["arms"][arm] for m in METHODS}
        truth = [reference["reference"][axis] for axis in ("latitude_deg", "longitude_deg")]
        error = {m: distance_km(terminal[m]["latlon"], truth) for m in METHODS}
        response[arm] = dict(error_km=error, error_change_km=error["successor"]-error["installed"],
                             endpoint_displacement_km=distance_km(*(terminal[m]["latlon"] for m in METHODS)),
                             terminal_rf_rms_hz={m: terminal[m]["rf_rms_hz"] for m in METHODS}, streams=support)
    return dict(generation=pair["generation"], same_lease=pair["same_lease"], authority_sha256=pair["authority_sha256"],
                attempt_result_sha256=pair["attempt_result_sha256"],
                native_sha256={m: inputs[m][4]["native_sha256"] for m in METHODS}, arms=response,
                acquired_visits=authority["window_count"], admitted_visits=request["expected_admitted"],
                elapsed_s={m: inputs[m][4]["elapsed_s"] for m in METHODS},
                held_route=charted_receiver["held_anchor_route"]["choice"]["route"],
                refinement_calls=charted_receiver["held_anchor_route"]["refinement_calls"])


def audited(ledger):
    checked(TRACK_SOURCE.read_bytes(), TRACK_PIN)
    plan = document(ledger / "plan.json", PLAN_PIN)
    checked((ledger / "offer.json").read_bytes(), plan["offered_region_sha256"])
    refs = json.loads(checked(git_source("2d0ad2dfd", "reports/2026_11_21_ds30_full/reference-audit.json"), REFERENCE_PIN))
    refs = {r["dataset_label"]: r for r in refs["cases"]
            if r["dataset_label"] in PAIRS and r["authority_eligible"] and r["sealed_metadata_digests_verified"]}
    prior = json.loads(checked(decompress(git_source("5dad70d7d", "reports/ALGO08/v3/measurements/ds30-0049-saved-crossover.json.gz")),
                               CROSSOVER_PIN))
    with (ledger / "rows.jsonl").open() as stream:
        rows = [row for line in stream if (row := json.loads(line))["case"] in PAIRS]
    by_id = {(row["case"], row["algorithm"]): row for row in rows}
    if len(rows) != 8 or set(by_id) != {(case, m) for case in PAIRS for m in METHODS}:
        raise ValueError("Campaign export no longer uniquely identifies the enrolled arms")
    return dict(schema="ds30-four-positive-pair-owner-audit-v1", reference_sha256=REFERENCE_PIN,
                published_pair_pins=PAIRS, original_owner_proof_sha256=CROSSOVER_PIN,
                plan_sha256=PLAN_PIN, released_winning_observations_sha256=TRACK_PIN,
                cases={case: compare_case(ledger, case, by_id, plan, refs[case], prior if case == "DS30-0049" else None)
                       for case in PAIRS},
                waveform_reads=0, catalogue_body_reads=0, scientific_worker_runs=0)


def deny_original(event, args):
    if event == "open" and isinstance(args[0], (str, bytes)):
        name = Path(args[0]).absolute() if isinstance(args[0], str) else Path(args[0].decode()).absolute()
        if name.is_relative_to("/srv/bulk") or name.is_relative_to("/mnt/qnap01") or name.name.endswith(".ci16.zst"):
            raise ValueError("No original capture, waveform, or archive-body reads in the receipt audit")


if __name__ == "__main__":
    sys.addaudithook(deny_original)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = audited(LEDGER)
    with args.output.open("xb") as stream:
        stream.write(encoded(result) + b"\n")
