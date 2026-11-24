"""Validate the exact raw solver handoff on the already saved physical weak packet."""

import argparse
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
CONTROL = Path("/dev/shm/leo-v3-named-weak-all8-result01")
CONTROL_PINS = {"binding.json": "8cd58402cda6656bd7b15739656de645230b12dd0cf38dc33af721869a62542f",
                "result.json": "f7a55412fe0bf00a105236e636e8b654af7d3f90f166ec9b16bc59104f397ec6"}
RAW_RECEIPT = "33d6cab032ab19f6093d57d6017be32820d479e5e96c082a21b40d4ea75824c0"
FROZEN = {"exact_named_raw.py": "5a03140ae71f62715d26dfe5deff9ac46b7ae0cc9acec20d7b41cb516837a135",
          "history_risk_route.py": "56cef69f9bfeed078e938da61e319e2b8c3a250fa45133907096ac8d0e5272b7",
          "eight_ms_native_receiver.py": "e2d991699dd238df40ab665d199ab891c45145a37a36b193000ede773158e34b"}
SOURCES = (Path(__file__).name, "history-risk-weak-physical-protocol.md", *FROZEN)


def read(path):
    return json.loads(path.read_bytes())


def source_pins():
    from empty_bootstrap import checked

    for name, digest in FROZEN.items():
        checked(HERE/name, digest)
    return {name: sha256((HERE/name).read_bytes()).hexdigest() for name in SOURCES}


def deny_original(event, args):
    if event == "open" and isinstance(args[0], (str, bytes)):
        path = Path(os.path.abspath(os.fsdecode(args[0])))
        if path.is_relative_to("/srv/bulk") or path.is_relative_to("/mnt/qnap01"):
            raise ValueError(f"Saved publication cannot open original backing sources: {path}")


def controls():
    from empty_bootstrap import checked

    job, same = (json.loads(checked(CONTROL/name, sha)) for name, sha in CONTROL_PINS.items())
    named = json.loads(gzip.decompress(checked(HERE/"measurements/raw-0016-best.json.gz", RAW_RECEIPT)))
    req, admission, stock = job["request"], named["admission"], named["original"]["stock"]
    if (not same["exact_science"] or not all(same["output_parity"].values()) or stock["process"]["clock"]["exit_code"]
            or req["archive"]["snapshots_sha256"] != admission["archive"]["sha256"]
            or any(req[name] != admission[name] for name in ("inventory", "offer_sha256", "cutoff_utc_ns", "session", "recording"))
            or req["authority"] != stock["science"]["raw_authority"]
            or req["authority"] != admission["raw_authority"]
            or stock["science"]["receipt"]["region"] != same["terminals"]["exact"]["region"]):
        raise ValueError("Original deployed and same-packet exact references do not share the enrolled physical input")
    return job, same, stock


def validate_selection(native, original, detector, selected, req, expected):
    from leo.contracts.digests import canonical_digest

    if (native["source"]["probes"] != original["source"]["probes"] or selected["choice"]["route"] != "unfiltered"
            or selected["selected"] != 506 or selected["refinement_calls"] or len(native["source"]["probes"]) != 1426
            or selected["native_sha256"] != req["native"] or "sha256:"+detector != req["detector"]
            or canonical_digest(selected["choice"]) != canonical_digest(expected)
            or native["source"]["raw_recording_authority_digest"] != req["authority"]
            or native["clock_anchor"]["before"]["realtime_ns"] != req["cutoff_utc_ns"]):
        raise ValueError("The original held policy must reproduce the complete physical 20/8 ms packet")


