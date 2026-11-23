"""Run the installed graph once on the actual authenticated dense short detector."""

import argparse
from contextlib import ExitStack
from hashlib import sha256
from inspect import getsource
import json
from pathlib import Path
from unittest.mock import patch

from aperture_trial import ARMS, archive_identity, configuration, inputs, read, solve, write
from dense_geographic_trial import elapsed, host, now
from dense_quadratic_proxy import LIVE_ROUTE_PIN


HERE = Path(__file__).resolve().parent
CASE = "DS30-0008"
ISSUED, ADMITTED = 6772, 6765
TRACK_ASSET_PIN = "a7a252b2fd9a9fe7c617f4565b171c159846705803f4fb80ab755ba9ea94710a"
OWNER_KEYS = ("observation_id", "norad", "role")


def file_sha(path):
    return sha256(path.read_bytes()).hexdigest()


def same_source(probes):
    return [{key: value for key, value in probe.items() if key != "candidates"} for probe in probes]


def command_path(command, flag, path):
    return command.count(flag) == 1 and Path(command[command.index(flag) + 1]).resolve() == Path(path).resolve()


def validate_receipt(terminal, detail, result, native_pin, region, session, raw_authority):
    from leo.contracts.digests import canonical_digest

    if (terminal["native_sha256"] != native_pin or detail["input_sha256"] != native_pin
            or canonical_digest(terminal) != result["terminal_sha256"]
            or detail["terminal_sha256"] != result["terminal_sha256"]
            or any(row["region"] != region for row in (result, terminal, detail))
            or result["session_id"] != session or terminal["session_id"] != session
            or detail["raw_authority"] != raw_authority or detail["state"] != result["decision"]):
        raise ValueError("The original signed terminal and web evidence do not bind the candidate packet")


