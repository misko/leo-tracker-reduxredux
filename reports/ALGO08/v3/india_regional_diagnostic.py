"""Compare the original complete regional diagnostics on the two sealed India offers."""

import argparse
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch

from aperture_trial import ARMS, configuration, machine, read, write
from india_saved_transfer import HERE, MODES, ROUTES, STAGED, bind, digest
from joint_publication import full_catalogue_route
from mixture_trial import elapsed, summarize
from prepared_exterior import handoff


BASELINE = HERE / "measurements/india-saved-transfer.json.gz"


def pins(live):
    from sgp4.exporter import export_tle
    from leo.contracts.digests import canonical_digest

    catalogue = live.catalogue
    sats = catalogue.catalogue
    items = [[norad, list(export_tle(sat)), evidence] for norad, sat, evidence in
             zip(sats.satellite_numbers, sats.satellites, catalogue.provenance, strict=True)]
    return dict(graph_sha256=canonical_digest(live.tracks), catalogue_sha256=canonical_digest(items),
                archive=str(live.root), cutoff=live.cutoff, members=len(items))


def pair_original(runs, current, mode, route):
    from leo.application.localization_v3_engine import _json_value

    prior = runs[mode][route]
    # The installed probe uses integer receiver keys in memory. Its original
    # sealed JSON receipt converts them to strings and encodes array values.
    current = json.loads(json.dumps(current, default=_json_value, allow_nan=False))
    keys = ("identity", "arms", "owners", "selected_rows", "science", "status", "reason", "grid_points", "associated", "objective_replay")
    differences = [key for key in keys if prior.get(key) != current.get(key)]
    if [c["result"] for c in prior["exterior_checks"]] != [c["result"] for c in current["exterior_checks"]]:
        differences.append("exterior_result")
    if differences:
        raise ValueError(f"Catalogue handoff changed the original {route} result: {differences}")


def run(mode, route, output, *, site):
    host = machine()
    if (host["cpu"] != [2] or host["nice"] < 15 or "prio 7" not in host["ionice"]
            or any(n != "1" for n in host["threads"].values())):
        raise ValueError("Expected one shared low-priority Gauss slot")
    release, spec = configuration()
    from leo.analysis.localization_v3.region import SearchRegion
    from leo.operations.tle_archive import TleArchiveReader
    from tools import algo08_position, algo08_scan
    from tools.pipeline_eval.variants import v5_core
    from tools.pipeline_eval.variants.experimental import regional_bound_guard

    native, catalogue, region_file, identity, verify = bind(site, mode)
    baseline = json.loads(gzip.decompress(BASELINE.read_bytes()))["runs"]
    attempts, checks = [], []

    def analyze(recording, _root, assets, archive, offer):
        if recording.exists() or archive != catalogue or offer.document() != identity["offer"]:
            raise ValueError("Expected the original saved-only waveform offer")
        reader = TleArchiveReader(archive)
        original_infer = v5_core.infer
        chosen = (full_catalogue_route(original_infer, reader, attempts)
                  if route == "full-catalogue" else original_infer)
        original_check = regional_bound_guard.inspect_boundary

        def check(*args, **kwargs):
            start = process_time(), perf_counter()
            found = original_check(*args, **kwargs)
            checks.append(dict(result=found, **elapsed(*start)))
            return found

        with (handoff(reader) as (live, counts, native_probe), patch.object(v5_core, "infer", chosen),
              patch.object(regional_bound_guard, "inspect_boundary", check)):
            start = process_time(), perf_counter()
            decision, evidence, policy = algo08_position.solve(native, reader, assets, offer)
            numerical_clocks = elapsed(*start)
        if evidence is None or not evidence["position_grid"]["complete"] or live.catalogue is None:
            raise ValueError("Expected the original full fix and a bound causal catalogue")
        result, _ = summarize(decision, evidence, policy)
        owners = {arm: [[row["observation_id"], row["norad"], row["role"]] for row in evidence["rows"][arm]] for arm in ARMS}
        result.update(identity=identity, exterior_checks=checks, selected_rows=owners)
        pair_original(baseline, result, mode, route)
        result.update(solve=numerical_clocks, actual_handoff=dict(counts), binding=pins(live), route_attempts=attempts)
        if route == "stock":
            region = SearchRegion(offer.center, width_km=offer.width_km)
            order = ("fresh", "prepared") if mode == "matched-tile" else ("prepared", "fresh")
            probes, clocks = {}, {}
            for choose in order:
                supplied = live.match(live.tracks, reader) if choose == "prepared" else None
                start = process_time(), perf_counter()
                probes[choose] = native_probe(live.tracks, reader, region, catalogue=supplied)
                clocks[choose] = elapsed(*start)
            if probes["fresh"] != probes["prepared"] or len(probes["prepared"]["points"]) != 96:
                raise ValueError("Prepared reuse changed the complete geographic scores")
            result.update(full_diagnostic=probes["prepared"], diagnostic_clocks=clocks, diagnostic_order=order,
                          exact_probe_match=True)
        return result

    with TemporaryDirectory() as scratch, patch.object(algo08_scan, "analyze", analyze):
        root = Path(scratch)
        data = release.run(SimpleNamespace(recording=root / "unused-recording", bulk_root=root,
                                           archive=catalogue, region=region_file), spec)
    verify()
    if len(attempts) != int(route == "full-catalogue"):
        raise ValueError("Expected one solver through the selected saved route")
    data.update(host=host, route=route, baseline_sha256=digest(BASELINE.read_bytes()),
                sources={name: digest((HERE / name).read_bytes()) for name in
                         ("india_regional_diagnostic.py", "prepared_exterior.py", "india-regional-diagnostic-protocol.md")})
    write(output, data)


