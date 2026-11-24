"""Add first-use map production to the same original history-risk entry."""

from contextlib import ExitStack
import json
from pathlib import Path
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))

import legacy_block_raw_entry as raw

ordinary_parser = raw.parser
LIBRARIES = ("history", "replay")


def parser():
    cli = ordinary_parser()
    for label in LIBRARIES:
        cli.add_argument(f"--legacy-first-map-{label}", type=Path, required=label == "history")
        cli.add_argument(f"--legacy-first-map-{label}-sha256", required=label == "history")
    cli.add_argument("--legacy-first-map-plan", type=Path,
                     help="Optional independent replay plan for byte-parity qualification")
    cli.add_argument("--legacy-first-map-plan-sha256")
    cli.add_argument("--legacy-first-map-fast", type=Path,
                     help="Research-only exact first-use acceleration artifact roster")
    cli.add_argument("--legacy-first-map-fast-sha256")
    cli.add_argument("--verify-original-once", action="store_true",
                     help="Verify and analyze the original once without constructing a replay index")
    cli.add_argument("--first-map-setup-only", action="store_true")
    return cli


class ReachedScanner(Exception):
    pass


def require_verified_terminal(terminal, plan, audit):
    """The terminal must bind complete signed acquisition, including valid withholds."""
    if (terminal["decision"] not in ("complete", "withheld")
            or terminal["session_id"] != plan["session"] or terminal["window_count"] != plan["windows"]
            or audit.get("finished_raw_authority") != plan["raw_authority"]):
        raise ValueError("No complete first-use receiver and publication")


def run(args):
    import empty_bootstrap as boot
    from legacy_map_receipt import write

    if (not args.eight_ms_native_history or not args.held_anchor_route or not args.history_risk_route
            or args.legacy_map_custody or args.legacy_map_library):
        raise ValueError("Expected the ordinary 20/8 history-risk path with first-use map production")
    if bool(args.legacy_first_map_plan) != bool(args.legacy_first_map_plan_sha256):
        raise ValueError("Provide the optional qualification plan and external pin together")
    fast = getattr(args, "legacy_first_map_fast", None)
    fast_pin = getattr(args, "legacy_first_map_fast_sha256", None)
    if bool(fast) != bool(fast_pin):
        raise ValueError("Provide the optional exact acceleration roster and external pin together")
    build_maps = not getattr(args, "verify_original_once", False)
    replay_args = args.legacy_first_map_replay, args.legacy_first_map_replay_sha256
    if build_maps and not all(replay_args):
        raise ValueError("Replay collection requires the exact replay decoder and its pin")
    if not build_maps and (any(replay_args) or args.legacy_first_map_plan or fast is None):
        raise ValueError("Verify-once requires exact acceleration and excludes replay artifacts and plans")
    old = boot.load_runtime
    audit, pending = {}, {}
    state = {}
    acceleration, solver_audit = {}, {}
    if args.first_map_setup_only:
        def forbid(event, call):
            if event == "open" and str(call[0]).endswith(".ci16.zst"):
                raise ValueError("The first-use startup probe cannot open an original waveform")
        sys.addaudithook(forbid)

    with ExitStack() as stack:
        if fast is not None:
            from legacy_first_map_acceleration import checked_artifacts, solver_ports

            # Bind the publisher before the ordinary raw entry hands its
            # callback to the scanner. The libraries are checked in load.
            stack.enter_context(solver_ports(acceleration, solver_audit))

        def installed():
            runtime = old()
            began = boot.now()
            with patch.object(sys, "path", [*sys.path, str(ROOT)]):
                from reports.ALGO08.v3 import legacy_block_input as port, legacy_block_seek as core
                from reports.ALGO08.v3 import legacy_first_map_input as producing, legacy_fused_map as fused
            for label in LIBRARIES if build_maps else ("history",):
                path = getattr(args, f"legacy_first_map_{label}")
                pin = getattr(args, f"legacy_first_map_{label}_sha256")
                port.checked_file(path, pin, 2_000_000)
                audit[label + "_sha256"] = pin
            plan = None
            expected_pin = args.legacy_first_map_plan_sha256
            if args.legacy_first_map_plan is not None:
                plan = port.load_custody(args.legacy_first_map_plan, expected_pin)
            audit["authority_mode"] = ("verified-once" if not build_maps else
                                       "qualified-parity" if plan is not None else "verified-first-use")
            spec = runtime[1]
            paired = spec["paired_sha256"]
            hasher = Path(paired["library"])
            boot.checked(hasher, paired["sha256"])
            options = {} if build_maps else {"build_maps": False}
            if fast is not None:
                acceleration.update(checked_artifacts(fast, fast_pin))
                hasher = Path(acceleration["hasher"]["path"])
                from hashlib import sha256

                probe = (fused.prefix_hasher() if build_maps else fused.PairedSha256)(hasher)
                probed = probe.window_and_prefix(b"exact", 2) if build_maps else (probe.window(b"exact"),)
                wanted = (sha256(b"exact").digest(), sha256(b"ex").digest()) if build_maps else (sha256(b"exact").digest(),)
                if probed != wanted:
                    raise ValueError("The pinned first-use hasher failed its startup check")
                audit["acceleration"] = dict(pin=fast_pin, artifacts=acceleration, solver=solver_audit)
                options["accelerate"] = True
            history = fused.load(args.legacy_first_map_history)
            if not build_maps and not hasattr(history, "fused_history_open_unindexed"):
                raise ValueError("Verify-once requires the unindexed native history interface")
            replay = core.load(args.legacy_first_map_replay) if build_maps else None
            if args.first_map_setup_only:
                ordinary = boot.staged_scanner

                def stop(*call, **options):
                    ordinary(*call, **options)
                    if any(name in sys.modules for name in boot.SCIENTIFIC_IMPORTS):
                        raise ValueError("First-use map setup imported premature scientific modules")
                    raise ReachedScanner

                stack.enter_context(patch.object(boot, "staged_scanner", stop))
            stack.enter_context(producing.binding(boot, plan, history, hasher, replay, pending, audit, **options))
            if build_maps:
                state["publish"] = producing.publish_bundle
            audit["setup"] = boot.clock(began)
            return runtime

        stack.enter_context(patch.object(boot, "load_runtime", installed))
        try:
            terminal = raw.run(args)
        except ReachedScanner:
            if not args.first_map_setup_only or args.output.exists() or pending:
                raise
            print(json.dumps(dict(reached_scanner=True, waveform_opens=0, audit=audit)))
            return
    key = "verified_plan" if build_maps else "verified_source"
    if args.first_map_setup_only or key not in audit:
        raise ValueError("No complete first-use receiver and publication")
    plan = audit[key]
    require_verified_terminal(terminal, plan, audit)
    if not build_maps:
        write(args.output / "legacy-original-acquisition.json", audit)
        return terminal
    audit.pop(key)
    began = boot.now()
    pin = state["publish"](args.output / "legacy-first-maps", plan, pending)
    if args.legacy_first_map_plan_sha256 is not None and pin != args.legacy_first_map_plan_sha256:
        raise ValueError("Published complete replay custody changed")
    audit["plan_sha256"] = pin
    audit["map_publication"] = boot.clock(began)
    write(args.output / "legacy-first-map-acquisition.json", audit)
    return terminal


if __name__ == "__main__":
    run(parser().parse_args())
