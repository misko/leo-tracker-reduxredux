"""Measure exact preparation of the sealed raw weak-fix handoff, without RF."""

import argparse
from collections import Counter
from contextlib import ExitStack, contextmanager
from hashlib import sha256
from importlib import import_module
import json
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]
RAW = Path("/dev/shm/leo-v3-history-risk-0016-cairo-result01")
ADMISSION = "7764306f4b15a7de036098b904eefcef44ba15bbdf169ac7fb60183873a38b5c"
WITNESS = "a0290938a29ff2fd7419a7ba6ceb3302402250a074211c443c29661434440455"
ORDERS = (("cold", "retain", "portable"), ("portable", "retain", "cold"))


def job():
    from empty_bootstrap import bind_native, checked
    from exact_named_raw import staged_path, portable_binding
    from combined_raw_trial import PRODUCER

    req = json.loads(checked(staged_path(RAW/"admission.json"), ADMISSION))["request"]
    witness = json.loads(checked(staged_path(RAW/"candidate/exact-named-raw-witness.json"), WITNESS))
    (file,) = (RAW/"candidate/fast-scan-automatic-work").glob("*/detections.json")
    native = json.loads(checked(staged_path(file), req["native"][7:]))
    bind_native(native, req["session"], req["inventory"], req["detector"][7:], expected=req["native"])
    if (native["clock_anchor"]["before"]["realtime_ns"] != req["cutoff_utc_ns"]
            or native["source"]["raw_recording_authority_digest"] != req["authority"]
            or witness["solver_recipe"]["orbit_index"] != "cold"):
        raise ValueError("The original physical saved handoff changed")
    possible = SimpleNamespace(portable_orbit_index=PRODUCER.file, portable_orbit_index_sha256=PRODUCER.sha256,
                               portable_orbit_producer_sha256=PRODUCER.producer_sha256)
    portable_binding(possible, req["cutoff_utc_ns"])
    return req, native, witness, PRODUCER


def setup_catalogue(req):
    from exact_named_route import checked_catalogue, resident_path
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader

    bound = {"archive": req["archive"]["root"]}
    details = dict(local_archive=dict(snapshots=46, bytes=82_259_111), original_archive=req["archive"],
                   causal_cutoff_utc_ns=req["cutoff_utc_ns"])
    return checked_catalogue(bound, details, TleArchiveReader, canonical_digest, resident=resident_path)


def prepare(mode, native, req, archive, refs, producer, offer, assets):
    import empty_bootstrap as boot
    from combined_raw_research import portable_factory
    from exact_graph_execution import graph_execution
    from held_adaptive_0160 import catalogue_scope
    from historical_orbit_index import fingerprint, guarded_preparation, TRACK_PIN
    from leo.analysis.localization_v3 import orbits
    from leo.application import localization_v3
    from leo.operations.tle_archive import TleArchiveReader
    from portable_orbit_index_trial import observed
    from sgp4.api import Satrec
    from tools import algo08_position
    from tools.pipeline_eval.variants import algo08_causal_reuse
    from validated_satrec_reuse import ScanElements

    archive_bytes, audit, pieces = Counter(), {}, {part: {} for part in ("verify", "strict_records", "bank", "forecast")}
    read = catalogue_scope(archive, refs, req["cutoff_utc_ns"], TleArchiveReader.read, archive_bytes)
    retained = ScanElements(Satrec.twoline2rv) if mode == "retain" else None
    options = {} if retained is None else dict(index_factory=retained.index_factory(), element_scope=retained.scope)
    if mode == "portable":
        parser = algo08_causal_reuse.parse_element_set_records

        def checked_index():
            # The loader authenticates the C-bound parser's callable identity.
            # Time the work on bodies only, after admission of the sidecar.
            with patch.object(algo08_causal_reuse, "parse_element_set_records", parser):
                index = portable_factory(producer, audit)
            transfer, = audit["transfers"]
            if transfer["compatibility"]["fallback"] or transfer["loading"]["fallback"]:
                raise ValueError(f"The current installed route declined the trusted earlier index: {transfer}")
            return index

        options["index_factory"] = checked_index
    start = boot.now()
    policy = guarded_preparation(algo08_position.prepare_native_scan, audit, **options)
    config = json.loads(boot.checked(assets/"tracks.json", TRACK_PIN))["config"]
    with ExitStack() as stack:
        for module, attribute, measure in ((TleArchiveReader, "read", "verify"),
                (algo08_causal_reuse, "parse_element_set_records", "strict_records"),
                (orbits, "ecef_states", "bank"), (localization_v3, "forecast", "forecast")):
            operation = read if measure == "verify" else getattr(module, attribute)
            stack.enter_context(patch.object(module, attribute, observed(operation, pieces[measure])))
        stack.enter_context(graph_execution(enabled=True))
        prepared = policy(native, TleArchiveReader(archive), algo08_position.TrackConfig(**config),
                          screen_latitude_deg=offer.screen_center[0], screen_longitude_deg=offer.screen_center[1])
    paid = boot.clock(start)
    result = fingerprint(prepared)
    if not audit["attempts"] or any(not case["guard"] or case["fallback"] or case["port"] != "regional" for case in audit["attempts"]):
        raise ValueError("Expected the original installed regional preparation port")
    return dict(science=result, paid=paid, subtasks=pieces, orbit=audit, verified_ledger=dict(archive_bytes),
                retain=None if retained is None else dict(retained.counts, limit=retained.limit))


