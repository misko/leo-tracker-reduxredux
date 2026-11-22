"""Read archived solver profiles and published paths without running inference."""

import argparse
import json
import pstats
from hashlib import sha256
from pathlib import Path

MEASUREMENTS = Path(__file__).resolve().parent / "measurements"
FUNCTIONS = {
    "serialize_path": ("position_path.py", "recorded_fit_path"),
    "selected_packet": ("algo08_position.py", "selected_packet"),
    "grid": ("position_grid.py", "sample_position_grid"),
    "optimizer": ("compact_cavity_optimizer.py", "bounded_secant"),
    "curvature": ("compact_cavity_optimizer.py", "linearize"),
    "curved_projection": ("marginal.py", "_phase_geometry"),
    "predictive_projection": ("predictive_linear.py", "geometry_features"),
    "orbital_mode_bank": ("orbit_modes.py", "build_modes"),
    "cavity_calibration": ("family_cavity.py", "family_data"),
    "dense_fallback": ("hierarchical.py", "hierarchical_bound"),
    "prepare_native": ("localization_v3.py", "prepare_native_scan"),
    "prepare_tracks": ("tracks.py", "prepare_tracks"),
}


def lookup(rows, filename, function):
    matches = [value for (path, _, name), value in rows.items()
               if Path(path).name == filename and name == function]
    if len(matches) != 1:
        raise ValueError(f"Expected one profiled call site for {filename}::{function}")
    return matches[0]


def profile_readout(path, expected_digest):
    digest = sha256(path.read_bytes()).hexdigest()
    if digest != expected_digest:
        raise ValueError("Profiler input differs from the recorded digest")
    profile = pstats.Stats(str(path))
    profile.calc_callees()
    rows = profile.stats
    totals = {}
    for label, (filename, function) in FUNCTIONS.items():
        _, calls, own, inclusive, _ = lookup(rows, filename, function)
        totals[label] = dict(calls=calls, own_cpu_s=own, inclusive_cpu_s=inclusive)
    cavity = lookup(profile.all_callees, "family_cavity.py", "family_data")
    calls = {
        label: lookup(cavity, filename, function)
        for label, filename, function in (
            ("construct_models", "event_position.py", "make_event_problem"),
            ("fit_phase_states", "marginal.py", "state"),
            ("read_last_posterior", "history_position.py", "calculate"),
        )
    }
    return dict(
        profile_sha256=digest,
        profile_cpu_s=profile.total_tt,
        totals=totals,
        cavity_calls={name: dict(calls=row[0], inclusive_cpu_s=row[-1])
                      for name, row in calls.items()},
        cavity_setup_and_final_read_cpu_ceiling_s=(
            calls["construct_models"][-1] + calls["read_last_posterior"][-1]
        ),
    )


def accepted_path(terminal):
    path = terminal["evidence"]["position_path"]
    stage, = path["stages"]
    arms = {}
    for arm in ("c0", "fitted_c"):
        recorded = stage["arms"][arm]
        counts = []
        for row in recorded["rounds"]:
            if (row["detail"] != "accepted_optimizer_iterates" or not row["points"]
                    or row["points"][-1] != row["endpoint"]):
                raise ValueError("Path has no recorded accepted-step history for a round")
            counts.append(len(row["points"]))
        arms[arm] = dict(points_by_round=counts, accepted_moves=sum(n - 1 for n in counts))
    return arms


def read_json(path):
    return json.loads(path.read_bytes())


def summarize(bench):
    profiles = {
        label: profile_readout(bench / directory / "solver.prof",
                               read_json(MEASUREMENTS / receipt)["profile_sha256"])
        for label, directory, receipt in (
            ("DS30-0008", "restored-graph-profile-0008", "restored-scout-0008-solver-profile.json"),
            ("south-portable", "screened-stock-profile", "screened-stock-profile.json"),
        )
    }
    path_bindings = read_json(MEASUREMENTS / "solver-deployed-margin-recovery.json")["cases"]
    paths = {}
    for label in ("DS30-0008", "DS30-0374", "south"):
        saved = bench / "deployed-margin-saved-cross" / label / "terminal.json"
        evidence = saved.read_bytes()
        digest = sha256(evidence).hexdigest()
        if digest != path_bindings[label]["restored_terminal_sha256"]:
            raise ValueError(f"Path source differs from the audited restored solver for {label}")
        paths[label] = dict(terminal_sha256=digest, arms=accepted_path(json.loads(evidence)))
    return dict(frozen_profiles=profiles, restored_margin_paths=paths)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("bench", type=Path)
    cli.add_argument("output", type=Path)
    options = cli.parse_args()
    audited = summarize(options.bench)
    with options.output.open("x") as stream:
        json.dump(audited, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
