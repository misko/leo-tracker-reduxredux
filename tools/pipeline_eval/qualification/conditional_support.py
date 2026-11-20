"""Trace original conditional RF and captured-causal orbit geometry on identical points."""

import argparse
import gzip
import json
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from sgp4.api import Satrec
from sgp4.exporter import export_tle

from leo.sky.frames import geodetic_to_ecef_km

from ..__main__ import ROOT, encoded, save_json, write
from ..scoring import ARMS
from ..variants import robust_orbit_fit as lean
from ..variants.v5_lean import SOURCE, bound_request
from . import association_evidence as audit
from . import owner_factor as previous
from .association_orbit_diagnostic import elements, rms
from .v5_postfit import _map
from .v5_prefix_audit import value

CASES = ("DS26-0197", "DS26-0223")
OUTPUT = ROOT / "reports/2026_11_19_receiver_screening/recovery/conditional-support"
PERIOD = lean.lean.PERIOD


def harmonic_difference(native_hz, lifted_hz):
    branch = np.rint((lifted_hz - native_hz) / PERIOD).astype(int)
    if not np.allclose(lifted_hz, native_hz + branch * PERIOD, rtol=0, atol=1e-6):
        raise ValueError("point is not an integer native harmonic lift")
    return branch


def factors(case):
    lock = audit.read(previous.REPORT / "prediction-lock.json")
    for name, expected in lock["files"].items():
        if audit.phase.digest(previous.REPORT / name) != expected:
            raise ValueError("sealed owner-model archive is different")
    selected = next(r for r in previous._load(previous.REPORT / previous.FILE) if r["id"] == case)
    expanded, shared = {arm: {} for arm in ARMS}, {arm: set() for arm in ARMS}
    with gzip.open(previous.REPORT / previous.RESIDUALS, "rt") as stream:
        for row in map(json.loads, stream):
            if row["case"] != case:
                continue
            if row["cell"] == "v5_owner_v5_alias":
                shared[row["arm"]].add(row["id"])
            if row["cell"] == "v5_full_lean":
                expanded[row["arm"]][row["id"]] = row
    groups = {}
    for arm in ARMS:
        added = expanded[arm].keys() - shared[arm]
        groups[arm] = defaultdict(list)
        for identifier in added:
            row = expanded[arm][identifier]
            groups[arm][row["component"]].append(row)
        for rows in groups[arm].values():
            rows.sort(key=lambda r: r["time_s"])
    if any(
        sum(map(len, g.values())) != selected["counts"]["v5_only_conditional"]
        for g in groups.values()
    ):
        raise ValueError("additional support count changed")
    return selected, groups, lock


def _eligible_catalogue(raw, collected, newest):
    candidates = {}
    for number, row in elements(raw, collected, "native_current"):
        if newest - 48 * 3600 * 10**9 <= row["epoch_ns"] <= collected and (
            number not in candidates or row["epoch_ns"] > candidates[number]["epoch_ns"]
        ):
            candidates[number] = row
    return candidates


def swap_states(lean_orbit, original_orbit, lean_hardware, original_clock, remainder, old, new):
    return {
        "lean_prediction": lean_orbit + lean_hardware,
        "site_only": original_orbit[0] + lean_hardware,
        "tle_only": original_orbit[1] + lean_hardware,
        "phase_only": original_orbit[2] + lean_hardware,
        "clock_replaced": original_orbit[2] + original_clock,
        "original_model_remainder": original_orbit[2] + original_clock + remainder,
        "alias_delta_hz": (new - old) * PERIOD,
    }


