"""Transfer the current cumulative solver to the first signed rank-one case."""

import argparse
from collections import defaultdict
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter, process_time
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

from prospective_0155_solver import ARMS, DETECTOR, LIBRARIES, ORDER, PINS, ROSTER_SHA, archive_plan, orbit_legends
from prospective_0155_solver import checked, inspect, owner_delta, pinned, verify_sources, worker


CASE = "DS30-0402"
BASE = "3764e3ada"
LOCAL = Path("/tmp/ds30-v2-stage-all-6cdbac")
SIGNED = Path("/srv/bulk/leo-dev/ds30-full-20261121/bindings") / f"{CASE}.json"
SIGNED_SHA = "51380d04295b783b3ae457c0d81d6433dedf27802622595613729423e5941cdd"
INVENTORY_SHA = "85d85bba133cadabd26bc41644ec9a1e39982c93d02325f9321772a73e0598b5"
OFFER_SHA = "2698d6858da0a2d989d8c2185c9e3bbbba20d539988204c1f93a591eb9471236"
ARCHIVE_SHA = "sha256:9cce10b68b932cbc352a7f038441fa3e70077ae10dd3f11d407159c4848a155d"
CUTOFF = 1795130137115422247
PROTOCOL = HERE / "prospective-0402-solver-protocol.md"
SETTINGS = dict(native_sha="8fcd81df6bcbc3129b16b96de2109bf3ad22d2e306c5ccaca9383064f80f5d2c",
                windows=6773, admitted=6761, audit_name="saved-0402-worker.json")
PRIOR = tuple(Path("/dev/shm") / directory for directory in (
    "leo-v3-saved-0155-pair-01", "leo-v3-saved-0160-pair-01", "leo-held-anchor-selected-dense-01",
    "leo-v3-saved-0316-pair-01"))
PREFIX = {
    "DS30-0374": "4e86b8d310d00d263bf39082bd621d102c03188320cbcbdcd099316a8c3410a8",
    "DS30-0008": "b2a0a7b73a245731ae2c21bdb3e44664a402397bb65cad6c42b66c8e2989b919",
    "DS30-0155": "e07989fd71164913cc4c4120f5aa45be3d79881d8d3c148b007d85043eba1b00",
    "DS30-0001": "d4fa0e052fdc2ced8b91b22f9b07caee9e0ee418ace7c3bc2f171bbe1610819b",
    "DS30-0171": "501fb693a829fcbae228e296ca1355476f9eb883e6f35a5900a2024e16bb714b",
    CASE: "76f59609416c956cdc6a90312bb1c1e126f9c697c68053dfe6e181955241fc6e",
}


def enrollment():
    from tools.pipeline_eval.qualification.paired_publication import V3_IDENTITY

    roster = pinned(HERE/"development/stages.json", ROSTER_SHA)["stages"]["16"]["cases"][:len(PREFIX)]
    if [row["case"] for row in roster] != list(PREFIX):
        raise ValueError("The original evaluation order changed")
    named_ranks = {}
    for row in roster:
        case = row["case"]
        pair = pinned(LOCAL/case/"pair.json", PREFIX[case])
        previous = pair["runs"]["candidate"]
        receipt = previous["receipt"]
        if (pair["candidate_specification_digest"] != V3_IDENTITY["frozen_specification"]
                or pair["candidate_specification"]["detector_sha256"] != DETECTOR
                or receipt["decision"] != "complete" or receipt["session_id"] != row["session"]
                or receipt["region"] != row["region"] or previous["raw_authority"] != row["raw_authority"]
                or pair["archive"]["snapshots_sha256"] != row["archive_digest"]):
            raise ValueError("Frozen roster row differs from the named publication")
        named_ranks[case] = receipt["screened_nomination"]["winning_rank"]
    if list(named_ranks.values()) != [0, 0, 0, 0, 0, 1]:
        raise ValueError("Expected the first nonzero named screened winner")

    signed = pinned(SIGNED, SIGNED_SHA)
    binding = signed["case"]
    root = LOCAL / CASE / "candidate"
    location = root / "fast-scan-automatic-work"
    terminal, = location.glob("*/terminal.json")
    native_file, = location.glob("*/detections.json")
    terminal_doc = pinned(terminal, receipt["terminal_sha256"])
    native = pinned(native_file, SETTINGS["native_sha"])
    inventory_file = root / "fast-scan-inputs" / f"{receipt['session_id']}.json"
    manifests = [[str(Path("/srv/bulk")/row["path"]), "sha256:"+row["sha256"]]
                 for row in binding["recording"]["segments"]]
    if (binding["id"] != CASE or binding["session_id"] != receipt["session_id"]
            or binding["raw_authority"] != previous["raw_authority"]
            or signed["orbit_cutoff_ns"] != CUTOFF or native["clock_anchor"]["before"]["realtime_ns"] != CUTOFF
            or native["source"]["probe_ms"] != 20 or native["source"]["input_manifest_sha256"] != "sha256:"+INVENTORY_SHA
            or native["provenance"]["detector_sha256"] != "sha256:"+DETECTOR
            or pair["archive"]["snapshots_sha256"] != ARCHIVE_SHA or receipt["window_count"] != SETTINGS["windows"]
            or receipt["counts"]["processed"] != SETTINGS["admitted"]
            or terminal_doc["native_sha256"] != "sha256:"+SETTINGS["native_sha"]
            or manifests != [[row["path"], row["sha256"]] for row in pair["cache_observation"]["manifests"]]):
        raise ValueError("Signed case is inconsistent with the original 20 ms packet or causal cutoff")
    return dict(case=CASE, named_ranks=named_ranks, roster_sha256=ROSTER_SHA, prefix_sha256=PREFIX,
                original_archive=pair["archive"], session=receipt["session_id"], raw_authority=previous["raw_authority"],
                inventory="sha256:"+INVENTORY_SHA, manifests=manifests, recording=pair["recording"],
                native_input=str(native_file), native_sha256=SETTINGS["native_sha"], offer_input=pair["region"],
                inventory_input=str(inventory_file), offer_sha256=OFFER_SHA, causal_cutoff_utc_ns=CUTOFF,
                signed_case_sha256=SIGNED_SHA), previous


