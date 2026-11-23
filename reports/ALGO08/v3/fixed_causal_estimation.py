"""Mask the original unfiltered signed likelihood on frozen assignments."""

import argparse
from copy import copy
from hashlib import sha256
from pathlib import Path
import subprocess
from time import perf_counter, process_time
from types import SimpleNamespace

from aperture_trial import ARMS, RELEASE, read, write


HERE = Path(__file__).resolve().parent
CASES = ("north", "physical")
BASE = {
    "physical": Path("/var/tmp/leo-short-graph-20261123-physical"),
    "north": Path("/var/tmp/leo-north-short-regional-nov23/containing"),
}
FORWARD = {
    "physical": Path("/var/tmp/leo-causal-weak-south-nov23/physical"),
    "north": Path("/var/tmp/leo-north-short-causal-raw-nov23/containing"),
}


def clock():
    return process_time(), perf_counter()


def spent(since):
    now = clock()
    return dict(cpu_s=now[0]-since[0], elapsed_s=now[1]-since[1])


def flatten(members):
    return sorted((oid, satellite, role) for role, satellite, ids in members.values() for oid in ids)


def retained_members(members, selected):
    return {key: (role, norad, observations & selected)
            for key, (role, norad, observations) in members.items()}


def restriction(signed, members, selected):
    """Keep the original curved design and subset existing predictive inputs."""
    import numpy as np
    from leo.analysis.research.retained_track_likelihood import whitening

    original = signed["scan"]
    scan = copy(original)
    scan.tracks, scan.white, scan.rx_basis, scan.index = map(list, (
        original.tracks, original.white, original.rx_basis, original.index))
    tracks = {track["key"]: track for track in original.tracks}
    parts = []
    retained = retained_members(members, selected)
    for row in signed["node"]["seed"]["rows"]:
        if row["active_curvature"]:
            key = row["component"]
            use = retained.get(key, (None, None, frozenset()))[2]
            parts.append(np.isin(tracks[key]["observation_ids"], sorted(use)))
    keep = np.concatenate(parts)
    if keep.shape != signed["keep"].shape or np.any(keep & ~signed["keep"]):
        raise ValueError("Restriction changed the original curved layout or activated a formerly rejected row")
    entries = []
    for entry in signed["entries"]:
        index, key = entry["track_index"], entry["component"]
        track = original.tracks[index]
        if track["key"] != key or frozenset(track["observation_ids"]) != members[key][2]:
            raise ValueError("Predictive data do not match the original published arc")
        mask = np.isin(track["observation_ids"], sorted(retained[key][2]))
        if mask.all():
            entries.append(entry)
            continue
        ids = [oid for oid, use in zip(track["observation_ids"], mask, strict=True) if use]
        track = dict(track, observation_ids=ids, times=track["times"][mask], values=track["values"][mask])
        scan.tracks[index] = track
        scan.white[index] = whitening(track["times"])
        scan.rx_basis[index] = original.rx_basis[index][mask]
        scan.index[index] = original.index[index][mask]
        entries.append(dict(entry, observation_ids=ids, points=len(ids)))
    return dict(signed, scan=scan, keep=keep, entries=entries)


