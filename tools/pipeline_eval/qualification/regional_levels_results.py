"""Score sealed regional geometry, exact emitter identity checks and standard plots."""

import argparse
import gzip
import json
from pathlib import Path

from ..__main__ import save_json
from ..scoring import ARMS, ROLES, distance_km
from . import identity_ablation as owners
from . import regional_levels_trial as trial
from .absolute_doppler_results import MATCH, calibration_support
from .armijo_finish_results import pack
from .native_joint_full_results import original_scores, roi_margin
from .prefix_figures import csv_file

OUT, PREDICTIONS, world = trial.OUT, trial.PREDICTIONS, trial.world
CENTER = "regional_tile_center"


def physical_key(row):
    return row["receiver"], row["channel"], float(row["rf_hz"]), float(row["time_s"])


def owner_archive(case, original):
    catalog = owners._load_case(case)
    capture = world.clock.load(case)
    _, probes = owners.adapter.physical_index(capture, catalog["session_id"])
    rows, receipt = owners.v5_rows(catalog, probes, original[case]["baseline"])
    return {physical_key(r): r for r in rows}, receipt


def peak_map(capture):
    first = capture["first_counter"]
    rate = capture["sample_rate_hz"]
    midpoint = capture["probe_ms"] / 2000
    return {
        (
            p["receiver_id"],
            p["channel"],
            float(p["actual_rf_hz"]),
            (p["valid_start_counter"] - first) / rate + midpoint,
        ): p["candidates"]
        for p in capture["probes"]
    }


