"""Read the actual two-arm curved posterior clocks and operands on the genuine saved grid."""

import argparse
from functools import partial
from pathlib import Path
from runpy import run_path
from unittest.mock import patch

from aperture_trial import read, write
from cold_track_row_trial import REPLAY_PIN
from cold_track_row_transfer import DENSE, GEOGRAPHIC, PREVIOUS, RAW, same_route
import dense_full_short_crossover as crossover
from grid_cross_arm_posterior import Audit, PINNED_BOUND, PINNED_HANDOFF
from grid_phase_state_trial import SCIENCE


def run(output):
    if crossover.file_sha(DENSE) != REPLAY_PIN:
        raise ValueError("The archived installed-graph genuine short control changed")
    baseline = read(DENSE)
    archived = PREVIOUS / "reports/ALGO08/v3/dense_full_short_crossover.py"
    if crossover.file_sha(archived) != baseline["code"][archived.name]:
        raise ValueError("The archived source verifier changed")
    verify = run_path(str(archived))["raw_candidate"]
    original_solve = crossover.solve
    audit = Audit()

    def solve(*args):
        from leo.presentation import localization_v3 as presentation
        from tools import algo08_position
        from tools.pipeline_eval.variants import algo08_posterior_handoff as handoff

        original_packet = algo08_position.selected_packet

        def packet(*args, **kwargs):
            sample = audit.grid(presentation.sample_position_grid)
            with patch.object(presentation, "sample_position_grid", sample):
                return original_packet(*args, **kwargs)

        with (patch.object(algo08_position, "selected_packet", packet),
              patch.object(handoff, "grid_handoff", partial(audit.count_handoff, handoff.grid_handoff))):
            return original_solve(*args)

    output.mkdir(exist_ok=False)
    replay = output / "replay.json"
    with patch.object(crossover, "raw_candidate", verify), patch.object(crossover, "solve", solve):
        crossover.run(RAW / "publication", RAW / "process.json", GEOGRAPHIC, replay)
    candidate = read(replay)
    checks = {key: candidate[key] == baseline[key] for key in SCIENCE}
    checks.update(route=same_route(candidate["attempts"][0], baseline["attempts"][0]),
                  proof=candidate["regional"][0]["result"] == baseline["regional"][0]["result"],
                  checked_grid=candidate["grid"]["complete"] and candidate["posterior_grid_handoff"]["factor_calls"] == 356)
    observed = audit.records()
    handoff = candidate["posterior_grid_handoff"]
    checks["curved_clock"] = round(1e9*observed["ceiling"]["curved"]["both_arms_cpu_s"]) == handoff["curved_cpu_ns"]
    names = ("grid-cross-arm-posterior-protocol.md", "grid_cross_arm_posterior.py", "grid_cross_arm_posterior_trial.py")
    source = {name: crossover.file_sha(Path(__file__).with_name(name)) for name in names}
    write(output / "ceiling.json", dict(checks=checks, matched_archived_replay_sha256=REPLAY_PIN,
          new_replay_sha256=crossover.file_sha(replay), installed=dict(bound=PINNED_BOUND, handoff=PINNED_HANDOFF),
          source_sha256=source, machine=candidate["machine"], native_sha256=candidate["raw"]["raw_native_sha256"],
          track_asset_sha256=candidate["track_asset_sha256"], archive=candidate["raw"]["holder"]["archive"],
          scientific_digests=candidate["science"], route_clock=handoff,
          current_solve=candidate["solve"], recorded_control_solve=baseline["solve"], **observed))
    if not all(checks.values()):
        raise ValueError(f"Original scientific grid or timing coverage changed: {checks}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output)