class FixedCausal:
    def __init__(self, required):
        self.required = required
        self.audit = {}
        self.native = None

    def bind(self, native, assets):
        from leo.analysis.localization_v3.tracks import winning_observations
        from leo.contracts.digests import canonical_digest
        from local_future_policy import TRACKS_SHA256
        from north_factor_swap import continued

        if self.native is not None or canonical_digest(native) != self.required:
            raise ValueError("Expected one sealed unfiltered short packet")
        if sha256((assets / "tracks.json").read_bytes()).hexdigest() != TRACKS_SHA256:
            raise ValueError("Expected the original installed Graph profile")
        self.native = native
        start = clock()
        forward = continued(native)
        observations, _ = winning_observations(forward)
        self.ids = frozenset(row["observation_id"] for row in observations)
        self.forward_digest = canonical_digest(forward)
        self.selection = spent(start)

    def prepare(self, original, native, *args, **kwargs):
        if self.native is not native:
            raise ValueError("Full Graph preparation received a different packet")
        return original(native, *args, **kwargs)

    def repair(self, prepared, signed, measured):
        import numpy as np
        from blind_joint_finish import arm_finish, readout
        from leo.analysis.localization_v3.history_policy import pair_passes
        from local_future_repair import memberships

        start = clock()
        notes = measured["local_future_repair"] = self.audit
        notes["decision"] = "rejected"
        try:
            original = {arm: memberships(signed, arm) for arm in ARMS}
            if original["c0"] != original["fitted_c"]:
                raise ValueError("Calibrated unfiltered owner maps differ")
            raw = original["c0"]
            eligible = retained_members(raw, self.ids)
            notes.update(unfiltered_arms={arm: dict(latlon=value["endpoint_latlon"], rf_rms_hz=value["RMS_hz"])
                                         for arm, value in signed["arms"].items()},
                         unfiltered_members=flatten(raw), selected_members=flatten(eligible),
                         conditional_aliases=signed["node"]["aliases"],
                         predictive_aliases={e["component"]: e["alias"] for e in signed["entries"]},
                         coverage={key: dict(before=len(values[2]), after=len(eligible[key][2]),
                                             role=values[0], norad=values[1]) for key, values in raw.items()})
            missing = [key for key, values in eligible.items() if not values[2]]
            if missing:
                notes.update(reason="An originally owned arc has no causal support", empty_arcs=missing)
                return prepared, signed
            if raw == eligible:
                notes.update(decision="unchanged", reason="All owned observations pass continuation")
                return prepared, signed
            begin = clock()
            trial = restriction(signed, raw, self.ids)
            notes["mask_cost"] = spent(begin)
            begin = clock()
            try:
                trial["arms"] = {arm: arm_finish(trial["scan"], trial["node"], trial["keep"], arm,
                    signed["arms"][arm]["phase_reference"], trial["powers"], trial["means"], trial["model"],
                    trial["entries"], signed["arms"][arm]["endpoint_east_north_km"]) for arm in ARMS}
            finally:
                notes["refit_cost"] = spent(begin)
            notes["trial_arms"] = {arm: readout(value) for arm, value in trial["arms"].items()}
            if not pair_passes(trial["arms"], include_linear=bool(trial["entries"]),
                               half_width_km=trial["scan"].search_region.half_width_km):
                notes["reason"] = "Original paired compatibility gate"
                return prepared, signed
            if any(memberships(trial, arm) != eligible for arm in ARMS):
                raise ValueError("Retained owner, role or arc identity changed after the refit")
            notes["decision"] = "proposed"
            return prepared, trial
        except (AssertionError, ValueError, np.linalg.LinAlgError) as error:
            notes["reason"] = f"{type(error).__name__}: {error}"
            return prepared, signed
        finally:
            notes["cost"] = spent(start)


def request(case):
    from full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA
    from short_stereo_trial import load_source, source_for

    recording, archive, region, pin, offer, _ = load_source(case)
    saved = source_for(case)[3]
    libraries = read(HERE / "measurements/short-raw-diagnostic.json")["native_libraries"]
    geo, track = (Path(libraries[key]["path"]) for key in ("geographic", "regional"))
    for path, expected in ((geo, GEOGRAPHIC_SHA), (track, TRACK_SCORES_SHA)):
        if sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Unexpected numerical library")
    return dict(saved=str(saved), pin=pin, recording=str(recording), archive=archive,
                region=str(region), offer=offer, geographic=str(geo), regional=str(track))


def worker(path, output):
    from full_short_run import geographic_projection
    from full_short_raw import RECIPE_SHA
    from joint_publication import run

    inputs = read(path)
    policy = FixedCausal(inputs["pin"])
    args = SimpleNamespace(saved=Path(inputs["saved"]), saved_digest=inputs["pin"], output=output,
              recording=Path(inputs["recording"]), archive=Path(inputs["archive"]["root"]),
              region=Path(inputs["region"]), verify_images=True, optimized_full_catalogue=True)
    report = run(args, early_regional=True, keep_selected_rows=True, saved_receiver=RECIPE_SHA,
                 geographic_projector=lambda: geographic_projection(Path(inputs["geographic"]), Path(inputs["regional"])),
                 reuse_cold_rows=True, reuse_grid_phase_states=True, local_future_policy=policy)
    write(output / "fixed-causal-estimation-policy.json", dict(source=inputs["pin"], forward=policy.forward_digest,
          eligible=len(policy.ids), selection=policy.selection, trial=policy.audit, terminal=report["receipt"]["terminal_sha256"]))


