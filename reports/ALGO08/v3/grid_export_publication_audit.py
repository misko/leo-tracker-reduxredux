"""Verify the archived controls for the checked posterior's publication boundary."""

import gzip
import json
from hashlib import sha256
from pathlib import Path

from leo.contracts.digests import canonical_digest
from leo.contracts.fast_standard_analysis import PLOTS
from leo.contracts.position_grid import ARMS

REPORTS = Path(__file__).resolve().parents[1]
PINS = {
    "v3/measurements/integrated-south.json.gz":
        "8953474fff07f72f81bd58848c6075797e5e1ffacdd4973f9049e2a64cc5a674",
    "v3/measurements/frozen-south-north-face.json.gz":
        "b4d218026c8eb64a4d031c1403efbab5eeed2b5e9aba5554a3117541fbad8fb8",
    "v3/measurements/frozen-build-geography.json":
        "be4d89302c90b2eee19ff930e4485de7ea22b0ef04e1ba216bf9734e47c4ddd1",
    "single-core-2x/measurements/exact-curved-lookahead-south-offers.json":
        "5181abf1c8a36d45dfe140e8851f0a423b69ec69b8ca231a3f87bcc9fdcecca9",
    "v3/measurements/exact-named-raw.json.gz":
        "e654af8ddfc9c9bf0b479f722003e984a35ca47eab8a94c4540bee57f0dc6b86",
    "v3/measurements/profiled-grid-export-0008.json":
        "20bcf8679a1c68e9eebd55c31fcc3c81b95e7250fc4c153a4de80e2449d2b017",
}


def checked(relative):
    path = REPORTS / relative
    content = path.read_bytes()
    if sha256(content).hexdigest() != PINS[relative]:
        raise ValueError(f"Archived study changed: {relative}")
    return json.loads(gzip.decompress(content) if path.suffix == ".gz" else content)


def positive(binding, receipt, images, owners, points):
    if set(images) != set(PLOTS) or any(not r["rgba_sha256"] for r in images.values()):
        raise ValueError("Expected all eight products with saved decoded hashes")
    if (binding["position_png_sha256"] != images["position"]["sha256"]
            or binding["terminal_sha256"] != receipt["terminal_sha256"]
            or binding["run_id"] != receipt["run_id"]
            or set(owners) != set(ARMS)
            or binding["owner_sha256"] != {
                arm: canonical_digest({row[0]: row[1] for row in owners[arm]}) for arm in ARMS
            }
            or receipt["decision"] != "complete" or not points):
        raise ValueError("The saved grid, terminal, owners, and position PNG must bind")
    native = receipt["posterior_grid_handoff"]
    return {
        "input_sha256": binding["input_sha256"], "terminal_sha256": binding["terminal_sha256"],
        "owners": {arm: len(owners[arm]) for arm in ARMS}, "points": points, "images": len(images),
        "stock_factors": native.get("factor_calls", 0),
        "stock_predictive_calls": native.get("prediction_calls", 0),
    }


def integrated(offer):
    receipt, witness = offer["published"]["receipt"], offer["witness"]
    evidence = witness["evidence"]
    if evidence["grid"] != offer["sidecars"]["grid_points"]:
        raise ValueError("The two saved South publication witnesses disagree on grid count")
    result = positive(offer["sidecars"]["binding"], receipt, offer["images"],
                      evidence["owner_rows"], evidence["grid"])
    history = witness["ports"]["history_risk"]
    check, = history["boundary_checks"]
    return dict(result, archive_sha256=witness["solver_recipe"]["archive_sha256"],
                clearance_km=offer["truth_clearance_km"], route=history["choice"]["route"],
                guard=check["result"], sidecar_digests=evidence["sidecars"],
                seal_sha256=offer["seal_sha256"])


