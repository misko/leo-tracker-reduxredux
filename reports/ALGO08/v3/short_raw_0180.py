"""Replay a length-selected small original recording on the two actual process entry points."""

import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import resource
import subprocess
from time import perf_counter, process_time

from empty_bootstrap import RELEASE, checked


HERE = Path(__file__).resolve().parent
BULK = Path("/srv/bulk")
BINDING = BULK / "leo-dev/ds30-full-20261121/bindings/DS30-0180.json"
BINDING_SHA = "229d77358a899cdb50ef3cb66701fc2a77e3a67d95a08075b5a11282a09f6be0"
SHORT = Path("/var/tmp/leo-mixed-aperture.pdUjDb1S/build-v2/short-primary.so")
STAGED = Path("/dev/shm/leo-v3-saved-0402-pair-01")
ORDER = ("stock", "candidate")
RAW_LIMIT = 112 * 1024**2
ORBIT_LIMIT = 100 * 1024**2
OPERATOR_OFFER = Path("/tmp/leo-algo08v2-2x-bench/integration02/ds30-station-offer.json")
BOOTSTRAP = HERE / "unified_short_bootstrap.py"
FLAGS = ("--prove-empty-graph", "--one-pass-web-png")
PROOF_SOURCES = {
    "unified_short_bootstrap.py": "5cd6580673fee701854d08f337bc72678bb2aa105a3c24b79f7d46bb606a7057",
    "short_graph_guard.py": "269eaab36011523072e25798ba3bdb34a9968d49ee39eba6d89022ef08a8cffd",
}
REVIEWED_PROOF_LAUNCHERS = frozenset((
    PROOF_SOURCES[BOOTSTRAP.name],
    "226fdf3634e5e5ba9480912eed9e02e1bd28b4653100e6a83a3c38d1cc2f0bae",
))


def proof_sources(launcher_sha):
    if launcher_sha not in REVIEWED_PROOF_LAUNCHERS:
        raise ValueError("Unreviewed time-proof launcher")
    return {**PROOF_SOURCES, BOOTSTRAP.name: launcher_sha}


@dataclass(frozen=True)
class Workload:
    id: str
    binding: Path
    binding_sha: str
    windows: int
    snapshots: int
    compressed_bytes: int
    raw_limit: int
    order: tuple[str, str] = ORDER
    time_proof: bool = False


LEGACY = Workload("DS30-0180", BINDING, BINDING_SHA, 92, 50, 111_464_875, RAW_LIMIT)
TRANSFER = Workload(
    "DS30-0102", BINDING.with_name("DS30-0102.json"),
    "27af68985485eb20861757291452ed9210c3be906831bd729808fb212ab3e7b6",
    124, 51, 147_843_885, 160 * 1024**2, ("candidate", "stock"), True,
)
WORKLOADS = {row.id: row for row in (LEGACY, TRANSFER)}


def stage_orbits(target, source, names, cutoff, *, expected_count=50):
    if len(names) != expected_count:
        raise ValueError("Unexpected signed causal snapshot count")
    source = source / "archive/space-track"
    distinct = {}
    for name, digest in sorted(names.items()):
        if Path(name).name != name or int(name.split("-")[0]) >= cutoff or len(digest) != 64:
            raise ValueError("Invalid causal orbit entry")
        original = source / name
        size = original.stat().st_size
        if size > ORBIT_LIMIT:
            raise ValueError("Orbit staging exceeds the one-recording allowance")
        if distinct.setdefault(digest, (original, size))[1] != size:
            raise ValueError("Duplicate signed catalogue bodies differ in size")
    unique_bytes = sum(size for _, size in distinct.values())
    if unique_bytes > ORBIT_LIMIT:
        raise ValueError("Orbit staging exceeds the one-recording allowance")
    directory = target / "archive/space-track"
    directory.mkdir(parents=True)
    logical = 0
    copies = {}
    for name, digest in sorted(names.items()):
        original, size = distinct[digest]
        path = directory / name
        if digest in copies:
            path.hardlink_to(copies[digest])
        else:
            with original.open("rb") as stream:
                if os.fstat(stream.fileno()).st_size != size:
                    raise ValueError("Signed catalogue size changed before staging")
                body = stream.read(size)
            if len(body) != size or sha256(body).hexdigest() != digest:
                raise ValueError("Signed catalogue content changed before staging")
            path.write_bytes(body)
            copies[digest] = path
        logical += size
    return dict(snapshots=len(names), unique=len(copies), copied_bytes=unique_bytes, logical_bytes=logical)