def launch(case, root):
    from dense_full_short_raw import usage
    from dense_geographic_trial import host
    from full_short_physical import environment

    settings = host()
    root.mkdir(exist_ok=False)
    path = root / "request.json"
    write(path, request(case))
    env = environment(root)
    python = RELEASE / "venv/bin/python"
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    start, before = perf_counter(), usage()
    run = subprocess.run([python, "-BPs", __file__, "worker", str(path), str(root / "fixed")],
                         env=env, capture_output=True, text=True, timeout=75)
    after = usage()
    write(root / "clock.json", dict(machine=settings, elapsed_s=perf_counter()-start, status=run.returncode,
                                    stderr_tail=run.stderr[-4000:], **{k: after[k]-before[k] for k in before}))
    if run.returncode:
        raise ValueError(run.stderr[-4000:])


def overlap(left, right):
    first = {oid: (norad, role) for oid, norad, role in left}
    second = {oid: (norad, role) for oid, norad, role in right}
    if len(first) != len(left) or len(second) != len(right):
        raise ValueError("Duplicate observation in counterfactual ownership")
    common = first.keys() & second.keys()
    return dict(left=len(first), right=len(second), common=len(common), left_only=len(first.keys()-second.keys()),
                right_only=len(second.keys()-first.keys()),
                norad_changed=sum(first[oid][0] != second[oid][0] for oid in common),
                role_changed=sum(first[oid][1] != second[oid][1] for oid in common))


