"""Compare the active-face gate with the frozen face-loss readout on sealed metadata."""

import argparse
import gzip
import json
from collections import Counter
from math import cos, radians
from pathlib import Path

from leo.contracts.digests import canonical_digest
from leo.storage.fast_scan import FastScanStore
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
from reports.ALGO08.v3.ds30_centered_error import (
    CAMPAIGN,
    EXPORT,
    EXPORT_SEAL,
    INITIAL,
    OVERLAY,
    PINS,
    PLAN,
    PROSPECTIVE,
    RELOCATION,
    checked,
    frozen_order,
    roster,
    verified_capture,
)
from reports.ALGO08.v3.grid_face_abstention_trial import load_publication
from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km
from tools.pipeline_eval.scoring import ARMS, distance_km
from tools.pipeline_eval.variants.experimental import exact_face_constraint as gate
from tools.pipeline_eval.variants.experimental import grid_face_abstention as loss_gate

HERE = Path(__file__).resolve().parent
MEASUREMENTS = HERE / "measurements"
HISTORIC = "sha256:b25d4903025271effe2c4b9764ba166694adfcc6aed07a8d8c19ff53c526d2f4"
SOUTH_1KM = "sha256:b4d218026c8eb64a4d031c1403efbab5eeed2b5e9aba5554a3117541fbad8fb8"
NORTH_NAMED = "sha256:f811b67eb0c90cdf8f64090a7a42232d161af4cccf12a065536eb618e9dcc536"
TRANSLATION = "sha256:609d520ebe9ea6bff3de85892ab1cb5d59358c8fc485354fb494eaf1ab6e52a1"
PUBLIC_KEY = "sha256:0bda865a20e62852220a9ab8df63895a449bf203a2deb5370920dc3ce215d37d"
NORTH_INSIDE = Path("/tmp/leo-algo08v2-2x-bench/exact-curved-lookahead-north-inside")
NORTH_PAIR = "sha256:9bf5dc4e3ef1e2df17f8d8184bca74f2ce9559a1e154401b9f6330f8e97feaeb"
RECORDING = {"north": "0abe7b4514be674d9f5388e3", "south": "6bd1f26bfa0bedfcf3f100f8"}
FIELD_TRANSLATION = "DS30-0086"


def pinned_json(path, pin):
    raw = checked(path, pin)
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def position_readout(status, width, endpoints, face_loss):
    exact = gate.diagnose(status, width, endpoints)
    loss = {"state": face_loss["state"], "outcome": status}
    if status == "complete" and face_loss["state"] == "assessable":
        loss["outcome"] = "withheld" if face_loss["paired_abstain"] else status
        loss["gaps"] = {arm: face_loss["arms"][arm]["gap"] for arm in ARMS}
    return {"original": status, "exact": exact, "face_loss": loss}


def from_documents(terminal, path, grid, receipt):
    """Bind the exact selected endpoint from the final path and terminal."""
    if canonical_digest(terminal) != receipt["terminal_sha256"]:
        raise ValueError("Saved position terminal does not match its receipt")
    offer = terminal["region"]
    width = offer["width_km"]
    if offer != receipt["region"] or terminal["decision"] != "ok":
        raise ValueError("Expected a complete signed fit in its original offered square")
    if (
        path["binding"]["terminal_sha256"] != receipt["terminal_sha256"]
        or path["binding"]["input_sha256"] != terminal["native_sha256"]
        or path["region_center"] != offer["center"] or path["box_width_km"] != width
    ):
        raise ValueError("Selected path differs from the original terminal or offer")
    endpoints = {arm: path["stages"][-1]["arms"][arm]["endpoint"] for arm in ARMS}
    loss = {"state": "unassessable"}
    if grid is not None:
        if (
            grid["binding"] != path["binding"] or grid["endpoints"] != endpoints
            or grid["region_center"] != offer["center"] or grid["box_width_km"] != width
            or grid["endpoint_latlon"] != {
                arm: terminal["arms"][arm]["latlon"] for arm in ARMS
            }
        ):
            raise ValueError("Signed terminal, native endpoints, grid and path disagree")
        loss = loss_gate.face_contact(grid)
    result = position_readout("complete", width, endpoints, loss)
    result.update(endpoints_km=endpoints, native_sha256=terminal["native_sha256"],
                  model_version=terminal["model_version"],
                  terminal_sha256=receipt["terminal_sha256"], path_sha256=canonical_digest(path),
                  grid_sha256=None if grid is None else canonical_digest(grid),
                  identity={"region": offer, "arms": terminal["arms"]})
    return result


