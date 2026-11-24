"""Verify saved diagonal identity, then reduce the four published crossover cells."""

import argparse
from collections import Counter
from io import BytesIO
import json
from math import isfinite
from pathlib import Path
from statistics import median
import subprocess

from ds30_0049_saved_crossover import ARMS, CASE, MODE, ROOT, ROLES, bind_input, one, read
import integrated_original_batch as batch

REFERENCE_SHA = "sha256:c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5"


def scientific_grid(grid):
    return {name: value for name, value in grid.items() if name != "elapsed_seconds"}


def publication(path, diag):
    from leo.presentation.localization_v3 import owner_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from PIL import Image

    worker = read(path / "crossover-worker.json")
    receipt = worker["receipt"]
    if worker["waveform_reads"] != 0 or worker["verified_handoffs"] != 1:
        raise ValueError("Expected one saved handoff and no original receiver work")
    run_id = receipt["run_id"]
    terminal = batch.document(path / "fast-scan-automatic-work" / run_id / "terminal.json",
                              receipt["terminal_sha256"])
    batch.checked(one(path, "fast-scan-automatic-work/*/detections.json"), diag["native_sha256"])
    if terminal["native_sha256"] != diag["native_sha256"] or set(terminal["arms"]) != set(ARMS):
        raise ValueError("Expected both submitted calibration arms bound to the original packet")
    store = FastStandardAnalysisStore(path)
    detail = store.detail(run_id)
    if (detail["state"] != receipt["decision"] or detail["terminal_sha256"] != receipt["terminal_sha256"]
            or detail["input_sha256"] != diag["native_sha256"]
            or detail["raw_authority"] != diag["raw_identity"]["raw_authority_sha256"]):
        raise ValueError("The standard publication is unbound")
    if receipt["decision"] == "withheld":
        if (receipt["terminal_sha256"] == "" or list(path.glob("**/*.png")) or worker["ordered_owners"]
                or any(row["latlon"] is not None for row in terminal["arms"].values())):
            raise ValueError("The saved withhold has position or media products")
        return dict(terminal=terminal, receipt=receipt, owners={}, owner_rows={}, figures={}, grid=None, path=None)
    grid, trace = store.position_grid(run_id), store.position_path(run_id)
    results = {}
    for item in detail["artifacts"]:
        data = store.artifact(run_id, item["name"], item["sha256"])
        if batch.tagged_bytes(data) != item["sha256"]:
            raise ValueError("Stored PNG differs from the certified bytes")
        with Image.open(BytesIO(data)) as image:
            if image.format != "PNG":
                raise ValueError("Expected an encoded standard PNG")
            results[item["name"]] = (item["sha256"], batch.tagged_bytes(image.convert("RGBA").tobytes()), list(image.size))
    if len(results) != 8 or not grid["complete"] or grid["evaluated_points"] != 179:
        raise ValueError("The positive saved solver did not produce the complete grid and eight standard plots")
    if any(doc["binding"]["position_png_sha256"] != results["position"][0] for doc in (grid, trace)):
        raise ValueError("Numerical products are detached from their verified position PNG")
    if any(row["latlon"] is None or not all(isfinite(x) for x in (*row["latlon"], row["rf_rms_hz"]))
           for row in terminal["arms"].values()):
        raise ValueError("The positive saved solver has invalid calibrated results")
    owners = {arm: owner_digest({row[0]: row[1] for row in rows}) for arm, rows in worker["ordered_owners"].items()}
    if set(owners) != set(ARMS) or any(owners[arm] != detail["arms"][arm]["owner_sha256"] for arm in ARMS):
        raise ValueError("Ordered owner readout does not bind the published owner digest")
    return dict(terminal=terminal, receipt=receipt, owners=owners, owner_rows=worker["ordered_owners"],
                figures=results, grid=grid, path=trace, audit=worker["audit"])


