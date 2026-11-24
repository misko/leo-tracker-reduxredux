"""Publish the archived dense hybrid once through the unchanged named launcher."""

import argparse
from contextlib import ExitStack, contextmanager
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

from dense_hybrid_combined import NAMED_PIN, PLAN_PIN, data, pin
from empty_bootstrap import BASELINE, BASELINE_PIN, PAYLOAD, RELEASE, checked, clock, now
from preloaded_saved_worker import read, write


ADAPTIVE = Path("/dev/shm/leo-v3-live-adaptive-grid-result01")
ADAPTIVE_BINDING = "5145340dc4851b1668779566fef0a88411a02ad5d54db64b3d6124bec028d9bf"
ADAPTIVE_RESULT = "4980d2c33a8809b6c7653e83251358c68f653befd646c0ec6367c51c8fe1a482"
ADAPTIVE_TRACE = "a0205c691d44f885a7d2ca02e2e9602ec6acd978b609ae0379926243fbaf7fd4"
ADAPTIVE_WORKER = "db4eaeee87e0b9cfcd4504ff55abc94a8a67b64bbcfe7f3574e1d3e91bbc6834"
HISTORICAL_CLOCKS = "ae947ab9906b878b9491f9c4a227f0dd4f14c0332891d46b9f0b4a61264c910a"
FINGERPRINT = "6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f"
INSTALLED_NATIVE = "2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5"
INPUT = "sha256:161d3ff4a85777f81217a929fdf0c999eb09f48575322ab46dcdcd773a95e23a"
PROTOCOL = HERE/"named-hybrid-baseline-protocol.md"
ARMS = ("c0", "fitted_c")


def deny_waveform(*_args, **_kwargs):
    raise RuntimeError("Waveform access is outside the named saved comparison")


def verify_request():
    from aperture_trial import archive_identity
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader

    bound = data(ADAPTIVE/"binding.json", ADAPTIVE_BINDING)
    result = data(HERE/"measurements/live-adaptive-grid-dense.json", ADAPTIVE_RESULT)
    request = bound["request"]
    plan = data(Path(request["plan"])/"plan.json", PLAN_PIN)
    if (request["native"] != INPUT or plan["native_sha256"] != INPUT
            or plan["detector_recipe"] != bound["detector_recipe"]
            or canonical_digest(plan["detector_recipe"]) != request["detector"]
            or not result["passed"] or result["original_waveform_reads"]):
        raise ValueError("The exact original signed adaptive request and proof are required")
    for label, digest in (("packet", INPUT[7:]), ("region", request["offer_sha256"]),
                          ("saved_inventory", request["inventory"][7:])):
        path = Path(request[label])
        if not path.resolve(strict=True).is_relative_to("/dev/shm"):
            raise ValueError("Only original tmpfs saved inputs are admitted")
        checked(path, digest)
    archive = Path(request["archive"]["root"]).resolve(strict=True)
    if (not archive.is_relative_to("/dev/shm") or archive_identity(archive)["snapshots_sha256"] !=
            request["archive"]["snapshots_sha256"]):
        raise ValueError("Original causal archive identity changed")
    refs = TleArchiveReader(archive).list_snapshots("space-track")
    if len(refs) != 47 or any(ref.collected_utc_ns >= request["cutoff_utc_ns"]
                              or not ref.path.resolve(strict=True).is_relative_to(archive) for ref in refs):
        raise ValueError("Original archive needs its 47 pre-cutoff local snapshots")
    pages = json.loads(subprocess.check_output(["fincore", "--json", "--bytes", "-o", "RES,PAGES,SIZE,FILE",
                                               *(ref.path for ref in refs)]))["fincore"]
    if len(pages) != 47 or any(row["res"] < row["size"] for row in pages):
        raise ValueError("Original saved archive is no longer resident")
    return request, bound["detector_recipe"], pages, bound["portable"]["generator"]


def inventory_check(request, inventory, audit):
    def acquire(_store, recording, *, verify_windows=True):
        if verify_windows or Path(recording) != Path(request["recording"]) or audit:
            raise ValueError("Expected one exact metadata-only inventory lookup")
        audit.append(request["inventory"])
        return request["session"], request["inventory"], inventory
    return acquire


@contextmanager
def detector_handoff(scan, request, native, audit):
    def acquire(session, digest, *_args):
        from empty_bootstrap import bind_native

        started = now()
        if (audit or (session, digest) != (request["session"], request["inventory"])
                or scan.PINS["cancellation-factors.so"] != INSTALLED_NATIVE):
            raise ValueError("The verified installed scanner requested a different saved acquisition")
        detector = request["detector"][7:]
        bind_native(native, session, digest, detector, expected=INPUT)
        scan.PINS["cancellation-factors.so"] = detector
        audit.update(clock(started), native=INPUT, detector=request["detector"], original_asset=INSTALLED_NATIVE)
        return native

    with patch.dict(scan.PINS, {}), patch.object(scan, "acquire", acquire):
        yield