def enrollment(workload):
    signed = json.loads(checked(workload.binding, workload.binding_sha))
    case = signed["case"]
    request = json.loads(checked(BULK / case["request"]["path"], case["request"]["sha256"]))
    job = request["job"]
    if (case["id"] != workload.id or case["recording"]["window_count"] != workload.windows
            or job["evaluation_reference"] is not None or len(request["causal_snapshots"]) != workload.snapshots
            or case["regions"][0]["center"] != job["search_center"]):
        raise ValueError("Changed enrollment or geographic offer")
    return signed, request


def output_digests(root, order):
    scope = [root / "admission.json", root / "offer.json"]
    for mode in order:
        scope.extend(root / f"{mode}{suffix}" for suffix in ("-clock.json", ".stdout", ".stderr"))
        scope.extend(p for p in (root / mode).rglob("*") if p.is_file())
    return {str(path.relative_to(root)): sha256(path.read_bytes()).hexdigest() for path in sorted(scope)}


def candidate_flags(workload):
    return (*FLAGS, "--prove-graph-time-support") if workload.time_proof else FLAGS


def launch(root, workload=LEGACY):
    from aperture_trial import write
    from dense_geographic_trial import host
    from full_short_physical import REGION_SHA, environment
    from short_raw_diagnostic import CACHE_LIB, CACHE_SHA, FastScanStore, cache_residency, measure, pairs, require_warm
    from triage_bounds import ShortWindowReader, warm_recording

    machine = host()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Research outputs must use a fresh tmpfs directory")
    signed, request = enrollment(workload)
    case = signed["case"]
    job = request["job"]
    manifests = tuple((BULK/r["path"], "sha256:"+r["sha256"]) for r in case["recording"]["segments"])
    recording = manifests[0][0].parent.parent
    root.mkdir()
    (root/"tmp").mkdir()
    store = FastScanStore(root)
    checked(CACHE_LIB, CACHE_SHA)
    query = cache_residency.load_query(CACHE_LIB)
    def residency():
        return cache_residency.bound_snapshot(store, recording, manifests, os.sysconf("SC_PAGE_SIZE"), query)
    before = residency()
    total = sum(chunk.compressed_bytes for path, _ in manifests for chunk in ShortWindowReader(path.parent).manifest.chunks)
    if total != workload.compressed_bytes or total > workload.raw_limit or before["members"] != 2 or before["unavailable"]:
        raise ValueError("Original signed payload does not fit the selected recording budget")
    offer = root / "offer.json"
    official_offer = checked(OPERATOR_OFFER, REGION_SHA)
    original_offer = json.loads(official_offer)
    if original_offer["center"] != job["search_center"] or original_offer["screen_center"] != job["screen_center"]:
        raise ValueError("Archive and original operator offer disagree")
    if workload.time_proof:
        offer.write_bytes(official_offer)
    else:
        write(offer, original_offer)
    cpu, wall = process_time(), perf_counter()
    orbit = stage_orbits(root/"tle", Path(job["tle_root"]), request["causal_snapshots"],
                         signed["orbit_cutoff_ns"], expected_count=workload.snapshots)
    orbit.update(stage_wall_s=perf_counter()-wall, stage_cpu_s=process_time()-cpu)
    named = pairs.verified_v3(pairs.NAMED_V3)
    pinned_sources = {}
    if workload.time_proof:
        pinned_sources = proof_sources(sha256(BOOTSTRAP.read_bytes()).hexdigest())
        for name, digest in pinned_sources.items():
            checked(HERE / name, digest)
    env = environment(root)
    env["TMPDIR"] = str(root/"tmp")
    subprocess.run([RELEASE/"venv/bin/python", "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    cpu, wall = process_time(), perf_counter()
    blocks = resource.getrusage(resource.RUSAGE_SELF).ru_inblock
    needed = before["cached_pages"] != before["observed_file_pages"]
    charged = warm_recording(manifests, maximum_bytes=workload.raw_limit) if needed else 0
    conditioning = dict(used=needed, cpu_s=process_time()-cpu, wall_s=perf_counter()-wall, before=before, bytes=total)
    if charged != (total if needed else 0):
        raise ValueError("The bounded conditioning pass differs from the signed payload size")
    conditioning.update(charged_bytes=charged, input_blocks=resource.getrusage(resource.RUSAGE_SELF).ru_inblock-blocks)
    write(root/"admission.json", dict(case=case["id"], binding=workload.binding_sha, request=case["request"]["sha256"],
          order=workload.order, host=machine, stock=named, conditioning=conditioning, archive=orbit,
          offer=original_offer, offer_sha256=REGION_SHA, proof_sources=pinned_sources,
          raw_budget_bytes=workload.raw_limit, orbit_budget_bytes=ORBIT_LIMIT, issued_visits=workload.windows))
    common = ["--recording", recording, "--region", offer, "--archive", root/"tle"]
    for mode in workload.order:
        target = root/mode
        if mode == "stock":
            target.mkdir()
            cmd = [pairs.NAMED_V3, *common, "--bulk-root", target]
        else:
            cmd = [RELEASE/"venv/bin/python", "-IB", BOOTSTRAP, *common,
                   "--output", target, "--short-binary", SHORT, "--geographic-library", STAGED/"geographic_library.so",
                   "--regional-track-library", STAGED/"regional_track_library.so", "--frontier-block-library",
                   STAGED/"frontier_block_library.so", *candidate_flags(workload)]
        cache = residency()
        require_warm(cache)
        clock = measure(cmd, env, target)
        write(root/f"{mode}-clock.json", dict(clock=clock, cache=cache, command=list(map(str, cmd))))
        if clock["exit_code"]:
            raise RuntimeError(clock["stderr_tail"])
    if workload.time_proof:
        write(root / "prediction-seal.json", output_digests(root, workload.order))


def score(root, destination, workload=LEGACY):
    from aperture_trial import read, write
    from empty_bootstrap import bind_native
    from full_short_run import RECIPE_SHA
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from local_future_cli_trial import native_packet
    from short_raw_diagnostic import pairs
    from triage_bounds import REFERENCE, REFERENCE_SHA256, distance_km

    signed, _ = enrollment(workload)
    case = signed["case"]
    admission = read(root/"admission.json")
    results = {}
    if admission["case"] != workload.id or admission["binding"] != workload.binding_sha or tuple(admission["order"]) != workload.order:
        raise ValueError("Process admission differs from the recorded enrollment or launch order")
    prediction_digest = None
    if workload.time_proof:
        seal = root / "prediction-seal.json"
        if read(seal) != output_digests(root, workload.order):
            raise ValueError("The paired process outputs differ from the pre-score seal")
        prediction_digest = sha256(seal.read_bytes()).hexdigest()
    for mode in workload.order:
        target = root/mode
        clock = read(root/f"{mode}-clock.json")
        pub = json.loads(target.with_suffix(".stdout").read_text().splitlines()[-1])
        if "receipt" in pub:
            pub = pub["receipt"]
        if mode == "stock":
            pairs.verify_v3_publication(target, pub)
        bootstrap = None if mode == "stock" else read(target/"unified-short-bootstrap.json")
        if bootstrap and (bootstrap["receipt"] != pub or bootstrap["raw_acquisitions"] != 1
                          or bootstrap["verified_handoffs"] != 1):
            raise ValueError("Expected exactly one authenticated receiver pass")
        if bootstrap and workload.time_proof:
            proof = bootstrap["graph_proof"]
            proof_source = proof.get("implementation_sha256") if proof else None
            graph_route = bootstrap["route"] == "authenticated_installed_graph_ineligible"
            if ("--prove-graph-time-support" not in clock["command"]
                    or bootstrap["frozen_specification"] != pairs.V3_IDENTITY["frozen_specification"]
                    or bootstrap["stock_launcher_sha256"] != pairs.V3_LAUNCHER_SHA
                    or bootstrap["requested_offer_sha256"] != admission["offer_sha256"]
                    or proof_sources(bootstrap["source_sha256"][BOOTSTRAP.name]) != admission["proof_sources"]
                    or proof_source not in (None, PROOF_SOURCES["short_graph_guard.py"])
                    or graph_route and proof_source is None
                    or bool(proof and proof["proven"]) != graph_route):
                raise ValueError("Candidate release, offer or time-proof route differs from the frozen input")
        raw = read(native_packet(target))
        source = raw["source"]
        science = pairs.evidence(target, pub, clock["clock"]["started_unix_ns"], read_only=True)
        media = artifacts(target, pub)
        recipe = pairs.V3_IDENTITY["detector_sha256"] if mode == "stock" else RECIPE_SHA
        bind_native(raw, case["session_id"], source["input_manifest_sha256"], recipe.removeprefix("sha256:"))
        if (clock["clock"]["exit_code"] or pub["window_count"] != workload.windows or pub["region"] != admission["offer"]
                or pub["session_id"] != case["session_id"] or pub["counts"]["processed"] != case["valid_visits"]
                or raw["clock_anchor"]["before"]["realtime_ns"] != signed["orbit_cutoff_ns"]
                or source["raw_recording_authority_digest"] != case["raw_authority"]
                or science["raw_authority"] != case["raw_authority"] or set(science["arms"]) != {"c0", "fitted_c"}):
            raise ValueError(f"Mismatched {mode} input, cutoff or geographic offer")
        probes = source["probes"]
        results[mode] = dict(process=clock, decision=pub["decision"], reason=science["reason"], arms=science["arms"],
            owners=science["owners"], counts=pub["counts"], native=canonical_digest(raw), terminal=pub["terminal_sha256"],
            input_manifest=source["input_manifest_sha256"], opportunity=canonical_digest([
                {k:v for k,v in row.items() if k != "candidates"} for row in probes]), grid_path=science["scientific_digests"],
            media=media, probes=len(probes), factors=sum(len(row["candidates"]) for row in probes),
            route=bootstrap["route"] if bootstrap else "named", proof=bootstrap["graph_proof"] if bootstrap else None)
        if workload.time_proof:
            release = (dict(specification=bootstrap["frozen_specification"], launcher=bootstrap["stock_launcher_sha256"],
                            sources=bootstrap["source_sha256"], solver=bootstrap["solver_recipe"])
                       if bootstrap else dict(admission["stock"], launcher=pairs.V3_LAUNCHER_SHA))
            results[mode].update(release=release, phases=bootstrap["phases"] if bootstrap else None)
    a, b = (results[mode] for mode in ("stock", "candidate"))
    if any(a[key] != b[key] for key in ("opportunity", "input_manifest", "probes")):
        raise ValueError("The two receiver methods used different opportunities")
    if any(r["decision"] == "complete" for r in results.values()):
        reference, = (c for c in json.loads(checked(REFERENCE, REFERENCE_SHA256))["cases"]
                      if c["dataset_label"] == case["id"] and c["authority_eligible"] and c["sealed_metadata_digests_verified"])
        truth = [reference["reference"][k] for k in ("latitude_deg","longitude_deg")]
        for r in results.values():
            r["errors_km"] = {k: distance_km(truth, v["latlon"]) for k,v in r["arms"].items() if v.get("latlon")}
    result = dict(admission=admission, runs=results, elapsed_ratio=b["process"]["clock"]["elapsed_s"] /
                  a["process"]["clock"]["elapsed_s"])
    if prediction_digest is not None:
        if not b["process"]["clock"]["started_unix_ns"] < a["process"]["clock"]["started_unix_ns"]:
            raise ValueError("Candidate was not the first measured process")
        result["pre_score_sha256"] = prediction_digest
    write(destination, result)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "score"))
    cli.add_argument("root", type=Path)
    cli.add_argument("--receipt", type=Path)
    cli.add_argument("--case", choices=WORKLOADS, default=LEGACY.id)
    args = cli.parse_args()
    if args.action == "launch":
        launch(args.root, WORKLOADS[args.case])
    elif args.receipt:
        score(args.root, args.receipt, WORKLOADS[args.case])
    else:
        cli.error("Supply --receipt when scoring")