def launch(root):
    import empty_bootstrap as boot

    started = boot.now()
    sys.addaudithook(deny_original)
    from eight_ms_south_transfer import environment_for
    from exact_named_raw import staged_path, write
    from portable_orbit_index_trial import local_launcher_tools

    local_launcher_tools()
    from dense_geographic_trial import host
    from eight_ms_native_receiver import prepare
    from exact_named_route import checked_catalogue
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from leo.storage.fast_scan import immutable_json
    from short_graph_guard import prove
    from short_raw_diagnostic import measure
    from weak_all8_combined import acquired

    job, _, stock = controls()
    machine = host()
    req = job["request"]
    staged_path(root.parent)
    for key, pin in (("region", req["offer_sha256"]), ("saved_inventory", req["inventory"][7:]),
                     ("packet", req["native"][7:])):
        boot.checked(staged_path(Path(req[key])), pin)
    archive = Path(req["archive"]["root"])
    _, refs = checked_catalogue(dict(archive=str(archive)), job["catalogue"], TleArchiveReader, canonical_digest)
    res = subprocess.check_output(["fincore", "--json", "--bytes", "-o", "RES,SIZE", *(r.path for r in refs)])
    residency = json.loads(res)["fincore"]
    if len(residency) != len(refs) or any(row["res"] < row["size"] for row in residency):
        raise ValueError("All archived causal bodies must already be resident")

    root.mkdir()
    (root/"tmp").mkdir()
    shutil.copytree(CONTROL/"fonts", root/"fonts")
    scope = boot.now()
    original, raw, _, original_sha = acquired()
    native, recipe, detector, selected = prepare(original, raw["recipe"], req["session"], req["inventory"], root/"held.json")
    validate_selection(native, original, detector, selected, req, job["held_choice"])
    opportunities = canonical_digest([{k: v for k, v in row.items() if k != "candidates"}
                                     for row in original["source"]["probes"]])
    if opportunities != stock["opportunities"]:
        raise ValueError("The true full-20 comparison must cover the original stereo opportunities")
    packet = root/"selected-detections.json"
    immutable_json(packet, native)
    if packet.read_bytes() != Path(req["packet"]).read_bytes() or canonical_digest(recipe) != req["detector"]:
        raise ValueError("Regenerated native bytes differ from the independently published exact 20/8 ms packet")
    selection_time = boot.clock(scope)
    proof = prove(native, boot.RELEASE/"assets", use_time_support=True, use_curvature_extent=True)
    if proof["proven"]:
        raise ValueError("The original raw early gate would bypass this frozen numerical route")
    write(root/"graph-proof.json", proof)
    command = ["/usr/bin/timeout", "--kill-after=2s", "35s", sys.executable, "-IB", __file__, "worker", str(root)]
    write(root/"binding.json", dict(request=req, sources=source_pins(), machine=machine, command=command, original_sha=original_sha,
        selection_sha256=sha256((root/"held.json").read_bytes()).hexdigest(), selected=selected["native_sha256"],
        raw_input_pins=CONTROL_PINS, archive_residency=dict(snapshots=len(refs), bytes=sum(x["size"] for x in residency)),
        selection_time=selection_time, admission=boot.clock(started)))
    result = measure(command, environment_for(root), root/"candidate")
    write(root/"clock.json", result)
    if result["exit_code"]:
        raise RuntimeError(result["stderr_tail"])


def worker(root):
    import empty_bootstrap as boot
    from exact_named_raw import publish_active, write

    sys.addaudithook(deny_original)
    binding = read(root/"binding.json")
    req = binding["request"]
    if binding["sources"] != source_pins() or req != controls()[0]["request"]:
        raise ValueError("Frozen source, authenticated inventory or original operator offer changed")
    _, specification, _, publication, _ = boot.load_runtime()
    from cumulative_grid_projection import saved_inventory_port
    from leo.storage.fast_scan import FastSegmentSource
    from named_constrained_research import deny_waveform
    from raw_cfo_north_trial import native_file
    from unified_short_bootstrap import Handoff

    packet = root/"selected-detections.json"
    native = json.loads(boot.checked(packet, req["native"][7:]))
    boot.checked(Path(req["region"]), req["offer_sha256"])
    selected = json.loads(boot.checked(root/"held.json", binding["selection_sha256"]))
    detector = selected["detector_recipe_sha256"].removeprefix("sha256:")
    boot.bind_native(native, req["session"], req["inventory"], detector, expected=req["native"])
    args = SimpleNamespace(recording=Path(req["recording"]), archive=Path(req["archive"]["root"]),
        archive_sha256=req["archive"]["snapshots_sha256"], region=Path(req["region"]), output=root/"candidate",
        portable_orbit_index=None, portable_orbit_index_sha256=None, portable_orbit_producer_sha256=None,
        history_risk_route=True)
    handoff = Handoff(req["session"], req["inventory"], detector, native)
    with (saved_inventory_port(req | {"receiver": "native-20-8-held-history"}) as inventory,
          patch.object(FastSegmentSource, "windows", deny_waveform)):
        terminal, _ = publish_active(args, publication, specification, handoff)
    if not inventory or handoff.calls != 1 or native_file(args.output).read_bytes() != packet.read_bytes():
        raise ValueError("Expected one real numerical invocation on the exact reconstructed packet")
    write(root/"publication.json", dict(receipt=terminal, waveform_acquisitions=0, verified_handoffs=handoff.calls,
                native_sha256=req["native"], release=boot.BASELINE_PIN))


