"""Score the six sealed signed carrier placements against both exact-CFO replays."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path

from aperture_score import PHYSICAL, SIMULATED, face_clearance_km, references
from aperture_trial import inputs
from carrier_grid_trial import GRID_HZ
from mixture_score import section
from mixture_trial import ARMS, CASES
from primary_owner_census import APERTURE_SHA, canonical_owners, pinned_aperture


HERE = Path(__file__).resolve().parent
SIGNED = HERE / "measurements/blind-joint-signed.json.gz"
SIGNED_SHA = "de4a1be32d35c5b4c7ae6164ae663f450f8408937f4eb6de46c3977436dcfc54"
PREPARATION = HERE / "measurements/owner-union.json"
PREPARATION_SHA = "4dc961e1c63d96bcfc392e490ee3d2be3fdd77f4f4914d3f1399c5e596590589"
LIMIT_KM = .25


def checked_bytes(path, pin):
    data = path.read_bytes()
    if sha256(data).hexdigest() != pin:
        raise ValueError(f"Frozen comparison differs at {path}")
    return data


def changes(before, after):
    if before is None or after is None:
        return None
    common = before.keys() & after.keys()
    relabeled = sum(before[key] != after[key] for key in common)
    return dict(kept=len(common) - relabeled, relabeled=relabeled,
                lost=len(before.keys() - after.keys()), added=len(after.keys() - before.keys()))


def arm_errors(comparison):
    return [scores["delta_error_km"] for scores in comparison["arms"].values()]


def evidence(terminal, roles):
    return {key: terminal.get(key) for key in ("status", "reason", "orbit_policy", "associated", "owners",
                                               "grid_points", "objective_replay", "science")} | {"roles": roles}


def attempt_summary(step):
    signed = step.get("signed", {})
    selection = signed.get("selection", {})
    return dict(route=step["decision"], reason=step.get("reason"), signed=signed.get("status"),
                signed_selection={key: selection.get(key) for key in
                                  ("kind", "coefficient", "qualified", "disjoint_future_gain")},
                fallback=step.get("fallback_clocks"),
                clocks={name: value for name, value in step.items()
                        if name.endswith("_clocks") and name != "fallback_clocks"})


def compare(row, signed, stock, owners, full, truth):
    decision = row["result"]
    clearance = face_clearance_km(row["identity"]["offer"], truth)
    containing = clearance >= 0.
    paired = {
        "candidate_vs_signed": section(decision["arms"], truth, signed["result"]["arms"]),
        "candidate_vs_installed_v3": section(decision["arms"], truth, stock["arms"]),
        "exact_signed": section(signed["result"]["arms"], truth, signed["result"]["arms"]),
        "exact_installed_v3": section(stock["arms"], truth, stock["arms"]),
    }
    attempts = [attempt_summary(step) for step in row["attempts"]]
    fallback = sum((item["fallback"] or {}).get("cpu_s", 0.) for item in attempts)
    same_outcome = (
        decision["status"] == signed["result"]["status"] == stock["status"]
        and decision["reason"] == signed["result"]["reason"] == stock["reason"]
    )
    deltas = arm_errors(paired["candidate_vs_signed"]) + arm_errors(paired["candidate_vs_installed_v3"])
    if containing:
        passes = (same_outcome and row["numerical_grid_complete"]
                  and all(value is not None and value <= LIMIT_KM for value in deltas))
    else:
        passes = same_outcome and decision["status"] == "withheld"
    stock_terminal = dict(stock, associated=full.get("associated"), grid_points=full.get("grid_points"),
                          objective_replay=full.get("objective_replay"))
    overlaps = {}
    for arm in ARMS:
        signed_digest = signed["result"].get("owners", {}).get(arm)
        same_original_map = signed_digest is not None and signed_digest == stock.get("owners", {}).get(arm)
        overlaps[arm] = dict(
            vs_installed_v3=changes(owners.get(arm), row["owners"].get(arm)),
            vs_signed=changes(owners.get(arm), row["owners"].get(arm)) if same_original_map else None,
        )
    return dict(containing=containing, truth_clearance_km=clearance, placement=row["placement"],
                transformed_sha256=row["transformed_sha256"], graph=row["preparation"],
                accuracy_screen=bool(passes), same_terminal_status_and_reason=same_outcome,
                numerical_grid_complete=row["numerical_grid_complete"], metrics=paired,
                terminal=evidence(decision, row["published_roles"]),
                exact_signed=evidence(signed["result"], signed["published_roles"]),
                exact_installed_v3=evidence(stock_terminal, signed["stock_roles"]),
                map_comparison=overlaps, attempts=attempts,
                timing=dict(charged=row["charged"], fallback_cpu_s=fallback,
                            pre_fallback_cpu_s=row["charged"]["cpu_s"] - fallback,
                            exact_signed=signed["charged"],
                            exact_installed_v3=signed["control_clocks"] or {
                                key: full.get(key) for key in ("cpu_s", "elapsed_s")
                            }))


def score(directory, output):
    paths = {(case, mode): directory / f"{case}-{mode}.json" for case in CASES for mode in GRID_HZ}
    data = {key: path.read_bytes() for key, path in paths.items()}
    rows = {key: json.loads(raw) for key, raw in data.items()}
    driver = sha256((HERE / "carrier_grid_trial.py").read_bytes()).hexdigest()
    for (case, mode), row in rows.items():
        if row["case"] != case or row["mode"] != mode or row["driver_sha256"] != driver:
            raise ValueError("Candidate receipt does not match the frozen trial")
    for mode in GRID_HZ:
        if rows["south-containing", mode]["transformed_sha256"] != rows["south-far", mode]["transformed_sha256"]:
            raise ValueError("The two southern offers did not see the same transformed waveform")
    signed = json.loads(gzip.decompress(checked_bytes(SIGNED, SIGNED_SHA)))["receipts"]
    preparation = json.loads(checked_bytes(PREPARATION, PREPARATION_SHA))["cases"]
    original = pinned_aperture()
    truth = references()
    result = {}
    for case in CASES:
        native, _, _, stock, identity = inputs(case)
        if any(ref != identity for ref in (signed[case]["identity"], preparation[case]["identity"],
                                           *(rows[case, mode]["identity"] for mode in GRID_HZ))):
            raise ValueError("Evidence, offered region or causal archive differs from the frozen input")
        full = original[case]["full"]
        maps = canonical_owners(native, full, identity, stock) if stock["status"] == "ok" else {}
        owner_ids = {arm: {row["observation_id"]: row["norad"] for row in positions.values()}
                     for arm, positions in maps.items()}
        result[case] = dict(identity=identity, exact_graph=preparation[case]["full_preparation"])
        for mode in GRID_HZ:
            result[case][mode] = compare(rows[case, mode], signed[case], stock, owner_ids, full, truth[case])
    source_pins = {str(path.relative_to(HERE.parents[2])): sha256(path.read_bytes()).hexdigest()
                   for path in (PHYSICAL, SIMULATED)}
    source_pins.update(signed_baseline=SIGNED_SHA, installed_v3_owners=APERTURE_SHA,
                       exact_graph_baseline=PREPARATION_SHA, candidate_driver=driver,
                       scorer=sha256(Path(__file__).read_bytes()).hexdigest())
    receipt = dict(cases=result, accuracy_limit_km=LIMIT_KM, grid=rows["DS30-0008", "bin"]["grid"],
                   worker=rows["DS30-0008", "bin"]["machine"], pins=source_pins,
                   candidate_receipts={path.name: sha256(data[key]).hexdigest() for key, path in paths.items()})
    with output.open("x") as stream:
        print(json.dumps(receipt, indent=2, allow_nan=False, sort_keys=True), file=stream)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("output", type=Path)
    score(**vars(parser.parse_args()))
