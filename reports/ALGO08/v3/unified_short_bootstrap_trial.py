"""Measure the two existing original-input controls using one unified raw entry."""

import argparse
from contextlib import ExitStack
import gzip
from hashlib import sha256
import json
import mmap
from pathlib import Path
from statistics import median
import subprocess
from time import perf_counter

from aperture_trial import RELEASE, archive_identity, read, write
from combined_frontier_run import BLOCK_SHA
from dense_geographic_trial import host
from full_short_physical import ISSUED, assigned, environment
from full_short_run import GEOGRAPHIC_SHA, RECIPE_SHA, SHORT_SHA, TRACK_SCORES_SHA
from joint_publication import artifacts
from local_future_cli_trial import cache_before, native_packet
from short_raw_diagnostic import (
    CACHE_LIB, CACHE_SHA, CASES, HERE, FastScanStore, assignment, cache_residency, canonical_digest, checked, measure, pairs,
)
from triage_bounds import ShortWindowReader, confined_path
from weak_combined_raw import REFERENCE, REFERENCE_PIN


CONTROLS = {
    "tiny": "4512b1627e700004c64cf241effaddf5f16f57cf8e44225576da452777deccb9",
    "weak": "f049c5c80b1fcdb6004dab75c76324193bb7313918631292b354b9fa413b695e",
}
WEAK_SCIENCE = "a704861e37e40e7364fbf97bcb74e98bb9c701ca474c12821e8ed7df86cab233"
SURVEY = "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5"
ORIGINAL_TIMING_DRIVER = "4948954903289835646c81e753af518be1f74cd73f35f91708a1e1073792f54d"


def control(case):
    path = HERE / "measurements" / f"combined-frontier-{'empty' if case == 'tiny' else 'weak'}-bypass.json.gz"
    return json.loads(gzip.decompress(checked(path, CONTROLS[case]).read_bytes()))


def condition_tiny(manifests, scope):
    mapped = 0
    for manifest, digest in manifests:
        reader = ShortWindowReader(manifest.parent)
        if reader.manifest_sha256 != digest:
            raise ValueError("Signed cache conditioning source differs")
        for chunk in reader.manifest.chunks:
            mapped += chunk.compressed_bytes
            if mapped > 32 * 1024**2:
                raise ValueError("Only the tiny cache control may retain a mapping")
            member = confined_path(reader.path, reader.path / chunk.payload_relative_path, must_exist=True)
            stream = scope.enter_context(member.open("rb"))
            view = scope.enter_context(mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ))
            view[::mmap.PAGESIZE]
    return mapped


