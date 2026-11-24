"""Complete the missing installed-solver/mixed-receiver cell without reading waveforms."""

import argparse
import fcntl
import json
import os
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
import subprocess
import sys
from time import perf_counter, time_ns
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]
from field_installed_packet_saved import ARMS, BUILD_PIN, CHARTED, PANEL, check, deny_backing, digest, enroll, read, write
from sparse8_cfo_epoch_trial import LOCK, attrs, geography
import signed_cfo_time_readout as signed


CASE = "DS30-0086"
BASE = PANEL/"cases"/CASE
OFF_DIAGONAL = Path("/tmp/leo-v3-field-stock-saved-0086-01/candidate")
PROTOCOL = HERE/"field-receiver-solver-cross-protocol.md"
STOCK_KEY = "6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f"
CHARTED_RECEIPTS = ("915ddc6e1c49e4725bef885ca418e7aff3e4a938464a4c2a9a1e58e14e3d06a9",
                    "5d775bbb9ff01ca9943c8001ed316cd2d65925da8348368452ddd8c0855ae084")
OLDER_WORKER = "36c964fe7e2cf12ed2d322bf85dc52f82f3f67877fbeb929ce35873f63b2bcf5"
OLDER_SCORE = "b6f0afe62a52313dd8b5aaddcbdb1cfb6f1bd14349752ed9bf2929f2ed7bf6f9"


def exact_charted_policy(left, right):
    def policy(witness):
        # The route decision is an output. Its configured options are held.
        recipe = dict(witness["solver_recipe"])
        route = recipe.pop("history_risk")
        return recipe, {k: route[k] for k in ("requested", "optional_prefit_exterior_probe")}, witness["source_sha256"]

    if not left["source_sha256"] or policy(left) != policy(right):
        raise ValueError("Archived charted arms use different configured policies or source bytes")


def contrasts(values):
    a,b,c,d = (values[k] for k in ("installed/full", "installed/mixed", "charted/full", "charted/mixed"))
    if any(x is None for x in (a,b,c,d)):
        return None
    return dict(receiver_under_installed=b-a, receiver_under_charted=d-c,
                solver_on_full=c-a, solver_on_mixed=d-b, interaction=(d-c)-(b-a))


def archived():
    stage, pair, stock, authority, inventory, full = enroll(CASE)
    pub_i, pub_m = (BASE/role/"attempt-000001"/"publication" for role in ("installed", "successor"))
    mix = read(pub_m.parent/"result.json", pair["attempt_result_sha256"]["successor"])
    if (mix["raw_identity"] != authority or any(x["outcome"] != "complete" or x["process"]["exit_code"]
                                               for x in (stock,mix))):
        raise ValueError("Requires both complete signed original cells")
    offer = authority["region_sha256"]
    native, chart_m, _ = signed.qualified_candidate(pub_m, read(pub_m/"unified-short-bootstrap.json"), mix["native_sha256"], offer)
    rows = [signed.opportunities(doc) for doc in (full,native)]
    signed.bind_pair(full, native, *rows)
    check(pub_m/"fast-scan-inputs"/(authority["session_id"]+".json"), authority["inventory_sha256"])
    release = read(pub_i/"algo08v3-release.json")
    raw_launch = read(pub_i.parent/"launch.json")["command"]
    if (release != dict(version="ALGO08v3", frozen_specification="sha256:"+STOCK_KEY, detector_sha256=signed.FULL,
                        session_id=authority["session_id"], decision="complete")
            or raw_launch[0] != "/opt/leo-algo08/algo08v3/run"
            or set(raw_launch[1::2]) != {"--recording", "--region", "--archive", "--bulk-root"}
            or read(pub_m/"algo08v3-successor-release.json")["build_sha256"] != "sha256:"+BUILD_PIN):
        raise ValueError("Actual original publication recipe changed")
    chart_f = read(OFF_DIAGONAL/"exact-named-raw-witness.json", CHARTED_RECEIPTS[0])
    check(pub_m/"exact-named-raw-witness.json", CHARTED_RECEIPTS[1])
    exact_charted_policy(chart_f, chart_m)
    charted = read(OFF_DIAGONAL/"crossover-worker.json", OLDER_WORKER)
    previous = read(HERE/"measurements/field-installed-packet-saved-0086.json", OLDER_SCORE)
    if (charted["waveform_reads"] or charted["verified_handoffs"] != 1
            or chart_f["evidence"]["detail"]["input_sha256"] != stock["native_sha256"]
            or previous["native_sha256"] != stock["native_sha256"] or not previous["qualification"]["qualified"]
            or charted["receipt"]["region"] != stock["evidence"]["receipt"]["region"]):
        raise ValueError("Archived charted/full cell lost scientific provenance")
    return SimpleNamespace(stage=stage, pair=pair, stock=stock, mix=mix, authority=authority, inventory=inventory,
                           native=native, full=full, archived_full=charted, chart_f=chart_f, previous=previous,
                           pubs=(pub_i,pub_m), chart_m=chart_m)


