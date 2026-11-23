"""Verify sealed DS30-0016 publications before independently scoring geography."""

import argparse
import gzip
from io import BytesIO
import json
from pathlib import Path

from empty_bootstrap import bind_native, checked
from raw_0016_best_trial import ARCHIVE, CASE, FLAGS, HERE, INVENTORY, MIXED_NATIVE, PROJECTION_SHA, seal, sha


STOCK_NATIVE = "sha256:4c0e22cbc5646e059abf59e968df2ee9d971795204d552adc9223d2426a7a7e0"
STOCK_OWNERS = Path("/var/tmp/leo-full-short-DS30-0016-pair/stock/joint-research-receipt.json")
STOCK_OWNERS_SHA = "f6c56736b6382ca1c8fc062d49e5e2d9503230a3c6d82ede33cf607e5fe81bed"
ARMS = ("c0", "fitted_c")
CONTROLS = {
    "unified-short-layout": "56b4d57f4534091150621f7dba65cce1edba1d0fbe33238680e10516bf552c5e",
    "named-finish-cli-0016": "1fb16e437b3b5c56ba34c4b60bd1e0cfb5f3c3c10f1a1233dc93340edb4952de",
    "direct-orbits-corrected": "7b63475c1e47d7df045bf3f18af8cd518fa4bf0dd0b50017a7ff1dc34f9f1a9c",
    "cumulative-grid-projection": "3393db5089c1727522b515b1af471f447d4d79c15e027cf0c654fc89a278c4dc",
}


def archived(name):
    data = checked(HERE/"measurements"/f"{name}.json.gz", CONTROLS[name])
    return json.loads(gzip.decompress(data))


def match_science(actual, expected):
    return {key: actual[key] == expected[key] for key in
            ("arms", "owners", "reason", "raw_authority", "scientific_digests")}


def position_sides(store, receipt, media):
    from leo.contracts.position_grid import binding
    from PIL import Image

    run_id = receipt["run_id"]
    detail = store.detail(run_id)
    plot_headers = {}
    for name, record in media["images"].items():
        with Image.open(BytesIO(store.artifact(run_id, name, record["sha256"]))) as plot:
            plot_headers[name] = dict(format=plot.format, mode=plot.mode, dpi=plot.info.get("dpi"))
    expected = binding(detail)
    if expected["position_png_sha256"] != media["images"]["position"]["sha256"]:
        raise ValueError("Position-image binding does not name an independently checked figure")
    grid, path = store.position_grid(run_id), store.position_path(run_id)
    if (grid["binding"] != expected or path["binding"] != expected or not grid["complete"]
            or grid["evaluated_points"] != 179):
        raise ValueError("Invalid published path or matched numerical grid")
    return dict(grid_points=grid["evaluated_points"], binding=expected, figures=plot_headers)


