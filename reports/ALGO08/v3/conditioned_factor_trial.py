"""Run one authenticated saved full fix and audit its complete-fit lower bounds."""

import argparse
from contextlib import ExitStack
from pathlib import Path
from time import process_time_ns
from unittest.mock import patch

from aperture_trial import archive_identity, configuration, read, solve, write
from cold_track_row_transfer import GEOGRAPHIC, dense_inputs, small_inputs
from conditioned_factor import build, digest, supplied_kernel
from dense_geographic_trial import host

HERE = Path(__file__).resolve().parent
REGIONAL = Path("/var/tmp/leo-regional-track.O238AD0C/scores.so")


def run(case, mode, output):
    machine = host()
    publication, specification = configuration()
    import cold_finalist_race
    from cold_track_row_entry import cold_track_rows
    from early_region import before_fit
    from full_short_run import geographic_projection
    from grid_phase_state_reuse import cached_predictive_grid
    from joint_publication import full_catalogue_route
    from leo.analysis.localization_v3 import discovery, position
    from optimized_grid import reduced_grid
    from prepared_exterior import handoff
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core
    from tools.pipeline_eval.variants.experimental import regional_bound_guard

    if case == "dense":
        chosen, control = dense_inputs(GEOGRAPHIC)
    else:
        chosen, control = small_inputs("physical")
    _, archive, _, packet, pin, offer = chosen
    archive_path = Path(archive["root"])
    native = read(packet)
    if digest(packet) != pin.removeprefix("sha256:") or archive_identity(archive_path) != archive:
        raise ValueError("Input must be the sealed capture and original causal catalogue")

    output.mkdir()
    compiled = build(output / "build", mode)
    stock, original = cold_finalist_race.refine, algo08_position.solve
    attempts, regional, lower_bounds = [], [], []
    clocks = {}

    def audited(mode, prepared, region, native_bound):
        constructor = position.NormalPosition.__init__
        by_branch = {}

        def construct(self, scan, node, *a, **kw):
            constructor(self, scan, node, *a, **kw)
            if node["aliases"] is None:
                return
            signature = discovery.signature(node)
            floor = max(0., self.noise_volume*(1.-16.*2.220446049250313e-16))
            evidence = dict(rows=int(self.keep.sum()), noise_volume=float(self.noise_volume),
                            floor=float(floor), fitted_c=bool(self.fitted_c))
            previous = by_branch.setdefault(signature, evidence)
            if previous != evidence:
                raise ValueError("The branch's fixed lower bound changed during refresh")

        with patch.object(position.NormalPosition, "__init__", construct):
            result = stock(mode, prepared, region, native_bound)
        cold = result[3]
        incumbent = cold["scores"][cold["branch"]-1]
        lower_bounds.append(dict(
            completed_incumbent=incumbent, scores=cold["scores"],
            bounds=list(by_branch.values()), proven_losers=sum(x["floor"] > incumbent
                                                              for x in by_branch.values()),
        ))
        return result

    def observed(document, reader, assets, region):
        if document is not native or reader.root != archive_path or region.document() != offer:
            raise ValueError("Original detector, causal catalogue or offer changed")
        with ExitStack() as stack:
            stack.enter_context(patch.object(cold_finalist_race, "refine", audited))
            stack.enter_context(cold_track_rows())
            stack.enter_context(geographic_projection(GEOGRAPHIC, REGIONAL))
            live, _, _ = stack.enter_context(handoff(reader))
            stack.enter_context(reduced_grid())
            stack.enter_context(cached_predictive_grid())
            route = full_catalogue_route(v5_core.infer, reader, attempts, optimized=True)
            guarded = before_fit(route, reader, regional_bound_guard.causal_probes, regional, live.match)
            stack.enter_context(patch.object(v5_core, "infer", guarded))
            start = process_time_ns()
            result = original(document, reader, assets, region)
            clocks["solver_cpu_ns"] = process_time_ns()-start
            return result

    with (supplied_kernel(algo08_position, compiled) as counts,
          patch.object(algo08_position, "solve", observed)):
        result = solve(publication, specification, native, archive_path, offer)
    for name in ("cold_clocks", "standard_evidence_clocks", "signed_total_clocks"):
        clocks[name] = attempts[0][name]
    checks = dict(
        fix=result["status"] == "ok", both_arms=set(result["arms"]) == {"c0", "fitted_c"},
        grid=result["grid_points"] == 179, replay=all(value == 0 for value in result["objective_replay"].values()),
        route=len(attempts) == len(regional) == len(lower_bounds) == 1,
    )
    if case == "dense":
        checks["prior_science"] = all(result[key] == control[key] for key in (
            "arms", "objective_replay", "science", "owners",
        ))
    outputs = dict(
        result=result, cold={k: attempts[0]["cold"][k] for k in ("branch", "scores", "routing")},
        proof=regional[0]["result"], checks=checks, bound=lower_bounds, clocks=clocks,
        input_sha256=pin, counts=counts, compiled=compiled, machine=machine, case=case, mode=mode,
        code={p.name: digest(p) for p in (
            HERE / "conditioned-factor-protocol.md", HERE / "conditioned_factor.py",
            HERE / "conditioned_factor.inc", Path(__file__),
        )},
    )
    write(output / "receipt.json", outputs)
    if not all(checks.values()):
        raise ValueError(f"Scientific qualification failed: {checks!r}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=("dense", "weak"))
    parser.add_argument("mode", choices=("stock", "certificate"))
    parser.add_argument("output", type=Path)
    run(**vars(parser.parse_args()))