def maxima(points, width):
    if any(sum(p["side"] == side for p in points) != 48 for side in ("inside", "exterior")):
        raise ValueError("Expected the complete 48-plus-48 original layout")

    def score_rows(read_score):
        def best(side):
            top, second, *_ = sorted((point for point in points if point["side"] == side), key=read_score, reverse=True)
            return dict(xy_km=top["xy_km"], latlon=top["latlon"], score=read_score(top),
                        runner_up_gap=read_score(top) - read_score(second),
                        north_face_clearance_km=width/2-top["xy_km"][1],
                        winning_norads=sorted({norad for norad in top["owners"].values() if norad is not None}))

        inside, exterior = best("inside"), best("exterior")
        gain = exterior["score"] - inside["score"]
        return dict(inside=inside, exterior=exterior, exterior_gain=gain,
                    sampled_maximum="exterior" if gain > 0 else "inside" if gain < 0 else "tie")

    return dict(pooled=score_rows(lambda p: p["score"]), receivers={str(rx): score_rows(lambda p: p["receiver_scores"][str(rx)])
                for rx in (1, 2)})


def score(directory, summary, full):
    from tools.pipeline_eval.variants.experimental.regional_exterior_veto import evaluate

    files = {mode: {route: directory / f"{mode}-{route}.json" for route in ROUTES} for mode in MODES}
    runs = {mode: {route: read(path) for route, path in compared.items()} for mode, compared in files.items()}
    outcomes = {}
    for mode, compared in runs.items():
        stock, research = (compared[route] for route in ROUTES)
        if stock["identity"] != research["identity"] or stock["binding"] != research["binding"]:
            raise ValueError("Full probe evidence cannot transfer across different graphs, archives or offers")
        points = stock["full_diagnostic"]["points"]
        width = stock["identity"]["offer"]["width_km"]
        by_route = {route: {name: row[name] for name in ("solve", "status", "reason", "arms", "exterior_checks", "actual_handoff")}
                    for route, row in compared.items()}
        outcomes[mode] = dict(identity=stock["identity"], matching_prepared_binding=stock["binding"],
                              diagnostic=maxima(points, width), original_far_veto=evaluate(points, width),
                              fresh_and_prepared_exact=stock["exact_probe_match"], diagnostic_clocks=stock["diagnostic_clocks"],
                              diagnostic_order=stock["diagnostic_order"], routes=by_route)
    verification = {path.name: digest(path.read_bytes()) for pair in files.values() for path in pair.values()}
    write(summary, dict(cases=outcomes, verification=verification))
    with full.open("xb") as stream:
        stream.write(gzip.compress(json.dumps(dict(cases=outcomes, runs=runs, verification=verification),
                                             separators=(",", ":"), allow_nan=False).encode(), mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    trial = actions.add_parser("run")
    trial.add_argument("mode", choices=MODES)
    trial.add_argument("route", choices=ROUTES)
    trial.add_argument("output", type=Path)
    trial.add_argument("--site", type=Path, default=STAGED)
    scoring = actions.add_parser("score")
    for name in ("directory", "summary", "full"):
        scoring.add_argument(name, type=Path)
    args = vars(parser.parse_args())
    (run if args.pop("action") == "run" else score)(**args)
