"""Stress the exact named publication on one sealed South near-omitted offer."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
MODE = "near-omitted"
INPUT = Path("/dev/shm/leo-v3-eight-ms-south-result01")
INPUT_PINS = {"binding.json": "c68bb6474204d10365a3080dcf55e95c4864bcc7ff7503e459dadddb8809bf9c",
              "seal.json": "b1dbe1ee71fb7dcb63ced474b7aa13e7877db2a801149899de3b3c4da17581fc"}
PACKET = "sha256:f0982e61080ddff6ff98ba4215dff03c12eb1260e19b5cbd23bea711724487a9"
SOURCES = (Path(__file__).name, "exact-named-south-omitted-protocol.md", "exact_named_raw.py",
           "exact_named_route.py", "unified_short_bootstrap.py")


def freeze():
    from empty_bootstrap import checked
    from eight_ms_south_transfer import NAMED_RECEIPT, NAMED_RECEIPT_SHA, pin

    binding, acquisition = (json.loads(checked(INPUT/name, digest)) for name, digest in INPUT_PINS.items())
    req = binding["request"]
    offer = Path(req["offers"][MODE])
    checked(offer, req["offer_sha256"][MODE])
    checked(Path(req["saved_inventory"]), req["inventory"][7:])
    checked(NAMED_RECEIPT/"result.json", NAMED_RECEIPT_SHA)
    if (acquisition["binding_sha256"] != INPUT_PINS["binding.json"]
            or acquisition["raw"]["native_sha256"] != PACKET or acquisition["clock"]["exit_code"] != 0):
        raise ValueError("Require the verified, complete original 20/8 ms acquisition")
    selected = binding["command"]
    portable = {flag.replace("-", "_"): selected[selected.index("--"+flag)+1] for flag in (
        "portable-orbit-index", "portable-orbit-index-sha256", "portable-orbit-producer-sha256")}
    return dict(request=req, input_pins=INPUT_PINS, packet=acquisition["packet"], native_sha256=PACKET,
                portable=portable, sources={name: pin(HERE/name) for name in SOURCES},
                comparator=dict(path=str(NAMED_RECEIPT/"result.json"), sha256=NAMED_RECEIPT_SHA))


def observe_boundary(inspect, audit):
    def observed(endpoints, width_km, score, **options):
        decision = inspect(endpoints, width_km, score, **options)
        coordinates = {arm: [float(x) for x in point] if point is not None else None
                       for arm, point in endpoints.items()}
        audit.append(dict(width_km=width_km, endpoints_east_north_km=coordinates, **decision))
        return decision

    return observed


def recover_science(root):
    """Finish an ndarray audit failure from the terminal, exact path and partial receipt."""
    from empty_bootstrap import load_runtime
    from exact_named_raw import write
    from exact_named_raw_transfer import read

    load_runtime()
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from tools.pipeline_eval.variants.experimental.regional_bound_guard import bound_arms

    partial = root/"scientific-seal.json"
    measured = read(root/"clock.json")["clock"]
    data = partial.read_text()
    prefix = '{\n  "result": '
    if (measured["exit_code"] != 1 or "ndarray is not JSON serializable" not in measured["stderr_tail"]
            or not data.startswith(prefix)):
        raise ValueError("Expected the documented post-publication serialization failure")
    publication, end = json.JSONDecoder().raw_decode(data[len(prefix):])
    if '\n  "boundary": [\n' not in data[len(prefix)+end:] or publication["decision"] != "complete":
        raise ValueError("The original boundary observer must have returned during a complete publication")
    output = root/"candidate"
    witness = read(output/"exact-named-raw-witness.json")
    history = witness["ports"]["history"]
    store = FastStandardAnalysisStore(output)
    detail, path = store.detail(publication["run_id"]), store.position_path(publication["run_id"])
    terminal, = output.glob("fast-scan-automatic-work/*/terminal.json")
    native, = output.glob("fast-scan-automatic-work/*/detections.json")
    if (detail != witness["evidence"]["detail"] or detail["input_sha256"] != PACKET
            or canonical_digest(read(terminal)) != publication["terminal_sha256"]
            or "sha256:"+sha256(native.read_bytes()).hexdigest() != PACKET
            or canonical_digest(path) != witness["evidence"]["sidecars"]["path"]
            or witness["timing"]["solve"] == [] or history["solves"] != 1 or history["exterior_proof"]
            or len(path["stages"]) != 1):
        raise ValueError("The installed path or terminal no longer supports the audited result")
    width = path["box_width_km"]
    endpoints = {arm: row["endpoint"] for arm, row in path["stages"][0]["arms"].items()}
    if bound_arms(endpoints, width) != []:
        raise ValueError("The path must preserve both unconstrained optimizer endpoints")
    boundary = dict(width_km=width, endpoints_east_north_km=endpoints,
                    bound_arms=[], evaluated=False, would_withhold=False)
    write(root/"recovered-seal.json", dict(result=publication, boundary=[boundary], native_sha256=PACKET,
          waveform_calls=0, handoffs=1, recovery="bind original position path and no-call exterior port",
          original_partial_sha256=sha256(data.encode()).hexdigest()))


def worker(root):
    from empty_bootstrap import load_runtime
    from exact_named_raw import deny_backing, publish_active, staged_path, write
    from exact_named_raw_transfer import read

    binding = read(root/"binding.json")
    if binding != freeze():
        raise ValueError("The prespecified South input or source changed")
    _, specification, _, publication, _ = load_runtime()
    from cumulative_grid_projection import saved_inventory_port
    from eight_ms_south_transfer import native_probe
    from leo.storage.fast_scan import FastSegmentSource
    from named_constrained_research import deny_waveform
    from raw_cfo_north_trial import native_file
    from tools.pipeline_eval.variants.experimental import regional_bound_guard
    from unified_short_bootstrap import Handoff

    req = binding["request"]
    packet, native, raw = native_probe(INPUT, req)
    if str(packet) != binding["packet"] or raw["native_sha256"] != PACKET:
        raise ValueError("The saved publication must use the exact sealed 20/8 ms packet")
    recording, archive = Path(req["recording"]), staged_path(Path(req["archive"]["root"]))

    def prohibit_recording(event, values):
        if event == "open" and isinstance(values[0], (str, bytes)):
            file = Path(os.fsdecode(values[0])).resolve()
            if file.is_relative_to(recording):
                deny_waveform()

    sys.addaudithook(deny_backing(recording))
    sys.addaudithook(prohibit_recording)
    options = dict(binding["portable"], portable_orbit_index=Path(binding["portable"]["portable_orbit_index"]))
    args = SimpleNamespace(recording=recording, archive=archive, archive_sha256=req["archive"]["snapshots_sha256"],
                           region=Path(req["offers"][MODE]), output=root/"candidate", **options)
    handoff = Handoff(req["session"], req["inventory"], raw["detector_recipe_sha256"][7:], native)
    boundary = []
    observe = observe_boundary(regional_bound_guard.inspect_boundary, boundary)
    with (saved_inventory_port(req | {"receiver": "native-20-8-held-history"}) as inventory,
          patch.object(FastSegmentSource, "windows", deny_waveform),
          patch.object(regional_bound_guard, "inspect_boundary", observe)):
        result, _ = publish_active(args, publication, specification, handoff)
    if not inventory or handoff.calls != 1 or native_file(args.output).read_bytes() != packet.read_bytes():
        raise ValueError("Expected one saved handoff and the identical published native bytes")
    write(root/"scientific-seal.json", dict(result=result, boundary=boundary, native_sha256=PACKET,
                waveform_calls=0, handoffs=handoff.calls))


def launch(root):
    from dense_geographic_trial import host
    from eight_ms_south_transfer import environment_for
    from exact_named_raw import staged_path, write
    from portable_orbit_index_trial import local_launcher_tools

    local_launcher_tools()
    from short_raw_diagnostic import measure

    machine = host()
    staged_path(root.parent)
    binding = freeze()
    root.mkdir()
    (root/"tmp").mkdir()
    shutil.copytree(INPUT/"fonts", root/"fonts")
    args = ["/usr/bin/timeout", "--kill-after=2s", "45s", sys.executable, "-IB", __file__, "worker", str(root)]
    write(root/"binding.json", binding)
    timing = measure(args, environment_for(root), root/"candidate")
    write(root/"clock.json", dict(clock=timing, machine=machine, command=args))
    if timing["exit_code"]:
        raise ValueError(timing["stderr_tail"])


def score(root):
    from empty_bootstrap import checked, load_runtime
    from eight_ms_south_transfer import ARM_NAMES, KEY_SHA, geographic_status, pin
    from exact_named_raw import write
    from exact_named_raw_transfer import read

    load_runtime()
    from leo.contracts.algo08_region import Algo08Region
    from tools.pipeline_eval import qualification

    qualification.__path__.append(str(HERE.parents[2]/"tools/pipeline_eval/qualification"))
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km
    from tools.pipeline_eval.scoring import distance_km

    binding = read(root/"binding.json")
    measured = read(root/"clock.json")
    recovery = measured["clock"]["exit_code"] != 0
    seal_path = root/("recovered-seal.json" if recovery else "scientific-seal.json")
    sealed = read(seal_path)
    req, old = binding["request"], binding["comparator"]
    named = json.loads(checked(Path(old["path"]), old["sha256"]))["cases"][MODE]
    reference = json.loads(checked(HERE.parent/"regional-release/scoring-key.json", KEY_SHA))
    (truth,) = {tuple(row["truth"]) for row in reference["answers"].values()
                if row["recording"] == Path(req["recording"]).name}
    offer = Algo08Region.parse(json.loads(checked(Path(req["offers"][MODE]), req["offer_sha256"][MODE]))).document()
    published = sealed["result"]
    witness = read(root/"candidate/exact-named-raw-witness.json")
    terminal_path, = (root/"candidate").glob("fast-scan-automatic-work/*/terminal.json")
    terminal = read(terminal_path)
    verified = witness["evidence"]
    named_arms = named["historical_named"]["arms"]
    clearance = face_clearance_km(offer, truth)
    if (recovery and sealed.get("recovery") != "bind original position path and no-call exterior port"
            or sealed["waveform_calls"] or sealed["handoffs"] != 1
            or sealed["native_sha256"] != PACKET or abs(clearance+.100) > 1e-9
            or any(doc != offer for doc in (published["region"], verified["detail"]["region"], named["historical_named"]["offer"]))
            or named["named_status"] != "false_fix"):
        raise ValueError("The control, candidate and enrolled signed South omission differ")
    fixed = published["decision"] == "complete"
    if fixed and (set(verified["detail"]["arms"]) != set(ARM_NAMES) or len(verified["images"]) != 8
                  or verified["grid"] != 137 or not verified["sidecars"]):
        raise ValueError("Expected original grid, both arms and eight standard figures")
    arms = {}
    for arm in ARM_NAMES:
        candidate = terminal["arms"][arm]
        rows = {}
        for name, (latlon, rf) in (("candidate", (candidate["latlon"], candidate.get("rf_rms_hz"))),
                                  ("named", (named_arms[arm]["latlon"], named_arms[arm]["rf_rms_hz"]))):
            rows[name] = dict(position=latlon, rf_rms_hz=rf, error_km=distance_km(truth, latlon),
                              face_inward_km=face_clearance_km(offer, latlon) if latlon else None)
        rows["candidate"]["plot_residual_rms_hz"] = verified["detail"]["arms"].get(arm, {}).get("residual_rms_hz")
        arms[arm] = rows
    write(root/"result.json", dict(offer=offer, truth_face_inward_km=clearance, reference_sha256=KEY_SHA,
        candidate_status=geographic_status(clearance, published["decision"]), named_status=named["named_status"],
        named_control=named["historical_named"], arms=arms, measured=measured, candidate_geometry=sealed["boundary"],
        observations_published=verified["owner_rows"], fallback_status=sealed.get("recovery"),
        candidate_witness=witness, seal_sha256=pin(seal_path)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "worker", "recover", "score"))
    parser.add_argument("root", type=Path)
    opts = parser.parse_args()
    {"launch": launch, "worker": worker, "recover": recover_science, "score": score}[opts.action](opts.root)
