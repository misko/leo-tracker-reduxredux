"""Audit paired predictive geometry inside one genuine dense publication grid."""

import argparse
from pathlib import Path
from runpy import run_path
from unittest.mock import patch

from aperture_trial import read, write
from cold_track_row_transfer import DENSE, GEOGRAPHIC, PREVIOUS, RAW, same_route
from cold_track_row_trial import REPLAY_PIN
import dense_full_short_crossover as crossover
from grid_phase_state_reuse import GridAudit, SOURCES


SCIENCE = ("status", "reason", "orbit_policy", "arms", "owners", "selected_rows", "grid_points", "grid", "science",
           "associated", "objective_replay", "graph", "track_asset_sha256", "visited_probes")


def run(output):
    if crossover.file_sha(DENSE) != REPLAY_PIN:
        raise ValueError("The archived matched grid replay changed")
    baseline = read(DENSE)
    archived_source = PREVIOUS / "reports/ALGO08/v3/dense_full_short_crossover.py"
    if crossover.file_sha(archived_source) != baseline["code"][archived_source.name]:
        raise ValueError("The archived detector verification source changed")
    verify = run_path(str(archived_source))["raw_candidate"]
    original_solve = crossover.solve
    audit = GridAudit()

    def solve(*args):
        from leo.presentation import localization_v3 as presentation
        from tools import algo08_position

        original_packet = algo08_position.selected_packet

        def selected(*args, **kwargs):
            sample = audit.grid(presentation.sample_position_grid)
            with patch.object(presentation, "sample_position_grid", sample):
                return original_packet(*args, **kwargs)

        with patch.object(algo08_position, "selected_packet", selected):
            return original_solve(*args)

    output.mkdir(exist_ok=False)
    replay = output / "replay.json"
    with patch.object(crossover, "raw_candidate", verify), patch.object(crossover, "solve", solve):
        crossover.run(RAW / "publication", RAW / "process.json", GEOGRAPHIC, replay)
    candidate = read(replay)
    control_attempt, = baseline["attempts"]
    candidate_attempt, = candidate["attempts"]
    direct = audit.report()
    checks = {key: candidate[key] == baseline[key] for key in SCIENCE}
    checks.update(route=same_route(candidate_attempt, control_attempt),
                  proof=candidate["regional"][0]["result"] == baseline["regional"][0]["result"],
                  dense_grid=(candidate["grid"]["complete"] and candidate["grid_points"] == 179),
                  geometry=bool(direct["calls"]) and all(row["exact"] for row in direct["calls"]),
                  same_handoff=candidate["posterior_grid_handoff"]["factor_calls"] == len(direct["calls"]) == 356,
                  predictor_domain=direct["private_views"] == 2 and all(row["altitude"] == 0. for row in direct["calls"]))
    timings = {name: candidate[name] for name in ("solve", "posterior_grid_handoff", "grid_kernel", "curved_design")}
    timings["candidate_evidence"] = candidate_attempt["standard_evidence_clocks"]
    timings["matched_original_evidence"] = control_attempt["standard_evidence_clocks"]
    pins = {path.name: crossover.file_sha(path) for path in (
        Path(__file__), Path(__file__).with_name("grid_phase_state_reuse.py"),
        Path(__file__).with_name("grid-phase-state-reuse-protocol.md"), archived_source, replay,
    )}
    write(output / "grid-audit.json", dict(source_sha256=pins, installed=SOURCES, archived_replay_sha256=REPLAY_PIN,
          input_sha256=candidate["raw"]["raw_native_sha256"], track_asset_sha256=candidate["track_asset_sha256"],
          archive=candidate["raw"]["holder"]["archive"], science_sha256=candidate["science"],
          machine=candidate["machine"], checks=checks, times=timings, **direct))
    if not all(checks.values()):
        raise ValueError(f"Genuine grid did not reproduce the archived evidence: {checks}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output)