def preflight():
    sys.path[:0] = [str(CHARTED/"reports/ALGO08/v3"), str(CHARTED)]
    import empty_bootstrap as boot
    import integrated_original_batch as batch

    launcher, spec, _, publication, _ = boot.load_runtime()
    from tools import algo08_position, algo08_scan
    from leo.operations.tle_archive import TleArchiveReader
    from unified_short_bootstrap import Handoff
    from visit_frame_raw_0016 import resident

    a = archived()
    if (launcher["FINGERPRINT"] != STOCK_KEY or spec["detector_sha256"] != signed.FULL
            or Path(algo08_scan.__file__).resolve() != boot.PAYLOAD/boot.SCANNER
            or Path(algo08_position.__file__).resolve() != boot.PAYLOAD/"tools/algo08_position.py"):
        raise ValueError("Require the exact released installed backend")
    archive, offer, recording = a.stage/"tle", a.stage/"offer.json", Path(a.authority["recording"])
    args = SimpleNamespace(recording=recording, archive=archive, region=offer)
    batch.validate_case(a.authority, args)
    session, input_sha = a.authority["session_id"], a.authority["inventory_sha256"]
    batch.match_inventory(a.authority, session, input_sha, a.inventory)
    batch.match_native(a.authority, a.native)
    detector = a.native["provenance"]["detector_sha256"][7:]
    boot.bind_native(a.native, session, input_sha, detector, expected=a.mix["native_sha256"])
    paths = [ref.path for ref in TleArchiveReader(archive).list_snapshots("space-track")]
    if (len(paths) != 50 or not archive.is_relative_to("/dev/shm")
            or any(p.resolve(strict=True) != p or not p.is_relative_to(archive) for p in paths)
            or batch.archive_digest(archive, a.authority["causal_cutoff_utc_ns"]) != a.authority["archive_sha256"]):
        raise ValueError("Exact preexisting owner-private causal archive required")
    cache = resident([str(p) for p in paths])
    plan = dict(case=CASE, original_pair=a.pair["attempt_result_sha256"], original_raw=a.authority["raw_authority_sha256"],
                source_sha256=digest(Path(__file__).read_bytes()), protocol_sha256=digest(PROTOCOL.read_bytes()),
                native_sha256=a.mix["native_sha256"], installed_native_sha256=a.stock["native_sha256"], resident=cache,
                solver=STOCK_KEY, released_launcher=boot.BASELINE_PIN, charted_witnesses=CHARTED_RECEIPTS,
                handoff_source=digest(Path(sys.modules[Handoff.__module__].__file__).read_bytes()),
                archived_offdiagonal=OLDER_WORKER, archive_sha256=a.authority["archive_sha256"],
                offer_sha256=a.authority["region_sha256"], waveform_reads=0)
    return a, spec, publication, args, Handoff(session, input_sha, detector, a.native), plan, paths, resident


def worker(root, pin):
    entered = perf_counter()
    a, spec, publication, args, handoff, observed, paths, resident = preflight()
    # Installed entry modules were resolved above before importing study helpers.
    from ds30_0049_saved_crossover import stock
    from leo.storage.fast_scan import FastSegmentSource
    from leo.storage.short_window import ShortWindowReader

    if json.loads(json.dumps(observed)) != read(root/"admission.json", pin):
        raise ValueError("Admission and source bindings changed before launch")
    args.output = root/"cell"

    def raw_denied(*args, **kwargs):
        raise ValueError("Saved fourth cell requested waveform acquisition")

    before = perf_counter()
    with patch.object(FastSegmentSource, "windows", raw_denied), patch.object(ShortWindowReader, "windows", raw_denied):
        receipt, rows, audit = stock(publication, spec, args, handoff, a.authority, a.inventory)
    if (handoff.calls != 1 or resident([str(p) for p in paths]) != observed["resident"]
            or receipt["region"] != a.stock["evidence"]["receipt"]["region"]):
        raise ValueError("Original input or cache left the frozen scope")
    published, = args.output.glob("fast-scan-automatic-work/*/detections.json")
    check(published, a.mix["native_sha256"])
    check(args.output/"fast-scan-inputs"/(a.authority["session_id"]+".json"), a.authority["inventory_sha256"])
    write(args.output/"crossover-worker.json", dict(receipt=receipt, ordered_owners=rows, audit=audit,
          verified_handoffs=handoff.calls, waveform_reads=0, archive=observed["resident"], preamble_s=before-entered))