def score(root):
    import empty_bootstrap as boot
    from eight_ms_held_score import geographic_reference, owner_differences
    from exact_named_raw import ARM_NAMES, write

    sys.addaudithook(deny_original)
    boot.load_runtime()
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from tools.pipeline_eval.scoring import distance_km

    job, same, stock = controls()
    req = job["request"]
    witness, published, clock = (read(root/name) for name in (
        "candidate/exact-named-raw-witness.json", "publication.json", "clock.json"))
    receipt = published["receipt"]
    path, = (root/"candidate").glob("fast-scan-automatic-work/*/terminal.json")
    terminal = read(path)
    ports, observed = witness["ports"], witness["evidence"]
    risk = ports["history_risk"]
    older = same["evidence"]["exact"]["evidence"]
    if (clock["exit_code"] or receipt["decision"] != "complete" or published["waveform_acquisitions"]
            or published["verified_handoffs"] != 1 or canonical_digest(terminal) != receipt["terminal_sha256"]
            or terminal["native_sha256"] != req["native"] or terminal["region"] != stock["science"]["receipt"]["region"]
            or set(terminal["arms"]) != set(ARM_NAMES) or observed["grid"] != 179 or len(observed["images"]) != 8
            or ports["history"]["solves"] != 1 or len(ports["history"]["prepare"]) != 1 or risk["inference_calls"] != 1
            or not risk["boundary_checks"] or any(not x["terminal_only"] for x in risk["boundary_checks"])):
        raise ValueError("The physical publication is incomplete or no longer bound to the original request")
    run_id = receipt["run_id"]
    old_grid = FastStandardAnalysisStore(CONTROL/"exact").position_grid(run_id)
    new_grid = FastStandardAnalysisStore(root/"candidate").position_grid(run_id)
    if canonical_digest(old_grid) != older["sidecars"]["grid"] or canonical_digest(new_grid) != observed["sidecars"]["grid"]:
        raise ValueError("Both full grid documents must match the verified publication")
    truth, reference = geographic_reference("weak")
    parity = dict(terminal=terminal == same["terminals"]["exact"], ordered_owners=observed["owner_rows"] == older["owner_rows"],
        grid=sorted(key for key in old_grid if old_grid[key] != new_grid[key]), path=older["sidecars"]["path"] == observed["sidecars"]["path"],
        figures=[name for name in observed["images"] if older["images"][name] == observed["images"][name]])
    arms = {}
    for arm in ARM_NAMES:
        modes = {"routed": terminal["arms"][arm], "exact_20_8": same["terminals"]["exact"]["arms"][arm],
                 "deployed_full_20": stock["science"]["arms"][arm]}
        arms[arm] = {name: dict(row, error_km=distance_km(truth, row["latlon"])) for name, row in modes.items()}
        arms[arm]["routed"]["owner_rows"] = len(observed["owner_rows"][arm])
        arms[arm]["routed"]["conditional"] = sum(row[2] == "conditional" for row in observed["owner_rows"][arm])
        arms[arm]["deployed_full_20"]["owner_rows"] = stock["owner_counts"][arm]
    write(root/"verified-result.json", dict(clock=clock, physical="DS30-0016", arms=arms, position_reference=reference,
        original_named_raw_clock=stock["process"]["clock"], same_packet_exact_clock=same["clocks"]["exact"], parity=parity,
        owner_changes_vs_same_packet={arm: owner_differences(older["owner_rows"][arm], observed["owner_rows"][arm]) for arm in ARM_NAMES},
        full_20_owner_digests=stock["science"]["owners"], terminal=terminal, route=risk["choice"], scientific=witness))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "worker", "score"))
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    {"launch": launch, "worker": worker, "score": score}[args.action](args.root)
