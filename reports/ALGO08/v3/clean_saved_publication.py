"""Publish an authenticated saved named packet from an explicit staged request."""

import argparse
from collections.abc import Mapping
from contextlib import contextmanager
import json
from pathlib import Path
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
MODES = ("installed", "routed")


def load_job(path, pin):
    from empty_bootstrap import checked
    from exact_named_route import resident_path

    job = json.loads(checked(resident_path(path), pin))
    bound = job["binding"]
    if not isinstance(bound, Mapping) or bound["inventory"] not in bound["packets"] or bound["request"] not in bound["packets"]:
        raise ValueError("The saved inputs need an explicit signed binding")
    for name, digest in bound["packets"].items():
        checked(resident_path(Path(name)), digest)
    path = Path(bound["request"])
    request = json.loads(checked(path, bound["packets"][str(path)]))
    if request["local_archive"]["root"] != bound["archive"] or request["issued"] != bound["issued"] or request["admitted"] != bound["admitted"]:
        raise ValueError("The submitted signed request changed its scope")
    request["original_archive"] = job["original_archive"]
    return bound, request


def installed(bound, req, output):
    from prospective_0316_solver import worker

    worker(Path(bound["request"]), "stock", output, source_pins={}, native_sha=req["native_sha256"],
           windows=bound["issued"], admitted=bound["admitted"], inventory_file=Path(bound["inventory"]),
           audit_name="worker.json")


def routed(bound, req, root, *, route_binding=None):
    import exact_named_route as exact
    import named_history_once as history
    from history_cairo_render import binding as layout
    from history_risk_route import binding as risk

    named, exact_ports, read = history.named_solve, exact.exact_ports, exact.read
    active_route = risk if route_binding is None else route_binding
    result, render = dict(solves=[]), {}
    original_rank = None

    @contextmanager
    def route_ports(*args, **kwargs):
        nonlocal original_rank
        from tools import algo08_scan
        from tools.pipeline_eval.variants import v5_core

        original_rank = v5_core.ranked_initial_nodes
        with exact_ports(*args, **kwargs), layout(algo08_scan, render, orbit_sheets=False):
            yield

    @contextmanager
    def route_named(enabled, release, payload):
        from tools import algo08_scan

        with named(enabled, release, payload) as audit:
            ordinary = algo08_scan.solve

            def solve(native, reader, assets, offer):
                if original_rank is None:
                    raise ValueError("Expected the original shared rank before installing exact ports")
                result["solves"].append(trace := {})
                with active_route(reader, req["causal_cutoff_utc_ns"], trace, original_rank):
                    return ordinary(native, reader, assets, offer)

            with patch.object(algo08_scan, "solve", solve):
                yield audit

    def request_view(path):
        return req if path == Path(bound["request"]) else read(path)

    with (patch.object(history, "named_solve", route_named), patch.object(exact, "exact_ports", route_ports),
          patch.object(exact, "bind", return_value=bound), patch.object(exact, "read", request_view)):
        exact.worker(None, root)
    from aperture_trial import write

    write(root/"risk-route.json", result)
    write(root/"render-usage.json", render)


def run(mode, job, pin, root):
    from exact_named_route import resident_path

    if root/"binding.json" == job or (root/"candidate").exists():
        raise ValueError("Use a fresh worker output")
    resident_path(root)
    bound, request = load_job(job, pin)
    if mode == "installed":
        installed(bound, request, root/"candidate")
    else:
        routed(bound, request, root)


if __name__ == "__main__":
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=MODES)
    parser.add_argument("job", type=Path)
    parser.add_argument("job_sha256")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    run(args.mode, args.job, args.job_sha256, args.output)