def raw_candidate(root, process, binary, original, identity):
    from leo.contracts.digests import canonical_digest
    from leo.presentation.localization_v3 import owner_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from full_short_physical_score import classified
    from full_short_raw import GRAPH, RECIPE_SHA, SHORT_SHA, recipe
    from full_short_run import GEOGRAPHIC_SHA
    from joint_publication import artifacts

    completed = read(process)
    if process.resolve() != (root.parent / "process.json").resolve() or completed["status"] != 0:
        raise ValueError("The authorized complete raw candidate did not seal successfully")
    binding_path = root.parent / "binding.json"
    binding = read(binding_path)
    launcher_path = root / "full-short-recipe.json"
    research_path = root / "joint-research-receipt.json"
    launch, research = read(launcher_path), read(research_path)
    receipt = research["receipt"]
    native_path, = (root / "fast-scan-automatic-work").glob("*/detections.json")
    terminal_path = root / "fast-scan-automatic-work" / receipt["run_id"] / "terminal.json"
    native, terminal = read(native_path), read(terminal_path)
    source, provenance = native["source"], native["provenance"]
    audit, probes = launch["receiver_audit"], source["probes"]
    old = original["source"]
    scheduled = classified(probes)
    native_pin = canonical_digest(native)
    session = old["session_id"]
    authority = identity["raw_authority"]
    analysis = canonical_digest(["cancellation", authority, RECIPE_SHA, probes])
    command = binding["command"]
    if (binding["archive"] != identity["archive"] or binding["region_sha256"] != identity["offer_source_sha256"]
            or file_sha(Path(binding["region"])) != identity["offer_source_sha256"]
            or binding["case"] != CASE or binding["authority"] != authority or binding["session"] != session
            or binding["inventory"] != old["input_manifest_sha256"] or binding["pair_sha256"] != identity["pair_sha256"]
            or binding["short_sha256"] != SHORT_SHA or binding["geographic_sha256"] != GEOGRAPHIC_SHA
            or not command_path(command, "--archive", identity["archive"]["root"])
            or not command_path(command, "--region", binding["region"])
            or not command_path(command, "--geographic-library", binary)
            or not command_path(command, "--output", root) or "--saved" in command):
        raise ValueError("The sealed raw launch does not use the frozen archive, recipe, offer and fused projector")
    for name in ("full_short_run.py", "full_short_raw.py", "joint_publication.py", "dense_geographic_projection.py"):
        if file_sha(HERE / name) != binding["source_sha256"][name]:
            raise ValueError(f"The raw and saved launch bindings differ at {name}")
    if (not research["input"].startswith("verified raw") or research["saved_digest"] is not None
            or research["saved_handoff_manifest"] is not None or launch["saved_digest"] is not None
            or not research["optimized_full_catalogue"] or not research["signed_finish"] or research["stock_control"]
            or launch["recipe"] != recipe() or canonical_digest(launch["recipe"]) != "sha256:" + RECIPE_SHA
            or launch["graph"] != GRAPH or launch["geographic_sha256"] != GEOGRAPHIC_SHA or file_sha(binary) != GEOGRAPHIC_SHA
            or audit["detector_pin"] != RECIPE_SHA or provenance["detector_sha256"] != "sha256:" + RECIPE_SHA
            or source["session_id"] != session or not source["qualified"]
            or source["input_manifest_sha256"] != audit["input_manifest"]
            or source["input_manifest_sha256"] != old["input_manifest_sha256"]
            or source["raw_recording_authority_digest"] != authority or audit["recording_authority"] != authority
            or source["analysis_manifest_sha256"] != analysis or audit["analysis_manifest"] != analysis
            or receipt["window_count"] != ISSUED or audit["issued"] != ISSUED
            or provenance["window_count"] != ISSUED or provenance["processed_windows"] != ADMITTED
            or receipt["counts"] != dict(processed=ADMITTED, invalid_capture=ISSUED-ADMITTED, skipped_fast_score=0)
            or len(probes) != 2 * ADMITTED or same_source(probes) != same_source(old["probes"])
            or any(native[name] != original[name] for name in ("clock_anchor", "delivery_clocks"))
            or any(audit["native"].get(key) != value for key, value in scheduled.items())):
        raise ValueError("The raw candidate does not reproduce the frozen signed stereo detector or geography binding")

    for name, digest in research["source_sha256"].items():
        if name.startswith("installed/"):
            continue
        if file_sha(HERE / name) != digest:
            raise ValueError(f"The raw and saved routes differ at {name}")
    proof, = research["early_regional"]
    native_projection = research["solve"]["geographic_projector"]
    if sum(native_projection.get(k, 0) for k in ("calls", "original_fallback")) < proof["result"]["probes_evaluated"]:
        raise ValueError("The raw geographic proof did not account for all probe projections")

    store = FastStandardAnalysisStore(root)
    detail = store.detail(receipt["run_id"])
    validate_receipt(terminal, detail, receipt, native_pin, identity["offer"], session, authority)
    if json.loads(json.dumps(artifacts(root, receipt))) != research["evidence"]:
        raise ValueError("The original raw figure and numerical artifact digests changed")
    selected = research["selected_rows"]
    owners, counts = {}, {}
    grid = None
    if receipt["decision"] == "complete":
        grid = store.position_grid(receipt["run_id"])
        if not grid["complete"] or not research["solve"]["grid_complete"]:
            raise ValueError("The original raw result has incomplete grid evidence")
        for arm in ARMS:
            owners[arm] = detail["arms"][arm]["owner_sha256"]
            counts[arm] = detail["arms"][arm]["associated_points"]
            mapping = {oid: norad for oid, norad, _role in selected[arm]}
            if len(selected[arm]) != counts[arm] or len(mapping) != counts[arm] or owner_digest(mapping) != owners[arm]:
                raise ValueError("The raw owner and role rows failed the official owner's digest check")
    elif receipt["decision"] != "withheld" or selected or detail["artifacts"]:
        raise ValueError("Expected a complete raw detector and a terminal science outcome")

    pins = {path.name: file_sha(path) for path in (binding_path, launcher_path, research_path, native_path, terminal_path, process)}
    original_result = dict(status="ok" if grid is not None else "withheld", reason=terminal["reason"],
                           arms=terminal["arms"], selected_rows=selected, owners=owners, associated=counts,
                           grid=grid, grid_points=research["solve"].get("grid_points"),
                           objective_replay=research["solve"].get("objective_replay"),
                           science=research["evidence"], solve=research["solve"], regional=[proof],
                           attempts=[research["route_details"]] if research["route_details"] is not None else [],
                           route=research["route"], orbit_policy=terminal["orbit_policy"],
                           publication={"cpu_s": research["publication_cpu_s"], "elapsed_s": research["publication_elapsed_s"]})
    records = dict(raw_result=original_result, files_sha256=pins, process=completed, binding=binding, recipe=launch["recipe"],
                   raw_native_sha256=native_pin, stock_native_sha256=identity["native_sha256"],
                   holder=identity, schedule=scheduled, fused_geography_sha256=GEOGRAPHIC_SHA,
                   source_sha256=research["source_sha256"], archive_snapshots=proof["result"]["snapshots"])
    return native, records