def refs(root):
    from leo.operations.tle_archive import TleArchiveReader

    return TleArchiveReader(root).list_snapshots("space-track")


def bulk_sources(plan):
    unique = {}
    for name, item in plan.items():
        if item["source"] is None:
            unique.setdefault((item["sha256"], item["bytes"]), name)
    if len(unique) > 19 or sum(size for _, size in unique) > 34_002_575:
        raise ValueError("Original snapshot reads exceed the enrolled 19-payload / 34,002,575-byte budget")
    return unique


def preflight(request):
    from leo.contracts.digests import canonical_digest

    source = refs(Path(request["original_archive"]["root"]))
    if (canonical_digest({row.path.name: row.sha256 for row in source}) != ARCHIVE_SHA
            or len(source) != 48 or sum(row.byte_size for row in source) != 85_823_046
            or any(row.collected_utc_ns >= CUTOFF for row in source)):
        raise ValueError("Signed causal snapshot membership, sizes or timestamps changed")
    plan = archive_plan(source, [row for root in PRIOR for row in refs(root/"tle")])
    bulk = bulk_sources(plan)
    return dict(files=plan, prior_paths=[str(root) for root in PRIOR], bulk_unique=len(bulk),
                bulk_bytes=sum(size for _, size in bulk), waveform_calls=0)


def bounded_payload(path, digest, size):
    with path.open("rb") as stream:
        if os.fstat(stream.fileno()).st_size != size:
            raise ValueError(f"Snapshot changed size before reading: {path}")
        contents = stream.read(size)
    if len(contents) != size or sha256(contents).hexdigest() != digest:
        raise ValueError(f"Snapshot did not reproduce its sealed digest: {path}")
    return contents


