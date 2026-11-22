"""Replay released geodiverse detector packets through the ALGO08v2 solvers."""

import argparse
import gzip
import hashlib
import json
import math
import os
import subprocess
from pathlib import Path
from time import perf_counter, process_time
from types import SimpleNamespace

RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
SPEC = "sha256:375895c3afda3abd3a916f90bbd63248b5e792f70c78a0e4f136c9bf1a79d423"
PUBLIC_TREE = "9a9e4ebe50b9922f7e1443eadb840e3fec2b0b3d"
WAVEFORM_TREE = "e7d513fc8e745d48f9dce3974ba19443b889c649"
SOUTH = "0ea3bb46005a423fcdf0239e"
INDIA = "02213f589249d02be64805a5d2ea12ef"
MODES = ("matched-tile", "omitted-tile")
WAVEFORM_REQUESTS = {
    "matched-tile": "0000d0a5cbc2b3f00f7b0a49e0b9750c",
    "omitted-tile": "67f59d17b7ae5f7872896ce04a66d1c9",
}
ARMS = ("c0", "fitted_c")
DEADLINE_S = 110


def digest(content):
    return hashlib.sha256(content).hexdigest()


def public(name, tree=PUBLIC_TREE):
    return subprocess.check_output(["git", "show", f"{tree}:{name}"])


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def matched_inputs(row, document, tile, history):
    from tools.pipeline_eval.__main__ import encoded

    request = dict(document=document, tile=tile, history=history)
    return (
        row["offer"] == tile
        and row["document_sha256"] == digest(encoded(document))
        and row["history_sha256"] == digest(encoded(history))
        and row["input_sha256"] == digest(encoded(request))
    )


def stage_history(site, history, objects, cutoff):
    catalogue = site / "tle" / "archive" / "space-track"
    catalogue.mkdir(parents=True, exist_ok=True)
    for entry in history:
        sha = entry["sha256"]
        path = catalogue / f"{entry['collected_utc_ns']}-{sha}.tle"
        if entry["collected_utc_ns"] >= cutoff:
            raise ValueError("Original TLE snapshot is not strictly causal")
        if not path.exists():
            content = objects[sha].read_bytes()
            if digest(content) != sha:
                raise ValueError("Original TLE object changed")
            path.write_bytes(content)


def stage_waveform(root):
    from leo.contracts.algo08_region import Algo08Region
    from tools.pipeline_eval.qualification.cold_scenes import TLE_ARCHIVE

    input_lock = json.loads(public("input-lock.json", WAVEFORM_TREE))["files"]
    detector_lock = json.loads(public("detector-lock.json", WAVEFORM_TREE))["files"]
    inputs = {}
    for name, lock in (("native.json.gz", detector_lock), ("requests.json", detector_lock),
                       ("causal-authority.json", input_lock), ("track-config.json", input_lock)):
        inputs[name] = public(name, WAVEFORM_TREE)
        if digest(inputs[name]) != lock[name]:
            raise ValueError(f"Released waveform {name} differs from its lock")
    if inputs["track-config.json"] != (RELEASE / "assets/tracks.json").read_bytes():
        raise ValueError("Installed TrackConfig differs from the released waveform request")
    content = gzip.decompress(inputs["native.json.gz"])
    native = json.loads(content)
    cutoff = native["clock_anchor"]["before"]["realtime_ns"]
    history = list(json.loads(inputs["causal-authority.json"]).values())
    latest = max(history, key=lambda row: row["collected_utc_ns"])["sha256"]
    objects = {r["sha256"]: TLE_ARCHIVE / "raw/space-track" / (r["sha256"] + ".tle")
               for r in history}
    site = root / INDIA
    stage_history(site, history, objects, cutoff)
    (site / "native.json").write_bytes(content)
    requests = {row["id"]: row for row in json.loads(inputs["requests.json"])}
    plan = []
    for mode, ident in WAVEFORM_REQUESTS.items():
        row = requests[ident]
        if (row["session"] != INDIA or row["native_sha256"] != digest(content)
                or row["config_sha256"] != digest(inputs["track-config.json"])
                or row["catalog_sha256"] != latest):
            raise ValueError("Released waveform request inputs differ")
        offer = Algo08Region(tuple(row["tile"]), 25, tuple(row["screen_center"])).document()
        write(site / (mode + ".json"), offer)
        plan.append(dict(
            dataset="waveform-site", case=INDIA, mode=mode, request_id=ident, offer=offer,
            clock_cutoff_utc_ns=cutoff, snapshots=len(history), distinct_tle_objects=len(objects),
            probes=len(native["source"]["probes"]), native_schema_version=native["schema_version"],
            document_sha256=digest(content), history_sha256=digest(inputs["causal-authority.json"]),
            requests_sha256=digest(inputs["requests.json"]),
        ))
    return plan