def process_rows(root, admission):
    from full_short_raw import RECIPE_SHA
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from local_future_cli_trial import native_packet
    from short_raw_diagnostic import pairs, require_warm

    results = {}
    for mode in CASE.order:
        target = root/mode
        log = json.loads((root/f"{mode}-clock.json").read_bytes())
        require_warm(log["cache_before"])
        require_warm(log["cache_after"])
        receipt = json.loads(target.with_suffix(".stdout").read_text().splitlines()[-1])
        candidate = mode == "candidate"
        if candidate:
            bootstrap = json.loads((target/"unified-short-bootstrap.json").read_bytes())
            research = json.loads((target/"joint-research-receipt.json").read_bytes())
            projection = bootstrap.get("grid_feature_projection", {})
            scoped_sources = projection.get("source_sha256", {}) | bootstrap["source_sha256"]
            if (receipt != bootstrap["receipt"] or receipt != research["receipt"]
                    or bootstrap["raw_acquisitions"] != 1 or bootstrap["verified_handoffs"] != 1
                    or bootstrap["route"] != "optimized_installed_graph"
                    or bootstrap["frozen_specification"] != pairs.V3_IDENTITY["frozen_specification"]
                    or bootstrap["stock_launcher_sha256"] != pairs.V3_LAUNCHER_SHA
                    or bootstrap["requested_offer_sha256"] != admission["offer_sha256"]
                    or bootstrap["archive_root"] != str(root/"tle")
                    or any(admission["sources"][k] != v for k, v in scoped_sources.items() if k in admission["sources"])
                    or projection.get("library_sha256") != PROJECTION_SHA
                    or not set(FLAGS) <= set(log["command"])):
                raise ValueError("Candidate handoff/provenance differs from the frozen composition")
        else:
            pairs.verify_v3_publication(target, receipt)
            bootstrap, research = None, None

        raw = native_packet(target)
        native = json.loads(raw.read_bytes())
        expected_native, expected_recipe = (MIXED_NATIVE, RECIPE_SHA) if candidate else (
            STOCK_NATIVE, pairs.V3_IDENTITY["detector_sha256"])
        bind_native(native, admission["session"], INVENTORY, expected_recipe, expected=expected_native)
        source = native["source"]
        clock = log["clock"]
        now = pairs.evidence(target, receipt, clock["started_unix_ns"], read_only=True)
        media = artifacts(target, receipt)
        if (clock["exit_code"] or now["raw_authority"] != admission["raw_authority"]
                or source["raw_recording_authority_digest"] != now["raw_authority"]
                or native["clock_anchor"]["before"]["realtime_ns"] != admission["cutoff_utc_ns"]
                or receipt["window_count"] != CASE.windows or receipt["counts"]["processed"] != admission["admitted"]
                or receipt["session_id"] != admission["session"] or receipt["region"] != admission["offer"]
                or receipt["decision"] != "complete" or len(media["images"]) != 8 or set(now["arms"]) != set(ARMS)):
            raise ValueError(f"Invalid or scientifically incomplete {mode} publication")
        if candidate and bootstrap["native_sha256"] != expected_native:
            raise ValueError("Research handoff and published short packet disagree")
        detail = FastStandardAnalysisStore(target)
        sidecars = position_sides(detail, receipt, media)
        probes = source["probes"]
        detector_s = (raw.stat().st_mtime_ns-clock["started_unix_ns"])/1e9
        boundaries = dict(detections_file_s=detector_s, terminal_file_s=now["terminal_file_s"],
                          exit_s=clock["elapsed_s"])
        results[mode] = dict(process=log, native_sha256=expected_native, native_file_sha256=sha(raw.read_bytes()),
                             science=now, figures=media["images"], full_sidecar_sha256={n: media[n] for n in ("path", "grid")},
                             opportunities=canonical_digest([{k: v for k, v in p.items() if k != "candidates"} for p in probes]),
                             probes=len(probes), factors=sum(len(p["candidates"]) for p in probes),
                             time_boundaries=boundaries, sidecars=sidecars,
                             owner_counts={a: detail.detail(receipt["run_id"])["arms"][a]["associated_points"] for a in ARMS},
                             bootstrap=bootstrap)
        if research is not None:
            results[mode]["research"] = {k: research[k] for k in
                                         ("publication_cpu_s", "publication_elapsed_s", "solve", "route_details",
                                          "selected_roles", "selected_rows", "early_regional", "reference")}
    return results


def owner_comparison(runs):
    from leo.contracts.digests import canonical_digest
    from prospective_0316_solver import owner_delta

    archived_stock = json.loads(checked(STOCK_OWNERS, STOCK_OWNERS_SHA))
    stock, candidate = runs["stock"], runs["candidate"]
    controls = {}
    for mode, run, rows in (("stock", stock, archived_stock["selected_rows"]),
                            ("candidate", candidate, candidate["research"]["selected_rows"])):
        expected = run["science"]
        if mode == "stock" and archived_stock["receipt"]["terminal_sha256"] != expected["receipt"]["terminal_sha256"]:
            raise ValueError("Archived named owner rows identify a different scientific terminal")
        for arm in ARMS:
            selected = rows[arm]
            if len(selected) != run["owner_counts"][arm] or len({key for key, _, _ in selected}) != len(selected):
                raise ValueError("Owner row count or uniqueness differs from the current publication")
            if canonical_digest({key: norad for key, norad, _ in selected}) != expected["owners"][arm]:
                raise ValueError("Owner labels do not reproduce the official owner digest")
        controls[mode] = rows
    return {a: owner_delta(controls["stock"][a], controls["candidate"][a]) for a in ARMS}