def run(case):
    from leo.analysis.localization_v3.elements import ElementParser
    from leo.analysis.localization_v3.orbits import ecef_states, regional_bank
    from leo.analysis.localization_v3.tracks import prepare_tracks
    from leo.operations.localization_v3_job import read_bound

    from leo.analysis.polynomial_tracklets import TrackConfig
    from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
    from leo.analysis.research.phase_linear_geometry import (
        phase_linear_frequency,
        prepare_phase_geometry,
    )
    from leo.analysis.research.retained_track_likelihood import projected_receiver_basis
    from leo.operations.causal_tle_catalogue import causal_catalogue
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import ElementSetCatalogue

    if not Path(prepare_tracks.__code__.co_filename).is_relative_to(SOURCE):
        raise ValueError("the original v5 implementation is required for forensic replay")
    sealed, groups, lock = factors(case)
    folder = audit.phase.ARCHIVE / (case + "-r0") / "baseline"
    _, request, job = bound_request(folder / "experimental-request.json")
    capture = read_bound(job["native_input"])
    prepared = prepare_tracks(capture, TrackConfig(**read_bound(job["track_config"])["config"]))
    meta = prepared["metadata"]
    dt, anchor, cutoff = meta["duration_s"], meta["anchor_utc_ns"], meta["causal_cutoff_utc_ns"]
    original = causal_catalogue(
        TleArchiveReader(Path(job["tle_root"])), cutoff, element_parser=ElementParser()
    )
    regional = regional_bank(
        original.catalogue,
        anchor,
        max(float(t["times"][-1]) for t in prepared["tracks"]),
        screen_latitude_deg=job["screen_center"][0],
        screen_longitude_deg=job["screen_center"][1],
    )
    item = audit.phase.frozen_inputs()[case]
    packet, paths = audit.trial.native.request(item, "native")
    raw = paths["catalogue"].read_bytes()
    if (
        sha256(raw).hexdigest() != sealed["bindings"]["catalog_sha256"]
        or packet["cutoff"] != cutoff
    ):
        raise ValueError("lean owner-model causal catalogue differs from archive")
    current = _eligible_catalogue(raw, packet["catalog_timestamp"], cutoff)
    component = {t["key"]: t for t in prepared["tracks"]}
    native = {r["observation_id"]: r for r in prepared["observations"]}
    package = folder / "experimental-evidence.zip"
    publication = audit.original(case, item)
    exact = {}
    with ZipFile(package) as z:
        tree = _map(json.loads(z.read("values.json"))["tree"])
        stored = _map(tree["selected"])
        trail = _map(tree["audit"])
        cavity = _map(trail["cavity_policy"])
        node = _map(cavity["baseline_node"])
        aliases = {
            r["component"]: (a, r["candidate_index"])
            for row, a in zip(_map(node["seed"])["rows"][1], node["aliases"][1], strict=True)
            if (r := _map(row))
        }
        late = _map(_map(trail["reassociation_complete"])["recovery"])
        if cavity["accepted"] or late["selected"]:
            raise ValueError("this diagnostic expects original nominal published components")
        for arm, ar in _map(stored["arms"]).items():
            select = _map(ar)
            if select["events"][1]:
                raise ValueError("archived receiver events require explicit replay")
            state = _map(select["state"])
            exact[arm] = dict(
                beta=value(state["beta"], z),
                smooth=value(state["smooth"], z),
                phases=value(state["phases"], z),
                position=value(select["endpoint_latlon"], z),
                gates={
                    r["component"]: r for a in _map(select["gates"])["tracks"][1] if (r := _map(a))
                },
            )
    observed, summary = [], []
    for arm, table in groups.items():
        saved = exact[arm]
        for name, points in sorted(table.items()):
            track = component[name]
            graph_lookup = dict(
                zip(track["observation_ids"], enumerate(track["values"]), strict=True)
            )
            expected = saved["gates"][name]
            number, index = expected["norad"], expected["candidate_index"]
            alias, original_index = aliases[name]
            if (
                original_index != index
                or regional["catalogue"].satellite_numbers[index] != number
                or any(
                    publication["owners"][arm][r["id"]] != number or r["norad"] != number
                    for r in points
                )
            ):
                raise ValueError("candidate identity differs across the original and lean factor")
            match = [native[r["id"]] for r in points]
            raw_cfo = np.array([r["measured_cfo_hz"] for r in match])
            t = np.array([r["time_s"] for r in points])
            t_native = np.array([r["time_s"] for r in match])
            graph_t = np.array([track["times"][graph_lookup[r["id"]][0]] for r in points])
            if not np.array_equal(t, t_native) or not np.array_equal(graph_t, t_native):
                raise ValueError(
                    "original native, conditional and owner factor sample times differ"
                )
            rf = track["rf_hz"]
            if any(r["actual_rf_hz"] != rf for r in match) or any(r["rf_hz"] != rf for r in points):
                raise ValueError("true observed RF differs")
            graph = np.array([graph_lookup[r["id"]][1] for r in points])
            lifted = np.array([r["lifted_hz"] for r in points])
            original_lifted = graph + alias * PERIOD
            old, actual = (harmonic_difference(raw_cfo, v) for v in (lifted, original_lifted))
            original_sat = original.catalogue.satellites[regional["source_indices"][index]]
            tle = current[number]
            olines = export_tle(original_sat)
            osha = sha256(("\n".join(olines) + "\n").encode()).hexdigest()
            v5_phase = saved["phases"][index]
            lean_phase = points[0]["phase_s"]
            site = saved["position"]
            one = regional["bank"]
            orb = dict(
                time_s=one["time_s"],
                position_km=one["position_km"][index : index + 1],
                velocity_km_s=one["velocity_km_s"][index : index + 1],
            )
            geometry = prepare_phase_geometry(orb, t, v5_phase)
            v5_hz = phase_linear_frequency(geometry, *site, rf_hz=rf)[0][0]
            phase_check = phase_frequency_grid(orb, t, *site, phase_seconds=v5_phase, rf_hz=rf)[0][
                0
            ]
            knots = np.r_[
                lean.grid._knots(dt, 5)[0] - np.arange(4, 0, -1) * 5,
                lean.grid._knots(dt, 5),
                lean.grid._knots(dt, 5)[-1] + np.arange(1, 5) * 5,
            ]
            banks = []
            for sat in (Satrec.twoline2rv(*tle["lines"]), original_sat):
                cat = ElementSetCatalogue((str(number),), (number,), (sat,))
                p, v, valid = ecef_states(cat, anchor, knots)
                if not valid.all():
                    raise ValueError("cannot propagate causal bank on common padded time support")
                banks.append(lean.grid.Tile(np.zeros(3), np.eye(3), dt, knots, p, v, {}))

            def project(bank, loc, phase, times=t, carrier=rf):
                return lean.project(bank, 0, times, geodetic_to_ecef_km(*loc, 0.0), phase, carrier)[
                    0
                ]

            lean_xyz = sealed["estimates"]["v5_full_lean"]["arms"][arm]["forced_latlon"]
            predicted = np.array([p["predicted_hz"] for p in points])
            baseline = np.array([p["orbit_hz"] for p in points])
            roundtrip = project(banks[0], lean_xyz, lean_phase) - baseline
            if rms(roundtrip) > 0.01:
                raise ValueError(
                    f"captured lean projection changes the earlier budget: {rms(roundtrip)} Hz"
                )
            lean_clock = predicted - baseline
            target_orbits = (
                project(banks[0], site, lean_phase),
                project(banks[1], site, lean_phase),
                project(banks[1], site, v5_phase),
            )
            lane = 2 * (track["receiver"] - 1) + int(track["channel"] > 4)
            beta, smooth = saved["beta"], saved["smooth"]
            v5_affine = beta[lane] + beta[lane + 4] * (t - 150) / 150
            if len(beta) == 9:
                v5_affine += beta[8] * (rf / 1e9 - 11.5)
            v5_smooth = rf / 11.5e9 * projected_receiver_basis(t) @ smooth[track["receiver"] - 1]
            v5_resid = np.array([r["archived_v5_residual_hz"] for r in points])
            conditional = original_lifted - v5_resid
            remainder = conditional - target_orbits[2] - v5_affine - v5_smooth
            stages = swap_states(
                baseline, target_orbits, lean_clock, v5_affine + v5_smooth, remainder, old, actual
            )
            d = dict(
                id=case,
                arm=arm,
                component=name,
                norad=number,
                candidate_index=index,
                count=len(t),
                time_max_difference_s=float(max(abs(t_native - t))),
                alias_delta_cycles=np.unique(actual - old).tolist(),
                archived_whole_alias=alias,
                candidate_same_tle=osha == tle["sha256"],
                original_pair_sha256=osha,
                lean_pair_sha256=tle["sha256"],
                lean_element=tle,
                original_provenance=original.provenance[regional["source_indices"][index]],
                lean_phase_s=lean_phase,
                archived_phase_s=v5_phase,
                interpolation_rms_hz=rms(v5_hz - target_orbits[2]),
                roundtrip_rms_hz=rms(roundtrip),
                projection_formula_rms_hz=rms(v5_hz - phase_check),
                observed_aliases=np.unique(actual).tolist(),
                term_rms_hz=dict(
                    site=rms(target_orbits[0] - baseline),
                    tle=rms(target_orbits[1] - target_orbits[0]),
                    phase=rms(target_orbits[2] - target_orbits[1]),
                    clock=rms(v5_affine + v5_smooth - lean_clock),
                    smooth=rms(v5_smooth),
                    conditional_remainder=rms(remainder),
                ),
                residual_rms_hz={
                    key: rms((lifted if key == "lean_prediction" else original_lifted) - v)
                    for key, v in stages.items()
                    if key != "alias_delta_hz"
                },
            )
            summary.append(d)
            for i, row in enumerate(points):
                observed.append(
                    dict(
                        case=case,
                        arm=arm,
                        id=row["id"],
                        component=name,
                        norad=number,
                        time_s=t[i],
                        rf_hz=rf,
                        native_hz=raw_cfo[i],
                        graph_hz=graph[i],
                        lean_lift=int(old[i]),
                        archived_lift=int(actual[i]),
                        lean_clock_hz=lean_clock[i],
                        archived_clock_affine_hz=v5_affine[i],
                        archived_clock_smooth_hz=v5_smooth[i],
                        lean_observed_hz=lifted[i],
                        archived_observed_hz=original_lifted[i],
                        archived_residual_hz=v5_resid[i],
                        conditional_remainder_hz=remainder[i],
                        predictions_hz={
                            key: v[i] for key, v in stages.items() if key != "alias_delta_hz"
                        },
                    )
                )
    save_json(
        OUTPUT / f"{case}-components.json",
        dict(
            case=case,
            request_sha256=publication["request_sha256"],
            source_sha256=request["source"]["sha256"],
            archive_sha256=publication["artifact_sha256"],
            native_sha256=item["native"]["sha256"],
            lean_catalogue_sha256=packet["catalogue"]["sha256"],
            cutoff_ns=cutoff,
            anchor_ns=anchor,
            owner_model=lock["files"],
            components=summary,
        ),
    )
    write(
        OUTPUT / f"{case}-points.jsonl.gz",
        gzip.compress(b"".join(encoded(p) + b"\n" for p in observed), mtime=0),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    run(parser.parse_args().case)