def media_and_grid(output, receipt, native, selected):
    from leo.contracts.digests import canonical_digest
    from leo.contracts.fast_standard_analysis import PLOTS
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from PIL import Image

    run = receipt["run_id"]
    store = FastStandardAnalysisStore(output)
    detail = store.detail(run)
    if (detail["input_sha256"] != native or detail["terminal_sha256"] != receipt["terminal_sha256"]
            or detail["state"] != receipt["decision"]):
        raise ValueError("The installed publication did not bind the measured hybrid terminal")
    if detail["state"] == "withheld":
        if detail["artifacts"] or selected or not detail.get("decision"):
            raise ValueError("Expected a real withheld reason and no Figures")
        return dict(images={}, grid=None, owner_rows={})
    if detail["state"] != "complete" or tuple(image["name"] for image in detail["artifacts"]) != tuple(PLOTS):
        raise ValueError("The complete standard named publication must emit eight figures")
    images = {}
    for item in detail["artifacts"]:
        media = store.artifact(run, item["name"], item["sha256"])
        with Image.open(BytesIO(media)) as picture:
            picture.load()
            images[item["name"]] = dict(sha256=item["sha256"], size=picture.size,
                                       rgba_sha256=sha256(picture.convert("RGBA").tobytes()).hexdigest())
    grid, path = store.position_grid(run), store.position_path(run)
    if (not grid["complete"] or not grid["matched_c_grid"] or grid["evaluated_points"] != 179 or len(grid["points"]) != 179
            or not path["stages"] or any(set(stage["arms"]) != set(ARMS) for stage in path["stages"])):
        raise ValueError("The named positive control needs its original grid and both calibration paths")
    for document in (grid, path):
        binding = document["binding"]
        if (binding["position_png_sha256"] != images["position"]["sha256"] or binding["input_sha256"] != native
                or binding["terminal_sha256"] != receipt["terminal_sha256"]):
            raise ValueError("Position sidecars must bind the unique current figure and signed publication")
    owners = {arm: row["owner_sha256"] for arm, row in detail["arms"].items()}
    matching = [x for x in selected if set(x) == set(ARMS)
                and {a: canonical_digest({row[0]: row[1] for row in x[a]}) for a in ARMS} == owners]
    if not matching or any(x != matching[0] for x in matching[1:]):
        raise ValueError("The measured owner rows do not bind both published named arms")
    return dict(images=images, grid=grid["evaluated_points"], owner_rows=matching[0],
                sidecars=dict(grid=canonical_digest(grid), path=canonical_digest(path)),
                owner_maps=owners, owner_observations=len(selected))


