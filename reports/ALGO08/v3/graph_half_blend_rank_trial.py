"""Compare the two ordinary rank returns on one authenticated saved scan."""

import argparse
from collections import Counter
from math import isfinite
import os
from pathlib import Path
import runpy
import sys
from time import perf_counter_ns, process_time_ns, time_ns
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from graph_half_blend import proposal_view, verify_graph  # noqa: E402
import graph_half_blend_trial as saved  # noqa: E402


PORTS = {
    "exact_named_raw": "0495af4960cf0dc7df62034fa66fcdfa41798fc1dc2a7c035e2e6eeec5994186",
    "exact_named_route": "8799f632207d4a1b65954e454766605dcad109a799b9b81a08158c3a2ebc26ff",
    "solver_exception_0022": "657b8f55688b862500282de633c8c22f5f22b2e9c65969cc1ce7fa775791a95c",
    "discovery": "7ca045c3809c8da7b57268b9d9bcc4b8a49366e88376250d0b11227ce6d7e26a",
    "position": "c3507e6ecaba0adf6d3677f56d8056afcccbcf90d6a561bca7a42b06b0daef9d",
}
PREVIOUS = "c5e3d6ed044e561faecff9967aa9d1f2a7e140717236410cf8c15204da790615"


class RankComplete(RuntimeError):
    """Leave the installed setup at the rank return."""


def clock():
    return process_time_ns(), perf_counter_ns()


def elapsed(start):
    return dict(zip(("cpu_ns", "wall_ns"), (now - then for now, then in zip(clock(), start))))


def score(value):
    value = float(value)
    if not isfinite(value):
        raise ValueError("A nomination score was nonfinite")
    return dict(value=value, binary64=value.hex())


def rank_trace(rank, scan, discovery, position):
    """Observe ordinary nodes and scores without choosing or fitting a nominee."""
    fresh, explore, signature = discovery.fresh_discovery, discovery.explore, discovery.signature
    residual = position.NormalPosition.residual
    centres, proposals, corners, losses = [], [], [], []
    parent = None
    nested_explorations = 0

    def read_centres(view, sigma, *, budget):
        nonlocal parent
        if view is not scan or budget != 4 or centres:
            raise ValueError("Expected the four-centre ordinary producer")
        nodes = fresh(view, sigma, budget=budget)
        parent = min(nodes, key=lambda node: node["center_score"])
        for node in nodes:
            centres.append(dict(seed=int(node["hypothesis"]), signature=signature(node),
                                loss=score(node["center_score"]), corner_parent=node is parent))
        return nodes

    def read_exploration(view, state, anchor, *args, **kwargs):
        nonlocal nested_explorations
        if view is not scan:
            raise ValueError("Exploration left the enrolled scan")
        if centres:
            if state is not parent["seed"]["state"]:
                raise ValueError("Corner did not use the original centre winner")
            corners.append(tuple(map(float, anchor)))
        else:
            nested_explorations += 1
        return explore(view, state, anchor, *args, **kwargs)

    def read_signature(node):
        result = signature(node)
        proposals.append(result)
        return result

    def read_residual(problem, point):
        values = residual(problem, point)
        if len(proposals) != 8 or list(point) != [0, 0]:
            raise ValueError("Unexpected fixed-centre objective or paid fit")
        losses.append(score(values @ values))
        return values

    started = clock()
    with (patch.object(discovery, "fresh_discovery", read_centres),
          patch.object(discovery, "explore", read_exploration),
          patch.object(discovery, "signature", read_signature),
          patch.object(position.NormalPosition, "residual", read_residual)):
        result = rank(scan)
    timing = elapsed(started)
    radius = scan.search_region.half_width_km
    expected_corners = [(-radius, -radius), (-radius, radius), (radius, -radius), (radius, radius)]
    if ([node["seed"] for node in centres] != list(range(4)) or corners != expected_corners
            or proposals[:4] != [node["signature"] for node in centres] or len(proposals) != 8
            or nested_explorations != 8):
        raise ValueError("Ordinary proposal trace lost a centre, corner, or original order")
    first = {}
    for index, key in enumerate(proposals):
        first.setdefault(key, index)
    if len(first) != len(losses):
        raise ValueError("Expected exactly one objective per first-seen signature")
    rows = [dict(signature=key, first_proposal=index, loss=loss)
            for (key, index), loss in zip(first.items(), losses, strict=True)]
    ordered = sorted(rows, key=lambda row: row["loss"]["value"])
    if [signature(node) for node in result] != [row["signature"] for row in ordered]:
        raise ValueError("Observed stable rank differs from the original producer return")
    counts = Counter(row["loss"]["value"] for row in ordered)
    ties = [[i + 1 for i, row in enumerate(ordered) if row["loss"]["value"] == value]
            for value, count in counts.items() if count > 1]
    return dict(centres=centres, corners=[dict(anchor=anchor, signature=key)
                                         for anchor, key in zip(corners, proposals[4:], strict=True)],
                ordered=ordered, exact_ties=ties,
                counts=dict(centres=len(centres), corners=len(corners),
                            internal_centre_explorations=nested_explorations,
                            distinct=len(first), score_calls=len(losses)), timing=timing)


