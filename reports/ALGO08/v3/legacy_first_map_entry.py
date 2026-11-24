"""Add first-use map production to the same original history-risk entry."""

from contextlib import ExitStack
import json
from pathlib import Path
import sys
from unittest.mock import patch

import legacy_block_raw_entry as raw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ordinary_parser = raw.parser
RESOURCES = ("plan", "history", "replay")


def parser():
    cli = ordinary_parser()
    for label in RESOURCES:
        cli.add_argument(f"--legacy-first-map-{label}", type=Path, required=True)
        cli.add_argument(f"--legacy-first-map-{label}-sha256", required=True)
    cli.add_argument("--first-map-setup-only", action="store_true")
    return cli


class ReachedScanner(Exception):
    pass


def run(args):
    import empty_bootstrap as boot
    from legacy_map_receipt import write

    if (not args.eight_ms_native_history or not args.held_anchor_route or not args.history_risk_route
            or args.legacy_map_custody or args.legacy_map_library):
        raise ValueError("Expected the ordinary 20/8 history-risk path with first-use map production")
    old = boot.load_runtime
    audit, pending = {}, {}
    state = {}
    if args.first_map_setup_only:
        def forbid(event, call):
            if event == "open" and str(call[0]).endswith(".ci16.zst"):
                raise ValueError("The first-use startup probe cannot open an original waveform")
        sys.addaudithook(forbid)

    with ExitStack() as stack:
        def installed():
            runtime = old()
            began = boot.now()
            with patch.object(sys, "path", [*sys.path, str(ROOT)]):
                from reports.ALGO08.v3 import legacy_block_input as port, legacy_block_seek as core
                from reports.ALGO08.v3 import legacy_first_map_input as producing, legacy_fused_map as fused
            from legacy_block_all_entry import mapped_codec

            resources = {}
            for label in RESOURCES:
                path = getattr(args, f"legacy_first_map_{label}")
                pin = getattr(args, f"legacy_first_map_{label}_sha256")
                resources[label] = port.checked_file(path, pin, port.MAX_CUSTODY if label == "plan" else 2_000_000)
                audit[label + "_sha256"] = pin
            state["plan"] = plan = json.loads(resources["plan"])
            spec = runtime[1]
            paired = spec["paired_sha256"]
            hasher = Path(paired["library"])
            boot.checked(hasher, paired["sha256"])
            history = fused.load(args.legacy_first_map_history)
            replay = core.load(args.legacy_first_map_replay)
            codec = mapped_codec(plan)
            if args.first_map_setup_only:
                ordinary = boot.staged_scanner

                def stop(*call, **options):
                    ordinary(*call, **options)
                    if any(name in sys.modules for name in boot.SCIENTIFIC_IMPORTS):
                        raise ValueError("First-use map setup imported premature scientific modules")
                    raise ReachedScanner

                stack.enter_context(patch.object(boot, "staged_scanner", stop))
            stack.enter_context(producing.binding(boot, plan, history, hasher, codec, replay, pending, audit))
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
    if args.first_map_setup_only or terminal["decision"] != "complete" or "finished_raw_authority" not in audit:
        raise ValueError("No complete first-use receiver and publication")
    began = boot.now()
    pin = state["publish"](args.output / "legacy-first-maps", state["plan"], pending)
    if pin != audit["plan_sha256"]:
        raise ValueError("Published complete replay custody changed")
    audit["map_publication"] = boot.clock(began)
    write(args.output / "legacy-first-map-acquisition.json", audit)
    return terminal


if __name__ == "__main__":
    run(parser().parse_args())