def worker(job_path, output):
    started = now()
    job = read(job_path)
    request = job["request"]
    checked(BASELINE, BASELINE_PIN)
    launcher = runpy.run_path(str(BASELINE))
    if launcher["FINGERPRINT"] != FINGERPRINT or launcher["RELEASE"] != RELEASE or request["native"] != INPUT:
        raise ValueError("The trusted named launch or hybrid packet changed")
    native = json.loads(checked(Path(request["packet"]), INPUT[7:]))
    inventory = json.loads(checked(Path(request["saved_inventory"]), request["inventory"][7:]))
    raw = native["source"]
    checked(Path(request["region"]), request["offer_sha256"])
    if (inventory["window_count"] != 6772 or inventory["recording_name"] != Path(request["recording"]).name
            or raw["raw_recording_authority_digest"] != request["authority"] or len(raw["probes"]) != 13530
            or sum(len(row["candidates"]) for row in raw["probes"]) != 7342
            or native["clock_anchor"]["before"]["realtime_ns"] != request["cutoff_utc_ns"]):
        raise ValueError("The original dense hybrid opportunity count or authority changed")
    paths = [str(PAYLOAD), str(RELEASE/"src"), str(RELEASE)]
    sys.path[:0] = paths
    from tools.pipeline_eval.qualification import experimental_publication as publication
    from tools.pipeline_eval.variants.experimental import lean_startup
    if Path(publication.__file__).resolve() != PAYLOAD/"tools/pipeline_eval/qualification/experimental_publication.py":
        raise ValueError("Expected the actual named release publication")

    def deny_backing(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            path = os.fsdecode(args[0])
            if path.startswith(("/srv/bulk/", "/mnt/qnap01/")):
                deny_waveform()

    sys.addaudithook(deny_backing)
    scope, chosen, acquire, inventories, calls = ExitStack(), [], {}, [], {}
    timings = {"solve": [], "render": []}
    actual_startup, installed_run = lean_startup.install, publication.run

    def observed_publication(args, specification):
        if calls or specification["startup"] != "lazy-exports" or specification["detector_sha256"] != INSTALLED_NATIVE:
            raise ValueError("The saved boundary handled a different named invocation")
        calls["settings"] = {key: value for key, value in specification.items() if key != "sources"}
        result = installed_run(args, specification)
        calls["receipt"] = result
        return result

    def prepare_named():
        actual_startup()
        from leo.operations.tle_archive import TleArchiveReader
        from leo.storage.fast_scan import FastScanStore, FastSegmentSource
        from leo.storage.short_window import ShortWindowReader
        from leo.contracts.digests import canonical_digest
        from tools import algo08_position, algo08_scan

        if (Path(algo08_scan.__file__).resolve() != PAYLOAD/"tools/algo08_scan.py"
                or Path(algo08_position.__file__).resolve() != PAYLOAD/"tools/algo08_position.py"
                or canonical_digest(job["recipe"]) != request["detector"]
                or canonical_digest(inventory) != request["inventory"]):
            raise ValueError("Named release sources or signed request bindings changed")
        selected, analysis, archive_read = algo08_position.selected_packet, algo08_scan.analyze, TleArchiveReader.read
        archive = Path(request["archive"]["root"])

        def local(reader, snapshot):
            if (reader.root.resolve(strict=True) != archive or not snapshot.path.resolve(strict=True).is_relative_to(archive)
                    or snapshot.collected_utc_ns >= request["cutoff_utc_ns"]):
                raise ValueError("The named comparison may read only its original causal snapshots")
            return archive_read(reader, snapshot)

        def observe_selected(*args, **kwargs):
            packet = selected(*args, **kwargs)
            chosen.append({arm: [[row["observation_id"], row["norad"], row["role"]] for row in rows]
                           for arm, rows in packet["rows"].items()})
            return packet

        def timed(operation, scope_name):
            def observe(*args, **kwargs):
                begin = now()
                try:
                    return operation(*args, **kwargs)
                finally:
                    timings[scope_name].append(clock(begin))
            return observe

        def analyze(*args, **kwargs):
            with (detector_handoff(algo08_scan, request, native, acquire),
                  patch.object(algo08_scan, "solve", timed(algo08_scan.solve, "solve")),
                  patch.object(algo08_scan, "render", timed(algo08_scan.render, "render"))):
                return analysis(*args, **kwargs)

        for owner, name, value in (
            (FastScanStore, "inventory", inventory_check(request, inventory, inventories)),
            (FastSegmentSource, "windows", deny_waveform), (ShortWindowReader, "windows", deny_waveform),
            (TleArchiveReader, "read", local), (algo08_position, "selected_packet", observe_selected),
            (algo08_scan, "analyze", analyze),
        ):
            scope.enter_context(patch.object(owner, name, value))

    output.mkdir()
    with (scope, patch.object(lean_startup, "install", prepare_named),
          patch.object(publication, "run", observed_publication)):
        launcher["main"](["--recording", request["recording"], "--archive", request["archive"]["root"],
                          "--region", request["region"], "--bulk-root", str(output)])
    receipt = calls["receipt"]
    from raw_cfo_north_trial import native_file

    checked(native_file(output), INPUT[7:])
    if not acquire or inventories != [request["inventory"]] or len(timings["solve"]) != 1:
        raise ValueError("The original named solver must use exactly one saved handoff")
    start_verify = now()
    verified = media_and_grid(output, receipt, INPUT, chosen)
    write(output/"named-saved-witness.json", dict(receipt=receipt, named_identity=read(output/"algo08v3-release.json"),
                                                 handoff=acquire, stock_specification=calls["settings"], timing=timings,
                                                 verification=clock(start_verify), evidence=verified, full=clock(started)))


def launch(root):
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    if root.parent.resolve(strict=True) != Path("/dev/shm"):
        raise ValueError("Expected a fresh tmpfs root")
    start = now()
    request, recipe, pages, producer = verify_request()
    machine = host()
    checkout = HERE.parents[2]
    git = ["git", "-c", f"safe.directory={checkout}", "-C", str(checkout)]
    if subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise ValueError("Commit the frozen study before a paid launch")
    root.mkdir()
    (root/"tmp").mkdir()
    (root/"fonts").mkdir()
    for path in (ADAPTIVE/"fonts").glob("fontlist-*.json"):
        (root/"fonts"/path.name).hardlink_to(path)
    target, binding = root/"named", root/"binding.json"
    command = ["/usr/bin/timeout", "--kill-after=2s", "115s", RELEASE/"venv/bin/python", "-IB",
               Path(__file__), "worker", binding, target]
    write(binding, dict(request=request, recipe=recipe, machine=machine, clock_scope="saved launch through exit",
                        sources={p.name: pin(p) for p in (Path(__file__), PROTOCOL)}, archive_residency=pages,
                        candidate_same_cutoff_producer=producer, command=list(map(str, command)),
                        outer_admission=clock(start),
                        commit=subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()))
    timing = measure(command, environment(root) | {"TMPDIR": str(root/"tmp"), "XDG_CACHE_HOME": str(root/"tmp")}, target)
    write(root/"clock.json", timing)
    if timing["exit_code"]:
        write(root/"result.json", dict(state="named_incompatible_or_failed", execution=timing, binding_sha256=pin(binding)))
        raise RuntimeError(timing["stderr_tail"])


def score(root):
    from leo.contracts.digests import canonical_digest
    from prospective_0316_solver import owner_delta
    from tools.pipeline_eval.qualification.paired_publication import evidence
    from triage_bounds import calibration_comparison

    binding, elapsed = (read(root/f"{name}.json") for name in ("binding", "clock"))
    named = read(root/"named/named-saved-witness.json")
    receipt = named["receipt"]
    named_science = evidence(root/"named", receipt, elapsed["started_unix_ns"], read_only=True)
    adaptive_result = data(HERE/"measurements/live-adaptive-grid-dense.json", ADAPTIVE_RESULT)
    parent = data(ADAPTIVE/"candidate/dense-hybrid-combined-worker.json", ADAPTIVE_WORKER)
    adaptive_trace = data(ADAPTIVE/"candidate/joint-research-receipt.json", ADAPTIVE_TRACE)
    adaptive_started = adaptive_result["clocks"]["adaptive"]
    archive = data(HERE/"measurements/dense-full-short-raw.json.gz", NAMED_PIN)["baseline"]
    historical = data(HERE/"measurements/dense-control-clocks.json", HISTORICAL_CLOCKS)
    if (named_science["raw_authority"] != binding["request"]["authority"] or archive["authority"] != named_science["raw_authority"]
            or receipt["region"] != parent["receipt"]["region"] or receipt["region"] != archive["receipt"]["region"]
            or parent["native_sha256"] != INPUT or named["named_identity"]["frozen_specification"] != "sha256:"+FINGERPRINT
            or receipt["session_id"] != parent["receipt"]["session_id"] or receipt["counts"] != parent["receipt"]["counts"]
            or historical["common"]["terminal_sha256"] != archive["receipt"]["terminal_sha256"]
            or historical["common"]["archive"]["snapshots_sha256"] != binding["request"]["archive"]["snapshots_sha256"]):
        raise ValueError("Comparator authority, supplied region, saved inventory or named release differ")
    candidate_dir = ADAPTIVE/"candidate"
    candidate_terminal_path = candidate_dir/"fast-scan-automatic-work"/parent["receipt"]["run_id"]/"terminal.json"
    candidate = read(candidate_terminal_path)
    if candidate["native_sha256"] != INPUT or canonical_digest(candidate) != parent["receipt"]["terminal_sha256"]:
        raise ValueError("Archived adaptive terminal did not bind the same native packet")
    error = calibration_comparison(dict(named_same_packet=named_science, adaptive=candidate, named_own_detector=archive), "DS30-0008")
    owners = {}
    if receipt["decision"] == "complete":
        rows = named["evidence"]["owner_rows"]
        others = adaptive_trace["selected_rows"]
        owners = {arm: owner_delta(rows[arm], others[arm]) for arm in ARMS}
    first = adaptive_started["elapsed_s"] + binding["candidate_same_cutoff_producer"]["elapsed_s"]
    write(root/"result.json", dict(state=receipt["decision"], reference_valid=True, named=named, science=named_science,
          candidate_terminal=candidate, owners=owners, geography=error, history=historical["controls"],
          adaptive=dict(clock=adaptive_started, first_use_serial_s=first, grid=101, decision=parent["receipt"]["decision"]),
          clock=elapsed, saved_elapsed_speed_ratio=elapsed["elapsed_s"]/adaptive_started["elapsed_s"],
          saved_elapsed_speed_ratio_first_use=elapsed["elapsed_s"]/first, binding_sha256=pin(root/"binding.json")))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    for action in ("launch", "score"):
        actions.add_parser(action).add_argument("root", type=Path)
    child = actions.add_parser("worker")
    child.add_argument("job_path", type=Path)
    child.add_argument("output", type=Path)
    args = vars(parser.parse_args())
    {"launch": launch, "worker": worker, "score": score}[args.pop("action")](**args)
