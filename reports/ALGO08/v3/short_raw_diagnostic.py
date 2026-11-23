"""Time two frozen short physical raw pairs through publication and process exit."""

import argparse
import json
import os
from hashlib import sha256
from pathlib import Path
from statistics import median
import subprocess
from time import perf_counter, time_ns

from aperture_trial import RELEASE, read, write
from dense_full_short_raw import checked, usage
from dense_geographic_trial import host
from full_short_physical import CACHE_LIB, CACHE_SHA, environment
from full_short_raw import RECIPE_SHA, SHORT_SHA
from full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA, checked_recipe
from joint_publication import artifacts
from leo.contracts.algo08_region import Algo08Region
from leo.contracts.digests import canonical_digest
from leo.storage.fast_scan import FastScanStore
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
from tools.pipeline_eval.qualification import cache_residency, paired_publication as pairs
from tools.pipeline_eval.scoring import distance_km
from triage_bounds import REFERENCE, REFERENCE_SHA256, REGION_SHA256, warm_recording


HERE = Path(__file__).resolve().parent
ORIGINALS = Path("/srv/bulk/leo-dev/algo08v2-ds30-100-6cdbac/publications")
CASES = (
    ("DS30-0227", "6c36381a1af955638a46a008d39bd309bab8cd1f46ae9d62753e84bd998edb10", "withheld", 18,
     ("stock", "candidate")),
    ("DS30-0057", "e4a143d2c47b7e0bb41061d602780b11d37660fd65ce4b5863996d9d251f155b", "complete", 2717,
     ("candidate", "stock")),
)
LIBRARIES = dict(short=SHORT_SHA, geographic=GEOGRAPHIC_SHA, regional=TRACK_SCORES_SHA)
RUN_SOURCE = "a1052286202c24fb659f6ca8175ef678e66ac96443b0d32d0c907da3514c1c6d"


def assignment(case, digest, decision, visits):
    path = checked(ORIGINALS / case / "pair.json", digest)
    pair = read(path)
    archived = pair["runs"]["candidate"]
    receipt = archived["receipt"]
    region = checked(Path(pair["region"]), REGION_SHA256)
    archive = Path(pair["archive"]["root"])
    if (pair["candidate_specification_digest"] != pairs.V3_IDENTITY["frozen_specification"]
            or pair["candidate_specification"]["detector_sha256"] != pairs.V3_IDENTITY["detector_sha256"]
            or receipt["decision"] != decision or receipt["window_count"] != visits
            or receipt["region"] != Algo08Region.parse(read(region)).document()
            or pairs.archive_identity(archive) != pair["archive"]):
        raise ValueError(f"Changed frozen workload assignment for {case}")
    return pair, archived


def require_warm(cache):
    if (cache["unavailable"] or not cache["members"] or cache["members"] != cache["observed_members"]
            or not cache["observed_file_pages"] or cache["cached_pages"] != cache["observed_file_pages"]):
        raise ValueError(f"Raw recording was not fully resident at launch: {cache}")


def measure(command, env, destination):
    print(f"Measuring {destination.parent.name} {destination.name}", flush=True)
    started_ns = time_ns()
    before, start = usage(), perf_counter()
    try:
        execution = subprocess.run(command, env=env, capture_output=True, text=True, timeout=150)
        status, stdout, stderr = execution.returncode, execution.stdout, execution.stderr
    except subprocess.TimeoutExpired as error:
        status = 124
        stdout, stderr = (blob.decode(errors="replace") if isinstance(blob, bytes) else blob or ""
                          for blob in (error.stdout, error.stderr))
        stderr += "\nProcess timed out after 150 s"
    elapsed, after = perf_counter() - start, usage()
    destination.with_suffix(".stdout").write_text(stdout)
    destination.with_suffix(".stderr").write_text(stderr)
    return dict(started_unix_ns=started_ns, elapsed_s=elapsed, exit_code=status, stderr_tail=stderr[-2500:],
                **{name: value - before[name] for name, value in after.items()})


