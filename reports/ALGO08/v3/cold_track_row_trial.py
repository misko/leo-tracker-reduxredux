"""Measure one exact full-catalogue cold-rank pair on the sealed dense short receiver."""

import argparse
from collections import Counter
from contextlib import ExitStack
import json
from pathlib import Path
from runpy import run_path
from unittest.mock import patch

from aperture_trial import ARMS, archive_identity, configuration, inputs, read, solve, write
from blind_rank_trial import timer
from cold_track_row_reuse import shared_association_rows
from dense_full_short_crossover import CASE, HERE, TRACK_ASSET_PIN, file_sha
from dense_geographic_trial import elapsed, host, now
from proof_global_rank import ranked_scores


REPLAY_PIN = "07fc95971344bb0eeb50db142a8e0818f9c4ce6dfdbf3b6a2c9cb65421fabfb5"
SHARING = HERE.parents[2] / "tools/pipeline_eval/variants/algo08_blind_rank.py"


def fit_evidence(value):
    if isinstance(value, dict):
        return {key: fit_evidence(data) for key, data in value.items() if key != "cpu_ns"}
    if isinstance(value, list):
        return [fit_evidence(data) for data in value]
    return value


def rank_and_race(prepared, region, bound, reuse, share):
    from cold_finalist_race import refine
    from leo.analysis.localization_v3 import discovery
    from leo.application.localization_v3_engine import _json_value
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.variants import v5_core

    installed_rank = v5_core.ranked_initial_nodes
    attribution, reused = Counter(), Counter()
    result = {}

    def rank(scan):
        start = now()
        with ExitStack() as scope:
            shared = scope.enter_context(share(scan))
            if reuse:
                tables = discovery.phase_linear_frequency.__self__
                scope.enter_context(shared_association_rows(scan, tables, reused))
            for name in ("phase_linear_frequency", "proposal_phases", "improve", "standard_problem"):
                timer(scope, discovery, name, attribution)
            for name in ("association", "curve", "predictions"):
                timer(scope, scan, name, attribution)
            ranked = scope.enter_context(ranked_scores(installed_rank))(scan)
        result.update(rank=elapsed(start), shared=dict(shared), orbits=list(map(int, scan.norads)),
                      nominal_times=len(scan.times), curved_tracks=len(scan.curved))
        result["ranked"] = ranked
        return [row[1] for row in ranked]

    with ExitStack() as scope:
        scope.enter_context(patch.object(v5_core, "ranked_initial_nodes", rank))
        timer(scope, v5_core, "scan_context", attribution)
        start = now()
        node, point, reference, cold = refine("race", prepared, region, bound)
        clock = elapsed(start)
    result.update(cold=clock, branch=dict(cold, reference=reference, selected_signature=discovery.signature(node)),
                  attribution_ns=dict(attribution), reuse=dict(reused), records=[
                      dict(score=score, signature=discovery.signature(candidate),
                           diagnostics=canonical_digest(json.loads(json.dumps(
                               candidate["seed"]["rows"], default=_json_value))))
                      for score, candidate in result.pop("ranked")])
    return json.loads(json.dumps(result, default=_json_value, allow_nan=False))


def run(raw, process, binary, replay, archived_code, output):
    machine = host()
    publication, spec = configuration()
    from early_region import before_fit
    from full_short_run import geographic_projection
    from prepared_exterior import handoff
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core
    from tools.pipeline_eval.variants.experimental import regional_bound_guard

    if file_sha(replay) != REPLAY_PIN:
        raise ValueError("The original complete genuine short replay changed")
    sealed = read(replay)
    if file_sha(archived_code) != sealed["code"]["dense_full_short_crossover.py"]:
        raise ValueError("Expected the original source verifier in the archived replay checkout")
    verify_source = run_path(str(archived_code))["raw_candidate"]
    original, archive, offer, _, identity = inputs(CASE)
    native, source = verify_source(raw, process, binary, original, identity)
    share = run_path(str(SHARING))["shared_rank_preparation"]
    original_solve = algo08_position.solve
    pair, graphs, regional, counts = {}, [], [], {}

    def scheduled(prepared, region, bound, _stages, **_options):
        tracks = prepared["tracks"]
        graphs.append(dict(status=prepared["status"], graph_points=tracks["graph_points"],
                           tracks=len(tracks["tracks"]), active_curvature=len(tracks["curved_indices"])))
        for mode in ("reused", "released"):
            pair[mode] = rank_and_race(prepared, region, bound, mode == "reused", share)
        return dict(status="withheld", reason="cold_rank_pair_complete", arms={arm: {"latlon": None} for arm in ARMS})

    def observed(document, reader, assets, region):
        if (document is not native or reader.root != archive or region.document() != offer
                or file_sha(assets / "tracks.json") != TRACK_ASSET_PIN):
            raise ValueError("Expected the sealed genuine short detector and installed graph")
        with ExitStack() as scope:
            projection = scope.enter_context(geographic_projection(binary))
            live, catalogue, _ = scope.enter_context(handoff(reader))
            route = before_fit(scheduled, reader, regional_bound_guard.causal_probes, regional, live.match)
            scope.enter_context(patch.object(v5_core, "infer", route))
            result = original_solve(document, reader, assets, region)
        counts.update(projection=dict(projection), catalogue=dict(catalogue))
        return result

    with patch.object(algo08_position, "solve", observed):
        result = solve(publication, spec, native, archive, offer)
    if (result["reason"] != "cold_rank_pair_complete" or graphs != [sealed["graph"]]
            or len(regional) != 1 or regional[0]["result"] != sealed["regional"][0]["result"]
            or archive_identity(archive) != identity["archive"]):
        raise ValueError("The installed graph, paid geographic proof or causal archive changed")
    released, reused = pair["released"], pair["reused"]
    cold, archived = released["branch"], sealed["attempts"][0]["cold"]
    comparison = dict(
        same_candidates=released["orbits"] == reused["orbits"],
        same_ordered_ranks=released["records"] == reused["records"],
        same_branch=fit_evidence(cold) == fit_evidence(reused["branch"]),
        archived_branch=fit_evidence({key: cold[key] for key in archived}) == fit_evidence(archived),
        rank_saved_cpu_s=released["rank"]["cpu_s"]-reused["rank"]["cpu_s"],
    )
    if not comparison["archived_branch"] or len(released["orbits"]) != cold["catalogue"]:
        raise ValueError("The trial did not reproduce the previously sealed genuine-short cold result")
    names = ("cold-track-row-reuse-protocol.md", "cold_track_row_reuse.py", "cold_track_row_trial.py",
             "proof_global_rank.py", "cold_finalist_race.py", "joint_publication.py")
    pins = {name: file_sha(HERE / name) for name in names}
    pins[SHARING.name] = file_sha(SHARING)
    write(output, dict(machine=machine, source=source["files_sha256"], input_sha256=source["raw_native_sha256"],
                       archive=identity["archive"], offer=offer, controls={"sealed_replay": REPLAY_PIN,
                       "archived_solve": sealed["solve"], "graph_asset": TRACK_ASSET_PIN}, graph=graphs[0],
                       code=pins, pair=pair, comparison=comparison, regional=regional[0], **counts))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("raw", "process", "binary", "replay", "archived_code", "output"):
        parser.add_argument(field, type=Path)
    run(**vars(parser.parse_args()))