def north_face(row, margin):
    grid, path, receipt, terminal = (row[k] for k in ("grid", "path", "receipt", "terminal"))
    if (grid["binding"] != path["binding"] or not grid["complete"]
            or grid["evaluated_points"] != len(grid["points"])
            or canonical_digest(terminal) != receipt["terminal_sha256"]
            or grid["binding"]["input_sha256"] != terminal["native_sha256"]):
        raise ValueError("The north-face grid and path do not match their signed run")
    images = {name: dict(figure, sha256=figure["encoded_sha256"])
              for name, figure in row["figures"].items()}
    return dict(positive(grid["binding"], receipt, images, row["ordered_owners"],
                         grid["evaluated_points"]), clearance_km=margin,
                archive_sha256=row["archive_digest"],
                grid_sha256=canonical_digest(grid), path_sha256=canonical_digest(path))


def report():
    raw = checked("v3/measurements/integrated-south.json.gz")
    north = checked("v3/measurements/frozen-south-north-face.json.gz")
    freeze = checked("v3/measurements/frozen-build-geography.json")
    southern = checked("single-core-2x/measurements/exact-curved-lookahead-south-offers.json")
    charted = {name: integrated(offer) for name, offer in raw["offers"].items()}
    north_face_rows = {
        name: north_face(row, north["summary"][name]["signed_reference_margin_km"])
        for name, row in north["outcomes"].items()
    }
    same = freeze["proposed_saved_pair"]
    for build in ("installed", "integrated"):
        rows = [r for name, r in north_face_rows.items() if name.endswith(f":{build}")]
        rows += list(charted.values()) if build == "integrated" else []
        if any((r["input_sha256"], r["archive_sha256"]) != (
            "sha256:" + same["packets"][build]["sha256"], "sha256:" + same["causal_archive_sha256"]
        ) for r in rows):
            raise ValueError("Saved South controls do not use the same enrolled packet per build")

    far = southern["results"]["south-far"]
    installed = north_face_rows["containing:installed"]
    if (southern["native_sha256"] != installed["input_sha256"]
            or southern["archive"]["snapshots_sha256"] != installed["archive_sha256"]
            or southern["specification"] != "sha256:" + freeze["installed_specification_sha256"]
            or far["status"] != "withheld" or far["reason"] != "both_receivers_support_far_exterior"
            or far["science"] or any(far["arms"][arm]["latlon"] is not None for arm in ARMS)):
        raise ValueError("The signed far result does not close the installed South control")

    named = checked("v3/measurements/exact-named-raw.json.gz")["north"]
    original = named["candidate/exact-named-raw-witness.json"]["value"]
    omitted = named["north-far-saved/exact-named-raw-witness.json"]["value"]
    saved = named["north-far-saved/saved-omitted-witness.json"]["value"]
    no_evidence = omitted["evidence"]
    detail = no_evidence["detail"]
    archive = original["solver_recipe"]["archive_sha256"]
    if (detail["state"] != "withheld" or detail["arms"] or detail["artifacts"]
            or no_evidence["images"] or no_evidence["owner_rows"] or no_evidence["grid"] is not None
            or saved["receipt"]["posterior_grid_handoff"].get("prediction_calls", 0)
            or original["evidence"]["detail"]["input_sha256"] != saved["native_sha256"]
            or detail["input_sha256"] != saved["native_sha256"]
            or archive != omitted["solver_recipe"]["archive_sha256"]):
        raise ValueError("Expected the earlier matched North no-product regional withhold")

    physical = checked("v3/measurements/profiled-grid-export-0008.json")
    if physical["new_full_grids"] or physical["new_solves"]:
        raise ValueError("The component receipt claims a full run outside its enrolled scope")
    return {
        "charted_south": charted, "south_north_face": north_face_rows,
        "installed_south_far": dict(far, input_sha256=southern["native_sha256"]),
        "earlier_north_far": dict(detail, grid=None, posterior_grid_calls=0),
        "measured_physical_proof": physical["physical_proof_sha256"],
    }


if __name__ == "__main__":
    print(json.dumps(report(), indent=2, sort_keys=True, allow_nan=False))
