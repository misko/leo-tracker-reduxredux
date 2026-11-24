"""Run the guarded successor after the normal verified-once native receiver."""

from contextlib import contextmanager
import json
from pathlib import Path
import runpy
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]


@contextmanager
def solver_ports(spec, audit):
    import exact_named_raw as raw

    publish = raw.publish_active

    def accelerated(*args, **kwargs):
        import empty_bootstrap as boot
        from tools import algo08_position, algo08_scan
        import history_risk_route as risk
        from combined_successor import exact_grid, successor_binding
        from live_orbit_support import bind
        from solver_exception_0022 import GUARD, GUARD_PIN, OLD_GUARD

        boot.checked(Path(algo08_position.corner_support.__wrapped__.__code__.co_filename), OLD_GUARD)
        boot.checked(GUARD, GUARD_PIN)
        repaired = runpy.run_path(str(GUARD))["corner_support"]
        ordinary = risk.binding
        audit.update(grid={}, in_flight=[], original_restart=[])

        @contextmanager
        def original_restart():
            with repaired() as report:
                audit["original_restart"].append(report)
                yield

        @contextmanager
        def route(reader, cutoff, trace, original_rank):
            # Reuse the real publisher's boundary inspection and named
            # recovery. The successor calls the original route internally.
            with patch.object(risk, "binding", ordinary), successor_binding(reader, cutoff, trace, original_rank):
                yield

        with (patch.object(risk, "binding", route),
              patch.object(algo08_position, "corner_support", original_restart),
              bind(algo08_position, algo08_scan, repaired, audit["in_flight"]),
              exact_grid(spec["projection"]["path"], spec["template"]["path"], audit["grid"])):
            return publish(*args, **kwargs)

    with patch.object(raw, "publish_active", accelerated):
        yield


def smoke(args, acceleration):
    """Exercise the installed scientific port setup after the denied scanner probe."""
    import empty_bootstrap as boot
    import exact_named_raw as raw
    import grid_phase_state_reuse as phase
    import history_risk_route as risk
    from tools import algo08_position, algo08_scan

    if (Path(algo08_scan.__file__) != boot.PAYLOAD/boot.SCANNER
            or Path(algo08_position.__file__) != boot.PAYLOAD/"tools/algo08_position.py"):
        raise ValueError("Scientific startup did not bind the original installed runtime")
    spec = acceleration.checked_artifacts(args.legacy_first_map_fast, args.legacy_first_map_fast_sha256)
    original, grid, route = algo08_scan.solve, phase.cached_predictive_grid, risk.binding
    answer = (dict(decision="withheld"), dict(timing={}, ports={}))

    def publication(*_args, **_kwargs):
        if (algo08_scan.solve is original or algo08_scan.solve is not algo08_position.solve
                or phase.cached_predictive_grid is grid or risk.binding is route):
            raise ValueError("The guarded candidate or exact grid did not bind")
        return answer

    audit = {}
    with patch.object(raw, "publish_active", publication), solver_ports(spec, audit):
        actual = raw.publish_active(None, None, None, None)
    if actual is not answer or algo08_scan.solve is not original or args.output.exists():
        raise ValueError("The scoped raw publisher did not retain its return contract")
    print(json.dumps(dict(solver_setup=True, witness_shape=[sorted(part) for part in actual],
                          native_grid_setup=audit["grid"], raw_children=0, waveform_opens=0)))


def main():
    import legacy_first_map_acceleration as acceleration
    import legacy_first_map_entry as receiver

    args = receiver.parser().parse_args()
    if not args.verify_original_once or not args.legacy_first_map_fast:
        raise ValueError("The guarded original route needs the qualified verified-once receiver")
    with patch.object(acceleration, "solver_ports", solver_ports):
        receiver.run(args)
    if args.first_map_setup_only:
        smoke(args, acceleration)


if __name__ == "__main__":
    main()
