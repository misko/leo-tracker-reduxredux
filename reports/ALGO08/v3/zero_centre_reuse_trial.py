"""Measure one saved South cold race and its request-local zero-centre reuse."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]

from single_rank_refusal_trial import ColdComplete, checked, forbid_raw, fork_arm, strip_clocks, write


STAGE = Path("/tmp/leo-v3-integrated-south-result02-containing")
RESULT = "01dcc43ce2648c3bc2a243f05f0e797d82fabd9be39cee44356b6228d73b244e"
SEAL = "f94821596f03d0ca1295c725d65f146ad9d0e47d7f36744a13d7e7638323dce8"
ORDER = "ordinary", "fixed"


def compare(pair, prior):
    ordinary, candidate = (pair[mode] for mode in ORDER)
    fields = (
        "calls", "prepared_geometry_sha256", "winner", "endpoint", "reference", "finalist_evidence",
        "checkpoint", "tracked_owner_signature",
    )
    exact = {k: ordinary[k] == candidate[k] for k in fields}
    history = prior["lean_attempts"][0]["cold"]
    old_scout = strip_clocks(prior["two_centre_rank"])
    for arm in (ordinary, candidate):
        scout = strip_clocks({k: v for k, v in arm["scopes"]["two_centre_rank"].items() if k != "zero_centre"})
        if (scout != old_scout or arm["finalist_evidence"] != strip_clocks(history) or len(arm["calls"]) != 2
                or arm["scopes"]["nomination_handoff"]["prefixes_captured"] != 2 or len(arm["checkpoint"]) != 2):
            raise ValueError("The two-centre rejection, ordinary retry or original cold finalists changed")
    memo = candidate["scopes"]["two_centre_rank"]["zero_centre"]
    return dict(exact=exact, qualified=all(exact.values()) and memo.get("reused") == 1, memo=memo,
                cold_cpu_saving_ns=ordinary["clock"]["cpu_ns"]-candidate["clock"]["cpu_ns"])


def inputs():
    from empty_bootstrap import bind_native
    from exact_named_raw import staged_path
    from leo.operations.tle_archive import TleArchiveReader

    scored = checked(STAGE/"result.json", RESULT)
    seal = checked(STAGE/"prediction-seal.json", SEAL)
    book = checked(STAGE/"admission.json", seal["admission.json"])
    request = book["request"]
    packet, = (STAGE/name for name in seal if name.endswith("/detections.json"))
    inventory, = (STAGE/name for name in seal if "/fast-scan-inputs/" in name)
    checked(inventory, seal[str(inventory.relative_to(STAGE))])
    pin = scored["receiver"]["native_sha256"]
    native = checked(packet, pin)
    receiver = native["provenance"]["detector_sha256"][7:]
    bind_native(native, request["session"], request["inventory"], receiver, expected=pin)
    offer = checked(Path(request["offers"]["containing"]), request["offer_sha256"]["containing"])
    archive = staged_path(Path(request["archive"]["root"]))
    refs = TleArchiveReader(archive).list_snapshots("space-track")
    portable = Path(book["portable"][0])
    paths = [packet, inventory, portable, portable.parent/"artifact-bind.json", *(ref.path for ref in refs)]
    for path in paths:
        staged_path(path)
    pages = json.loads(subprocess.check_output(["fincore", "--json", "--bytes", "-o", "RES,SIZE,FILE", *paths]))["fincore"]
    if (len(pages) != len(paths) or any(row["res"] < row["size"] for row in pages)
            or not scored["qualified"] or book["mode"] != "containing" or len(refs) != 29
            or len(native["source"]["probes"]) != 2400 or native["provenance"]["window_count"] != 1200
            or native["source"]["raw_recording_authority_digest"] != request["authority"]
            or native["clock_anchor"]["before"]["realtime_ns"] != request["cutoff_utc_ns"]):
        raise ValueError("Expected the sealed South signed detections, offered region and resident causal inputs")
    return book, native, receiver, inventory, offer, scored, pages


def run(root):
    from empty_bootstrap import PAYLOAD, load_runtime

    _, specification, _, publication, _ = load_runtime()
    from tools import algo08_position, algo08_scan
    from combined_successor_raw_entry import solver_ports
    from cumulative_grid_projection import saved_inventory_port
    from dense_geographic_trial import host
    import exact_named_raw as raw
    from legacy_first_map_acceleration import checked_artifacts
    from legacy_first_map_entry import parser
    from named_constrained_research import deny_waveform
    import nomination_handoff as nomination
    import single_rank_refusal as refusal
    from unified_short_bootstrap import Handoff
    from leo.storage.fast_scan import FastSegmentSource
    from two_centre_seeds import elapsed, now
    from zero_centre_reuse import zero_centre_reuse

    if any(Path(module.__file__).resolve() != PAYLOAD/"tools"/f"algo08_{name}.py"
           for name, module in (("position", algo08_position), ("scan", algo08_scan))):
        raise ValueError("The released scanner and solver must bind first")
    sys.addaudithook(forbid_raw)
    book, native, receiver, inventory, offer, scored, pages = inputs()
    request = book["request"]
    argv = book["command"]
    if Path(argv[5]).name != "integrated_original_entry.py" or argv[6] != "--recording":
        raise ValueError("Require the exact qualified South original-file command")
    options = list(argv[6:])
    options.remove("--sparse8-primary")   # The signed saved packet supplies that receiver, without a callback.
    options[options.index("--output")+1] = str(root/"cold-input")
    args = parser().parse_args(options)
    libraries = checked_artifacts(args.legacy_first_map_fast, args.legacy_first_map_fast_sha256)
    handoff = Handoff(request["session"], request["inventory"], receiver, native)
    saved = dict(recording=str(args.recording), saved_inventory=str(inventory), session=handoff.session,
                 inventory=handoff.inventory, receiver="authenticated-sparse-20-8")
    raw.staged_path(root.parent)
    machine = host()
    root.mkdir(mode=0o700)
    pair, preparation = {}, {}
    start = now()
    original_factory = nomination.capture_race

    def observe(race, ready):
        original = race.refine

        def test(mode, prepared, region, bound):
            if (mode != "race" or pair or prepared["sky"]["metadata"]["cutoff_utc_ns"] != request["cutoff_utc_ns"]
                    or list(region.center) != offer["center"] or region.width_km != offer["width_km"]):
                raise ValueError("Expected one full original cold stage with the fixed offer")
            preparation.update(clock=elapsed(start), geometry=nomination.numerical_inputs(prepared).hex())
            for label in ORDER:
                pair[label] = fork_arm(root/(label+".json"), original_factory, race, original, ready, prepared,
                                       region, bound, mode, label, preparation["geometry"])
            raise ColdComplete

        return test

    try:
        with (patch.object(nomination, "capture_race", observe), patch.object(FastSegmentSource, "windows", deny_waveform),
              patch.object(refusal, "single_rank_refusal", zero_centre_reuse),
              saved_inventory_port(saved), solver_ports(libraries, {})):
            raw.publish_active(args, publication, specification, handoff)
    except ColdComplete:
        if set(pair) != set(ORDER) or handoff.calls != 1:
            raise ValueError("The measured original handoff did not reach both cold comparisons")
    else:
        raise ValueError("The worker continued beyond the cold race")
    if any(root.rglob("terminal.json")) or any(root.rglob("*.png")):
        raise ValueError("The cold study may produce no final fit or figures")
    prior = scored["witness"]["ports"]["history_risk"]
    write(root/"result.json", dict(compare(pair, prior), order=ORDER, pair=pair, preparation=preparation, machine=machine,
          waveform_reads=0, saved_input_pin=scored["receiver"]["native_sha256"], input_seal=SEAL, stage_result_pin=RESULT,
          causal=request["archive"], cutoff=request["cutoff_utc_ns"], offer=offer, passive_residency=pages,
          sources={name: sha256((HERE/name).read_bytes()).hexdigest() for name in (
              Path(__file__).name, "zero_centre_reuse.py", "zero-centre-reuse-protocol.md", "two_centre_seeds.py",
              "single_rank_refusal_trial.py", "combined_successor.py", "nomination_handoff.py")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--admission-only", action="store_true")
    args = parser.parse_args()
    if args.admission_only:
        sys.addaudithook(forbid_raw)
        book, native, _, _, _, _, pages = inputs()
        print(json.dumps(dict(issued=native["provenance"]["window_count"], checked=len(pages), offer=book["mode"])))
    else:
        run(args.root)
