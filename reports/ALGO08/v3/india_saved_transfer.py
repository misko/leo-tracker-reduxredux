"""Replay the public waveform-derived India evidence without a raw publication claim."""

import argparse
from contextlib import nullcontext
import gzip
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch

from aperture_trial import ARMS, BENCH, RELEASE, configuration, machine, read, write
from joint_publication import full_catalogue_route
from mixture_trial import elapsed, summarize


HERE = Path(__file__).resolve().parent
HISTORY = HERE.parent / "single-core-2x"
ARCHIVED = HISTORY / "measurements/covariance-geographic-transfer.json"
ARCHIVED_SHA = "05d450897ceb839f27a307b2c440ecfefba5e3474e06940b49504c69ff741d40"
CASE = "02213f589249d02be64805a5d2ea12ef"
TREE = "e7d513fc8e745d48f9dce3974ba19443b889c649"
STAGED = BENCH / "portable-v5-geodiverse" / CASE
NATIVE_SHA = "5bfc82a689df80b482a2dae985642403fb4615c1fac34550e490884fcc96d569"
MODES = {"matched-tile": "0000d0a5cbc2b3f00f7b0a49e0b9750c",
         "omitted-tile": "67f59d17b7ae5f7872896ce04a66d1c9"}
ROUTES = ("stock", "full-catalogue")


def digest(data):
    return sha256(data).hexdigest()


def check_contract(native):
    source = native["source"]
    if (native["schema_version"] != 1 or source["session_id"] != CASE or source["qualified"] is not True
            or len(source["probes"]) != 2400 or len(native["delivery_clocks"]) != 1200
            or not native["clock_anchor"]):
        raise ValueError("Unexpected public waveform packet contract")
    raw_authority = ("input_manifest_sha256", "analysis_manifest_sha256", "raw_recording_authority_digest")
    return dict(schema_version=1, source_detector_sha256=native["provenance"]["detector_sha256"],
                missing_raw_publication_fields=[key for key in raw_authority if key not in source],
                probe_rows=len(source["probes"]), delivery_clocks=len(native["delivery_clocks"]))


def bind(site, mode):
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest

    transfer = run_path(str(HISTORY / "covariance_transfer_trial.py"))
    verify_archive = run_path(str(HISTORY / "complete_family_cavity_trial.py"))["verify_archive"]
    if (transfer["WAVEFORM_TREE"] != TREE or transfer["WAVEFORM_REQUESTS"] != MODES
            or digest(ARCHIVED.read_bytes()) != ARCHIVED_SHA):
        raise ValueError("Public development comparison changed")

    def public(name):
        return transfer["public"](name, TREE)

    detector_lock = json.loads(public("detector-lock.json"))["files"]
    input_lock_raw = public("input-lock.json")
    if digest(input_lock_raw) != detector_lock["input-lock.json"]:
        raise ValueError("Released input lock differs from the detector lock")
    input_lock = json.loads(input_lock_raw)["files"]
    provenance = {}
    for name, lock in (("native.json.gz", detector_lock), ("requests.json", detector_lock),
                       ("causal-authority.json", input_lock), ("track-config.json", input_lock)):
        blob = public(name)
        if digest(blob) != lock[name]:
            raise ValueError(f"Public India {name} changed")
        provenance[name] = blob

    native_bytes = (site / "native.json").read_bytes()
    if digest(native_bytes) != NATIVE_SHA or native_bytes != gzip.decompress(provenance["native.json.gz"]):
        raise ValueError("Staged waveform detections differ from the released bytes")
    config = provenance["track-config.json"]
    if config != (RELEASE / "assets/tracks.json").read_bytes():
        raise ValueError("Released and v3 TrackConfig differ")
    native = json.loads(native_bytes)
    authority = list(json.loads(provenance["causal-authority.json"]).values())
    cutoff = native["clock_anchor"]["before"]["realtime_ns"]
    if (len(authority) != 35 or len({row["sha256"] for row in authority}) != 23
            or any(row["collected_utc_ns"] >= cutoff for row in authority)):
        raise ValueError("The original waveform archive must be strictly causal")
    latest = max(authority, key=lambda entry: entry["collected_utc_ns"])["sha256"]
    request, = [r for r in json.loads(provenance["requests.json"]) if r["id"] == MODES[mode]]
    offer = Algo08Region(tuple(request["tile"]), 25, tuple(request["screen_center"])).document()
    region_file = site / (mode + ".json")
    if (request["session"] != CASE or request["native_sha256"] != NATIVE_SHA
            or request["catalog_sha256"] != latest or request["config_sha256"] != digest(config)
            or read(region_file) != offer):
        raise ValueError("Staged offer differs from the original waveform request")
    identity = dict(case=CASE, dataset="waveform-site", mode=mode, offer=offer, request_id=request["id"],
                    document_sha256=NATIVE_SHA, native_canonical_sha256=canonical_digest(native),
                    history_sha256=digest(provenance["causal-authority.json"]), locked_config_sha256=digest(config),
                    requests_sha256=digest(provenance["requests.json"]), clock_cutoff_utc_ns=cutoff,
                    snapshots=35, distinct_tle_objects=23, contract=check_contract(native), previous_public_sha256=ARCHIVED_SHA)
    verify = lambda: verify_archive(transfer, identity, site)
    verify()
    return native, site / "tle", region_file, identity, verify