def diagonal_equivalence(mode, fresh, raw):
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    method, detector = MODE[mode]
    if method != detector:
        raise ValueError("Raw equivalence is a diagonal-only check")
    folder = CASE / method / "attempt-000002/publication"
    store = FastStandardAnalysisStore(folder)
    raw_receipt = raw["evidence"]["receipt"]
    raw_run = raw_receipt["run_id"]
    raw_figures = {row["name"]: (row["sha256"], batch.tagged(row["rgba_sha256"]), row["size"]) for row in raw["figures"]}
    checks = dict(
        exact_terminal=fresh["receipt"]["terminal_sha256"] == raw_receipt["terminal_sha256"],
        exact_both_arms=fresh["terminal"]["arms"] == batch.document(
            folder / "fast-scan-automatic-work" / raw_run / "terminal.json", raw_receipt["terminal_sha256"])["arms"],
        owner_digests=fresh["owners"] == raw["evidence"]["owners"],
        exact_full_grid=scientific_grid(fresh["grid"]) == scientific_grid(store.position_grid(raw_run)),
        exact_path=fresh["path"] == store.position_path(raw_run),
        eight_encoded_and_decoded_pngs=fresh["figures"] == raw_figures,
    )
    if not all(checks.values()):
        raise ValueError(f"{mode} did not reproduce the fresh raw publication: {checks}")
    return checks


def owner_changes(a, b):
    result = {}
    for arm in ARMS:
        left, right = (dict((row[0], row[1:]) for row in value.get(arm, [])) for value in (a, b))
        shared = left.keys() & right.keys()
        result[arm] = dict(shared=len(shared), removed=len(left.keys()-right.keys()),
                           added=len(right.keys()-left.keys()),
                           different_norad=sum(left[k][0] != right[k][0] for k in shared),
                           different_role=sum(left[k][1] != right[k][1] for k in shared))
    return result


def retained_native_support(packets, original_owners, successor_owners):
    """Join ordered observation identities to each receiver's actual accepted support."""
    elected = {}
    for role, native in packets.items():
        session = native["source"]["session_id"]
        winners = {}
        for row in native["source"]["probes"]:
            lane = batch.tagged_bytes(f"{session}:{row['receiver_id']}:{row['valid_start_counter']}".encode())
            if lane in winners:
                raise ValueError("A signed lane was repeated")
            winners[lane] = max((r for r in row["candidates"] if r["passed_fractional_margin_gate"]),
                                key=lambda r: (r["fractional_margin"], -r["candidate_rank"]), default=None)
        elected[role] = winners
    stock, alternate = (elected[role] for role in ROLES)
    if stock.keys() != alternate.keys():
        raise ValueError("The raw pair does not offer identical receiver lanes")
    prior, recent = ({row[0] for row in roster} for roster in (original_owners, successor_owners))
    support = {}
    for name, keys in (("lost", prior-recent), ("shared", prior & recent), ("added", recent-prior)):
        states, frequency, epoch = Counter(), [], []
        identical = 0
        for key in keys:
            a, b = stock[key], alternate[key]
            states[f"{'accepted' if a else 'empty'}_to_{'accepted' if b else 'empty'}"] += 1
            if a is None or b is None:
                continue
            f = abs(a["fractional_tracking_cfo_hz"] - b["fractional_tracking_cfo_hz"])
            e = abs((a["integer_epoch_sample"] - b["integer_epoch_sample"])
                    + a["fractional_epoch_offset_samples"] - b["fractional_epoch_offset_samples"])
            frequency.append(f)
            epoch.append(e)
            identical += f == e == 0
        support[name] = dict(lanes=len(keys), states=dict(states), exact_pairs=identical,
                             median_abs_cfo_delta_hz=median(frequency) if frequency else None,
                             median_abs_epoch_delta_samples=median(epoch) if epoch else None)
    return dict(matched_lanes=len(stock), support=support)


def geography():
    raw = subprocess.check_output(["git", "-c", f"safe.directory={ROOT}", "-C", str(ROOT), "show",
                                    "2d0ad2dfd:reports/2026_11_21_ds30_full/reference-audit.json"])
    if batch.tagged_bytes(raw) != REFERENCE_SHA:
        raise ValueError("The archived survey reference changed")
    row, = (row for row in json.loads(raw)["cases"] if row["dataset_label"] == "DS30-0049"
            and row["authority_eligible"] and row["sealed_metadata_digests_verified"])
    return [row["reference"][key] for key in ("latitude_deg", "longitude_deg")]