def physical_publication(root, row, evidence):
    receipt = evidence["receipt"]
    if row["outcome"] != "complete":
        result = position_readout(row["outcome"], 0, None, {"state": "unchanged"})
        result["identity"] = {"region": receipt.get("region"), "arms": row["arms"]}
        return result
    run_id = receipt["run_id"]
    workspace = FastScanStore(root).automatic_workspace(run_id, create=False)
    terminal = json.loads((workspace / "terminal.json").read_bytes())
    store = FastStandardAnalysisStore(root)
    path, grid = store.position_path(run_id), store.position_grid(run_id)
    expected = evidence["scientific_digests"]
    if path is None:
        result = position_readout(row["outcome"], 0, None, {"state": "unassessable"})
        result["identity"] = {"region": receipt["region"], "arms": row["arms"]}
        return result
    for name, document in (("path", path), ("grid", grid)):
        if document is None:
            continue
        body = {k: v for k, v in document.items() if k not in ("binding", "elapsed_seconds")}
        if canonical_digest(body) != expected[name]:
            raise ValueError(f"Field publication {name} differs from the selected signed attempt")
    return from_documents(terminal, path, grid, receipt)


def read_field(snapshot):
    plan = pinned_json(CAMPAIGN / "plan.json", PLAN)
    entries = frozen_order(plan)
    selection = INITIAL + PROSPECTIVE
    if tuple(entry["case"] for entry in entries[:len(selection)]) != selection:
        raise ValueError("The original enrolled and reserved captures differ from the protocol")
    seal = pinned_json(snapshot / "rows-with-relocations-seal.json", EXPORT_SEAL)
    if seal["plan_sha256"] != PLAN or seal["combined_sha256"] != EXPORT:
        raise ValueError("Expected the frozen original selected attempt ledger")
    rows = {case: {} for case in INITIAL}
    required = {case.encode() for case in INITIAL}
    for line in checked(snapshot / "rows-with-relocations.jsonl", EXPORT).splitlines():
        if not any(case in line for case in required):
            continue
        row = json.loads(line)
        if row["case"] in rows:
            group = rows[row["case"]]
            if row["algorithm"] in group:
                raise ValueError("The selected attempt ledger contains duplicate outcomes")
            group[row["algorithm"]] = row

    overlay_root = CAMPAIGN / "relocation" / RELOCATION
    overlay = pinned_json(overlay_root / "overlay.json", OVERLAY)
    if (overlay["case"] != RELOCATION or overlay["plan_sha256"] != PLAN
            or overlay["proof_path"] != f"relocation/{RELOCATION}/proof.json"
            or overlay["proof_sha256"] != seal["proofs"][RELOCATION]):
        raise ValueError("The relocated publication lacks its enrolled proof")
    checked(overlay_root / "proof.json", overlay["proof_sha256"])
    checked(overlay_root / "native-encoded-auth.json", overlay["encoded_auth_sha256"])
    result = {}
    for entry in entries[:len(INITIAL)]:
        case = entry["case"]
        assigned = {"case_id": entry["case_id"], "release_100": entry["historical_first100"],
                    "raw_authority": entry["manifest_raw_authority_sha256"],
                    "physical_content": entry["raw_identity_sha256"],
                    "recording_state": entry["recording_state"], "reference": None}
        _, pair_proof = verified_capture(CAMPAIGN, entry, rows[case], assigned, overlay)
        row = rows[case]["successor"]
        attempt = CAMPAIGN / row["attempt"]
        selected = pinned_json(attempt, row["attempt_result_sha256"])
        publication = attempt.parent / "publication"
        signed = physical_publication(publication, row, selected["evidence"])
        signed.update(attempt_sha256=row["attempt_result_sha256"],
                      pair_sha256=pair_proof["pair_sha256"],
                      selected_relative_attempt=row["attempt"])
        if case == FIELD_TRANSLATION:
            release = json.loads((publication / "algo08v3-successor-release.json").read_bytes())
            if (release["build_sha256"] != PINS["successor"]
                    or release["terminal_sha256"] != signed["terminal_sha256"]
                    or release["authority_sha256"] != row["authority_sha256"]):
                raise ValueError("The ordinary paired neighbor differs from its frozen release")
            signed["archive_sha256"] = release["archive_sha256"]
            signed["build_sha256"] = release["build_sha256"]
            signed["clock"] = {k: selected[k] for k in ("cpu_s", "elapsed_s", "timing_scope")}
        result[case] = signed
    return result


