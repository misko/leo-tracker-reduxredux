"""One audited pair using the complete existing prepared packed derivatives."""

import argparse
import json
from hashlib import sha256
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from reports.ALGO08.v3 import integrated_packed_cost as costs

READY = (
    (Path("/dev/shm/leo-v3-strict-cairo-0016-result01"), "bf45309c533abb57805c9a5d8167c07e06d24252e815bc0e2dd558e5c0c0f3d7",
     Path("/dev/shm/leo-v3-guarded-selective-0016-stage01/fast8-auto-20261113-112146-b04f5461-1-lower")),
    (Path("/dev/shm/leo-v3-strict-packed-0107-result02"), "f0457bd6ad67e70edc4fda6cc5bd250b7f6e610c5633a953561c3de61e90144a",
     Path("/dev/shm/leo-v3-continued-cfo-0107-pair01/fast8-auto-20261115-002130-7ec6871a-1-upper")),
)
CASES = costs.CASES
REGULAR_MEMBERS = (13, 1)
ORIGINAL_PAGES = (242_675, 8_205)


def registered_root(recording, stage):
    from exact_named_raw import staged_path

    original, known = staged_path(recording), staged_path(stage)
    options = subprocess.check_output(["findmnt", "-n", "-o", "OPTIONS", "-T", recording], text=True).strip()
    if not original.samefile(known) or "ro" not in options.split(","):
        raise ValueError("The original metadata path must be the enrolled read-only tmpfs bind")
    return original


def command(options, output, config, release):
    args = list(options)
    args[args.index("--output")+1] = str(output)
    for flag in ("--legacy-first-map-history", "--legacy-first-map-history-sha256"):
        start = args.index(flag)
        del args[start:start+2]
    args.remove("--verify-original-once")
    args.extend(("--strict-packed-eight", "--packed-ci16-map", config["map"], "--packed-ci16-map-sha256",
                 config["map_sha256"], "--packed-ci16-codec", config["codec"]))
    return ["/usr/bin/timeout", "--kill-after=2s", "75s", str(release / "venv/bin/python"),
            "-IB", str(HERE / "integrated_packed_entry.py"), *args]


def prepare(index, older, previous, output):
    from ci16_packing import Packing
    from empty_bootstrap import RELEASE, checked, clock, now
    from exact_named_raw import staged_path
    from leo.storage.fast_scan import FastScanStore
    from packed_combined_input import member_map
    from seekable_eight_raw import PREFIX
    from seekable_member import open_member
    from visit_frame_raw_0016 import resident

    started = now()
    archive, conversion_pin, stage = READY[index]
    staged_path(archive)
    request = previous["rebound_request"]
    recording = registered_root(Path(request["recording"]), stage)
    session, pin, inventory = FastScanStore(output.parent).inventory(recording, verify_windows=False)
    issued = previous["receiver"]["receipt"]["window_count"]
    if (session, pin, inventory["window_count"]) != (request["session"], request["inventory"], issued):
        raise ValueError("The ordinary preflight changed the signed full logical inventory")
    conversion = json.loads(checked(staged_path(archive / "conversion.json", root=archive), conversion_pin))
    if conversion != older["conversion"] or not conversion["independent_check"]:
        raise ValueError("An independent complete decoded replay must already authenticate this derivative")
    config = conversion["request"]
    map_path = staged_path(Path(config["map"]), root=archive)
    codec_path = staged_path(Path(config["codec"]), root=archive)
    if (map_path, codec_path) != (archive / "conversion/map.json", archive / "packing.so"):
        raise ValueError("Expected the original prepared map and decoder identities")
    byte_map = checked(map_path, config["map_sha256"][7:])
    variable = index == 1
    codec_pin, mapping = member_map(byte_map, strict_eight=True, variable_extents=variable)
    checked(codec_path, codec_pin[7:])
    codec = Packing(codec_path)
    accepted = []
    packed_paths = []
    for section in conversion["sections"]:
        binding = section["binding"]
        key = binding["manifest_sha256"], binding["chunk_index"]
        directory, seek_pin = mapping[key]
        if (directory, seek_pin) != (binding["directory"], binding["seek_sha256"]):
            raise ValueError("Prepared map selects a different signed derivative member")
        path = staged_path(map_path.parent / directory, root=archive)
        with open_member(path, seek_pin, codec=codec, prefix_samples=PREFIX, variable_extents=variable) as source:
            if (source.manifest_sha256 != key[0] or source.chunk.model_dump(mode="json") != section["original"]
                    or source.counts()["payload_bytes"] != 0):
                raise ValueError("Prepared admission must recover original metadata without re-reading encoded samples")
        accepted.append(key)
        packed_paths.extend(staged_path(path / name, root=archive) for name in ("seek.json", "source-index.jsonl",
                          "source-manifest.json", "prefix.ci16p", "tail.ci16p"))
    if len(mapping) != len(accepted) or len(accepted) != REGULAR_MEMBERS[index] or len(set(accepted)) != len(accepted):
        raise ValueError("Derivative must cover every original signed member exactly once")
    original_paths = [staged_path(Path(path), root=recording) for path in previous["admission"]["case_source"]["wavepaths"]]
    original_before, packed_before = resident(original_paths), resident(packed_paths)
    if original_before["cached_pages"] != ORIGINAL_PAGES[index]:
        raise ValueError("Original custody stage cache coverage changed")
    launch_command = command(previous["admission"]["command"][6:], output, config, RELEASE)
    return dict(case=CASES[index], request=request, stage=str(stage), conversion_sha256=conversion_pin,
                source_check=clock(started), packed_before=packed_before, cache_before=original_before,
                packed_paths=list(map(str, packed_paths)), original_paths=list(map(str, original_paths)),
                config=config, issued=issued, command=launch_command)