def launch(root, pin):
    host = attrs(expected_priority="idle")
    check(root/"admission.json", pin)
    with LOCK.open("rb") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Gauss lease active. No numerical worker started.")
            return
        scratch = root/"scratch"
        scratch.mkdir()
        command = [sys.executable, "-IB", str(Path(__file__)), "worker", str(root), "--pin", pin]
        with (root/"stdout").open("x") as out, (root/"stderr").open("x") as err:
            start, began, before = time_ns(), perf_counter(), getrusage(RUSAGE_CHILDREN)
            try:
                status = subprocess.run(command, stdout=out, stderr=err, stdin=subprocess.DEVNULL, timeout=60,
                    env=os.environ | dict(TMPDIR=str(scratch), MPLCONFIGDIR=str(scratch)), check=False).returncode
            except subprocess.TimeoutExpired:
                status = 124
            after, elapsed = getrusage(RUSAGE_CHILDREN), perf_counter()-began
        clock = root/"clock.json"
        write(clock, dict(command=command, cpu_s=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
                          elapsed_s=elapsed, started_ns=start, finished_ns=time_ns(), exit_code=status,
                          input_blocks=after.ru_inblock-before.ru_inblock, major_faults=after.ru_majflt-before.ru_majflt))
        worker_receipt = root/"cell/crossover-worker.json"
        seal = root/"prediction-seal.json"
        write(seal, dict(host=host, clock=digest(clock.read_bytes()), admission=pin,
                         worker=digest(worker_receipt.read_bytes()) if status==0 else None, waveform_reads=0))
        print(digest(seal.read_bytes()))


def score(root, pin):
    a, *_ = preflight()
    from ds30_0049_saved_crossover_score import owner_changes, publication
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from tools.pipeline_eval.scoring import distance_km

    seal = read(root/"prediction-seal.json", pin)
    clock = read(root/"clock.json", seal["clock"])
    result = dict(case=CASE, clock=clock, scientific_cells=3, seal=pin)
    if clock["exit_code"]:
        write(root/"score.json", result | dict(disposition="failed fourth worker"))
        return
    control = root/"cell"
    check(control/"crossover-worker.json", seal["worker"])
    missing = publication(control, a.mix)
    stock, mix = a.stock,a.mix
    charts = [read(OFF_DIAGONAL/"fast-scan-automatic-work"/a.archived_full["receipt"]["run_id"]/"terminal.json",
                   a.archived_full["receipt"]["terminal_sha256"])["arms"], mix["evidence"]["arms"]]
    named = [stock["evidence"]["arms"], missing["terminal"]["arms"]]
    cells = dict(zip(("installed/full", "installed/mixed", "charted/full", "charted/mixed"), named+charts, strict=True))
    georef = geography(CASE)
    arms = {}
    for arm in ARMS:
        errors = {cell: distance_km(georef, values[arm]["latlon"]) for cell,values in cells.items()}
        rf = {cell: values[arm]["rf_rms_hz"] for cell,values in cells.items()}
        all_owned = {}
        for cell, (path, receipt) in zip(cells, ((a.pubs[0],stock["evidence"]["receipt"]), (control,missing["receipt"]),
                                               (OFF_DIAGONAL,a.archived_full["receipt"]), (a.pubs[1],mix["evidence"]["receipt"])), strict=True):
            detail = FastStandardAnalysisStore(path).detail(receipt["run_id"])
            if detail["terminal_sha256"] != receipt["terminal_sha256"]:
                raise ValueError("Report is detached from its archived terminal")
            all_owned[cell] = (detail["arms"][arm]["residual_rms_hz"] if receipt["decision"] == "complete" else None)
        arms[arm] = dict(error_km=errors, conditional_rf_hz=rf, all_owned_rf_hz=all_owned,
                         error_effects_km=contrasts(errors), rf_effects_hz=contrasts(rf))
    if missing["terminal"]["region"] != stock["evidence"]["receipt"]["region"]:
        raise ValueError("Missing cell changed geographic offer")
    write(root/"score.json", result | dict(scientific_cells=4, arms=arms, grid=missing["grid"], path=missing["path"],
        figures=missing["figures"], new_owner_maps=missing["owners"], new_owners=missing["owner_rows"],
        named_mixed=missing["receipt"], named_full_owners=stock["evidence"]["owners"],
        charted_mixed_vs_installed_mixed=owner_changes(missing["owner_rows"],a.chart_m["evidence"]["owner_rows"]),
        charted_full_vs_mixed=owner_changes(a.archived_full["ordered_owners"],a.chart_m["evidence"]["owner_rows"])))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "worker", "launch", "score"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--pin")
    args = parser.parse_args()
    sys.addaudithook(deny_backing)
    if args.action == "prepare":
        if args.root.parent.resolve() != Path("/dev/shm") or args.root.exists():
            parser.error("Use one fresh private tmpfs output root")
        *_, plan, _, _ = preflight()
        args.root.mkdir(mode=0o700)
        write(args.root/"admission.json", plan)
        print(digest((args.root/"admission.json").read_bytes()))
    elif args.pin:
        {"worker":worker, "launch":launch, "score":score}[args.action](args.root, args.pin)
    else:
        parser.error("Pass the sealed preflight or prediction hash")