def stage_portable(root):
    from leo.contracts.algo08_region import Algo08Region
    from tools.pipeline_eval.__main__ import encoded
    from tools.pipeline_eval.qualification import cold_scenes, portable_v5_transfer

    source = json.loads(public("synthetic-source-lock.json"))
    for label, module in (("generator", cold_scenes), ("adapter", portable_v5_transfer)):
        if digest(Path(module.__file__).read_bytes()) != source[label]:
            raise ValueError(f"Published {label} source differs")
    labels = json.loads(public("synthetic-labels.json"))
    seed = bytes.fromhex(labels["seed_hex"])
    jobs, answers, history_manifest = portable_v5_transfer.new_scenes(seed)
    if encoded(answers) != encoded(labels["captures"]):
        raise ValueError("Published geographic references differ after reconstruction")
    if encoded(history_manifest) != encoded(json.loads(public("authentic-history.json"))):
        raise ValueError("Published TLE history differs after reconstruction")
    prediction_lock = json.loads(public("prediction-lock.json"))
    predictions = {}
    for mode in MODES:
        payload = public(mode + ".jsonl.gz")
        if digest(payload) != prediction_lock[mode]:
            raise ValueError("Published prediction SHA-256 differs")
        rows = map(json.loads, gzip.decompress(payload).splitlines())
        predictions[mode] = {row["id"]: row for row in rows}

    plan = []
    for ident, mode, document, tile, history, objects in jobs:
        if ident != SOUTH:
            continue
        row = predictions[mode][ident]
        if not matched_inputs(row, document, tile, history):
            raise ValueError(f"Reconstructed {ident}/{mode} differs from its released input")
        cutoff = document["clock_anchor"]["before"]["realtime_ns"]
        site = root / ident
        stage_history(site, history, objects, cutoff)
        # The portable display ID is outside the ALGO08 region contract.
        offer = Algo08Region.parse({k: tile[k] for k in ("center", "width_km")}).document()
        (site / "native.json").write_bytes(encoded(document))
        write(site / (mode + ".json"), offer)
        plan.append(dict(
            dataset="portable-v5", case=ident, mode=mode, offer=offer, clock_cutoff_utc_ns=cutoff,
            snapshots=len(history), distinct_tle_objects=len(objects),
            probes=len(document["source"]["probes"]),
            native_schema_version=document["schema_version"],
            **{k: row[k] for k in ("input_sha256", "document_sha256", "history_sha256")},
        ))
    return plan


def worker(native_path, archive, region, output, specification=None):
    from leo.application.localization_v3_engine import _json_value
    from leo.contracts.algo08_region import Algo08Region
    from leo.operations.tle_archive import TleArchiveReader
    from tools import algo08_position

    native = json.loads(native_path.read_bytes())

    def solve(assets, offer):
        start_cpu, start_wall = process_time(), perf_counter()
        decision, packet, policy = algo08_position.solve(
            native, TleArchiveReader(archive), assets, offer,
        )
        result = dict(
            status=decision["status"], reason=decision.get("reason"),
            arms=decision["arms"], orbit_policy=policy,
            solver_cpu_s=process_time() - start_cpu, solver_wall_s=perf_counter() - start_wall,
        )
        for key in ("observations", "tracks", "regional_bound_guard"):
            if key in decision.get("metrics", {}):
                result[key] = decision["metrics"][key]
        if packet is not None:
            result["owners"] = {arm: packet["arms"][arm]["owner_sha256"] for arm in ARMS}
            result["associated"] = {arm: packet["arms"][arm]["associated_points"] for arm in ARMS}
        return result

    if specification is None:
        result = solve(RELEASE / "assets", Algo08Region.parse(json.loads(region.read_bytes())))
    else:
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        from tools import algo08_scan
        from tools.pipeline_eval.qualification.experimental_publication import run

        spec = json.loads(specification.read_bytes())
        publication_only = {"png_filter", "png_deflate", "paired_sha256"}
        spec = {k: v for k, v in spec.items() if k not in publication_only}
        spec.update(schedule="all", rendering="individual", ingress="stock", startup="stock")
        with TemporaryDirectory() as temp:
            output_root = Path(temp)
            recording = output_root / "no-recording"

            def from_saved(requested, _output, assets, causal_archive, offer):
                if requested != recording or causal_archive != archive:
                    raise ValueError("Unexpected inputs to post-detector replay")
                return solve(assets, offer)

            args = SimpleNamespace(
                recording=recording, bulk_root=output_root, archive=archive, region=region,
            )
            with patch.object(algo08_scan, "analyze", from_saved):
                result = run(args, spec)
    write(output, json.loads(json.dumps(result, default=_json_value, allow_nan=False)))