def normalized(value):
    from leo.application.localization_v3_engine import _json_value

    return json.loads(json.dumps(value, default=_json_value, allow_nan=False))


def score(index, folder, log, book, previous, earlier, older):
    from combined_successor_cairo_trial import require_renderer
    from integrated_original_entry import HELD_SHA
    from integrated_original_trial import terminal
    from legacy_block_raw_score import snapshot as positive
    from legacy_block_0107_score import snapshot as withheld
    from publication_media_checks import image_comparison_fields
    from strict_history_raw_trial import packed_integrity
    from visit_frame_raw_0016 import checked, read

    target = folder / "candidate"
    raw = read(target / "unified-short-bootstrap.json")
    rec = raw["receipt"]
    previous_raws = [record["receiver"] for record in (previous, earlier)]
    native_path, = target.glob("fast-scan-automatic-work/*/detections.json")
    packets = [checked(native_path, record["rebound_request"]["native"]) for record in (previous, earlier)]
    if packets[0] != packets[1] or raw["detector_recipe_sha256"] != "sha256:" + HELD_SHA:
        raise ValueError("Complete sparse native bytes or bound detector changed")
    for prev in previous_raws:
        if any(raw[k] != prev[k] for k in ("native_sha256", "receiver_recipe", "clock_anchor", "graph_proof",
                                           "raw_acquisitions", "verified_handoffs", "route")):
            raise ValueError("The selected signed receiver/graph route changed")
        for field in ("choice", "parent_native_sha256", "observed", "selected", "refinement_calls"):
            if raw["held_anchor_route"][field] != prev["held_anchor_route"][field]:
                raise ValueError("Original held route, zero refinement or signed parent differs")
    effects = raw["receiver_audit"]["native"]
    if any(effects[key] != previous_raws[0]["receiver_audit"]["native"][key]
           for key in ("factors", "native_calls", "streams", "visits", "installed_sha256", "short_primary_sha256")):
        raise ValueError("The actual full/short acquisition schedule changed")
    if any(raw["prefetch"][key] for key in ("submitted", "hits", "fallback")):
        raise ValueError("Strict source must avoid any original waveform worker")
    storage = packed_integrity(raw["packed_ci16_input"], older["conversion"])
    if storage != older["acquire"] or storage["apertures"] != effects["visits"]:
        raise ValueError("The required native packed bytes or demanded apertures changed")
    final = terminal(target, rec)
    if any(rec["terminal_sha256"] != r["receiver"]["receipt"]["terminal_sha256"] for r in (previous, earlier)):
        raise ValueError("Standard terminal differs from the earlier integrated originals")
    engine = read(target / "integrated-packed-solver.json")
    if index == 0:
        producer = previous["admission"]["case_source"]["producer"]
        evidence = normalized(positive(target, log, book["request"], producer, verify_renderer=require_renderer))
        for delivered in (previous["science"], earlier["science"]):
            if any(evidence["published"][key] != delivered["published"][key]
                   for key in ("arms", "owners", "raw_authority", "scientific_digests")):
                raise ValueError("Both calibration arms and exact path/grid evidence must match")
            if (evidence["ordered_owners"] != delivered["ordered_owners"]
                    or evidence["positions"] != delivered["positions"]
                    or image_comparison_fields(evidence["images"]) != image_comparison_fields(delivered["images"])):
                raise ValueError("The full ordered owners, 179-node grid or standard eight images changed")
        witness = read(target / "exact-named-raw-witness.json")
        actual = witness["ports"]["history_risk"]
        expected = previous["witness"]["ports"]["history_risk"]
        rank = actual["two_centre_rank"]
        png = engine["ports"]["png_native"]
        if (actual["boundary_checks"] != expected["boundary_checks"]
                or [attempt["exterior"] for attempt in actual["lean_attempts"]] !=
                   [attempt["exterior"] for attempt in expected["lean_attempts"]]
                or not rank["declined_before_centre_fits"] or rank["paid_centres"] != 0 or "ordinary_retry" not in rank
                or engine["ports"]["grid"]["projection"]["grids"] != 1 or len(engine["ports"]["in_flight"]) != 1
                or len(evidence["images"]) != 8 or (png["native"], png["fallback"]) != (8, 0)):
            raise ValueError("Integrated scientific and media hooks did not execute as frozen")
        if evidence["published"]["arms"] != older["witness"]["science"]["arms"]:
            raise ValueError("Published fixes differ from the sealed physical-reference evaluations")
        physical = older["physical_scores"]
    else:
        evidence = normalized(withheld(target, log["clock"], book["request"]))
        if (engine["ports"] or raw["packed_ci16_input"]["members"][0]["empty_parts"] != 2
                or any(evidence[k] != previous["science"][k] for k in (
                    "terminal", "opportunities", "factors", "receiver_visits", "scan_digest"))):
            raise ValueError("The genuine early withholding or variable-extent packed evidence differs")
        physical = None
    paid = {key: log["clock"][key] + book["source_check"][key] for key in ("elapsed_s", "cpu_s")}
    return dict(qualified=True, native=raw["native_sha256"], terminal=final, science=evidence,
                physical=physical, storage=storage, receipts=raw, solver=engine, paid=paid)