def score(root, output):
    from aperture_trial import write
    from full_short_physical import REGION_SHA
    from leo.contracts.digests import canonical_digest
    from prospective_0155_solver import orbit_legends
    from triage_bounds import calibration_comparison

    prediction = root/"prediction-seal.json"
    witness = prediction.read_bytes()
    if json.loads(witness) != seal(root):
        raise ValueError("Frozen raw process evidence changed before scoring")
    admission = json.loads((root/"admission.json").read_bytes())
    if (admission["case"] != CASE.id or tuple(admission["order"]) != CASE.order
            or admission["inventory"] != INVENTORY or admission["offer_sha256"] != REGION_SHA
            or admission["archive"]["sha256"] != ARCHIVE):
        raise ValueError("Pre-scoring authority differs from enrollment")
    rows = process_rows(root, admission)
    candidate, stock = (rows[a] for a in CASE.order)
    if (candidate["opportunities"] != stock["opportunities"] or candidate["probes"] != stock["probes"]
            or candidate["process"]["clock"]["started_unix_ns"] >= stock["process"]["clock"]["started_unix_ns"]):
        raise ValueError("Launch order or physical opportunity equality failed")
    older = archived("unified-short-layout")["observations"]["weak"]["rows"]
    checked_reference = archived("named-finish-cli-0016")["runs"]["named-finish"]["science"]
    corrected = archived("direct-orbits-corrected")
    if corrected["source_sha256"]["direct_orbit_figures.py"] != admission["sources"]["direct_orbit_figures.py"]:
        raise ValueError("The archived orbit figure baseline must match the admitted layout revision")
    figure_reference = corrected["figures"]
    grid_reference = archived("cumulative-grid-projection")["weak"]["result"]["runs"]["combined"]["science"]
    compare = dict(
        candidate_same_saved_finish_science=match_science(candidate["science"], checked_reference),
        candidate_same_saved_projected_science=match_science(candidate["science"], grid_reference),
        named_same_archived_science=match_science(stock["science"], older["stock"]["science"]["publication"]),
        candidate_png_exact={k: canonical_digest(v) == canonical_digest(figure_reference[k]) for k, v in candidate["figures"].items()},
        named_png_exact={k: canonical_digest(v) == canonical_digest(older["stock"]["science"]["figures"][k])
                         for k, v in stock["figures"].items()})
    compare["orbit_legend"] = orbit_legends(root/"candidate", dict(
        worker=dict(layout=candidate["bootstrap"]["one_pass_web_png"], receipt=candidate["science"]["receipt"]),
        selected_rows=candidate["research"]["selected_rows"], figures=candidate["figures"]))
    verify_owners = owner_comparison(rows)
    geographic = calibration_comparison({a: rows[a]["science"] for a in rows}, CASE.id)
    clocks = {a: rows[a]["process"]["clock"] for a in CASE.order}
    output_doc = dict(pre_score_sha256=sha(witness), admission=admission, original=rows, verification=compare,
                      conditioning=json.loads((root/"conditioning.json").read_bytes()), owners=verify_owners,
                      named_archived_owner_rows_sha256=STOCK_OWNERS_SHA, geographic=geographic,
                      error_delta_m={a: 1e3*(geographic["runs"]["candidate"]["horizontal_error_km"][a] -
                                             geographic["runs"]["stock"]["horizontal_error_km"][a]) for a in ARMS},
                      prior={a: dict(clock=older[a]["clock"], errors_km=older[a]["errors_km"]) for a in CASE.order},
                      speedup=clocks["stock"]["elapsed_s"]/clocks["candidate"]["elapsed_s"],
                      cpu_speedup=clocks["stock"]["cpu_s"]/clocks["candidate"]["cpu_s"],
                      archived_sha256=CONTROLS)
    write(output, output_doc)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    score(args.root, args.output)
