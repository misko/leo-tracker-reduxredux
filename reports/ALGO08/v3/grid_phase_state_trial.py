"""Audit paired predictive geometry inside one genuine dense publication grid."""

import argparse
from contextlib import ExitStack
from pathlib import Path
from runpy import run_path
from unittest.mock import patch

from aperture_trial import archive_identity, configuration, read, solve as saved_solve, write
from cold_track_row_transfer import DENSE, GEOGRAPHIC, PREVIOUS, RAW, same_route
from cold_track_row_trial import REPLAY_PIN, same_proof
import dense_full_short_crossover as crossover
from dense_geographic_trial import host
from grid_phase_state_reuse import GridAudit, SOURCES, cached_predictive_grid


SCIENCE = ("status", "reason", "orbit_policy", "arms", "owners", "selected_rows", "grid_points", "grid", "science",
           "associated", "objective_replay", "graph", "track_asset_sha256", "visited_probes")
SOUTH = Path("/var/tmp/leo-short-graph-20261123-south-inside")
SOUTH_SHA256 = "5d7b28ab3ce6dd3f06e09153481eb125dfad45a11486cc863fdd2fd2e018ce64"


def run(output):
    if crossover.file_sha(DENSE) != REPLAY_PIN:
        raise ValueError("The archived matched grid replay changed")
    baseline = read(DENSE)
    archived_source = PREVIOUS / "reports/ALGO08/v3/dense_full_short_crossover.py"
    if crossover.file_sha(archived_source) != baseline["code"][archived_source.name]:
        raise ValueError("The archived detector verification source changed")
    verify = run_path(str(archived_source))["raw_candidate"]
    original_solve = crossover.solve
    audit = GridAudit()

    def solve(*args):
        from leo.presentation import localization_v3 as presentation
        from tools import algo08_position

        original_packet = algo08_position.selected_packet

        def selected(*args, **kwargs):
            sample = audit.grid(presentation.sample_position_grid)
            with patch.object(presentation, "sample_position_grid", sample):
                return original_packet(*args, **kwargs)

        with patch.object(algo08_position, "selected_packet", selected):
            return original_solve(*args)

    output.mkdir(exist_ok=False)
    replay = output / "replay.json"
    with patch.object(crossover, "raw_candidate", verify), patch.object(crossover, "solve", solve):
        crossover.run(RAW / "publication", RAW / "process.json", GEOGRAPHIC, replay)
    candidate = read(replay)
    control_attempt, = baseline["attempts"]
    candidate_attempt, = candidate["attempts"]
    direct = audit.report()
    checks = {key: candidate[key] == baseline[key] for key in SCIENCE}
    checks.update(route=same_route(candidate_attempt, control_attempt),
                  proof=candidate["regional"][0]["result"] == baseline["regional"][0]["result"],
                  dense_grid=(candidate["grid"]["complete"] and candidate["grid_points"] == 179),
                  geometry=bool(direct["calls"]) and all(row["exact"] for row in direct["calls"]),
                  same_handoff=candidate["posterior_grid_handoff"]["factor_calls"] == len(direct["calls"]) == 356,
                  predictor_domain=direct["private_views"] == 2 and all(row["altitude"] == 0. for row in direct["calls"]))
    timings = {name: candidate[name] for name in ("solve", "posterior_grid_handoff", "grid_kernel", "curved_design")}
    timings["candidate_evidence"] = candidate_attempt["standard_evidence_clocks"]
    timings["matched_original_evidence"] = control_attempt["standard_evidence_clocks"]
    pins = {path.name: crossover.file_sha(path) for path in (
        Path(__file__), Path(__file__).with_name("grid_phase_state_reuse.py"),
        Path(__file__).with_name("grid-phase-state-reuse-protocol.md"), archived_source, replay,
    )}
    write(output / "grid-audit.json", dict(source_sha256=pins, installed=SOURCES, archived_replay_sha256=REPLAY_PIN,
          input_sha256=candidate["raw"]["raw_native_sha256"], track_asset_sha256=candidate["track_asset_sha256"],
          archive=candidate["raw"]["holder"]["archive"], science_sha256=candidate["science"],
          machine=candidate["machine"], checks=checks, times=timings, **direct))
    if not all(checks.values()):
        raise ValueError(f"Genuine grid did not reproduce the archived evidence: {checks}")


