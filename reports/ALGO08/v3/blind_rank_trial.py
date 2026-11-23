"""Measure and compare the cold ranking and three exact refinements on saved inputs."""

import argparse
from collections import Counter
from contextlib import ExitStack, nullcontext
from functools import wraps
from hashlib import sha256
import json
from pathlib import Path
import runpy
from tempfile import TemporaryDirectory
from time import perf_counter, process_time, process_time_ns
from types import SimpleNamespace
from unittest.mock import patch

from aperture_trial import archive_identity, configuration, inputs, machine, write


def timer(stack, module, name, counters, *, key=None):
    original = getattr(module, name)
    prefix = key or name

    @wraps(original)
    def measured(*args, **kwargs):
        start = process_time_ns()
        try:
            return original(*args, **kwargs)
        finally:
            counters[prefix + "_calls"] += 1
            counters[prefix + "_cpu_ns"] += process_time_ns() - start

    stack.enter_context(patch.object(module, name, measured))


def trial(case, output, *, candidate, profile):
    publication, specification = configuration()

    from leo.analysis.localization_v3 import discovery, position, scan
    from leo.analysis.research import shared_orbit_phase_fit
    from leo.application.localization_v3_engine import _json_value
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from tools import algo08_position, algo08_scan
    from tools.pipeline_eval.variants import v5_core
    from blind_joint_finish import cold_candidate
    from mixture_trial import elapsed

    native, archive, offer, _, identity = inputs(case)
    if identity["detector_sha256"] != "sha256:" + specification["detector_sha256"]:
        raise ValueError("The saved receiver packet differs from the released binary")
    result = {}

    def analyze(_recording, _root, assets, archive_root, region):
        installed_rank = v5_core.ranked_initial_nodes
        clock = Counter()
        metrics = {}
        rank_records = []
        fitted = []
        operation = lambda _: nullcontext({})
        if candidate:
            module = Path(__file__).resolve().parents[3] / (
                "tools/pipeline_eval/variants/algo08_blind_rank.py"
            )
            operation = runpy.run_path(str(module))["shared_rank_preparation"]
            metrics["source_sha256"] = sha256(module.read_bytes()).hexdigest()

        def rank(current):
            cpu, wall = process_time(), perf_counter()
            with operation(current) as observed:
                nodes = installed_rank(current)
            clocks = elapsed(cpu, wall)
            rank_records.append(dict(clocks=clocks, candidates=len(nodes),
                                     signatures=[discovery.signature(node) for node in nodes],
                                     rows=[node["seed"]["rows"] for node in nodes],
                                     metrics=observed))
            return nodes

        stock_refresh = position.refreshed

        def refreshed(*args, **kwargs):
            cpu, wall = process_time(), perf_counter()
            model, fit, trace = stock_refresh(*args, **kwargs)
            clocks = elapsed(cpu, wall)
            fitted.append(dict(clocks=clocks, site=fit["parameters"], score=fit["score"],
                               trace_phases=[row["posterior_phase_s"] for row in trace]))
            return model, fit, trace

        def route(prepared, search_region, bound, stages, *, selected_evidence=None):
            cpu, wall = process_time(), perf_counter()
            with ExitStack() as stack:
                if profile:
                    for name in ("phase_linear_frequency", "statistics", "augment_phase_statistics",
                                 "proposal_phases", "improve", "score_at"):
                        timer(stack, discovery, name, clock)
                    timer(stack, shared_orbit_phase_fit, "profile_phases", clock)
                    timer(stack, scan.ScanLikelihood, "association", clock)
                stack.enter_context(patch.object(v5_core, "ranked_initial_nodes", rank))
                stack.enter_context(patch.object(position, "refreshed", refreshed))
                node, point, reference, cold = cold_candidate(prepared, search_region, bound)
            clocks = elapsed(cpu, wall)
            for ranked in rank_records:
                rows = json.loads(json.dumps(ranked.pop("rows"), default=_json_value))
                ranked["all_rows_sha256"] = canonical_digest(rows)
            result.update(cold=cold, total_clocks=clocks, profile=dict(clock),
                          ranks=rank_records, fits=fitted, metrics=metrics,
                          chosen_signature=discovery.signature(node), chosen_reference=reference)
            return dict(status="rank_only", reason=None, arms={})

        with patch.object(v5_core, "infer", route):
            decision, packet, policy = algo08_position.solve(native, TleArchiveReader(archive_root), assets, region)
        if decision["status"] != "rank_only" or packet is not None or not result:
            raise ValueError("Expected the complete cold ranking and refinement")
        result["orbit_policy"] = policy
        return result

    with TemporaryDirectory() as work:
        scratch = Path(work)
        offer_path = scratch / "offer.json"
        offer_path.write_text(json.dumps(offer))
        root = scratch / "output"
        root.mkdir()
        args = SimpleNamespace(recording=scratch / "saved", bulk_root=root, archive=archive, region=offer_path)
        with patch.object(algo08_scan, "analyze", analyze):
            data = publication.run(args, specification)
    if archive_identity(archive) != identity["archive"]:
        raise ValueError("Causal archive changed during the trial")
    data.update(identity=identity, machine=machine(), driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
    write(output, data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=("DS30-0008", "north-containing", "south-containing", "south-far"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--candidate", action="store_true")
    parser.add_argument("--profile", action="store_true")
    trial(**vars(parser.parse_args()))