def science(work, arm, run, archived, inventory_digest):
    root = work / arm
    trial = read(root / "joint-research-receipt.json") if arm == "candidate" else None
    receipt = trial["receipt"] if trial is not None else json.loads(root.with_suffix(".stdout").read_text().splitlines()[-1])
    evidence = pairs.evidence(root, receipt, run["started_unix_ns"], read_only=True)
    for name in ("region", "counts", "session_id", "window_count"):
        if receipt[name] != archived["receipt"][name]:
            raise ValueError(f"Published {name} changes the assigned raw support or region")
    workdir = FastScanStore(root).automatic_workspace(receipt["run_id"], create=False)
    terminal = read(workdir / "terminal.json")
    native_path, = workdir.parent.glob("*/detections.json")
    native = read(native_path)
    source = native["source"]
    pin = RECIPE_SHA if trial is not None else pairs.V3_IDENTITY["detector_sha256"]
    raw = evidence["raw_authority"]
    probes = source["probes"]
    analysis = canonical_digest(["cancellation", raw, pin, probes])
    if (raw != archived["raw_authority"] or source["raw_recording_authority_digest"] != raw
            or source["session_id"] != receipt["session_id"] or source["input_manifest_sha256"] != inventory_digest
            or source["analysis_manifest_sha256"] != analysis or canonical_digest(native) != terminal["native_sha256"]
            or native["provenance"]["detector_sha256"] != "sha256:" + pin
            or len(probes) != 2 * receipt["counts"]["processed"]):
        raise ValueError("Native detector document differs from raw authority, recipe or terminal")
    images = artifacts(root, receipt)
    started = run["started_unix_ns"]
    storage = FastStandardAnalysisStore(root)
    detail = storage.detail(receipt["run_id"])
    if receipt["decision"] == "complete":
        grid = storage.position_grid(receipt["run_id"])
        if not grid["complete"]:
            raise ValueError("Completed position used an unfinished standard grid")
        grid_points = grid["evaluated_points"]
    else:
        grid_points = 0
        if any(row["latlon"] is not None for row in terminal["arms"].values()) or images["images"]:
            raise ValueError("Withheld decision published a position or figure")
    result = dict(decision=receipt["decision"], reason=terminal["reason"], orbit_policy=terminal["orbit_policy"],
                  native_sha256=terminal["native_sha256"], terminal_sha256=receipt["terminal_sha256"],
                  run_id=receipt["run_id"], detector_pin=pin, raw_authority=raw, input_manifest=inventory_digest,
                  counts=receipt["counts"], probes=len(probes), selected_lanes=sum(bool(row["candidates"]) for row in probes),
                  selections=sum(len(row["candidates"]) for row in probes), arms=terminal["arms"], owners=evidence["owners"],
                  associated={arm: value["associated_points"] for arm, value in detail["arms"].items()},
                  scientific_digests=evidence["scientific_digests"], pngs=images["images"], grid_points=grid_points,
                  detection_file_s=(native_path.stat().st_mtime_ns - started) / 1e9,
                  terminal_file_s=evidence["terminal_file_s"])
    if trial is None:
        pairs.verify_v3_publication(root, receipt)
        if any(evidence[name] != archived[name] for name in ("arms", "owners", "reason", "scientific_digests", "artifacts")):
            raise ValueError("Named ALGO08v3 did not reproduce its archived publication")
    else:
        recipe = read(root / "full-short-recipe.json")
        actual_config = dict(graph="installed", reuse_cold_track_rows=True, reuse_grid_phase_states=True,
                             geographic_sha256=GEOGRAPHIC_SHA, regional_track_sha256=TRACK_SCORES_SHA)
        if (any(recipe[key] != value for key, value in actual_config.items()) or recipe["recipe"] != checked_recipe()
                or recipe["saved_digest"] is not None or trial["saved_digest"] is not None
                or not trial["optimized_full_catalogue"] or canonical_digest(images) != canonical_digest(trial["evidence"])):
            raise ValueError("Published research configuration or artifacts differ from the frozen candidate")
        for source_path, digest in trial["source_sha256"].items():
            if not source_path.startswith("installed/"):
                checked(HERE / source_path, digest)
        result.update(config=actual_config, source_sha256=trial["source_sha256"], route=trial["route"],
                      solve=trial["solve"], early_regional=trial["early_regional"], receiver=recipe["receiver_audit"])
    return result


