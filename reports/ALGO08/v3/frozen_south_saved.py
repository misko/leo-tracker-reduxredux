"""Replay the predeclared South offers at the authenticated detector handoff."""

import argparse
from contextlib import ExitStack
from hashlib import sha256
import json
import os
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
PINS = HERE / "measurements"
FREEZE_SHA = "be4d89302c90b2eee19ff930e4485de7ea22b0ef04e1ba216bf9734e47c4ddd1"
RUNTIME = Path("/tmp/leo-v3-0049-saved-crossover/reports/ALGO08/v3")
CROSS_SHA = "748efc75ca9381129580c106779caddfc3d97f694f0b6c73ed68ba22ccf60c69"
NAMED_ORIGIN = Path("/tmp/leo-v3-integrated-south-controls/south-result.json")
NAMED_ORIGIN_SHA = "e0ac0972934671d6536daed5ba64de4cf21f2d695bc51893c0720a08a7fef903"
PYTHON = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/venv/bin/python")


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def deny_original(recording, archive):
    def guard(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            path = Path(os.path.abspath(os.fsdecode(args[0])))
            if (path.name.endswith(".ci16.zst") or path.is_relative_to(recording)
                    or path.is_relative_to("/srv/bulk") or path.is_relative_to("/mnt/qnap01")):
                raise ValueError(f"A saved South publication cannot read an original source: {path}")
            if path.is_relative_to(archive) and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_TRUNC | os.O_CREAT):
                raise ValueError(f"A saved South publication cannot change its causal archive: {path}")
    return guard


def bootstrap():
    if digest(RUNTIME / "ds30_0049_saved_crossover.py") != CROSS_SHA:
        raise ValueError("The independently qualified saved handoff source changed")
    sys.path.insert(0, str(RUNTIME))
    import ds30_0049_saved_crossover as crossover
    import empty_bootstrap as boot

    batch = crossover.batch
    freeze = batch.document(PINS / "frozen-build-geography.json", FREEZE_SHA)
    specification, sources, publication = boot.load_runtime()[1:4]
    book, _, producer_cutoff = batch.load_build(crossover.BUILD, freeze["frozen_build_sha256"])
    if specification["detector_sha256"] != freeze["south_existing_raw"]["stock_detector_sha256"]:
        raise ValueError("The checked stock receiver specification changed")
    return freeze, book, producer_cutoff, specification, sources, publication, crossover


def inputs(freeze, producer_cutoff, batch):
    from empty_bootstrap import bind_native
    from leo.contracts.algo08_region import Algo08Region

    saved = freeze["proposed_saved_pair"]
    archive = Path(saved["causal_archive_root"])
    body = Path(saved["packets"]["integrated"]["path"])
    origin = body.parents[3]
    seal = batch.document(origin / "prediction-seal.json", freeze["south_existing_raw"]["containing_prediction_seal_sha256"])
    candidate = batch.document(origin / "admission.json", seal["admission.json"])
    raw = batch.document(origin / "candidate/unified-short-bootstrap.json", seal["candidate/unified-short-bootstrap.json"])
    stock = batch.document(NAMED_ORIGIN, NAMED_ORIGIN_SHA)
    recording = Path(candidate["request"]["recording"])
    sys.addaudithook(deny_original(recording, archive))
    authority = dict(recording=str(recording), session_id=saved["session_id"],
                     causal_cutoff_utc_ns=saved["causal_cutoff_utc_ns"], window_count=saved["issued_stereo_visits"],
                     inventory_sha256=batch.tagged(saved["inventory_sha256"]),
                     raw_authority_sha256=batch.tagged(saved["raw_authority_sha256"]))
    roster = batch.tagged(saved["causal_archive_sha256"])
    if (producer_cutoff != saved["portable_producer_cutoff_utc_ns"] or producer_cutoff >= authority["causal_cutoff_utc_ns"]
            or batch.archive_digest(archive, authority["causal_cutoff_utc_ns"]) != roster
            or recording.name != saved["recording_name"]
            or candidate["request"]["manifest_sha256"] != saved["original_manifest_sha256"]
            or raw["raw_acquisitions"] != 1 or raw["verified_handoffs"] != 1 or not stock["qualified"]):
        raise ValueError("The new offers must use the prior authenticated South recording and causal archive")
    inventory = batch.document(Path(saved["inventory_path"]), authority["inventory_sha256"])
    if inventory["window_count"] != authority["window_count"]:
        raise ValueError("The signed inventory changed")
    packets = {}
    for role, value in saved["packets"].items():
        path = Path(value["path"])
        expected = batch.tagged(value["sha256"])
        native = batch.document(path, expected)
        bind_native(native, authority["session_id"], authority["inventory_sha256"], value["recipe_sha256"], expected=expected)
        batch.match_native(authority, native)
        if (len(native["source"]["probes"]) != saved["ordered_probe_rows"]
                or len(native["delivery_clocks"]) != authority["window_count"]
                or native["provenance"]["processed_windows"] != authority["window_count"]):
            raise ValueError("The submitted packet must retain all original offered observations and clocks")
        packets[role] = native
    if (raw["native_sha256"] != batch.tagged(seal[str(body.relative_to(origin))])
            or raw["native_sha256"] != batch.tagged(saved["packets"]["integrated"]["sha256"])
            or stock["named"]["native_sha256"] != batch.tagged(saved["packets"]["installed"]["sha256"])
            or stock["named"]["verified"]["raw_authority"] != authority["raw_authority_sha256"]
            or raw["held_anchor_route"]["choice"]["route"] != "history"
            or any(packets["installed"][k] != packets["integrated"][k] for k in ("clock_anchor", "delivery_clocks"))):
        raise ValueError("The sealed detector prefixes differ from the recorded original acquisitions")
    offers = {name: PINS / item["path"] for name, item in saved["offers"].items()}
    old_offer = batch.document(Path(candidate["request"]["offers"]["containing"]),
                               freeze["south_existing_raw"]["containing_offer_sha256"])
    for name, path in offers.items():
        doc = batch.document(path, saved["offers"][name]["sha256"])
        if (Algo08Region.parse(doc).document() != doc or doc["width_km"] != old_offer["width_km"]
                or doc["screen_center"] != old_offer["screen_center"]):
            raise ValueError("Only the offered search centre may change")
    if offers["containing"].read_bytes() == offers["omitted"].read_bytes():
        raise ValueError("Expected two different region offers")
    return authority, inventory, packets, recording, archive, roster, offers