def clock(root, mode):
    fields = dict(value.split("=", 1) for value in (root / f"{mode}.time").read_text().split())
    result = {key: float(value) if key.endswith("_s") else int(value) for key, value in fields.items()}
    return result | {"cpu_s": round(result["user_s"] + result["system_s"], 3)}


def effects(errors):
    i, r, s, f = (errors[name] for name in ("installed-installed", "installed-successor",
                                            "successor-installed", "successor-successor"))
    if any(x is None for x in (i, r, s, f)):
        return None
    return dict(raw_diagonal_delta=f-i, receiver_with_installed_solver=r-i,
                receiver_with_successor_solver=f-s, solver_with_installed_receiver=s-i,
                solver_with_successor_receiver=f-r, interaction=f-r-s+i)


def score(root, full, receipt):
    from tools.pipeline_eval.scoring import distance_km

    authority, _, packets, raw, _ = bind_input()
    diagonal = {f"{name}-{name}": publication(root / f"{name}-{name}", raw[name]) for name in ROLES}
    checks = {mode: diagonal_equivalence(mode, result, raw[MODE[mode][0]]) for mode, result in diagonal.items()}
    if not full:
        print(json.dumps(checks))
        return
    cross = {mode: publication(root / mode, raw[packet]) for mode, (solver, packet) in MODE.items()
             if solver != packet}
    cells = diagonal | cross
    # The survey is joined only after each saved science/product comparison.
    reference = geography()
    summarized = {}
    for mode, result in cells.items():
        arms = result["terminal"]["arms"]
        summarized[mode] = dict(
            terminal_sha256=result["receipt"]["terminal_sha256"], native_sha256=result["terminal"]["native_sha256"],
            decision=result["receipt"]["decision"], reason=result["terminal"]["reason"],
            clocks=clock(root, mode), figures=result["figures"],
            arms={arm: dict(latlon=values["latlon"], rf_rms_hz=values.get("rf_rms_hz"),
                            error_m=None if values["latlon"] is None else 1000 * distance_km(values["latlon"], reference),
                            owners=len(result["owner_rows"].get(arm, ())), owner_sha256=result["owners"].get(arm))
                  for arm, values in arms.items()},
        )
    summaries = {arm: effects({mode: value["arms"][arm]["error_m"] for mode, value in summarized.items()}) for arm in ARMS}
    comparisons = {}
    for axis in ("receiver", "solver"):
        for fixed in ROLES:
            left, right = ((f"{fixed}-{varied}" if axis == "receiver" else f"{varied}-{fixed}") for varied in ROLES)
            comparisons[f"{axis}_fixed_{fixed}"] = owner_changes(cells[left]["owner_rows"], cells[right]["owner_rows"])
    factors = {role: dict(probes=len(doc["source"]["probes"]),
                          candidates=sum(len(p["candidates"]) for p in doc["source"]["probes"]))
               for role, doc in packets.items()}
    output = dict(case="DS30-0049", authority_sha256=batch.tagged_bytes((CASE / "authority.json").read_bytes()),
                  reference_sha256=REFERENCE_SHA, cells=summarized, effects_m=summaries,
                  owner_changes=comparisons, raw_diagonal_equivalence=checks, raw_metadata=authority,
                  receiver_factor_counts=factors, waveform_reads=0,
                  raw_clocks={role: {k: raw[role][k] for k in ("elapsed_s", "cpu_s", "process")} for role in ROLES})
    output["native_support"] = {arm: retained_native_support(
        packets, cells["installed-installed"]["owner_rows"][arm], cells["successor-successor"]["owner_rows"][arm])
        for arm in ARMS}
    output["ordered_owner_rows"] = {mode: result["owner_rows"] for mode, result in cells.items()}
    output["owner_row_source_sha256"] = {mode: batch.tagged_bytes(
        (root / mode / "crossover-worker.json").read_bytes()) for mode in cells}
    batch.write(receipt or root / "result.json", output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    score(args.root, args.full, args.receipt)