def score(case, root):
    from aperture_score import references
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from mixture_score import section
    from north_factor_swap import continued
    from short_stereo_trial import CONTROLS, controls, single_packet
    from tools.pipeline_eval.scoring import distance_km
    from triage_bounds import REFERENCE, REFERENCE_SHA256

    expected = request(case)
    if read(root / "request.json") != expected:
        raise ValueError("Expected the original frozen case request")
    original = read(Path(expected["saved"]))
    forward = continued(original)
    policy = read(root / "fixed/fixed-causal-estimation-policy.json")
    if policy["source"] != expected["pin"] or policy["forward"] != canonical_digest(forward):
        raise ValueError("The intervention changed the acquisition or continuation")
    if case == "physical":
        if sha256(REFERENCE.read_bytes()).hexdigest() != REFERENCE_SHA256:
            raise ValueError("Physical scoring roster changed")
        item, = [row["reference"] for row in read(REFERENCE)["cases"] if row["dataset_label"] == "DS30-0016"
                 and row["authority_eligible"] and row["sealed_metadata_digests_verified"]]
        truth = [item["latitude_deg"], item["longitude_deg"]]
    else:
        truth = references()["north-containing"]
    refs = {name: read(HERE / "measurements" / name) for name in CONTROLS}
    stock, stock_pin, stock_terminal, _, _ = controls(case, refs)
    terminal_path, = stock.glob("fast-scan-automatic-work/*/terminal.json")
    outside = read(terminal_path)
    if (canonical_digest(outside) != stock_terminal or outside["region"] != expected["offer"]
            or outside["native_sha256"] != stock_pin or canonical_digest(read(single_packet(stock))) != stock_pin):
        raise ValueError("Installed-v3 scoring control no longer matches its sealed authority")
    stock_figures = artifacts(stock, dict(run_id=terminal_path.parent.name, decision="complete",
                                         terminal_sha256=stock_terminal))
    stock_grid = FastStandardAnalysisStore(stock).position_grid(terminal_path.parent.name)

    def checked(folder, expected_probes):
        run = read(folder / "joint-research-receipt.json")
        receipt = run["receipt"]
        terminal = read(folder / "fast-scan-automatic-work" / receipt["run_id"] / "terminal.json")
        native = read(single_packet(folder))
        artifact = artifacts(folder, receipt)
        if (receipt["decision"] != "complete" or canonical_digest(terminal) != receipt["terminal_sha256"]
                or terminal["region"] != expected["offer"] or canonical_digest(native) != terminal["native_sha256"]
                or native["source"]["probes"] != expected_probes
                or native["source"]["raw_recording_authority_digest"] != original["source"]["raw_recording_authority_digest"]
                or canonical_digest(artifact) != canonical_digest(run["evidence"])
                or not run["solve"]["grid_complete"] or set(run["solve"]["objective_replay"].values()) != {0.}):
            raise ValueError("An archived arm failed its native packet and evidence checks")
        return dict(score=section(terminal["arms"], truth, outside["arms"]), evidence=artifact,
                    terminal=receipt["terminal_sha256"], native=terminal["native_sha256"],
                    solve=run["solve"]), run["selected_rows"]

    stock_result = dict(score=section(outside["arms"], truth, outside["arms"]), evidence=stock_figures,
                        solve=dict(grid_points=stock_grid["evaluated_points"], grid_complete=stock_grid["complete"],
                                   objective_replay=stock_grid["endpoint_objective_replay"]),
                        terminal=stock_terminal, native=stock_pin)
    full, full_owners = checked(BASE[case], original["source"]["probes"])
    rebuilt, forward_owners = checked(FORWARD[case], forward["source"]["probes"])
    fixed, fixed_owners = checked(root / "fixed", original["source"]["probes"])
    notes = policy["trial"]
    applied = notes["decision"] == "accepted"
    baseline_parity, contrasts = {}, {}
    for arm in ARMS:
        old = full["score"]["arms"][arm]
        live = notes["unfiltered_arms"][arm]
        baseline_parity[arm] = dict(endpoint_delta_m=1000*distance_km(old["latlon"], live["latlon"]),
                                    rms_delta_hz=abs(old["rf_rms_hz"]-live["rf_rms_hz"]))
        if sorted(full_owners[arm]) != notes["unfiltered_members"]:
            raise ValueError("The live unfiltered assignments do not reproduce the frozen control")
        if baseline_parity[arm]["endpoint_delta_m"] > .001 or baseline_parity[arm]["rms_delta_hz"] > 1e-4:
            raise ValueError("Baseline numerical drift exceeds the pre-fit comparison tolerances")
        wanted = notes["selected_members"] if applied else notes["unfiltered_members"]
        if sorted(fixed_owners[arm]) != wanted:
            raise ValueError("Fallback or published fixed assignments do not match the frozen support")
        contrasts[arm] = dict(full_vs_rebuilt=overlap(full_owners[arm], forward_owners[arm]),
                              planned_fixed_vs_rebuilt=overlap(notes["selected_members"], forward_owners[arm]),
                              full_vs_applied=overlap(full_owners[arm], fixed_owners[arm]))
    if fixed["terminal"] != policy["terminal"]:
        raise ValueError("The diagnostic policy names a different published terminal")
    fixed["process"] = read(root/"clock.json")
    trial_arms = {arm: {key: row[key] for key in ("latlon", "rf_rms_hz")} for arm, row in notes.get("trial_arms", {}).items()}
    return dict(case=case, input=expected, applied=applied, controls_reproduced=baseline_parity,
                attempts=policy, overlaps=contrasts, truth=truth,
                diagnostic_trial_score=section(trial_arms, truth, outside["arms"]) if trial_arms else None,
                runs=dict(stock=stock_result, unfiltered=full, rebuilt_forward=rebuilt, fixed_publication=fixed))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("trial", "worker", "score"))
    parser.add_argument("case_or_request")
    parser.add_argument("root", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    if args.mode == "worker":
        worker(Path(args.case_or_request), args.root)
    elif args.case_or_request not in CASES:
        parser.error("Expected a frozen development case")
    elif args.mode == "trial":
        launch(args.case_or_request, args.root)
    elif args.receipt is None:
        parser.error("--receipt is required for scoring")
    else:
        write(args.receipt, score(args.case_or_request, args.root))