def charted(publication, spec, sources, args, handoff, authority, inventory, acceleration, crossover):
    import empty_bootstrap as boot
    import exact_named_raw as raw
    from combined_successor_raw_entry import solver_ports
    from integrated_original_entry import HELD_SHA, positive_ports
    from leo.analysis.glrt_frequency_input import frequency_evidence
    from leo.storage.fast_scan import FastScanStore
    from short_graph_guard import prove
    from unified_short_bootstrap import withhold

    if handoff.receiver != HELD_SHA or Path(raw.publish_active.__code__.co_filename) != RUNTIME / "exact_named_raw.py":
        raise ValueError("The charted raw publisher must receive its own authenticated held packet unchanged")
    scan = boot.staged_scanner(sources)
    offer = scan.Algo08Region.parse(read(args.region))
    guard, proof, ports, scientific = boot.empty_reason(handoff.native, frequency_evidence), None, {}, None
    with TemporaryDirectory() as scratch, ExitStack() as stack:
        assets = Path(scratch)
        for name in (*scan.PINS, "native", "projector.so"):
            original = Path(spec["detector"]) if name == "cancellation-factors.so" else boot.RELEASE / "assets" / name
            (assets / name).symlink_to(original)
        scan.PINS["cancellation-factors.so"] = spec["detector_sha256"]
        for name, pin in scan.PINS.items():
            boot.checked(assets / name, pin)
        if guard is None:
            proof = prove(handoff.native, assets, use_time_support=True, use_curvature_extent=True)
            if proof["proven"]:
                guard = "no_active_curvature"
        stack.enter_context(patch.object(FastScanStore, "inventory", crossover.inventory_hook(authority, inventory)))
        if guard is None:
            stack.enter_context(positive_ports(solver_ports, acceleration, ports))
            extent = proof.get("curvature_extent", {})
            receipt, scientific = raw.publish_active(args, publication, spec, handoff, {},
                                                     no_active_curvature_sha256=extent.get("native_sha256"))
        else:
            boot.check_inert_solver_assets(assets)
            receipt = withhold(scan, args, offer, assets, handoff, guard, graph_proof=proof)
    owners = scientific["evidence"]["owner_rows"] if scientific is not None else {}
    return receipt, owners, {"early_proof": proof, "early_withhold": guard, "successor_ports": ports}