def read_reference_cases():
    result = {}
    original = pinned_json(MEASUREMENTS / "grid-face-abstention.json", HISTORIC)
    for name, source in original["cases"].items():
        identity, loss = source["identity"], source["readout"]
        endpoints = {arm: loss["arms"][arm]["endpoint_xy_km"] for arm in ARMS}
        parsed = position_readout("complete", identity["region"]["width_km"], endpoints, loss)
        result[name] = dict(parsed, build=source["build"], identity=identity)

    old = pinned_json(MEASUREMENTS / "geographic-jackknife.json", NORTH_NAMED)
    for row in old["results"]:
        if row["site"] != "north" or row["case"] not in ("inside", "outside"):
            continue
        name = row["case"]
        endpoints = {arm: row["gate"]["arms"][arm]["endpoint_km"] for arm in ARMS}
        loss = {"state": "unassessable"}
        if name == "inside":
            saved = pinned_json(NORTH_INSIDE / "pair.json", NORTH_PAIR)["runs"]["candidate"]
            _, loss = load_publication(
                NORTH_INSIDE / "candidate", saved["receipt"],
                digests=saved["scientific_digests"], scrub=True,
            )
            if endpoints != {arm: list(loss["arms"][arm]["endpoint_xy_km"]) for arm in ARMS}:
                raise ValueError("The named North grid differs from the selected signed endpoint")
        parsed = position_readout("complete", row["offer"]["width_km"], endpoints, loss)
        result[f"north-named-{name}"] = dict(
            parsed, build="named ALGO08v3", identity={"region": row["offer"],
                                                      "arms": row["signed"]["arms"]},
            archived_signed_sha256=row["archived_signed_sha256"],
        )

    south = pinned_json(MEASUREMENTS / "frozen-south-north-face.json.gz", SOUTH_1KM)
    for name, row in south["outcomes"].items():
        parsed = from_documents(row["terminal"], row["path"], row["grid"], row["receipt"])
        result[f"south-1km-{name}"] = dict(parsed, build=name.split(":")[1])
    return result


def read_translations(path, ordinary):
    saved = pinned_json(path, TRANSLATION)
    control = saved["original_control"]["receipt"]
    if (control["terminal_sha256"] != ordinary["terminal_sha256"]
            or control["region"] != ordinary["identity"]["region"]
            or saved["source"]["native_sha256"] != ordinary["native_sha256"]
            or saved["source"]["archive_sha256"] != ordinary["archive_sha256"]):
        raise ValueError("The translation archive does not bind the enrolled ordinary offer")
    result = {}
    for name, row in saved["alternatives"].items():
        parsed = from_documents(row["terminal"], row["path"], row["grid"], row["receipt"])
        if (parsed["native_sha256"] != ordinary["native_sha256"]
                or parsed["model_version"] != ordinary["model_version"]
                or row["archive_digest"] != ordinary["archive_sha256"]):
            raise ValueError("Translated publications must use the ordinary detector and model")
        parsed["clock"] = row["clock"]
        result[name] = parsed
    return result


