"""External exact comparison of causal residual-family screening."""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from check_algo07v3_scan_likelihood import fingerprint


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(args):
    started = time.monotonic()
    packet = json.loads(args.preflight.read_text())
    catalogue = json.loads(args.catalogue.read_text())
    if args.side == "candidate":
        from check_algo07v3_track_preparation import deny_legacy

        sys.addaudithook(deny_legacy)
        from leo.analysis.localization_v3.region import SearchRegion
        from leo.analysis.localization_v3.residual_screen import screen_candidates

        result = screen_candidates(
            packet,
            catalogue,
            SearchRegion(tuple(args.search_center)),
            policy=args.policy,
            on_target=lambda row: print(
                json.dumps(
                    dict(
                        target=row["source"]["fragment_id"],
                        finalists=len(row["finalists"]),
                        accepted=[s["policy"] for s in row["summaries"] if s["screen_pass"]],
                    )
                ),
                flush=True,
            ),
        )
    else:
        sys.path[:0] = [str(args.runtime / "src"), str(args.runtime / "tools")]
        from algo06_science import screen
        from prototype_dsx01_continuous_position import CENTER

        if tuple(args.search_center) != tuple(CENTER):
            raise ValueError("Original policy has a frozen regional center")
        screen.POLICIES = {args.policy: screen.POLICIES[args.policy]}

        def read(path):
            if path.parent.name == "preflight":
                return packet
            if path.parent.name == "catalogues":
                return catalogue
            raise ValueError("Unexpected original input: " + str(path))

        captured = {}

        def write(path, value):
            if path.name == "result.json":
                captured.update(value)

        screen.read, screen.write = read, write
        screen.one(packet["case"])
        captured.pop("seconds")
        result = captured
    args.output.write_text(json.dumps(fingerprint(result), sort_keys=True, allow_nan=False) + "\n")

    def binding(path):
        return dict(path=str(path), sha256=digest(path))

    receipt = dict(
        side=args.side,
        policy=args.policy,
        seconds=time.monotonic() - started,
        scope="Full causal residual-family screen from explicit corrected native packet",
        full_pipeline_parity=False,
        search_center=args.search_center,
        inputs={str(p): digest(p) for p in (args.preflight, args.catalogue)},
        modules={
            name: binding(module.__file__)
            for name, module in sys.modules.items()
            if getattr(module, "__file__", None)
            and (
                str(module.__file__).startswith(str(args.runtime))
                or "/src/leo/" in str(module.__file__)
                or name in ("check_algo07v3_scan_likelihood", "check_algo07v3_track_preparation")
            )
        },
        tool=binding(__file__),
        output=binding(args.output),
    )
    args.output.with_suffix(".receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps(dict(side=args.side, seconds=receipt["seconds"], output=receipt["output"])),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--side", choices=["reference", "candidate"], required=True)
    for name in ("preflight", "catalogue", "runtime", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--search-center", type=float, nargs=2, required=True)
    parser.add_argument(
        "--policy", choices=["48h_15s", "72h_15s", "72h_30s", "72h_30s_recency"], default="72h_30s"
    )
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix(".receipt.json").exists():
        raise ValueError("Screen output exists")
    run(args)