def materialize(root, request, plan):
    from leo.contracts.digests import canonical_digest
    from prospective_0316_solver import saved_inventory

    source = Path(request["original_archive"]["root"]) / "archive/space-track"
    target = root / "tle/archive/space-track"
    target.mkdir(parents=True)
    bulk = bulk_sources(plan["files"])
    staged, charged = {}, 0
    for name, row in plan["files"].items():
        digest, count = row["sha256"], row["bytes"]
        key = (digest, count)
        destination = target / name
        if key in staged:
            destination.hardlink_to(staged[key])
            continue
        if row["source"] is not None:
            origin = Path(row["source"]).resolve(strict=True)
            if not any(origin.is_relative_to(prior) for prior in PRIOR):
                raise ValueError("Staged orbit payload is outside the approved tmpfs inputs")
        else:
            origin = source / bulk[key]
            charged += count
        destination.write_bytes(bounded_payload(origin, digest, count))
        staged[key] = destination
    census = refs(root / "tle")
    if (charged != plan["bulk_bytes"] or any(row.collected_utc_ns >= CUTOFF for row in census)
            or canonical_digest({row.path.name: row.sha256 for row in census}) != ARCHIVE_SHA
            or any(row.byte_size != plan["files"][row.path.name]["bytes"] for row in census)):
        raise ValueError("Materialized archive has different signed names, sizes or cutoff")
    native, inventory, offer = root/"named-detections.json", root/"inventory.json", root/"operator-offer.json"
    native.write_bytes(checked(Path(request["native_input"]), SETTINGS["native_sha"]))
    inventory.write_bytes(checked(Path(request["inventory_input"]), INVENTORY_SHA))
    saved_inventory(request, inventory)
    offer.write_bytes(checked(Path(request["offer_input"]), OFFER_SHA))
    libraries = {}
    for name, (_, pin) in LIBRARIES.items():
        path = root / f"{name}.so"
        path.write_bytes(checked(PRIOR[1] / path.name, pin))
        libraries[name] = str(path)
    request.update(native_file=str(native), offer_file=str(offer), staged_inventory=str(inventory),
                   local_libraries=libraries, local_archive=dict(root=str(root/"tle"), snapshots_sha256=ARCHIVE_SHA,
                                                                  bytes=sum(row.byte_size for row in census)))
    return charged


def invoke(job, mode, output):
    import unified_short_bootstrap as entry

    original = entry.publish_active

    def configured(args, *values, **options):
        args.direct_residual_figures = True
        args.direct_orbit_figures = True
        return original(args, *values, **options)

    with patch.object(entry, "publish_active", configured):
        worker(job, mode, output, source_pins=PINS, inventory_file=job.parent/"inventory.json", **SETTINGS)


def run(root):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    machine = host()
    verify_sources(checked, PINS)
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Expected fresh private tmpfs output")
    root.mkdir()
    (root/"tmp").mkdir()
    request, _ = enrollment()
    plan = preflight(request)
    write(root/"admission.json", dict(request=request, archive=plan, host=machine,
          io_pressure=Path("/proc/pressure/io").read_text(), source_sha256=PINS,
          protocol_sha256=sha256(PROTOCOL.read_bytes()).hexdigest()))
    start_cpu, start_wall = process_time(), perf_counter()
    charge = materialize(root, request, plan)
    write(root/"stage-clock.json", dict(cpu_s=process_time()-start_cpu, elapsed_s=perf_counter()-start_wall,
                                      verified_original_payload_bytes=charge))
    job = root/"request.json"
    write(job, request)
    env = environment(root)
    env["TMPDIR"] = str(root/"tmp")
    python = RELEASE/"venv/bin/python"
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=20)
    for mode in ORDER:
        output = root/mode
        command = [python, "-IB", __file__, "worker", job, mode, output]
        timing = measure(command, env, output)
        write(root/f"{mode}-clock.json", dict(timing=timing, command=list(map(str, command))))
        if timing["exit_code"]:
            raise RuntimeError(f"The saved {mode} process exit was sealed before evaluation")


def dropped_owner_lanes(native, rows, dropped):
    """Join sealed owner identities to the original receiver lanes and visits."""
    source = native["source"]
    indexed = {}
    for probe in source["probes"]:
        key = f"{source['session_id']}:{probe['receiver_id']}:{probe['valid_start_counter']}"
        indexed["sha256:"+sha256(key.encode()).hexdigest()] = probe
    groups = defaultdict(list)
    missing = set(dropped)
    for identity, norad, role in rows:
        if identity in missing:
            probe = indexed[identity]
            groups[(norad, role, probe["receiver_id"] + 1, probe["channel"], probe["actual_rf_hz"])].append(
                probe["visit_index"])
    return [dict(norad=norad, role=role, receiver=rx, channel=channel, rf_hz=rf,
                 count=len(visits), first_visit=min(visits), last_visit=max(visits))
            for (norad, role, rx, channel, rf), visits in sorted(groups.items())]


