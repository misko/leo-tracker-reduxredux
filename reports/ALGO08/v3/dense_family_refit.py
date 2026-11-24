"""Replay the signed dense 8 ms result and test its one late family swap."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from time import perf_counter, process_time
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
CONTROL = Path("/dev/shm/leo-exact-solver-0008-result01")
HYBRID = Path("/dev/shm/leo-dense-8ms-prefix-fit01")
CONTROL_SOURCES = Path("/dev/shm/leo-v3-exact-solver-0008/reports/ALGO08/v3")
JOINT = "candidate/joint-research-receipt.json"
CONTROL_SHA = "c1f7486fb931e782049f6191d6751354cbb908cc739a05248c058e5ef2e9ac3a"
HYBRID_SHA = "f70566671491da7eb1b5b572e60ffd5eb5ab65c398757de9e1e40137d2784c95"
BINDING_SHA = "4c74d02b61a428ef87ffbaba45b950188b7fd2e33f0dae9e5eda64d5b3e8a30f"
ARMS = ("c0", "fitted_c")
OLD, NEW = 67511, 63478


def checked(path, pin):
    data = path.read_bytes()
    if sha256(data).hexdigest() != pin:
        raise ValueError(f"Unexpected saved input {path}")
    return data


def clock():
    return process_time(), perf_counter()


def spent(start):
    cpu, wall = clock()
    return dict(cpu_s=cpu-start[0], elapsed_s=wall-start[1])


def unique(rows):
    result = {oid: (norad, role) for oid, norad, role in rows}
    if len(result) != len(rows):
        raise ValueError("An observation has two selected owners")
    return result


def contrast(control, hybrid):
    swaps = {}
    for arm in ARMS:
        old, new = (unique(candidate[arm]) for candidate in (control, hybrid))
        changed = {oid for oid in old.keys() & new.keys() if old[oid][0] != new[oid][0]}
        if (changed != {oid for oid, (norad, _) in new.items() if norad == NEW}
                or any(old[oid] != (OLD, new[oid][1]) for oid in changed)):
            raise ValueError("The observed contrast is not a single role-preserving family")
        swaps[arm] = changed
    if not swaps["c0"] or swaps["c0"] != swaps["fitted_c"]:
        raise ValueError("The calibration arms disagree on the family contrast")
    return swaps["c0"]


def exchanged(signed, members, changed):
    """Switch complete published arcs and keep the signed track layout and weights."""
    import numpy as np

    affected = {key for key, (_, _, ids) in members.items() if ids & changed}
    if not affected or any(members[key][1] != NEW or not members[key][2] <= changed for key in affected):
        raise ValueError("The contrast crosses the boundary of an active arc")
    tracks = {track["key"]: track for track in signed["scan"].tracks}
    seed = signed["node"]["seed"]
    labels = {int(norad): index for index, norad in enumerate(signed["scan"].norads)}

    def changed_row(row):
        return row["component"] in affected

    rows = [dict(row, candidate_index=labels[OLD], candidate_norad=OLD) if changed_row(row)
            else row for row in seed["rows"]]
    entries = [dict(entry, candidate_index=labels[OLD], norad=OLD) if changed_row(entry)
               else entry for entry in signed["entries"]]
    keys = {row["component"] for row in seed["rows"] if row["active_curvature"]} | {
        entry["component"] for entry in signed["entries"]}
    if affected - keys:
        raise ValueError("A switched arc is absent from the signed likelihood")
    before, after = (sorted({row["candidate_index"] for row in layout if row["active_curvature"]})
                     for layout in (seed["rows"], rows))
    if labels[OLD] not in before or any(entry["candidate_index"] not in after for entry in entries):
        raise ValueError("The replacement needs independent curved support in the signed likelihood")
    choose = [before.index(label) for label in after]
    arms = {arm: dict(record, phase_reference=record["phase_reference"][choose])
            for arm, record in signed["arms"].items()}
    detail = {key: dict(role=members[key][0], active_ids=sorted(members[key][2]),
                        masked_ids=sorted(set(tracks[key]["observation_ids"]) - members[key][2]),
                        rf_hz=tracks[key]["rf_hz"]) for key in sorted(affected)}
    return dict(signed, node=dict(signed["node"], seed=dict(seed, rows=rows)), entries=entries,
                arms=arms, means=np.asarray(signed["means"])[choose]), detail


def witness(record):
    return dict(latlon=record["endpoint_latlon"], east_north_km=record["endpoint_east_north_km"],
                rf_rms_hz=record["RMS_hz"], objective=record["negative_twice_elbo"],
                curved_objective=record["curved_negative_twice_elbo"],
                calibration=record["state"]["beta"],
                curved_points=record["active_points"], predictive_points=record["predictive_points"],
                failed_curved=[row["component"] for row in record["gates"]["tracks"] if not row["compatible"]],
                failed_predictive=[row["component"] for row in record["linear_gates"] if not row["compatible"]])


def slope_audit(signed, arm, details):
    """Measure shape and trend of both orbits at the same position and RF state."""
    import numpy as np
    from leo.analysis.research.continuous_curve_fit import paired_phase_frequency

    scan = signed["scan"]
    state = signed["arms"][arm]["state"]
    tracks = {track["key"]: (i, track) for i, track in enumerate(scan.tracks)}
    labels = {int(norad): index for index, norad in enumerate(scan.norads)}
    result = {}
    for key, detail in details.items():
        i, track = tracks[key]
        use = np.isin(track["observation_ids"], detail["active_ids"])
        times = track["times"][use]
        centered = times - times.mean()
        q = track["rf_hz"] / 11.5e9
        cfo = track["values"] - scan.hardware(track, state["beta"])
        cfo -= q * scan.rx_basis[i] @ state["smooth"][track["receiver"] - 1]
        row = result[key] = dict(points=len(times), measured_hz_per_s=float(centered @ cfo[use] / (centered @ centered)))
        for norad in (OLD, NEW):
            j = labels[norad]
            freq, elev = paired_phase_frequency(scan.sky, times, np.full(len(times), j), state["phases"],
                                                 *signed["arms"][arm]["endpoint_latlon"])
            r = cfo[use] - q * freq
            row[str(norad)] = dict(orbit_hz_per_s=float(centered @ (q * freq) / (centered @ centered)),
                                   centered_residual_rms_hz=float(np.std(r)), min_elevation_deg=float(elev.min()))
    return result


def fixed(signed, arm):
    from leo.analysis.localization_v3 import event_position as model

    record = signed["arms"][arm]
    p = model.make_event_problem(signed["scan"], signed["node"], signed["keep"], arm, record["phase_reference"],
                                 signed["powers"], signed["means"], signed["model"], [])
    model.attach_event_predictive(p, signed["entries"], signed["powers"])
    model.cached(p)
    return model.summary(p, record["endpoint_east_north_km"], signed["entries"])


def audit(signed, changed):
    import numpy as np
    from blind_joint_finish import arm_finish
    from leo.analysis.localization_v3 import position
    from leo.analysis.localization_v3.history_policy import pair_passes
    from local_future_repair import memberships
    from tools.pipeline_eval.variants.compact_cavity_optimizer import INITIAL_RADIUS_KM
    from tools.pipeline_eval.variants.experimental.regional_bound_guard import inspect_boundary

    def paired_members(candidate):
        first, second = (memberships(candidate, arm) for arm in ARMS)
        if first != second:
            raise ValueError("Expected the same memberships in both arms")
        return first

    members = paired_members(signed)
    start = clock()
    replay = {arm: fixed(signed, arm) for arm in ARMS}
    identity_cost = spent(start)
    if (paired_members(dict(signed, arms=replay)) != members
            or any(not np.allclose(replay[arm][key], signed["arms"][arm][key], rtol=0, atol=1e-8)
                   for arm in ARMS for key in ("RMS_hz", "negative_twice_elbo", "endpoint_east_north_km"))):
        raise ValueError("Original signed endpoints, memberships or likelihood did not replay")
    start = clock()
    alternate, arcs = exchanged(signed, members, changed)
    staged = {arm: fixed(alternate, arm) for arm in ARMS}
    staged_cost = spent(start)
    half = signed["scan"].search_region.half_width_km
    expected = {key: (role, OLD if key in arcs else norad, ids) for key, (role, norad, ids) in members.items()}
    result = dict(identity={arm: witness(record) for arm, record in replay.items()}, identity_cost=identity_cost,
                  arcs=arcs, fixed_alternate={arm: witness(record) for arm, record in staged.items()},
                  fixed_alternate_cost=staged_cost, decision="fixed_point_gate_failed")
    if any(r["failed_curved"] or r["failed_predictive"] for r in result["fixed_alternate"].values()):
        result["matched_slopes"] = {arm: slope_audit(signed, arm, arcs) for arm in ARMS}
        return result
    if paired_members(dict(alternate, arms=staged)) != expected:
        raise ValueError("Unexpected membership outside the alternate family")
    start = clock()
    paired = {}
    solve = position.fit
    for name, trial in (("identity", signed), ("alternate", alternate)):
        paired[name] = {}
        for arm in ARMS:
            anchor = trial["arms"][arm]["endpoint_east_north_km"]

            def bounded(problem, point, *, iterations):
                problem.lower = np.maximum(problem.lower, anchor - INITIAL_RADIUS_KM)
                problem.upper = np.minimum(problem.upper, anchor + INITIAL_RADIUS_KM)
                return solve(problem, point, iterations=iterations)

            with patch.object(position, "fit", bounded):
                paired[name][arm] = arm_finish(trial["scan"], trial["node"], trial["keep"], arm,
                    trial["arms"][arm]["phase_reference"], trial["powers"], trial["means"], trial["model"],
                    trial["entries"], anchor)
    result["refit_cost"] = spent(start)
    result["refit"] = {name: {arm: dict(witness(r), phase_change_s=r["final_phase_change_s"],
                                         refreshes=len(r["history"])) for arm, r in pair.items()}
                       for name, pair in paired.items()}
    checks = result["gates"] = {}
    for name, pair in paired.items():
        endpoints = {arm: r["endpoint_east_north_km"] for arm, r in pair.items()}
        same_basin = all(np.max(abs(np.asarray(step["fit"]["parameters"])-replay[arm]["endpoint_east_north_km"]))
                         <= INITIAL_RADIUS_KM for arm in ARMS for step in pair[arm]["history"])

        def no_boundary_probe():
            raise ValueError("Conditional interior study does not authorize new exterior probes")

        checks[name] = dict(paired=pair_passes(pair, include_linear=True, half_width_km=half), same_basin=same_basin,
                            exterior=inspect_boundary(endpoints, 2*half, no_boundary_probe, terminal_only=True))
    for name, trial in (("identity", signed), ("alternate", alternate)):
        gate = checks[name]
        gate["accepted"] = bool(gate["paired"] and gate["same_basin"] and not gate["exterior"]["would_withhold"]
                                and not gate["exterior"].get("diagnostic_error")
                                and paired_members(dict(trial, arms=paired[name])) == (members if name == "identity" else expected))
    result["decision"] = "matched_same_basin_refit" if all(gate["accepted"] for gate in checks.values()) else "refit_gate_failed"
    return result


def terminal(root, joint):
    from leo.contracts.digests import canonical_digest

    receipt = joint["receipt"]
    path = root / "fast-scan-automatic-work" / receipt["run_id"] / "terminal.json"
    data = json.loads(path.read_bytes())
    if receipt["decision"] != "complete" or canonical_digest(data) != receipt["terminal_sha256"]:
        raise ValueError("The archived publication is incomplete or differs from its receipt")
    return data


def verify_publication(target, result, archive, expected):
    from publication_media_checks import verify_position_sidecars

    receipt, historical = (candidate["receipt"] for candidate in (result, expected))
    if (terminal(target, result) != terminal(archive, expected)
            or any(receipt[key] != historical[key] for key in
                   ("run_id", "session_id", "window_count", "counts", "region", "decision", "terminal_sha256"))
            or result["selected_rows"] != expected["selected_rows"]
            or result["evidence"]["images"] != expected["evidence"]["images"]
            or result["solve"]["objective_replay"] != {arm: 0. for arm in ARMS}):
        raise ValueError("The before-intervention full signed publication did not reproduce")
    return verify_position_sidecars(archive, target, receipt["run_id"],
                                    expected["evidence"]["images"], result["evidence"]["images"])


def visits_for(request, changed):
    packet = json.loads(checked(Path(request["packet"]), request["native"].removeprefix("sha256:")))
    source = packet["source"]
    visits = {}
    for probe in source["probes"]:
        key = f"{source['session_id']}:{probe['receiver_id']}:{probe['valid_start_counter']}"
        oid = "sha256:" + sha256(key.encode()).hexdigest()
        if oid in changed:
            visits[oid] = probe["visit_index"]
    if visits.keys() != changed or min(visits.values()) < 192:
        raise ValueError("Expected every affected observation in the unmodified suffix")
    return visits


def validate_archive(request):
    from aperture_trial import archive_identity
    from leo.operations.tle_archive import TleArchiveReader

    archive = Path(request["archive"]["root"])
    refs = TleArchiveReader(archive).list_snapshots("space-track")
    if (archive_identity(archive)["snapshots_sha256"] != request["archive"]["snapshots_sha256"]
            or len(refs) != request["archive"]["records"]
            or not all(r.path.resolve(strict=True).is_relative_to(Path("/dev/shm"))
                       and r.collected_utc_ns < request["cutoff_utc_ns"] for r in refs)):
        raise ValueError("Only the enrolled causal orbit archive is permitted")


def worker(root):
    import cumulative_grid_projection as baseline
    import empty_bootstrap
    import joint_publication
    import exact_solver_0008
    from aperture_trial import THREADS, read, write
    from dense_geographic_trial import host

    machine = host()
    if any(os.environ.get(key) != "1" for key in (*THREADS, "OMP_THREAD_LIMIT")):
        raise ValueError("Require all six numerical thread settings")
    job = HYBRID / "binding.json"
    request = json.loads(checked(job, BINDING_SHA))
    original, hybrid = (json.loads(checked(folder / JOINT, pin)) for folder, pin in
                        ((CONTROL, CONTROL_SHA), (HYBRID, HYBRID_SHA)))
    changed = contrast(original["selected_rows"], hybrid["selected_rows"])
    if len(changed) != 222 or any(j["route_details"]["signed"]["status"] != "accepted" for j in (original, hybrid)):
        raise ValueError("This trial is confined to the enrolled completed signed 222-point contrast")
    visits = visits_for(request, changed)
    for name, path in request["libraries"].items():
        checked(Path(path), request["pins"]["libraries"][name])
    checked(Path(request["projection"]), request["pins"]["projection"])
    for name, pin in request["pins"]["sources"].items():
        checked(CONTROL_SOURCES / name, pin)

    captured = []
    original_route = joint_publication.make_route
    load = empty_bootstrap.load_runtime
    recording = Path(request["recording"])

    def deny_raw(event, info):
        if event == "open" and isinstance(info[0], (str, bytes)) and Path(os.fsdecode(info[0])).is_relative_to(recording):
            raise RuntimeError("The saved-only worker cannot open files in the raw recording")

    sys.addaudithook(deny_raw)

    def runtime():
        loaded = load()
        validate_archive(request)
        return loaded

    def route(*args, **kwargs):
        def collect(*, ordinary, signed):
            captured.append(signed)

        return original_route(*args, **kwargs, collect=collect)

    def detector(current, _specification, _mixed_recipe):
        if current != request:
            raise ValueError("Unexpected saved-worker binding")
        return request["detector"].removeprefix("sha256:")

    when = clock()
    target = root / "identity-publication"
    with (patch.object(joint_publication, "make_route", route), patch.object(baseline, "saved_detector", detector),
          patch.object(empty_bootstrap, "load_runtime", runtime)):
        exact_solver_0008.worker(job, target)
    publication_cost = spent(when)
    from local_future_repair import memberships

    expected_terminal = terminal(HYBRID / "candidate", hybrid)
    full = read(target / "joint-research-receipt.json")
    if len(captured) != 1 or request["native"] != expected_terminal["native_sha256"]:
        raise ValueError("Expected one signed context from the archived hybrid packet")
    sidecars = verify_publication(target, full, HYBRID / "candidate", hybrid)
    signed, = captured
    for arm in ARMS:
        actual = sorted((oid, norad, role) for role, norad, ids in memberships(signed, arm).values() for oid in ids)
        if actual != sorted(map(tuple, hybrid["selected_rows"][arm])):
            raise ValueError("Captured signed rows differ from the replayed publication")
    result = audit(signed, changed)
    write(root / "sealed.json", dict(result, saved_publication_cost=publication_cost, machine=machine,
                                    replay_terminal=full["receipt"]["terminal_sha256"], signed_packet=request["native"],
                                    archive=request["archive"]["snapshots_sha256"], changed=len(changed), raw_reads=0,
                                    sidecar_parity=sidecars, visits=visits,
                                    comparison_receipts=dict(control=CONTROL_SHA, hybrid=HYBRID_SHA),
                                    source_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))


def score(root):
    from aperture_trial import read, write
    from triage_bounds import calibration_comparison

    path = root / "sealed.json"
    sealed = read(path)
    sources = {name: terminal(folder / "candidate", json.loads(checked(folder / JOINT, pin)))
               for name, folder, pin in (("control", CONTROL, CONTROL_SHA), ("hybrid", HYBRID, HYBRID_SHA))}
    if sealed["decision"] == "matched_same_basin_refit":
        sources.update({f"refit_{name}": dict(arms=arms) for name, arms in sealed["refit"].items()})
    write(root / "scored.json", dict(seal_sha256=sha256(path.read_bytes()).hexdigest(),
                                    geography=calibration_comparison(sources)))


if __name__ == "__main__":
    sys.path[:0] = [str(CONTROL_SOURCES), str(HERE)]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("worker", "score"))
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    {"worker": worker, "score": score}[args.mode](args.root)
