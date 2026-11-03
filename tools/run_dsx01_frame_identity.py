"""Bounded M-step for timing-linked label proposals; no GPS in selection."""

import argparse
import copy
import hashlib
import json

import run_dsx01_joint_marginal as engine
from associate_merged_track_catalogue import write
from dsx01_frame_joint import FrameJoint
from run_dsx01_frame_joint import OUTPUT


def run(case):
    path = OUTPUT / "identity_probe" / case / "proposals.json"
    proposal = json.loads(path.read_text())
    choices = [
        r for r in proposal["proposals"] if r["anchor_gain"] >= 1 and r["selected"] != "incumbent"
    ]
    directory = OUTPUT / "identity_refits" / case
    directory.mkdir(parents=True, exist_ok=True)
    write(
        directory / "selection_protocol.json",
        dict(
            no_GPS_or_future_TLE_in_selection=True,
            proposal_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            minimum_full_anchor_gain=1.0,
            maximum_msteps=1,
            common_c0_selected_grid_three_starts_24_iterations_three_phase_rounds=True,
            original_point_population_preserved=True,
            aliases_recomputed_only_for_relabelled_fragments_at_blind_parent=True,
            retained_incumbent_unless_full_c0_score_and_residual_gates_improve=True,
            selected_proposals=len(choices),
        ),
    )
    if not choices:
        return
    chosen = max(choices, key=lambda r: r["anchor_gain"])
    item = next(v for v in chosen["variants"] if v["name"] == chosen["selected"])
    parent = (
        engine.ROOT
        / "reports/2026_10_18_dsx01_satellite_prior_controls"
        / case
        / "normal/endpoints.json"
    )
    fits = json.loads(parent.read_text())["fits"]
    proposed = copy.deepcopy(fits["c0"])
    proposed.update(
        rows=item["seed"]["rows"],
        state=item["seed"]["state"],
        aliases=item["aliases"],
        proposed_seed_only_not_completed_fit=True,
    )
    source = dict(c0=proposed, fitted_c=fits["fitted_c"])
    write(
        directory / "seed.json",
        dict(
            source=source,
            changed_components=item["changed_components"],
            proposed_norad=int(item["name"]),
            frame_edge=chosen["edge"],
        ),
    )
    engine.OUTPUT = directory / "mstep"
    engine.JointMarginal = FrameJoint
    engine.incumbents = lambda *args: dict(proposal=source)
    engine.run(case, variants=("linked_300",))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", required=True, choices=["DSX01-S01", "DSX01-S04"])
    run(p.parse_args().case)
