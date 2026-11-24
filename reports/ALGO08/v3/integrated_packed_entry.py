"""Research-only strict prepared packed source for the integrated publication."""

import os
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))


def parser():
    from legacy_block_raw_entry import parser as original

    cli = original()
    cli.add_argument("--sparse8-primary", action="store_true", required=True)
    cli.add_argument("--legacy-first-map-fast", type=Path, required=True,
                     help="Pinned integrated native solver artifact roster")
    cli.add_argument("--legacy-first-map-fast-sha256", required=True)
    return cli


def require_prepared_payload(event, arguments):
    if event == "open" and isinstance(arguments[0], (str, bytes)) and os.fsdecode(arguments[0]).endswith(".ci16.zst"):
        raise PermissionError("Strict prepared input cannot open original encoded I/Q")


def run(args):
    import combined_successor_raw_entry as guarded
    import empty_bootstrap as boot
    import integrated_original_entry as integrated
    import legacy_block_raw_entry as raw
    from legacy_first_map_acceleration import checked_artifacts
    from legacy_map_receipt import write

    if not (args.strict_packed_eight and args.sparse8_primary and args.cairo_six_sheets):
        raise ValueError("Strict prepared input, sparse 8 ms and standard six-Cairo publication are required")
    sys.addaudithook(require_prepared_payload)
    original = boot.load_runtime
    spec, audit = {}, {}

    def load():
        runtime = original()
        spec.update(checked_artifacts(args.legacy_first_map_fast, args.legacy_first_map_fast_sha256))
        return runtime

    with (patch.object(boot, "load_runtime", load),
          integrated.positive_ports(guarded.solver_ports, spec, audit)):
        terminal = raw.run(args, allow_cairo_orbits=True, allow_strict_packed=True)
    write(args.output / "integrated-packed-solver.json",
          dict(solver_artifacts_sha256=args.legacy_first_map_fast_sha256, ports=audit))
    return terminal


if __name__ == "__main__":
    run(parser().parse_args())