def evaluate(root, output):
    from aperture_trial import read, write
    from tools.pipeline_eval.scoring import distance_km
    from triage_bounds import REFERENCE, REFERENCE_SHA256

    request, admission = (read(root/name) for name in ("request.json", "admission.json"))
    archived = pinned(LOCAL/CASE/"pair.json", PREFIX[CASE])["runs"]["candidate"]
    actual = {}
    for mode in ORDER:
        result = root/mode
        timing = read(root/f"{mode}-clock.json")["timing"]
        trace = read(result/SETTINGS["audit_name"])
        if timing["exit_code"]:
            raise ValueError("Both identified processes must have exited successfully")
        actual[mode] = inspect(result, mode, trace["receipt"], timing, request, **SETTINGS)
    stock, cumulative = (actual[mode] for mode in ORDER)
    old = stock["science"]
    if (any(old[key] != archived[key] for key in ("arms", "owners", "reason", "raw_authority", "scientific_digests", "artifacts"))
            or old["receipt"]["terminal_sha256"] != archived["receipt"]["terminal_sha256"]
            or old["receipt"]["screened_nomination"]["winning_rank"] != 1):
        raise ValueError("Saved named v3 did not reproduce the nonzero rank and prior complete witness")
    if not cumulative["worker"]["graph"].get("enabled"):
        raise ValueError("The cumulative exact Graph path did not run")
    section = (cumulative["route_details"] or {}).get("signed", {})
    selection = section.get("selection")
    qualification = {"qualified": selection["qualified"]} if selection and "qualified" in selection else {
        "missing": "The cumulative route did not publish a signed selection qualification"}
    legends = orbit_legends(root/"cumulative", cumulative) if cumulative["figures"] else None
    reference, = (row["reference"] for row in pinned(REFERENCE, REFERENCE_SHA256)["cases"]
                  if row["dataset_label"] == CASE and row["authority_eligible"] and row["sealed_metadata_digests_verified"])
    truth = [reference[key] for key in ("latitude_deg", "longitude_deg")]
    scores = {mode: {arm: dict(horizontal_error_km=distance_km(truth, row["latlon"]) if row["latlon"] else None,
                               rf_rms_hz=row.get("rf_rms_hz")) for arm, row in result["terminal"]["arms"].items()}
              for mode, result in actual.items()}
    owners = {arm: owner_delta(stock["selected_rows"][arm], cumulative["selected_rows"].get(arm, [])) for arm in ARMS}
    native = pinned(Path(request["native_file"]), SETTINGS["native_sha"])
    for arm, delta in owners.items():
        delta["dropped_lanes"] = dropped_owner_lanes(native, stock["selected_rows"][arm], delta["dropped"])
    old_nomination = old["receipt"]["screened_nomination"]
    cold = (cumulative["route_details"] or {}).get("cold", {})
    shared_finalists = (old_nomination["screen_c0_scores"] == cold.get("scores"))
    ranking = dict(named_zero_based=old_nomination["winning_rank"], cumulative_one_based=cold.get("branch"),
                   identical_ordered_finalist_scores=shared_finalists,
                   same_winner=shared_finalists and old_nomination["winning_rank"]+1 == cold.get("branch"))
    process_cpu = stock["process"]["cpu_s"] - cumulative["process"]["cpu_s"]
    solve_cpu = stock["worker"]["solve"]["cpu_s"] - cumulative["worker"]["solve"]["cpu_s"]
    clocks = dict(saved_process_cpu_delta_s=process_cpu, matched_solve_cpu_delta_s=solve_cpu,
                  residual_cpu_delta_s=process_cpu-solve_cpu)
    figure_match = {name: {key: row[key] == cumulative["figures"].get(name, {}).get(key)
                           for key in ("size", "sha256", "rgba_sha256")} for name, row in stock["figures"].items()}
    write(output, dict(case=CASE, base=BASE, timing_driver_commit="ca3a64553", order=ORDER, inputs=request,
                       waveform_calls=0, admission=admission, finalist_ranking=ranking, clocks=clocks,
                       stage_clock=read(root/"stage-clock.json"), scores=scores, runs=actual, owners=owners,
                       cairo_legends=legends, pair_figure_equality=figure_match, signed_qualification=qualification,
                       named_reproduces_historical=True, reference_sha256=REFERENCE_SHA256))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    actions = cli.add_subparsers(dest="action", required=True)
    actions.add_parser("run").add_argument("root", type=Path)
    audit = actions.add_parser("evaluate")
    audit.add_argument("root", type=Path)
    audit.add_argument("output", type=Path)
    child = actions.add_parser("worker")
    child.add_argument("job", type=Path)
    child.add_argument("mode", choices=ORDER)
    child.add_argument("output", type=Path)
    options = cli.parse_args()
    if options.action == "run":
        run(options.root)
    elif options.action == "evaluate":
        evaluate(options.root, options.output)
    else:
        invoke(options.job, options.mode, options.output)