def worker(mode, offer_kind, output, source_dir):
    import empty_bootstrap as boot
    from validated_satrec_reuse import ORIGINAL_SOURCE, RETENTION_SOURCE

    started = boot.now()
    _, spec, _, publication, startup = boot.load_runtime()
    source = source_dir/"historical_orbit_index.py"
    boot.checked(source, RETENTION_SOURCE if mode == "retain" else ORIGINAL_SOURCE)
    sys.path.insert(0, str(source_dir))
    installed = import_module("historical_orbit_index")
    if Path(installed.__file__) != source:
        raise ValueError("The scoped comparator did not import its pinned source")
    from aperture_trial import write
    from dense_geographic_trial import host
    from exact_named_raw import deny_backing, staged_path
    from tools import algo08_scan

    host()
    request, native, _, producer = job()
    archive, refs = setup_catalogue(request)
    guard = deny_backing(archive)
    sys.addaudithook(guard)
    result = {}

    def analyze(recording, _output, assets, orbit_root, offer):
        if orbit_root != archive or recording != Path(request["recording"]):
            raise ValueError("Expected the exact physical metadata without reading its recording")
        result.update(prepare(mode, native, request, archive, refs, producer, offer, assets))
        return {}

    root = output.parent/output.stem
    root.mkdir()
    original_offer = staged_path(Path(request["region"]))
    offer = original_offer
    if offer_kind == "narrow":
        body = json.loads(boot.checked(original_offer, request["offer_sha256"]))
        body["width_km"] /= 2
        # Shift the independent coarse screen slightly to exercise a different
        # regional roster without using a fitted position.
        body["screen_center"][0] += 0.125
        offer = output.parent/(output.stem+"-offer.json")
        write(offer, body)
    args = SimpleNamespace(recording=Path(request["recording"]), bulk_root=root, archive=archive, region=offer)
    with patch.object(algo08_scan, "analyze", analyze):
        observed = publication.run(args, dict(spec, startup="stock"))
    process = boot.clock(started)
    usage = getrusage(RUSAGE_SELF)
    write(output, dict(result, mode=mode, offer_kind=offer_kind, offer=json.loads(offer.read_bytes()),
          native_sha256=request["native"], archive=request["archive"], cutoff_utc_ns=request["cutoff_utc_ns"],
          applied_tle_validation=observed["tle_records"], startup=startup, measured_before_audit_write=process,
          rss_peak_kib=usage.ru_maxrss, input_blocks=usage.ru_inblock, waveform_reads=0, position_runs=0))