def score(case, output, clock, reference):
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    receipt = json.loads(output.with_suffix(".stdout").read_bytes())
    packet = native_packet(output)
    native = read(packet)
    source = native["source"]
    probes = source["probes"]
    observed = pairs.evidence(output, receipt, clock["started_unix_ns"], read_only=True)
    science = artifacts(output, receipt)
    expected = reference.get("verified", reference)
    expected_images = expected.get("pngs", expected.get("images"))
    active = receipt["decision"] == "complete"
    terminal_sha = expected.get("terminal_sha256", expected.get("terminal"))
    if (terminal_sha != receipt["terminal_sha256"] or receipt["counts"] != expected["counts"]
            or any(observed[k] != expected[k] for k in ("arms", "owners", "scientific_digests") if k in expected)
            or canonical_digest(expected_images) != canonical_digest(science["images"])
            or len(science["images"]) != (8 if active else 0)):
        raise ValueError(f"{case} {output.name} publication disagrees with the archived arm")
    if not active and observed["reason"] != "no_active_curvature":
        raise ValueError("The small physical control no longer returns the original withheld decision")
    if output.name == "stock":
        pairs.verify_v3_publication(output, receipt)
        bootstrap = None
    else:
        bootstrap = read(output / "unified-short-bootstrap.json")
        research = read(output / "joint-research-receipt.json")
        if (bootstrap["receipt"] != receipt or bootstrap["raw_acquisitions"] != 1
                or bootstrap["verified_handoffs"] != 1 or bootstrap["scientific_imports_before"]
                or bootstrap["route"] != "optimized_installed_graph"
                or source["raw_recording_authority_digest"] != bootstrap["receiver_audit"]["recording_authority"]
                or bootstrap["native_sha256"] != canonical_digest(native)
                or bootstrap["detector_recipe_sha256"] != "sha256:"+RECIPE_SHA
                or native["provenance"]["detector_sha256"] != bootstrap["detector_recipe_sha256"]
                or bootstrap["causal_cutoff_utc_ns"] != native["clock_anchor"]["before"]["realtime_ns"]):
            raise ValueError("The research identity did not preserve one exact signed raw handoff")
        if case == "tiny" and (len(research["early_regional"]) != 1 or not research["early_regional"][0]["skipped_empty_graph"]):
            raise ValueError("Expected the ordinary no-track regional bypass on the tiny nonempty packet")
        if case == "weak":
            from combined_frontier_score import verify_callbacks

            verify_callbacks(bootstrap["prefetch"], research["solve"]["geographic_projector"])
        bootstrap["numerical_publication"] = {k: research[k] for k in ("solve", "early_regional", "route")}
    grid = FastStandardAnalysisStore(output).position_grid(receipt["run_id"]) if active else None
    if grid is not None and (not grid["complete"] or grid["evaluated_points"] != 179):
        raise ValueError("The completed control requires its original full diagnostic grid")
    canonical = canonical_digest(native)
    if expected["native_sha256"] != canonical:
        raise ValueError("The original arm does not reproduce its archived signed detector packet")
    return dict(publication=observed, figures=science["images"], bootstrap=bootstrap,
                report_file_s=((output / "fast-scan-reports" / (receipt["run_id"]+".json")).stat().st_mtime_ns
                               - clock["started_unix_ns"])/1e9,
                opportunity_digest=canonical_digest([{k: v for k, v in row.items() if k != "candidates"} for row in probes]),
                native=canonical, input_manifest=source["input_manifest_sha256"],
                cutoff_utc_ns=native["clock_anchor"]["before"]["realtime_ns"],
                probes=len(probes), selected=sum(len(row["candidates"]) for row in probes))