def top_three(raw, changed):
    original, proposal = ([row["signature"] for row in result["ordered"][:3]] for result in (raw, changed))
    return dict(same_order=original == proposal, same_members=set(original) == set(proposal),
                shared=len(set(original) & set(proposal)), original=original, half_blend=proposal)


def qualified(root):
    entry = saved.operands(root)
    custody, handoff, args, *_, rows, changes, native, _, _, _ = entry
    import exact_named_raw
    import exact_named_route
    import solver_exception_0022
    from leo.analysis.localization_v3 import discovery, position

    modules = (exact_named_raw, exact_named_route, solver_exception_0022, discovery, position)
    digests = {m.__name__.split(".")[-1]: saved.sha(Path(m.__file__)) for m in modules}
    if digests != PORTS:
        raise ValueError(f"The enrolled rank operand ports changed: {digests}")
    bound, request = exact_named_raw.request_from_handoff(args, handoff)
    witness_path = "publication/exact-named-raw-witness.json"
    witness = saved.read(saved.CONTROL / witness_path, saved.CONTROL_PINS[witness_path])
    route = witness["ports"]["history_risk"]
    if (route["choice"]["route"] != "lean" or route["nomination_handoff"]["ranked_nodes"] != 3
            or route["choice"]["census"]["prior"]["previous"]["catalogue_sha256"] != PREVIOUS
            or handoff.calls):
        raise ValueError("The authentic previous-bank rank control changed")
    binding = dict(case=saved.CASE, operand_registration=saved.registration(custody, rows, changes, native),
                   runner=saved.sha(Path(__file__)), ports=PORTS, request=request,
                   previous_bank_sha256=PREVIOUS, expected_original_nominees=3,
                   expected_original_labels=[row["labels"] for row in route["lean_attempts"][0]["cold"]["completed"]])
    return entry, binding, bound, modules