def reverse_required(metrics):
    return min(metrics["summed_speedup"], metrics["paired_median_speedup"]) >= 1.9


def launch(root, first=None, resume=False):
    from aperture_trial import write
    from dense_geographic_trial import host
    from eight_ms_south_transfer import environment_for
    from short_raw_diagnostic import measure
    from visit_frame_raw_0016 import read, resident

    archived = costs.read("integrated-original")["runs"]
    previous, earlier = [[archived[order][case]["result"]["document"] for case in CASES]
                         for order in ("positive_first", "withholding_first")]
    if first is not None:
        proof = read(first / "pair.json")
        if proof["order"] != list(CASES) or not reverse_required(proof["prepared"]):
            raise ValueError("The first qualified ready pair did not authorize reversing order")
    historical = tuple(costs.read("strict-cairo-" + case[5:]) for case in CASES)
    machine = host()
    orders = (0, 1) if first is None else (1, 0)
    sources = {name: sha256((HERE / name).read_bytes()).hexdigest() for name in (
        "integrated_packed_entry.py", "integrated_original_entry.py", "legacy_block_raw_entry.py",
        "integrated-packed-full-protocol.md", "packed_combined_input.py", "seekable_member.py")}
    plan = dict(order=[CASES[i] for i in orders], machine=machine, sources=sources, controls=costs.PINS)
    if resume:
        if plan != read(root / "plan.json"):
            raise ValueError("The launch plan or as-run child sources changed")
    else:
        root.mkdir(mode=0o700)
        for name in ("tmp", "fonts", *CASES):
            (root / name).mkdir()
        for i, case in enumerate(CASES):
            write(root / case / "admission.json", prepare(i, historical[i], previous[i], root / case / "candidate"))
        write(root / "plan.json", plan)
    paid = {}
    for index in orders:
        case = CASES[index]
        folder = root / case
        book = read(folder / "admission.json")
        clock_path, proof_path = folder / "clock.json", folder / "result.json"
        if clock_path.exists():
            log = read(clock_path)
        else:
            if any(folder.glob("candidate*")):
                raise ValueError("A paid process may already have started for this case")
            clock = measure(book["command"], environment_for(root), folder / "candidate")
            log = dict(clock=clock, command=book["command"], cache_before=book["cache_before"],
                       cache_after=resident(list(map(Path, book["original_paths"]))),
                       packed_after=resident(list(map(Path, book["packed_paths"]))))
            write(clock_path, log)
        if (log["clock"]["exit_code"] or log["packed_after"] != book["packed_before"]
                or log["cache_after"] != book["cache_before"] or log["command"] != book["command"]):
            raise ValueError(f"The prepared child or its residency failed for {case}: {log['clock']['stderr_tail']}")
        if proof_path.exists():
            result = read(proof_path)
        else:
            result = score(index, folder, log, book, previous[index], earlier[index], historical[index])
            write(proof_path, result)
        paid[case] = result["paid"]
    fresh = [r["clock"] for r in costs.score()["selected_stock_cases"]]
    prepared = costs.metrics([x["elapsed_s"] for x in fresh], [paid[c]["elapsed_s"] for c in CASES])
    old = {order: [cases[case]["result"]["document"]["process"] for case in CASES]
           for order, cases in archived.items()}
    write(root / "pair.json", dict(order=plan["order"], cases=CASES, paid=paid, machine=machine,
          fresh_stock=fresh, prepared=prepared, current_original=old, reverse_warranted=reverse_required(prepared),
          case_result_sha256={case: sha256((root / case / "result.json").read_bytes()).hexdigest() for case in CASES},
          backing_waveform_bytes=0, conversion_children=0))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    cli.add_argument("--first", type=Path)
    cli.add_argument("--resume", action="store_true", help="Reuse sealed paid launches after an offline scoring issue")
    args = cli.parse_args()
    launch(args.root, args.first, args.resume)