def calibration(runs, truth):
    stocks = runs["stock"].get("arms", {})
    scored = {}
    for arm, run in runs.items():
        rows = {}
        for name, solution in run.get("arms", {}).items():
            error = distance_km(truth, solution["latlon"])
            stock = stocks.get(name, {})
            stock_error = distance_km(truth, stock.get("latlon"))
            rms, stock_rms = solution.get("rf_rms_hz"), stock.get("rf_rms_hz")
            rows[name] = dict(horizontal_error_km=error, rf_rms_hz=rms,
                              delta_stock_error_km=None if error is None or stock_error is None else error - stock_error,
                              delta_stock_rms_hz=None if rms is None or stock_rms is None else rms - stock_rms)
        scored[arm] = rows
    return scored


def cumulative(rows):
    baseline = [r["runs"]["stock"]["elapsed_s"] for r in rows]
    candidate = [r["runs"]["candidate"]["elapsed_s"] for r in rows]
    ratios = [b / a for a, b in zip(baseline, candidate, strict=True)]
    return dict(cases=[r["case"] for r in rows], installed_elapsed_s=sum(baseline), candidate_elapsed_s=sum(candidate),
                paired_median_elapsed_ratio=median(ratios), summed_elapsed_ratio=sum(candidate) / sum(baseline),
                stock_complete=sum(r["runs"]["stock"].get("decision") == "complete" for r in rows),
                candidate_complete=sum(r["runs"]["candidate"].get("decision") == "complete" for r in rows),
                candidate_misses=sum(r["missed_fix"] for r in rows), candidate_false_fixes=sum(r["false_fix"] for r in rows),
                candidate_failures=sum("error" in r["runs"]["candidate"] for r in rows))