def independent_identity(factors, samples, archived=None, simulated=None):
    if (archived is None) == (simulated is None):
        raise ValueError("identity scoring needs one independent authority")
    emitters = (
        {(e["block"], e["channel"]): e["norad"] for e in simulated["emitters"]}
        if simulated is not None
        else {}
    )
    matched, eligible, ambiguous = 0, 0, 0
    families, unique = set(), set()
    for arc in factors:
        prefix = arc["receiver"], arc["channel"], arc["rf_hz"]
        for t, cfo in zip(
            arc["time_s"][arc["held_start"] :], arc["cfo_hz"][arc["held_start"] :], strict=True
        ):
            key = (*prefix, t)
            peaks = [
                p
                for p in samples.get(key, ())
                if abs(trial.model.world.physical.fold(cfo - p["fractional_tracking_cfo_hz"]))
                <= 1e-6
            ]
            if len(peaks) != 1:
                ambiguous += len(peaks) > 1
                continue
            (candidate,) = peaks
            if archived is not None:
                row = archived.get(key)
                expected = (
                    row["norad"]
                    if row and row["candidate_rank"] == candidate["candidate_rank"]
                    else None
                )
            else:
                block = int(t // 50)
                active = 3.01 < t - block * 50 < 46.99 and candidate["fractional_margin"] >= 0.26
                expected = emitters.get((block, arc["channel"])) if active else None
            if expected is None or key in unique:
                continue
            unique.add(key)
            eligible += 1
            if expected == arc["norad"]:
                matched += 1
                families.add(expected)
    return dict(
        identity_compared_points=eligible,
        identity_agree_points=matched,
        identity_agree_orbits=len(families),
        identity_ambiguous_cfo_rows=ambiguous,
    )


def checked_truth(work, plan):
    root = world.prior.archive.REPORT
    original = world.prior.archive.base.secant_full.REPORT
    world.verify(root, world.read(root / "omitted-figure-lock.json")["files"])
    world.verify(original, world.read(original / "receipt.json")["files"])
    truth_path = work / "private/labels.json"
    seed = (work / "private/seed.bin").read_bytes()
    if (world.digest(truth_path.read_bytes()), world.digest(seed)) != (
        plan["private_labels_sha256"],
        plan["seed_sha256"],
    ):
        raise ValueError("simulation truths differ from the commitments")
    truth = world.read(truth_path)
    save_json(OUT / "synthetic-truth.json", dict(seed_hex=seed.hex(), captures=truth))
    return (
        {
            r["id"]: r
            for panel in ("ds26-common127", "roof16")
            for r in world.prior.archive.base.phase.corpus.references(panel)
        },
        world.read(original / "original-v5-inputs.json"),
        {q["id"]: q for q in world.read(root / "omitted-queries.json")["queries"]},
        truth,
    )


def score(work):
    lock = world.read(OUT / "prediction-lock.json")
    world.verify(OUT, lock["files"])
    plan = world.read(OUT / "blind-plan.json")
    refs, original, omitted, synthetic = checked_truth(work, plan)
    with gzip.open(OUT / PREDICTIONS, "rt") as stream:
        rows = list(map(json.loads, stream))
    records = {(r["id"], r["method"]): r for r in rows}
    if len(rows) != len(records) or set(records) != {
        (q["id"], method) for q in plan["cases"] for method in trial.METHODS
    }:
        raise ValueError("regional predictions differ from the predeclared roster")
    scores, panels, prior_rows, receipts = [], {}, [], {}
    for q in plan["cases"]:
        key, case, cohort = (q[k] for k in ("id", "recording", "cohort"))
        first = records[key, trial.METHODS[0]]
        geo_ref = {}
        is_simulated = cohort.startswith("simulated-")
        panel = "simulated" if is_simulated else cohort
        truth = synthetic[case]["latlon"] if is_simulated else refs[case]["truth"]
        if cohort in ("reserve", "diagnostic"):
            geo_ref = original_scores(key, refs[case], original[case], truth)
        if cohort == "omitted":
            source = omitted[key]
            if source["truth"] != truth or any(
                first["original_request_sha256" if k == "input_sha256" else k] != v
                for k, v in source["bindings"].items()
            ):
                raise ValueError("omitted query differs from exactly bound archive")
        present = roi_margin(truth, q["tile"]) >= 0
        if present != (cohort in ("diagnostic", "reserve", "simulated-present")):
            raise ValueError("offer does not have its planned relation to truth")
        bind = {k: first[k] for k in MATCH}
        panels.setdefault(panel, []).append(
            dict(id=key, recording=case, condition=cohort, truth=truth, bindings=bind)
        )
        centre = q["tile"]["center"]
        prior_rows.append(
            dict(
                q,
                **{"input_sha256": bind["input_sha256"]},
                method=CENTER,
                result=dict(
                    status="ok",
                    reason=None,
                    boundary="Always report the offered tile centre",
                    metrics={},
                    arms={a: dict(latlon=centre, forced_latlon=None) for a in ARMS},
                ),
            )
        )
        peaks = peak_map(world.clock.data(q, work))
        archived = None
        if not is_simulated:
            archived, receipts[key] = owner_archive(case, original)
        for method in trial.METHODS:
            r = records[key, method]
            if any(r.get(k) != v for k, v in (bind | q).items()):
                raise ValueError("regional predictions use unmatched raw input or offers")
            result = r["result"]
            calibration_support(result["arms"])
            metrics = result["metrics"]
            id_stats = independent_identity(
                metrics.get("selected_factors", []),
                peaks,
                archived=archived,
                simulated=synthetic[case] if is_simulated else None,
            )
            distances = [
                distance_km(p, truth)
                for points in metrics.get("evaluated_cells", {}).values()
                for p in points
            ]
            for arm, v in result["arms"].items():
                error = distance_km(v.get("forced_latlon"), truth)
                center = distance_km(centre, truth)
                scores.append(
                    dict(
                        id=key,
                        recording=case,
                        cohort=cohort,
                        method=method,
                        arm=arm,
                        status=result["status"],
                        reason=result["reason"],
                        error_km=distance_km(v.get("latlon"), truth),
                        forced_error_km=error,
                        tile_error_km=center,
                        forced_minus_tile_km=error - center if error is not None else None,
                        nearest_evaluated_km=min(distances, default=None),
                        held_rms_hz=v.get("held_rms_hz"),
                        conditional_rf_rms_hz=v.get("rf_rms_hz"),
                        center_held_rms_hz=v.get("center_held_rms_hz"),
                        center_conditional_rf_rms_hz=v.get("center_rf_rms_hz"),
                        held_geographic_lead=v.get("held_geographic_lead"),
                        inside_held_cost_span=v.get("inside_held_cost_span"),
                        held_orbits=v.get("held_good_orbits"),
                        held_points=v.get("held_points"),
                        fitted_c_hz_per_ghz=v.get("c_hz_per_ghz"),
                        c_identifiable=v.get("c_identifiable"),
                        coarse_sites=metrics.get("coarse_sites"),
                        exact_sites=metrics.get("exact_sites"),
                        selected_arcs=metrics.get("selected_arcs"),
                        cpu_s=r.get("cpu_s"),
                        wall_s=r.get("native_elapsed_s"),
                        rss_kib=r.get("peak_rss_kib"),
                        **id_stats,
                        **{
                            role + "_error_km": geo_ref[role][arm][0] if role in geo_ref else None
                            for role in ROLES
                        },
                        **{
                            role + "_rf_rms_hz": geo_ref[role][arm][1] if role in geo_ref else None
                            for role in ROLES
                        },
                    )
                )
    csv_file(OUT / "scores.csv", scores)
    save_json(OUT / "scores.json", dict(rows=scores, identity_source_receipts=receipts))
    figures(panels, rows + prior_rows, lock["files"])
    return scores


def figures(panels, records, frozen):
    provenance = ["blind-plan.json", "prediction-lock.json", "scores.json", "synthetic-truth.json"]
    sources = {name: world.digest((OUT / name).read_bytes()) for name in provenance} | frozen
    titles = {
        "diagnostic": "Regional absolute Doppler on the diagnostic roof recordings",
        "reserve": "Regional absolute Doppler on four held roof recordings",
        "omitted": "Regional absolute Doppler on real omitted offers",
        "simulated": "Regional absolute Doppler at two newly drawn simulated sites",
    }
    descriptors = []
    for name, title in titles.items():
        transfer = name in ("omitted", "simulated")
        cases = [q["id"] for q in panels[name]]
        seal = name + "-figure-lock.json"
        positions = name + "-positions.jsonl.gz"
        files = sources | {
            positions: pack(OUT, positions, [r for r in records if r["id"] in cases])
        }
        card = dict(
            id=f"{trial.model.METHOD}-{name}",
            method=trial.model.METHOD,
            scope="transfer" if transfer else "roof",
            cases=cases,
            title=title,
            caption="Equal 25 km cells, a centre prior and separate forced estimates.",
            seal=seal,
            provenance=provenance,
            series=[],
        )
        for key, method, label in zip(
            ("candidate", "stock", "four") if transfer else ("one", "stock", "one_native_factors"),
            (*trial.METHODS, CENTER),
            ("Shared CFO level", "Free arc intercept", "Tile centre prior"),
            strict=True,
        ):
            series = dict(key=key, value=method, label=label, file=positions)
            if method != trial.METHODS[0]:
                series["match"] = list(MATCH)
            if method != CENTER and (transfer or method == trial.METHODS[0]):
                series["forced_label"] = label + " · forced"
            card["series"].append(series)
        if transfer:
            query = name + "-queries.json"
            save_json(OUT / query, dict(queries=panels[name]))
            files[query] = world.digest((OUT / query).read_bytes())
            card["queries"] = query
        save_json(OUT / seal, dict(cases=cases, files=files))
        descriptors.append(card)
    save_json(OUT / "figures.json", dict(version=1, charts=descriptors))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    score(parser.parse_args().work)


if __name__ == "__main__":
    main()