def worker(mode, target, *, probe=False):
    if len(os.sched_getaffinity(0)) != 1 or target.exists() or not target.is_absolute():
        raise ValueError("Use one pinned CPU and a fresh local publication directory")
    freeze, book, cutoff, spec, sources, publication, crossover = bootstrap()
    batch = crossover.batch
    authority, inventory, packets, recording, archive, roster, offers = inputs(freeze, cutoff, batch)
    from leo.contracts.algo08_region import Algo08Region
    from legacy_first_map_acceleration import checked_artifacts
    from unified_short_bootstrap import Handoff
    import empty_bootstrap as boot

    signed = book["native"]
    fast = signed["--legacy-first-map-fast"]
    acceleration = checked_artifacts(Path(fast["path"]), batch.tagged(fast["sha256"]))
    if probe:
        from tools import algo08_scan, algo08_position
        import exact_named_raw

        if (Path(algo08_scan.__file__) != boot.PAYLOAD / boot.SCANNER
                or Path(algo08_position.__file__) != boot.PAYLOAD / "tools/algo08_position.py"
                or Path(exact_named_raw.__file__) != RUNTIME / "exact_named_raw.py"):
            raise ValueError("Unexpected scientific imports in the saved process")
        print(json.dumps(dict(source_pins=len(book["sources"]), saved_packets=sorted(packets), causal_roster=roster,
                              modes=freeze["proposed_saved_pair"]["planned_order"], waveform_opened=False)))
        return
    offer_label, role = mode.split(":")
    native = packets[role]
    receiver = native["provenance"]["detector_sha256"].removeprefix("sha256:")
    handoff = Handoff(authority["session_id"], authority["inventory_sha256"], receiver, native)
    portable = signed["--portable-orbit-index"]
    args = SimpleNamespace(output=target, recording=recording, archive=archive, region=offers[offer_label],
                           archive_sha256=roster, history_risk_route=True, cairo_six_sheets=True, cairo_residual_layout=False,
                           portable_orbit_index=Path(portable["path"]), portable_orbit_index_sha256=batch.tagged(portable["sha256"]),
                           portable_orbit_producer_sha256=batch.tagged(book["portable_producer"]["sha256"])[7:])
    if role == "installed":
        receipt, rows, audit = crossover.stock(publication, spec, args, handoff, authority, inventory)
    else:
        receipt, rows, audit = charted(publication, spec, sources, args, handoff, authority, inventory, acceleration, crossover)
    submitted = batch.tagged(freeze["proposed_saved_pair"]["packets"][role]["sha256"])
    batch.checked(crossover.one(target, "fast-scan-automatic-work/*/detections.json"), submitted)
    terminal = batch.document(target / "fast-scan-automatic-work" / receipt["run_id"] / "terminal.json", receipt["terminal_sha256"])
    offered = Algo08Region.parse(read(args.region)).document()
    if (handoff.calls != 1 or receipt["region"] != offered or terminal["region"] != offered
            or terminal["native_sha256"] != submitted or receipt["session_id"] != authority["session_id"]
            or receipt["decision"] not in ("complete", "withheld")):
        raise ValueError("The saved publication must retain the exact signed packet and new offer")
    batch.write(target / "saved-south-worker.json", dict(mode=mode, submitted_native_sha256=submitted, receipt=receipt,
                ordered_owners=rows, audit=audit, waveform_reads=0, verified_handoffs=handoff.calls))


def launch(root, mode):
    freeze = read(PINS / "frozen-build-geography.json")["proposed_saved_pair"]
    order = freeze["planned_order"]
    target = root / mode.replace(":", "-")
    prior = [read(root / (key.replace(":", "-") + ".clock.json")) for key in order[:order.index(mode)]]
    if any(row["exit_code"] != 0 for row in prior) or target.exists() or target.with_suffix(".clock.json").exists():
        raise ValueError("Keep the frozen order and preserve all attempts")
    env = os.environ.copy()
    for name in ("OMP_NUM_THREADS", "OMP_THREAD_LIMIT", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[name] = "1"
    env.update(TMPDIR=str(root / "tmp"), MPLCONFIGDIR=str(root / "fonts"), XDG_CACHE_HOME=str(root / "tmp"))
    command = ["/usr/bin/timeout", "--kill-after=2s", f"{freeze['worker_timeout_s']}s", str(PYTHON), "-IB", str(Path(__file__)), "worker", mode, str(target)]
    before, start = getrusage(RUSAGE_CHILDREN), perf_counter()
    child = subprocess.run(command, env=env, capture_output=True, check=False)
    elapsed, after = perf_counter() - start, getrusage(RUSAGE_CHILDREN)
    target.with_suffix(".stdout").write_bytes(child.stdout)
    target.with_suffix(".stderr").write_bytes(child.stderr)
    record = dict(mode=mode, command=command, elapsed_s=elapsed, exit_code=child.returncode,
                  user_s=after.ru_utime-before.ru_utime, system_s=after.ru_stime-before.ru_stime,
                  input_blocks=after.ru_inblock-before.ru_inblock, major_faults=after.ru_majflt-before.ru_majflt)
    target.with_suffix(".clock.json").write_text(json.dumps(record) + "\n")
    print(json.dumps(record))
    child.check_returncode()


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("probe", "launch", "worker"))
    cli.add_argument("mode", choices=("containing:installed", "containing:integrated", "omitted:integrated", "omitted:installed"))
    cli.add_argument("path", type=Path)
    args = cli.parse_args()
    if args.action == "launch":
        launch(args.path, args.mode)
    else:
        worker(args.mode, args.path, probe=args.action == "probe")


if __name__ == "__main__":
    main()
