"""Observe the original named signed pair on two authenticated saved packets."""

import argparse
from pathlib import Path
import sys
from time import process_time_ns
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
BOOTSTRAP_SHA = "d2d2190bab69950f03c0ae6ba852c5a6faabe3b47aa0477ed6ae04c250b0f838"
CASES = ("0008", "0402")


def worker(case, root):
    import named_survivor_fit as named
    import survivor_sensitivity_trial as saved
    from empty_bootstrap import checked
    from signed_state_ceiling import Census, observe

    if case not in CASES:
        raise ValueError("Expected an enrolled dense or hard saved packet")
    staged, pin = saved.STAGED[case]
    request = root / "binding.json"
    request.write_bytes(checked(Path("/dev/shm") / staged, pin))
    result, handoffs = {}, []

    def cut(candidate, means, _audit, _witness):
        from blind_joint_finish import readout
        from blind_joint_signed import describe
        from leo.analysis.localization_v3.history_policy import pair_passes
        from named_phase_reuse_trial import owner_rows

        scan = candidate["scan"]
        node, keep, powers, model, entries = (candidate[key] for key in ("node", "keep", "powers", "model", "entries"))
        census = Census(scan)
        fits, arm_cpu = {}, {}
        with observe(census) as event:
            for arm in named.ARMS:
                start = process_time_ns()
                fits[arm] = event.refit(scan, node, keep, arm, powers, means, model, [], entries)
                arm_cpu[arm] = process_time_ns() - start
        start = process_time_ns()
        census.validate()
        validation_cpu = process_time_ns() - start
        captured = describe(dict(candidate, arms=fits, means=means))
        result.update(census=census.scopes(), common_operands=census.compare_common(), phase_views=census.phase_views,
                      row_count=len(owner_rows(captured)), roster=owner_rows(captured),
                      clocks_cpu_ns=arm_cpu, diagnostic_validation_cpu_ns=validation_cpu,
                      original_gate=pair_passes(fits, include_linear=True, half_width_km=scan.search_region.half_width_km),
                      readout={arm: readout(dict(record, history=[dict(step, movement_km=None) for step in record["history"]]))
                               for arm, record in fits.items()})
        raise saved.ProbeComplete

    source_pins = saved.SAVED_SOURCE_UPDATES | {"unified_short_bootstrap.py": BOOTSTRAP_SHA}
    with (saved.record_handoff(handoffs), patch.object(named, "fit_pair", cut),
          patch.object(saved, "SAVED_SOURCE_UPDATES", source_pins)):
        try:
            saved.run_case(case, root, request)
        except saved.ProbeComplete:
            pass
        else:
            raise ValueError("The saved trace did not enter the qualified original signed pair")
    if len(handoffs) != 1 or handoffs[0][0] != 1 or list(root.rglob("terminal.json")) or list(root.rglob("*.png")):
        raise ValueError("Expected exactly one saved handoff and a cut before publication")
    from aperture_trial import write

    write(root / "probe.json", dict(case=case, request_sha256=pin, handoff=handoffs[0], waveform_calls=0, **result))


def launch(root):
    from survivor_sensitivity_trial import launch as saved

    saved("held", root, worker_path=Path(__file__).resolve(), extra_sources=(
        "signed-state-ceiling-protocol.md", "signed_state_ceiling.py", "signed_state_ceiling_trial.py",
        "named_phase_reuse_trial.py", "cumulative_grid_projection.py", "named_survivor_0402_trial.py"))


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("launch").add_argument("root", type=Path)
    cut = sub.add_parser("worker")
    cut.add_argument("case", choices=CASES)
    cut.add_argument("root", type=Path)
    args = vars(parser.parse_args())
    globals()[args.pop("action")](**args)