def validate(records):
    for offer_kind in ("original", "narrow"):
        group = [row for row in records if row["offer_kind"] == offer_kind]
        if not group:
            continue
        reference = group[0]
        for row in group:
            if any(row[key] != reference[key] for key in ("science", "verified_ledger", "native_sha256", "archive", "cutoff_utc_ns")):
                raise ValueError("Prepared scientific output or the strict read ledger changed")
    transfers = [row["orbit"].get("transfers", []) for row in records if row["mode"] == "portable"]
    for entries in transfers:
        if len(entries) != 1 or entries[0].get("counts", {}).get("sidecar_hit_bodies") != 19:
            raise ValueError("Unexpected change in earlier index activation")


def launch(root, *, index_replay=False):
    from aperture_trial import RELEASE

    sys.path.extend((str(ROOT/"src"), str(RELEASE/"src")))
    from aperture_trial import write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure
    from validated_satrec_reuse import ORIGINAL_SOURCE, RETENTION_SOURCE, private_source

    machine = host()
    request, _, _, producer = job()
    _, refs = setup_catalogue(request)
    res = json.loads(subprocess.check_output(
        ["fincore", "--json", "--bytes", "-o", "RES,SIZE", *(r.path for r in refs)], text=True))["fincore"]
    if (root.parent.resolve(strict=True) != Path("/dev/shm") or len(res) != len(refs)
            or any(r["res"] < r["size"] for r in res)):
        raise ValueError("Use a new tmpfs study on the fully resident signed archive")
    root.mkdir(mode=0o700)
    (root/"fonts").mkdir()
    verify = {p.name: sha256(p.read_bytes()).hexdigest() for p in (
        Path(__file__), HERE/"historical_orbit_index.py", HERE/"validated_satrec_reuse.py")}
    rows = []
    source = (HERE/"historical_orbit_index.py").read_bytes()
    for variant, payload in (("pristine", source), ("retention", private_source(source))):
        directory = root/variant
        directory.mkdir()
        (directory/"historical_orbit_index.py").write_bytes(payload)
    exposures = [("original", mode) for mode in ("cold", "portable", "portable", "cold")] if index_replay else (
        [("original", mode) for order in ORDERS for mode in order]+[("narrow", "cold"), ("narrow", "retain")])
    write(root/"binding.json", dict(machine=machine, signed=request, source_sha256=verify, order=exposures,
          portable=producer.arguments(), archive_bytes=sum(r["size"] for r in res), untouched_index_sha256=ORIGINAL_SOURCE,
          private_retention_index_sha256=RETENTION_SOURCE))
    for index, (offer, mode) in enumerate(exposures):
        output = root/f"{index}-{offer}-{mode}.json"
        source_dir = root/("retention" if mode == "retain" else "pristine")
        command = [RELEASE/"venv/bin/python", "-IB", __file__, "worker", output, "--mode", mode, "--offer", offer,
                   "--source-dir", source_dir]
        clock = measure(command, environment(root) | {"TMPDIR": str(root)}, output.with_suffix(""))
        write(output.with_suffix(".clock.json"), clock)
        if clock["exit_code"]:
            raise ValueError(f"Preparation worker failed, see {output.with_suffix('.clock.json')}")
        rows.append(json.loads(output.read_bytes()) | {"exit": clock})
    validate(rows)
    write(root/"result.json", dict(verified=True, observations=rows, inputs=verify, waveform_reads=0, position_runs=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("worker", "launch", "index-replay"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--mode", choices=("cold", "retain", "portable"))
    parser.add_argument("--offer", choices=("original", "narrow"), default="original")
    parser.add_argument("--source-dir", type=Path)
    args = parser.parse_args()
    if args.action == "worker":
        if args.source_dir is None:
            parser.error("The worker requires its private pinned source directory")
        worker(args.mode, args.offer, args.output, args.source_dir)
    else:
        launch(args.output, index_replay=args.action == "index-replay")