def authenticated_neighbor(west, ordinary):
    """Express the original published fits in the translated west face's local frame."""
    region = ordinary["identity"]["region"]
    lat, lon = region["center"]
    half = region["width_km"] / 2
    # Match the archive's exact half-width construction, with the sky screen fixed.
    expected = dict(region, center=[lat, lon - half / (111.32 * cos(radians(lat)))])
    if west["identity"]["region"] != expected or west["exact"]["shared_faces"] != ["east"]:
        raise ValueError("The west offer is not the authenticated adjacent half-width challenge")
    focused = {
        arm: {"west": [west["endpoints_km"][arm][0] - half, west["endpoints_km"][arm][1]],
              "ordinary": ordinary["endpoints_km"][arm]}
        for arm in ARMS
    }
    return {"face": "east", "neighbor": "ordinary", "outward_center_shift_km": half,
            "axes": ["signed_distance_outward_from_tested_face", "north_from_offer_center"],
            "position_km": focused, "paired_archive_sha256": TRANSLATION,
            "paired_build_sha256": ordinary["build_sha256"]}


def apply_reference(row, reference):
    identity = row.pop("identity")
    row["truth_clearance_km"] = (
        face_clearance_km(identity["region"], reference)
        if identity["region"] is not None and reference is not None else None
    )
    row["scored_arms"] = {
        arm: {"error_km": distance_km(data["latlon"], reference),
              "rf_rms_hz": data.get("rf_rms_hz")}
        for arm, data in identity["arms"].items()
    }
    # Older withholds may omit region metadata. The unchanged outcome remains enrolled.
    for arm, data in row["scored_arms"].items():
        if row["original"] == "complete" and data["error_km"] is None:
            raise ValueError(f"Published fit lacks an enrolled reference for {arm}")


def verdicts(rows):
    result = {}
    for method in ("original", "exact", "face_loss"):
        statuses, lost, retained_false, unresolved = Counter(), [], [], []
        within = {arm: {"1km": 0, "2km": 0} for arm in ARMS}
        for name, row in rows.items():
            status = row["original"] if method == "original" else row[method]["outcome"]
            statuses[status] += 1
            if method != "original" and row[method]["state"] == "unassessable":
                unresolved.append(name)
            clearance = row["truth_clearance_km"]
            if row["original"] == "complete" and status == "withheld" and clearance >= 0:
                lost.append(name)
            if status == "complete":
                if clearance < 0:
                    retained_false.append(name)
                for arm in ARMS:
                    error = row["scored_arms"][arm]["error_km"]
                    within[arm]["1km"] += int(error <= 1)
                    within[arm]["2km"] += int(error <= 2)
        result[method] = {"outcomes": dict(statuses), "valid_returns_lost": lost,
                          "retained_false": retained_false, "unassessable": unresolved,
                          "within": within}
    return result


def encode(value):
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False)


def run(snapshot, translated):
    field = read_field(snapshot)
    ordinary = field[FIELD_TRANSLATION]
    translations = read_translations(translated, ordinary)
    return {"field": field, "translations": translations, "public": read_reference_cases(),
            "neighbor": authenticated_neighbor(translations["west"], ordinary),
            "reservation": list(PROSPECTIVE), "snapshot_sha256": EXPORT}


def score(path):
    data = json.loads(path.read_bytes())
    assigned = roster()
    for case, row in data["field"].items():
        apply_reference(row, assigned[case]["reference"])
        row.pop("endpoints_km", None)
    for row in data["translations"].values():
        apply_reference(row, assigned[FIELD_TRANSLATION]["reference"])
    answers = pinned_json(HERE.parent / "regional-release/scoring-key.json", PUBLIC_KEY)["answers"]
    truth = {}
    for site, recording in RECORDING.items():
        truth[site], = {tuple(r["truth"]) for r in answers.values() if r["recording"] == recording}
    for name, row in data["public"].items():
        apply_reference(row, truth[name.split("-")[0]])
    data["summary"] = {
        group: verdicts(data[group]) for group in ("field", "public", "translations")
    }
    data["prediction_sha256"] = canonical_digest(json.loads(path.read_bytes()))
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    worker = actions.add_parser("run")
    worker.add_argument("snapshot", type=Path)
    worker.add_argument("translated", type=Path)
    scorer = actions.add_parser("score")
    scorer.add_argument("path", type=Path)
    args = vars(parser.parse_args())
    print(encode((run if args.pop("action") == "run" else score)(**args)))


if __name__ == "__main__":
    main()
