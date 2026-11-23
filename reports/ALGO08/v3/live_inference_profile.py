"""Time the exact live full-catalogue numerical route on the saved dense packet."""

import argparse
from contextlib import ExitStack
import cProfile
from hashlib import sha256
from pathlib import Path
import pstats
from time import perf_counter, process_time
from unittest.mock import patch

from aperture_trial import ARMS, archive_identity, configuration, inputs, machine, solve, write


CASE = "DS30-0008"


def attribution(profiler):
    stats = pstats.Stats(profiler).stats
    return [dict(file=file, line=line, function=func, primitive_calls=native, calls=calls,
                 self_s=own, inclusive_s=total)
            for (file, line, func), (native, calls, own, total, _callers) in
            sorted(stats.items(), key=lambda pair: -pair[1][3]) if total >= .005]


def replay(mode, output, *, configure_solve=None, result_details=None):
    host = machine()
    if (host["cpu"] != [2] or host["nice"] < 15 or "prio 7" not in host["ionice"]
            or any(value != "1" for value in host["threads"].values())):
        raise ValueError("Use the shared Gauss slot with one numerical thread")
    publication, spec = configuration()
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core
    from tools.pipeline_eval.variants.experimental import regional_bound_guard, regional_reassignment
    from blind_joint_finish import elapsed
    from early_region import before_fit
    from joint_publication import full_catalogue_route
    from optimized_grid import reduced_grid
    from prepared_exterior import handoff

    native, archive, offer, _, identity = inputs(CASE)
    if identity["detector_sha256"] != "sha256:" + spec["detector_sha256"]:
        raise ValueError("The saved detector specification changed")
    installed_solve = algo08_position.solve
    attempts, regional, selected, grids, visited = [], [], {}, [], []
    profile = cProfile.Profile(timer=process_time) if mode == "profile" else None
    details = {}

    def observed(document, reader, assets, region):
        if reader.root != archive or region.document() != offer or document is not native:
            raise ValueError("Expected the original saved detector, causal archive and offered region")
        with ExitStack() as scope:
            route = full_catalogue_route(v5_core.infer, reader, attempts, optimized=True)
            live, prepared, _ = scope.enter_context(handoff(reader))
            grid = scope.enter_context(reduced_grid())
            route = before_fit(route, reader, regional_bound_guard.causal_probes, regional, live.match)
            scope.enter_context(patch.object(v5_core, "infer", route))
            proof_counts = None
            if mode == "visible":
                from visible_orbit_proof import visible_proof

                proof_counts = scope.enter_context(visible_proof())
            if profile is None:
                prepare_scores = regional_reassignment._prepare_probe_scores

                def track_probes(*args):
                    points, score, meta = prepare_scores(*args)

                    def observe_probe(point):
                        row = score(point)
                        visited.append(dict(row))
                        return row

                    return points, observe_probe, meta

                scope.enter_context(patch.object(regional_reassignment, "_prepare_probe_scores", track_probes))
            if configure_solve is not None:
                scope.enter_context(configure_solve(assets, full_catalogue_route))
            cpu, wall = process_time(), perf_counter()
            if profile is not None:
                profile.enable()
            try:
                decision, packet, policy = installed_solve(document, reader, assets, region)
            finally:
                if profile is not None:
                    profile.disable()
            measured = elapsed(cpu, wall)
        details.update(solve=measured, catalogue=prepared, grid_kernel=grid, proof_kernel=proof_counts)
        if packet is not None:
            if not packet["position_grid"]["complete"]:
                raise ValueError("The complete numerical grid is required")
            selected.update({arm: [[r[k] for k in ("observation_id", "norad", "role")]
                                   for r in packet["rows"][arm]] for arm in ARMS})
            grids.append({k: v for k, v in packet["position_grid"].items() if k not in ("binding", "elapsed_seconds")})
        return decision, packet, policy

    with patch.object(algo08_position, "solve", observed):
        result = solve(publication, spec, native, archive, offer)
    if len(regional) != 1 or len(attempts) != 1 or archive_identity(archive) != identity["archive"]:
        raise ValueError("Expected one replay on the unchanged causal archive")
    result.pop("owner_rows", None)
    names = ("live_inference_profile.py", "live-inference-profile-protocol.md", "joint_publication.py",
             "cold_finalist_race.py", "optimized_grid.py", "prepared_exterior.py", "early_region.py", "visible_orbit_proof.py")
    pins = {name: sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in names}
    result.update(case=CASE, mode=mode, machine=host, identity=identity, attempts=attempts, regional=regional,
                  selected_rows=selected, grid=grids[0] if grids else None, visited_probes=visited, source_sha256=pins, **details)
    if profile is not None:
        result["profile"] = attribution(profile)
    if result_details is not None:
        result.update(result_details())
    write(output, result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("profile", "control", "visible"))
    parser.add_argument("output", type=Path)
    replay(**vars(parser.parse_args()))