def run(raw, process, binary, output):
    current = host()
    publication, specification = configuration()
    from dense_geographic_projection import checked_runtime
    from early_region import before_fit
    from full_short_run import geographic_projection
    from joint_publication import full_catalogue_route
    from optimized_grid import reduced_grid
    from prepared_exterior import handoff
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core
    from tools.pipeline_eval.variants.experimental import regional_bound_guard

    original, archive, offer, _, identity = inputs(CASE)
    native, raw_records = raw_candidate(raw, process, binary, original, identity)
    stock = algo08_position.solve
    attempts, regional, visited, graph = [], [], [], []
    extra = {}
    if sha256(getsource(full_catalogue_route).encode()).hexdigest() != LIVE_ROUTE_PIN:
        raise ValueError("Expected the frozen full-catalogue route")

    def observed(document, reader, assets, region):
        if (document is not native or reader.root != archive or region.document() != offer
                or file_sha(assets / "tracks.json") != TRACK_ASSET_PIN):
            raise ValueError("Expected one bound saved input with the original installed graph asset")
        kernel, _ = checked_runtime()
        prepare = kernel._prepare_probe_scores

        def audit(*args):
            points, score, meta = prepare(*args)

            def scored(point):
                row = score(point)
                visited.append(dict(row))
                return row

            return points, scored, meta

        with ExitStack() as scopes:
            projection = scopes.enter_context(geographic_projection(binary))
            live, catalogue, _ = scopes.enter_context(handoff(reader))
            grid = scopes.enter_context(reduced_grid())
            full = full_catalogue_route(v5_core.infer, reader, attempts, optimized=True)
            guarded = before_fit(full, reader, regional_bound_guard.causal_probes, regional, live.match)

            def infer(prepared, *values, **options):
                tracks = prepared["tracks"]
                graph.append(dict(status=prepared["status"], graph_points=tracks["graph_points"],
                                  tracks=len(tracks["tracks"]), active_curvature=len(tracks["curved_indices"])))
                return guarded(prepared, *values, **options)

            scopes.enter_context(patch.object(kernel, "_prepare_probe_scores", audit))
            scopes.enter_context(patch.object(v5_core, "infer", infer))
            start = now()
            decision, packet, policy = stock(document, reader, assets, region)
            extra["solve"] = elapsed(start)
        extra.update(native_projection=dict(projection), catalogue=dict(catalogue), grid_kernel=dict(grid))
        if packet is not None:
            if not packet["position_grid"]["complete"]:
                raise ValueError("The saved replay must complete both numerical grids")
            extra.update(grid={k: v for k, v in packet["position_grid"].items() if k not in ("binding", "elapsed_seconds")},
                         selected_rows={arm: [[r[k] for k in OWNER_KEYS] for r in packet["rows"][arm]] for arm in ARMS})
        return decision, packet, policy

    with patch.object(algo08_position, "solve", observed):
        result = solve(publication, specification, native, archive, offer)
    proof, = regional
    projected = extra["native_projection"]
    if (len(graph) != 1 or proof["result"]["probes_evaluated"] > len(visited)
            or sum(projected.get(k, 0) for k in ("calls", "original_fallback")) != len(visited)
            or proof["result"]["snapshots"] != raw_records["archive_snapshots"]
            or archive_identity(archive) != identity["archive"]):
        raise ValueError("The saved result must reach the original fused geographic proof and causal archive")
    result.pop("owner_rows", None)
    write(output, dict(result, raw=raw_records, machine=current, attempts=attempts, regional=regional,
                       visited_probes=visited, graph=graph[0], track_asset_sha256=TRACK_ASSET_PIN,
                       code={name: file_sha(HERE / name) for name in (Path(__file__).name, "dense-full-short-crossover-protocol.md")},
                       **extra))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("raw", "process", "binary", "output"):
        parser.add_argument(name, type=Path)
    run(**vars(parser.parse_args()))