def decode_figures(output, labels):
    from PIL import Image

    figures = {}
    for name in labels:
        path = output / f"{name}.png"
        with Image.open(path) as img:
            if img.format != "PNG":
                raise ValueError("Original renderer must emit PNG bytes")
            img.load()
            figures[name] = dict(size=img.size, sha256=digest(path.read_bytes()),
                                 rgba_sha256=digest(img.convert("RGBA").tobytes()))
    return figures


def run(mode, route, output, *, site):
    host = machine()
    if (host["cpu"] != [2] or host["nice"] < 15 or "prio 7" not in host["ionice"]
            or any(n != "1" for n in host["threads"].values())):
        raise ValueError("Expected one shared low-priority Gauss slot")
    release, spec = configuration()
    from leo.contracts.fast_standard_analysis import PLOTS
    from leo.operations.tle_archive import TleArchiveReader
    from tools import algo08_position, algo08_scan
    from tools.pipeline_eval.variants import v5_core
    from tools.pipeline_eval.variants.experimental import regional_bound_guard

    native, catalogue, region, identity, verify = bind(site, mode)
    output.mkdir(exist_ok=False)
    attempts, checks = [], []

    def analyze(recording, _root, assets, archive, offer):
        if recording.exists() or archive != catalogue or offer.document() != identity["offer"]:
            raise ValueError("The saved comparison must use only the matched archive and offer")
        reader = TleArchiveReader(archive)
        installed = v5_core.infer
        scope = (patch.object(v5_core, "infer", full_catalogue_route(installed, reader, attempts))
                 if route == "full-catalogue" else nullcontext())
        inspect = regional_bound_guard.inspect_boundary

        def observe_exterior(*args, **kwargs):
            start = (process_time(), perf_counter())
            decision = inspect(*args, **kwargs)
            checks.append(dict(result=decision, **elapsed(*start)))
            return decision

        begin = (process_time(), perf_counter())
        with scope, patch.object(regional_bound_guard, "inspect_boundary", observe_exterior):
            decision, packet, policy = algo08_position.solve(native, reader, assets, offer)
        solve = elapsed(*begin)
        if (decision["status"] == "ok") != (packet is not None) or decision["status"] not in ("ok", "withheld"):
            raise ValueError("Expected an actual scientific decision")
        result, _ = summarize(decision, packet, policy)
        if packet is None:
            return dict(result, solve=solve, render_write=None, measured_post_detector=solve, images={}, selected_rows={})
        if not packet["position_grid"]["complete"] or set(packet["arms"]) != set(ARMS):
            raise ValueError("A published fix needs matched arms and the complete numerical grid")
        plotting_start = process_time(), perf_counter()
        plots = algo08_scan.render(packet, title="India waveform-derived development replay", evaluation_reference=None)
        if set(plots) != set(PLOTS):
            raise ValueError("The original standard renderer must emit all eight figures")
        for label in PLOTS:
            with (output / (label + ".png")).open("xb") as stream:
                stream.write(plots[label])
        for name in ("path", "grid"):
            write(output / f"position-{name}.json", packet[f"position_{name}"])
        render = elapsed(*plotting_start)
        total = elapsed(*begin)
        rows = {arm: [[r["observation_id"], r["norad"], r["role"]] for r in packet["rows"][arm]] for arm in ARMS}
        return dict(result, solve=solve, render_write=render, measured_post_detector=total,
                    images=decode_figures(output, PLOTS), selected_rows=rows)

    with TemporaryDirectory() as scratch, patch.object(algo08_scan, "analyze", analyze):
        root = Path(scratch)
        args = SimpleNamespace(recording=root / "unused-recording", bulk_root=root, archive=catalogue, region=region)
        result = release.run(args, spec)
    verify()
    if len(attempts) != int(route == "full-catalogue"):
        raise ValueError("Expected a single route attempt")
    result.update(identity=identity, route=route, host=host, exterior_checks=checks, route_attempts=attempts,
                  release_detector_sha256=spec["detector_sha256"], output=str(output.resolve()),
                  sources={name: digest((HERE / name).read_bytes()) for name in
                           ("india_saved_transfer.py", "india-saved-transfer-protocol.md", "joint_publication.py")})
    write(output / "saved-india-receipt.json", result)