def run_without_predictive(output):
    """Qualify the composable context on an existing zero-predictive saved fix."""
    machine = host()
    publication, specification = configuration()
    from early_region import before_fit
    from joint_publication import full_catalogue_route
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from optimized_grid import reduced_grid
    from prepared_exterior import handoff
    from proof_rank_short_transfer import saved
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core
    from tools.pipeline_eval.variants.experimental import regional_bound_guard

    prior = SOUTH / "joint-research-receipt.json"
    if crossover.file_sha(prior) != SOUTH_SHA256:
        raise ValueError("The archived southern empty-predictive control changed")
    control = read(prior)
    report = control["receipt"]
    terminal = read(SOUTH / "fast-scan-automatic-work" / report["run_id"] / "terminal.json")
    native, archive, offer, identity = saved("south-inside")
    if (canonical_digest(terminal) != report["terminal_sha256"] or terminal["region"] != offer
            or terminal["native_sha256"] != identity["native_sha256"]
            or control["route_details"]["support"]["predictive_points"] != 0):
        raise ValueError("Expected the source-bound southern fix with no predictive rows")
    old_solve = algo08_position.solve
    attempts, proofs, rows, counts = [], [], {}, {}

    def observed(document, reader, assets, region):
        if (document is not native or reader.root != archive or region.document() != offer
                or crossover.file_sha(assets / "tracks.json") != crossover.TRACK_ASSET_PIN):
            raise ValueError("The original saved packet, offer or installed graph changed")
        with ExitStack() as stack:
            live, _, _ = stack.enter_context(handoff(reader))
            stack.enter_context(reduced_grid())
            metrics = stack.enter_context(cached_predictive_grid())
            route = full_catalogue_route(v5_core.infer, reader, attempts, optimized=True)
            guarded = before_fit(route, reader, regional_bound_guard.causal_probes, proofs, live.match)
            stack.enter_context(patch.object(v5_core, "infer", guarded))
            decision, packet, policy = old_solve(document, reader, assets, region)
        counts.update(metrics)
        if packet is not None:
            for arm, selected in packet["rows"].items():
                rows[arm] = [[row[key] for key in crossover.OWNER_KEYS] for row in selected]
        return decision, packet, policy

    with patch.object(algo08_position, "solve", observed):
        result = saved_solve(publication, specification, native, archive, offer)
    result.pop("owner_rows", None)
    completed = output.with_suffix(".replay.json")
    write(completed, dict(solution=result, attempts=attempts, owners=rows, proofs=proofs, runtime=counts))
    archive_rows = read(completed)
    attempts, proofs = archive_rows["attempts"], archive_rows["proofs"]
    store = FastStandardAnalysisStore(SOUTH)
    methods = {"path": store.position_path, "grid": store.position_grid}
    science = {name: canonical_digest({k: v for k, v in method(report["run_id"]).items()
                                     if k not in ("binding", "elapsed_seconds")}) for name, method in methods.items()}
    checks = dict(route=len(attempts) == 1 and same_route(dict(salvage_shortlists=None) | attempts[0],
                        dict(salvage_shortlists=None) | control["route_details"]),
                  owners=rows == control["selected_rows"], grid_and_path=result["science"] == science,
                  proof=len(proofs) == 1 and same_proof(proofs[0]["result"], control["early_regional"][0]["result"]),
                  archive=archive_identity(archive) == identity["archive"],
                  terminal=result["status"] == "ok" and result["arms"] == terminal["arms"]
                  and result["reason"] == terminal["reason"] and result["orbit_policy"] == terminal["orbit_policy"],
                  empty_predictive=counts == dict(grids=1, prepared_views=0, prepared_calls=0))
    write(output, dict(identity=identity, machine=machine, control_sha256=SOUTH_SHA256, runtime=counts, checks=checks,
                       solution=result, proof=proofs, replay_sha256=crossover.file_sha(completed),
                       source_sha256={name: crossover.file_sha(Path(__file__).with_name(name))
                           for name in ("grid_phase_state_trial.py", "grid_phase_state_reuse.py")}))
    if not all(checks.values()):
        raise ValueError(f"The empty-predictive saved science changed: {checks}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--south-empty-predictive", action="store_true")
    args = parser.parse_args()
    (run_without_predictive if args.south_empty_predictive else run)(args.output)
