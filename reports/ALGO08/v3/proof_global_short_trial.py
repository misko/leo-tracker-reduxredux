"""Replay one sealed genuine dense-short packet with a paid global proof slate."""

import argparse
from functools import partial
import gzip
from hashlib import sha256
from inspect import getsource
from math import isfinite
from pathlib import Path

from aperture_trial import read, write
from dense_geographic_trial import difference
from dense_quadratic_proxy import LIVE_ROUTE_PIN
from proof_cold_reuse import clocks, now
from proof_global_rank import fallback_reason, ranked_scores, reduced_input, select_pool


CONTROL_SHA = "07fc95971344bb0eeb50db142a8e0818f9c4ce6dfdbf3b6a2c9cb65421fabfb5"
RANK_GATE_SHA = "78de98f0526061f077cf3bb30c25369cccd36b4c6c69be3dfce01553db2c8402"
CROSSOVER_SHA = "445c28bf2a62439553d1f9491169b11506f9216cc97ad5e685bbc406d178c615"
PROOF_TOLERANCE = 1e-10


def checked(path, expected):
    if sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError(f"The authenticated comparison source changed at {path}")
    return read(path)


def expand_nodes(scan, slate, results):
    from leo.analysis.localization_v3.discovery import zero_state

    expanded = []
    for _, candidate in results:
        rows = [dict(row, candidate_index=slate[row["candidate_index"]]) for row in candidate["seed"]["rows"]]
        if any(int(scan.norads[row["candidate_index"]]) != row["candidate_norad"] for row in rows):
            raise ValueError("Reduced NORAD does not map to its original catalogue row")
        expanded.append(dict(seed=dict(rows=rows, state=zero_state(scan)), aliases=candidate["aliases"]))
    return expanded


def rank_live(paid, audit, ordinary, scan, prepared, region, bound, share_geometry):
    from numpy.linalg import LinAlgError

    from blind_joint_finish import digest
    from leo.analysis.localization_v3.discovery import signature
    from tools.pipeline_eval.variants import v5_core

    start = now()
    slate = select_pool(paid, scan.norads)
    record = dict(probes=len(paid), original_orbits=len(scan.norads), slate_size=len(slate or []), selector=clocks(start))
    rejected = "unusable_proof_pool"
    if slate is not None:
        try:
            start = now()
            reduced = v5_core.scan_context(reduced_input(prepared, slate), region, digest(prepared["noise"]), bound, "previous")
            record["reduced_setup"] = clocks(start)
            start = now()
            with share_geometry(reduced) as shared, ranked_scores(ordinary) as rank:
                results = rank(reduced)
            record.update(reduced_rank=clocks(start), shared=shared)
            rejected = fallback_reason(results)
            if rejected is None:
                nodes = expand_nodes(scan, slate, results)
                record.update(top_three=[dict(score=score, signature=signature(node))
                                         for (score, _), node in zip(results[:3], nodes[:3], strict=True)],
                              fallback=None)
                audit.append(record)
                return nodes
        except (ValueError, ArithmeticError, LinAlgError) as error:
            rejected = f"invalid_reduced_rank: {error}"
    start = now()
    with share_geometry(scan):
        nodes = ordinary(scan)
    record.update(fallback=rejected, full_rank=clocks(start))
    audit.append(record)
    return nodes


def proof_route(original, installed, reader, attempts, paid, audit):
    source = getsource(original)
    known = "            with share_geometry(scan):\n                return ordinary_rank(scan)"
    if sha256(source.encode()).hexdigest() != LIVE_ROUTE_PIN or source.count(known) != 1:
        raise ValueError("The original cold route binding changed")
    interpreter = dict(original.__globals__, _fused_rank=partial(rank_live, paid, audit))
    edit = source.replace(known, "            return _fused_rank(ordinary_rank, scan, prepared, region, bound, share_geometry)")
    exec(compile(edit, original.__code__.co_filename, "exec"), interpreter)
    return interpreter[original.__name__](installed, reader, attempts, optimized=True)


def run(control_path, rank_gate, raw, process, binary, output, summary, archive):
    import dense_full_short_crossover as short

    control = checked(control_path, CONTROL_SHA)
    gate = checked(rank_gate, RANK_GATE_SHA)
    if not gate["global_rank"]["warrants_complete_replay"]:
        raise ValueError("A signed saved replay requires the original reduced rank to pass")
    if sha256(Path(short.__file__).read_bytes()).hexdigest() != CROSSOVER_SHA:
        raise ValueError("The successor control runner changed")
    source = getsource(short.run)
    old = "            full = full_catalogue_route(v5_core.infer, reader, attempts, optimized=True)"
    if source.count(old) != 1:
        raise ValueError("The successor full-catalogue port changed")
    new = "            full = _proof_route(full_catalogue_route, v5_core.infer, reader, attempts, visited, _rank_audit)"
    audit = []
    provider = dict(short.run.__globals__, _proof_route=proof_route, _rank_audit=audit)
    exec(compile(source.replace(old, new), short.run.__code__.co_filename, "exec"), provider)
    provider["run"](raw, process, binary, output)
    result = read(output)
    checks = {key: control[key] == result[key] for key in (
        "raw", "status", "reason", "orbit_policy", "track_asset_sha256", "graph", "arms", "owners", "associated",
        "grid", "grid_points", "selected_rows", "science", "objective_replay",
    )}
    proof_delta = difference(control["visited_probes"], result["visited_probes"])
    checks["paid_proof"] = proof_delta <= PROOF_TOLERANCE and difference(
        [row["result"] for row in control["regional"]], [row["result"] for row in result["regional"]]) <= PROOF_TOLERANCE
    checks["fit_route"] = ([row["decision"] for row in control["attempts"]] == [row["decision"] for row in result["attempts"]])
    checks["live_rank_paid"] = len(audit) == 1 and audit[0]["probes"] == len(result["visited_probes"])
    result_summary = dict(valid=all(checks.values()), checks=checks, prototype_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                          control_sha256=CONTROL_SHA, incumbent_rank_sha256=RANK_GATE_SHA, paid_rank=audit,
                          proof_score_difference=proof_delta if isfinite(proof_delta) else None,
                          receipts={name: dict(solve=row["solve"], regional=row["regional"], arms=row["arms"],
                                               status=row["status"], reason=row["reason"], owners=row.get("associated"),
                                               grid_points=row.get("grid_points"),
                                               cold_cpu_s=[a["cold_clocks"]["cpu_s"] for a in row["attempts"]])
                                    for name, row in (("control", control), ("proof_union", result))},
                          candidate_sha256=sha256(output.read_bytes()).hexdigest())
    write(summary, result_summary)
    with archive.open("xb") as stream:
        stream.write(gzip.compress(output.read_bytes(), mtime=0))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("control_path", "rank_gate", "raw", "process", "binary", "output", "summary", "archive"):
        cli.add_argument(name, type=Path)
    run(**vars(cli.parse_args()))