def replay(root, frozen):
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.__main__ import THREAD_ENV
    from tools.pipeline_eval.qualification.paired_publication import verify_sources

    spec_path = frozen / "spec.json"
    spec = json.loads(spec_path.read_bytes())
    if canonical_digest(spec) != SPEC:
        raise ValueError("Expected the frozen 375895c3 covariance build")
    verify_sources(frozen / "reports/ALGO08/single-core-2x/run-candidate", spec["sources"])
    if Path("/opt/leo-algo08/current").resolve() != RELEASE:
        raise ValueError("Installed ALGO08v2 differs from the released comparison build")
    root.mkdir(parents=True, exist_ok=False)
    plan = stage_waveform(root) + stage_portable(root)
    write(root / "plan.json", plan)
    env = os.environ.copy()
    for key in ("ALGO08_EVALUATION_LATITUDE", "ALGO08_EVALUATION_LONGITUDE", "ALGO08_REGION_FILE",
                "ALGO08_EXPERIMENT_CONFIG"):
        env.pop(key, None)
    env.update(THREAD_ENV)
    launcher = [str(RELEASE / "venv/bin/python"), "-BPs", str(Path(__file__).resolve()), "worker"]
    release_paths = [RELEASE / "src", RELEASE]
    for index, row in enumerate(plan):
        site = root / row["case"]
        mode = row["mode"]
        builds = ("installed", "covariance") if index % 2 == 0 else ("covariance", "installed")
        for build in builds:
            candidate = build == "covariance"
            paths = [frozen, *release_paths] if candidate else release_paths
            env["PYTHONPATH"] = os.pathsep.join(map(str, paths))
            output = site / f"{mode}-{build}.json"
            args = [site / "native.json", site / "tle", site / (mode + ".json"), output]
            if candidate:
                args.append(spec_path)
            start = perf_counter()
            try:
                proc = subprocess.run([*launcher, *map(str, args)], env=env, capture_output=True,
                                      timeout=DEADLINE_S, check=False)
                if proc.returncode != 0:
                    write(output, dict(status="failed", returncode=proc.returncode,
                                       error=proc.stderr.decode(errors="replace")[-3500:]))
            except subprocess.TimeoutExpired:
                write(output, dict(status="timed_out", deadline_s=DEADLINE_S))
            status = json.loads(output.read_bytes())["status"]
            print(row["case"], mode, build, status, round(perf_counter() - start, 2), flush=True)


def scoring_references():
    labels = public("synthetic-labels.json")
    captures = json.loads(labels)["captures"]
    waveform = public("truth-after-lock.json.gz", WAVEFORM_TREE)
    score_lock = json.loads(public("score-lock.json", WAVEFORM_TREE))["files"]
    if digest(waveform) != score_lock["truth-after-lock.json.gz"]:
        raise ValueError("Released waveform scoring reference differs")
    scene = json.loads(gzip.decompress(waveform))["scene"]
    captures[INDIA] = {"position": scene["coordinate"]}
    return captures, dict(portable_scoring_sha256=digest(labels),
                          waveform_scoring_sha256=digest(waveform))


def score(root, output):
    from tools.pipeline_eval.scoring import distance_km

    plan = json.loads((root / "plan.json").read_bytes())
    predictions = {}
    for row in plan:
        ident, mode = row["case"], row["mode"]
        for build in ("installed", "covariance"):
            path = root / ident / f"{mode}-{build}.json"
            content = path.read_bytes()
            predictions[ident, mode, build] = dict(
                json.loads(content), result_sha256=digest(content),
            )
    captures, reference_digests = scoring_references()
    for row in plan:
        row["builds"] = {}
        ident, mode = row["case"], row["mode"]
        truth = captures[ident]["position"]
        center_lat, center_lon = row["offer"]["center"]
        east = (truth[1] - center_lon) * 111.32 * math.cos(math.radians(center_lat))
        north = (truth[0] - center_lat) * 111.0
        row.update(
            reference_latlon=truth, reference_east_north_km=[east, north],
            reference_clearance_km=row["offer"]["width_km"] / 2 - max(abs(east), abs(north)),
            offer_center_error_km=distance_km([center_lat, center_lon], truth),
        )
        for build in ("installed", "covariance"):
            result = predictions[ident, mode, build]
            for arm in result.get("arms", {}).values():
                arm["horizontal_error_km"] = distance_km(arm["latlon"], truth)
            row["builds"][build] = result
    write(output, dict(
        spec=SPEC, release=RELEASE.name, portable_tree=PUBLIC_TREE, waveform_tree=WAVEFORM_TREE,
        solve_deadline_s=DEADLINE_S, rows=plan, **reference_digests,
    ))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    actions = {
        "replay": (replay, ("root", "frozen")),
        "worker": (worker, ("native_path", "archive", "region", "output", "specification")),
        "score": (score, ("root", "output")),
    }
    for action, (_, fields) in actions.items():
        command = commands.add_parser(action)
        for field in fields:
            options = {"nargs": "?"} if field == "specification" else {}
            command.add_argument(field, type=Path, **options)
    args = parser.parse_args()
    operation, names = actions[args.action]
    operation(*(getattr(args, name) for name in names))