def run(root, short, geographic, regional, block):
    system = host()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Use fresh tmpfs publication roots")
    libraries = tuple(checked(path, pin) for path, pin in ((short, SHORT_SHA), (geographic, GEOGRAPHIC_SHA),
                                                         (regional, TRACK_SCORES_SHA), (block, BLOCK_SHA)))
    frozen = {key: control(key) for key in CONTROLS}
    weak_science = read(checked(HERE / "measurements/weak-combined-raw.json", WEAK_SCIENCE))
    label, pin, decision, visits, _ = CASES[0]
    tiny, recorded = assignment(label, pin, decision, visits)
    weak = read(checked(REFERENCE, REFERENCE_PIN))
    basic = assigned(short)
    if (any(weak[k] != v for k, v in basic.items()) or basic != frozen["weak"]["binding"]["request"]
            or weak["inventory_sha256"] != frozen["weak"]["binding"]["inventory"]):
        raise ValueError("The DS30-0016 causal assignment changed")
    assignments = {
        "tiny": (tiny["recording"], tiny["archive"], tiny["region"], visits, recorded["raw_authority"], ("stock", "candidate")),
        "weak": (weak["recording"], weak["archive"], weak["region_file"], ISSUED, weak["raw_authority"], ("candidate", "stock")),
    }
    identified = pairs.verified_v3(pairs.NAMED_V3)
    query = cache_residency.load_query(checked(CACHE_LIB, CACHE_SHA))
    root.mkdir()
    env, python = environment(root), RELEASE / "venv/bin/python"
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    observations = {}
    for case, (recording, archive, offer, count, authority, order) in assignments.items():
        folder = root / case
        folder.mkdir()
        store, recording = FastScanStore(folder), Path(recording)
        _, inventory_pin, inventory = store.inventory(recording, verify_windows=False)
        if (archive_identity(Path(archive["root"])) != archive or inventory["window_count"] != count
                or inventory_pin != (frozen[case]["inventory"] if case == "tiny" else weak["inventory_sha256"])):
            raise ValueError("The original recording or causal archive changed")
        common = ["--recording", recording, "--archive", archive["root"], "--region", offer]
        named = [pairs.NAMED_V3, *common, "--bulk-root", folder / "stock"]
        candidate = [python, "-IB", HERE / "unified_short_bootstrap.py", *common, "--output", folder / "candidate"]
        for name, path in zip(("short-binary", "geographic-library", "regional-track-library", "frontier-block-library"), libraries, strict=True):
            candidate.extend(["--"+name, path])
        (folder / "stock").mkdir()
        members = tuple((Path(row["path"])/"manifest.json", row["manifest_digest"]) for row in inventory["segments"])
        rows = {}
        with ExitStack() as scope:
            prep = perf_counter()
            mapped = condition_tiny(members, scope) if case == "tiny" else 0
            conditioning = dict(mapped_bytes=mapped, elapsed_s=perf_counter()-prep)
            for arm in order:
                cmd = named if arm == "stock" else candidate
                cache = cache_before(store, recording, members, query)
                clock = measure(cmd, env, folder / arm)
                rows[arm] = dict(clock=clock, cache=cache, command=list(map(str, cmd)))
                write(folder / f"{arm}-clock.json", rows[arm])
                if clock["exit_code"]:
                    raise RuntimeError(f"{case} {arm} failed: {clock['stderr_tail']}")
        reference = frozen[case] if case == "tiny" else weak_science
        for arm in order:
            rows[arm]["science"] = score(case, folder / arm, rows[arm]["clock"], reference["runs"][arm])
        a, b = [rows[k]["science"] for k in ("stock", "candidate")]
        if (any(a[key] != b[key] for key in ("opportunity_digest", "input_manifest", "cutoff_utc_ns"))
                or any(row["publication"]["raw_authority"] != authority for row in (a, b))
                or b["bootstrap"]["requested_offer_sha256"] != sha256(Path(offer).read_bytes()).hexdigest()):
            raise ValueError("Signed opportunities or causal authority differ across arms")
        if case == "weak" and canonical_digest(b["figures"]) != canonical_digest(frozen[case]["runs"]["candidate"]["images"]):
            raise ValueError("Weak figure parity failed")
        evidence = dict(rows=rows, conditioning=conditioning, order=order, causal_archive=archive,
                        request_offer_sha256=sha256(Path(offer).read_bytes()).hexdigest())
        write(folder / "verified.json", evidence)
        observations[case] = evidence
    summarize(root, observations, system, identified, sha256(Path(__file__).read_bytes()).hexdigest())


def summarize(root, observations, system, identified, timing_driver):
    from aperture_score import PHYSICAL, distance_km

    (survey,) = [row["reference"] for row in read(checked(PHYSICAL, SURVEY))["cases"]
                 if row["dataset_label"] == "DS30-0016" and row["authority_eligible"]]
    truth = [survey[k] for k in ("latitude_deg", "longitude_deg")]
    for row in observations["weak"]["rows"].values():
        row["errors_km"] = {arm: distance_km(value["latlon"], truth) for arm, value in row["science"]["publication"]["arms"].items()}
    elapsed = [[r["rows"][arm]["clock"]["elapsed_s"] for arm in ("stock", "candidate")] for r in observations.values()]
    write(root / "result.json", dict(machine=system, stock_build=identified, controls=CONTROLS,
          weak_science_sha256=WEAK_SCIENCE,
          protocol_sha256=sha256((HERE / "unified-short-bootstrap-protocol.md").read_bytes()).hexdigest(),
          timing_driver_sha256=timing_driver, score_driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
          survey_sha256=SURVEY, observations=observations,
          median_ratio=median(b/a for a, b in elapsed), summed_ratio=sum(b for a, b in elapsed)/sum(a for a, b in elapsed)))


if __name__ == "__main__":
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    if sys.argv[1:2] == ["rescore-sealed"]:
        parser.add_argument("root", type=Path)
        root = parser.parse_args(sys.argv[2:]).root
        sealed = {case: read(root / case / "verified.json") for case in CONTROLS}
        summarize(root, sealed, host(), pairs.verified_v3(pairs.NAMED_V3), ORIGINAL_TIMING_DRIVER)
    else:
        for arg in ("root", "short", "geographic", "regional", "block"):
            parser.add_argument(arg, type=Path)
        run(**vars(parser.parse_args()))