def run_pair(entry, bound, binding, modules):
    import empty_bootstrap as boot
    from leo.operations.tle_archive import TleArchiveReader
    from tools import algo08_scan
    from blind_joint_finish import digest

    custody, handoff, args, _, _, _, _, _, _, core, _, installed, rows, changes, *_ = entry
    raw_entry, exact, guards, discovery, position = modules
    offer = algo08_scan.Algo08Region.parse(saved.read(args.region))
    boot.check_inert_solver_assets(boot.RELEASE / "assets")
    boot.checked(guards.GUARD, guards.GUARD_PIN)
    repaired = runpy.run_path(str(guards.GUARD))["corner_support"]
    request = binding["request"]
    audit = dict(rank=[], blocks=Counter(), graph={}, gates=Counter(), portable={}, verified_tle=Counter())
    result, clocks = {}, {}

    def infer(prepared, region, native_bound, _stages, **_kwargs):
        if result or prepared["status"] != "inputs_prepared" or "prepare" not in clocks:
            raise RuntimeError("Exactly one original prepared scan is required")
        started = clock()
        scan = core.scan_context(prepared, region, digest(prepared["noise"]), native_bound, "previous")
        if (scan.previous_tle_sha256 != PREVIOUS or len(scan.norads) != 1539
                or len(scan.curved) != 7 or sum(oid in changes for i in scan.curved
                                               for oid in scan.tracks[i]["observation_ids"]) != 38):
            raise ValueError("The prepared catalogue or curved treatment changed")
        verify_graph(scan.tracks, rows)
        edited = proposal_view(scan, changes)
        clocks["prepare_scan"] = elapsed(started)
        rank = core.ranked_initial_nodes
        result["raw"] = rank_trace(rank, scan, discovery, position)
        original = result["raw"]["ordered"]
        if (len(original) != binding["expected_original_nominees"]
                or [sorted({row[1] for row in item["signature"]}) for item in original]
                != binding["expected_original_labels"]):
            raise ValueError("The raw rank did not reproduce the sealed ordinary counts and labels")
        result["half_blend"] = rank_trace(rank, edited, discovery, position)
        verify_graph(scan.tracks, rows)
        result["top_three"] = top_three(result["raw"], result["half_blend"])
        raise RankComplete()

    def decline(*_args, **_kwargs):
        raise RuntimeError("Rank-only experiment attempted a finalist fit")

    with exact.exact_ports(bound, request, audit, resident=lambda path: raw_entry.staged_path(path, root=args.archive)):
        ordinary_prepare = installed.prepare_native_scan

        def prepare(*a, **kw):
            if "prepare" in clocks:
                raise RuntimeError("Rank-only experiment attempted a second preparation")
            started = clock()
            try:
                return ordinary_prepare(*a, **kw)
            finally:
                clocks["prepare"] = elapsed(started)

        try:
            with (repaired() as support, patch.object(installed, "prepare_native_scan", prepare),
                  patch.object(core, "infer", infer), patch.object(position, "fit", decline),
                  patch.object(position, "refreshed", decline)):
                installed.solve(handoff.native, TleArchiveReader(args.archive), boot.RELEASE / "assets", offer)
        except RankComplete:
            pass
        else:
            raise RuntimeError("The installed entry returned without the rank-only stop")
    if list(result) != ["raw", "half_blend", "top_three"] or len(audit["rank"]) != 2 or handoff.calls or args.output.exists():
        raise RuntimeError("Rank-only custody or termination changed")
    return dict(case=saved.CASE, ranks=result, clocks=clocks, native_sha256=custody["native"],
                archive=custody["archive"], region=custody["region"], previous_bank_sha256=PREVIOUS,
                exact_ports=audit, orbit_support=support, prepares=1, finalist_fits=0, publications=0,
                waveform_reads=0, survey_reads=0)


def preflight(output):
    _, binding, _, _ = qualified(output.parent)
    print(saved.write(output, dict(binding=binding, rank_calls=0)))


def worker(root, proof, pin, fd):
    started = clock()
    saved.ready_runtime()
    import second_curve_gate_trial as admission

    if (not os.path.samestat(os.fstat(fd), admission.LOCK.stat()) or os.sched_getaffinity(0) != {2}
            or os.nice(0) < 15 or any(os.environ.get(key) != "1" for key in
            ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"))):
        raise ValueError("Expected inherited single-CPU idle admission")
    pressure = saved.direct_pressure(continuous=False)
    entry, binding, bound, modules = qualified(root)
    if saved.read(proof, pin) != dict(binding=binding, rank_calls=0):
        raise ValueError("Rank-only custody changed after preflight")
    saved.write(root / "stage-start.json", dict(started_ns=time_ns(), pressure=pressure, ready_sha256=pin))
    result = run_pair(entry, bound, binding, modules)
    print(saved.write(root / "rank-result.json", dict(result, ready_sha256=pin, child_scope=elapsed(started))))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("preflight", "watch", "worker"))
    cli.add_argument("case", choices=(saved.CASE,))
    cli.add_argument("output", type=Path)
    cli.add_argument("proof", type=Path, nargs="?")
    cli.add_argument("pin", nargs="?")
    cli.add_argument("--lease-fd", type=int)
    options = cli.parse_args()
    if options.mode == "preflight":
        preflight(options.output)
    elif options.mode == "watch":
        with patch.object(saved, "__file__", __file__):
            sys.exit(saved.watch(options.output, options.proof, options.pin))
    else:
        worker(options.output, options.proof, options.pin, options.lease_fd)