def run(output, short, geographic, regional, resume=False):
    settings = host()
    build = pairs.verified_v3(pairs.NAMED_V3)
    checked(HERE / "full_short_run.py", RUN_SOURCE)
    checked_recipe()
    libraries = {name: dict(path=str(checked(path, LIBRARIES[name])), sha256=LIBRARIES[name])
                 for name, path in dict(short=short, geographic=geographic, regional=regional).items()}
    query = cache_residency.load_query(checked(CACHE_LIB, CACHE_SHA))
    verified = [assignment(*row[:4]) for row in CASES]
    if not resume:
        output.mkdir()
    store, env = FastScanStore(output), environment(output)
    python = str(RELEASE / "venv/bin/python")
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    results = []
    for (case, digest, decision, visits, order), (pair, archived) in zip(CASES, verified, strict=True):
        work = output / case
        if resume and (work / "result.json").is_file():
            previous = read(work / "result.json")
            if previous["original_pair_sha256"] != digest or tuple(previous["order"]) != order:
                raise ValueError("Resume changes the sealed first case's assignment")
            for item in previous["runs"].values():
                require_warm(item["cache"])
            previous["cache_mode"] = "fully_warm"
            results.append(previous)
            continue
        if resume and work.exists():
            if sorted(p.name for p in work.iterdir()) != ["stock"] or any((work / "stock").iterdir()):
                raise ValueError("Resume requires an unmeasured case with empty outputs")
        else:
            work.mkdir()
            (work / "stock").mkdir()
        recording = Path(pair["recording"])
        session, input_digest, inventory = store.inventory(recording, verify_windows=False)
        if session != archived["receipt"]["session_id"] or inventory["window_count"] != visits:
            raise ValueError(f"Signed inventory changed for {case}")
        manifests = tuple((Path(entry["path"]), entry["sha256"]) for entry in pair["cache_observation"]["manifests"])
        shared = ["--recording", recording, "--archive", pair["archive"]["root"], "--region", pair["region"]]
        commands = dict(stock=[pairs.NAMED_V3, *shared, "--bulk-root", work / "stock"],
                        candidate=[python, "-BPs", HERE / "full_short_run.py", *shared, "--short-binary", short,
                                   "--geographic-library", geographic, "--regional-track-library", regional,
                                   "--track-graph", "installed", "--reuse-cold-track-rows", "--reuse-grid-phase-states",
                                   "--output", work / "candidate"])
        runs = {}
        for arm in order:
            page_size = os.sysconf("SC_PAGE_SIZE")
            cache = cache_residency.bound_snapshot(store, recording, manifests, page_size, query)
            observations = [cache]
            previous_warm = all(item["fully_warm"] for item in runs.values())
            if previous_warm and cache["cached_pages"] != cache["observed_file_pages"]:
                warm_recording(manifests)
                cache = cache_residency.bound_snapshot(store, recording, manifests, page_size, query)
                observations.append(cache)
            try:
                require_warm(cache)
                fully_warm = True
            except ValueError as error:
                fully_warm = False
                print(f"Natural-cache fallback for {case} {arm}: {error}", flush=True)
            timed = measure(commands[arm], env, work / arm)
            runs[arm] = timed | dict(cache=cache, cache_before_warming=observations[0],
                                     cache_warming_observations=observations, fully_warm=fully_warm,
                                     command=list(map(str, commands[arm])))
            if timed["exit_code"]:
                runs[arm]["error"] = f"Process exited {timed['exit_code']}"
            else:
                try:
                    runs[arm].update(science(work, arm, timed, archived, input_digest))
                except Exception as error:
                    runs[arm]["error"] = f"{type(error).__name__}: {error}"
        assignment(case, digest, decision, visits)
        cache_mode = "fully_warm" if all(item["fully_warm"] for item in runs.values()) else "natural_cache_fallback"
        row = dict(case=case, order=order, issued=visits, expected_decision=decision, archive=pair["archive"],
                   original_pair_sha256=digest, recording=str(recording), region_file=pair["region"],
                   region=archived["receipt"]["region"], cache_mode=cache_mode, runs=runs,
                   missed_fix=decision == "complete" and runs["candidate"].get("decision") != "complete",
                   false_fix=decision == "withheld" and runs["candidate"].get("decision") == "complete")
        write(work / "result.json", row)
        results.append(row)
    reference = read(checked(REFERENCE, REFERENCE_SHA256))
    for row in results:
        ref, = (item for item in reference["cases"] if item["dataset_label"] == row["case"])
        truth = ([ref["reference"][k] for k in ("latitude_deg", "longitude_deg")]
                 if ref["authority_eligible"] and ref["sealed_metadata_digests_verified"] else None)
        row["calibration"] = calibration(row["runs"], truth)
    write(output / "results.json", dict(machine=settings, stock_build=build, native_libraries=libraries,
          candidate_source_commit="593a2ca5f", candidate_run_sha256=RUN_SOURCE, protocol_sha256=sha256(
              (HERE / "short-raw-diagnostic-protocol.md").read_bytes()).hexdigest(),
          driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), cache_library_sha256=CACHE_SHA,
          reference_audit_sha256=REFERENCE_SHA256, cases=results,
          resumed_unmeasured_second_case=resume,
          cumulative=[cumulative(results[:n]) for n in (1, 2)]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("output", "short", "geographic", "regional"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--resume", action="store_true", help="Preserve a sealed first case and complete an unmeasured second case")
    args = parser.parse_args()
    with pairs.single_core_slot(2):
        run(**vars(args))