def score(directory, summary, full):
    from mixture_score import section
    from signed_0374_transfer import owner_changes
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km
    from tools.pipeline_eval.scoring import distance_km

    paths = {mode: {route: directory / f"{mode}-{route}" / "saved-india-receipt.json" for route in ROUTES} for mode in MODES}
    runs = {mode: {route: read(path) for route, path in comparison.items()} for mode, comparison in paths.items()}
    for mode, comparison in runs.items():
        stock = comparison["stock"]["identity"]
        if stock != comparison["full-catalogue"]["identity"] or stock["request_id"] != MODES[mode]:
            raise ValueError("India routes must use the identical original offer, detections and catalogue")
        for route, row in comparison.items():
            if row["route"] != route or row["identity"]["document_sha256"] != NATIVE_SHA:
                raise ValueError("India route or input packet changed")
            folder = paths[mode][route].parent
            for name, image in row["images"].items():
                if digest((folder / f"{name}.png").read_bytes()) != image["sha256"]:
                    raise ValueError("Emitted India renderer bytes changed")
    transfer = run_path(str(HISTORY / "covariance_transfer_trial.py"))
    references = transfer["public"]("truth-after-lock.json.gz", TREE)
    lock = json.loads(transfer["public"]("score-lock.json", TREE))["files"]
    if digest(references) != lock["truth-after-lock.json.gz"] or digest(ARCHIVED.read_bytes()) != ARCHIVED_SHA:
        raise ValueError("Original scored India control changed")
    truth = json.loads(gzip.decompress(references))["scene"]["coordinate"]
    original = {row["mode"]: row for row in read(ARCHIVED)["rows"] if row["case"] == CASE}
    results = {}
    for mode, comparison in runs.items():
        stock, candidate = (comparison[key] for key in ROUTES)
        offer = stock["identity"]["offer"]
        clearance = face_clearance_km(offer, truth)
        historical = original[mode]["builds"]
        payload = {}
        for route, row in comparison.items():
            payload[route] = dict(
                status=row["status"], reason=row["reason"], returning=row["status"] == "ok",
                geometric_decision_correct=(row["status"] == "ok") == (clearance >= 0),
                solve=row["solve"], render_write=row["render_write"], post_detector=row["measured_post_detector"],
                versus_current_stock=section(row["arms"], truth, stock["arms"]),
                versus_original_covariance=section(row["arms"], truth, historical["covariance"]["arms"]),
                versus_original_v2=section(row["arms"], truth, historical["installed"]["arms"]),
                exterior_checks=row["exterior_checks"], figures=len(row["images"]), associated=row.get("associated"),
                grid_points=row.get("grid_points"), route_attempts=[{k: a[k] for k in ("decision", "reason") if k in a}
                                                                  for a in row["route_attempts"]],
            )
        images = {name: {key: stock["images"][name][key] == candidate["images"][name][key]
                         for key in ("sha256", "rgba_sha256")}
                  for name in sorted(stock["images"].keys() & candidate["images"].keys())}
        payload.update(center_error_km=distance_km(offer["center"], truth), truth_face_clearance_km=clearance,
                       historical_comparisons={key: {k: val[k] for k in ("status", "reason", "arms")}
                                               for key, val in historical.items()},
                       exact_arm_values=stock["arms"] == candidate["arms"],
                       exact_numerics={key: stock.get("science", {}).get(key) == candidate.get("science", {}).get(key)
                                       for key in ("path", "grid") if key in stock["science"] or key in candidate["science"]},
                       images_agree=images, owner_changes=owner_changes(stock, candidate),
                       solve_ratio={k: candidate["solve"][k] / stock["solve"][k] for k in ("cpu_s", "elapsed_s")},
                       post_detector_ratio={k: candidate["measured_post_detector"][k] / stock["measured_post_detector"][k]
                                            for k in ("cpu_s", "elapsed_s")})
        results[mode] = payload
    verified = dict(references_sha256=digest(references), prior_sha256=ARCHIVED_SHA,
                    receipts={str(path.relative_to(directory)): digest(path.read_bytes())
                              for group in paths.values() for path in group.values()})
    write(summary, dict(cases=results, verification=verified))
    with full.open("xb") as stream:
        stream.write(gzip.compress(json.dumps(dict(runs=runs, scores=results, verification=verified),
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
