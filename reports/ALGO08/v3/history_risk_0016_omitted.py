"""Replay the qualified raw physical 20/8 Cairo packet on the original omitted offer."""

import argparse
from collections import Counter
from contextlib import ExitStack
import gzip
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
CHECKOUT = HERE.parents[2]
sys.path.append(str(CHECKOUT))

from empty_bootstrap import RELEASE, bind_native, checked
from history_risk_weak_physical import deny_original
from named_0016_translated import OFFER_PIN


RAW = Path("/dev/shm/leo-v3-history-risk-0016-cairo-result01")
RAW_SCORE = Path("/dev/shm/leo-v3-history-risk-0016-cairo-score01.json")
RAW_SCORE_PIN = "b340a594fadae0b871c42d31ac269efe2cfe0a34d26089038c739e4bb8822e39"
OFFER = Path("/dev/shm/leo-v3-named-0016-translated-result01/offer.json")
NAMED_OMITTED = "8cc6ecc9354225e24cb597eca039a3d65cf7e7aee842a9c2836f0736d287d76c"
NAMED_OWNER_PIN = "f1ed977ecb8fe2830da578c01e019a84b41d9a2357b016d7c8f61e31f9a77c10"
NAMED_SCORE_PIN = "3f7563a0666512686775a6eed4d2500a6b4b4a7a7513cf4476689b8720fcc62d"
ARMS = ("c0", "fitted_c")


def read(path):
    return json.loads(path.read_bytes())


def pinned_gzip(path, pin):
    body = gzip.decompress(path.read_bytes())
    if sha256(body).hexdigest() != pin:
        raise ValueError(f"The archived comparison changed: {path}")
    return json.loads(body)


def translated_offer(offer):
    return {**offer, **{name: [offer[name][0], offer[name][1]+2.0] for name in ("center", "screen_center")}}


def changed_arguments(command, offer, output):
    argv = command[6:].copy()
    if (Path(command[5]).name != "exact_named_raw.py" or "--history-risk-route" not in argv
            or "--cairo-six-sheets" not in argv or "--strict-packed-eight" in argv or "--portable-orbit-index" in argv):
        raise ValueError("Require the qualified ordinary-input history-risk Cairo command")
    for flag, value in (("--region", offer), ("--output", output)):
        argv[argv.index(flag)+1] = str(value)
    return argv


def input_binding():
    from exact_named_raw import staged_path
    from history_risk_0016_raw import bundle_sha
    from raw_cfo_north_trial import native_file

    containing = json.loads(checked(RAW_SCORE, RAW_SCORE_PIN))
    if not containing["qualified"] or not all(containing["checks"].values()) or containing["optional_process"]["clock"]["exit_code"]:
        raise ValueError("Require the original qualified physical raw Cairo publication")
    seal = json.loads(checked(RAW/"prediction-seal.json", containing["seal_sha256"]))
    admission = json.loads(checked(RAW/"admission.json", seal["admission.json"]))
    if admission != containing["admission"]:
        raise ValueError("Original physical candidate admission changed")
    req = admission["request"]
    packet = staged_path(native_file(RAW/"candidate"), root=RAW)
    inventory = staged_path(RAW/"candidate/fast-scan-inputs"/(req["session"]+".json"), root=RAW)
    if seal[str(packet.relative_to(RAW))] != req["native"][7:] or seal[str(inventory.relative_to(RAW))] != req["inventory"][7:]:
        raise ValueError("Packet and inventory do not bind the qualified raw acquisition")
    board = json.loads(checked(RAW/"candidate/unified-short-bootstrap.json", seal["candidate/unified-short-bootstrap.json"]))
    if (board["raw_acquisitions"] != 1 or board["verified_handoffs"] != 1 or board["graph_proof"]["proven"]
            or board["detector_recipe_sha256"] != req["detector"]):
        raise ValueError("The prior containing run did not exercise the intended raw-to-solver path")
    original_offer = containing["native"]["science"]["receipt"]["region"]
    omitted = json.loads(checked(staged_path(OFFER), OFFER_PIN))
    if translated_offer(original_offer) != omitted:
        raise ValueError("The two-degree-east omitted offer differs from the earlier signed experiment")
    sources = admission["science"] | admission["adapters"] | admission["renderer_sources"]
    bundle_sha(CHECKOUT, sources)
    return dict(request=req, recording=req["recording"], packet=str(packet), saved_inventory=str(inventory),
                raw_command=admission["command"], sources=sources, raw_cairo_score_sha256=RAW_SCORE_PIN,
                containing_offer=original_offer, omitted_offer=omitted, omitted_offer_sha256=OFFER_PIN,
                containing_graph=board["graph_proof"], driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest())


def packet(binding):
    req = binding["request"]
    data = checked(Path(binding["packet"]), req["native"][7:])
    native = json.loads(data)
    bind_native(native, req["session"], req["inventory"], req["detector"][7:], expected=req["native"])
    source, provenance = native["source"], native["provenance"]
    if (source["raw_recording_authority_digest"] != req["authority"]
            or native["clock_anchor"]["before"]["realtime_ns"] != req["cutoff_utc_ns"]
            or provenance["window_count"] != 808 or provenance["processed_windows"] != 713
            or provenance["invalid_capture"] != 95 or len(source["probes"]) != 1426
            or sum(len(probe["candidates"]) for probe in source["probes"]) != 506):
        raise ValueError("The saved 20/8 packet lost original radio or clock authority")
    return data, native


def launch(root):
    from aperture_trial import write
    from dense_geographic_trial import host
    from eight_ms_south_transfer import environment_for
    from exact_named_raw import staged_path
    from leo.operations.tle_archive import TleArchiveReader
    from short_raw_diagnostic import measure
    from tools.pipeline_eval.qualification.paired_publication import archive_identity

    sys.addaudithook(deny_original)
    machine = host()
    staged_path(root.parent)
    binding = input_binding()
    packet(binding)
    req = binding["request"]
    checked(Path(binding["saved_inventory"]), req["inventory"][7:])
    archive = staged_path(Path(req["archive"]["root"]))
    refs = TleArchiveReader(archive).list_snapshots("space-track")
    if (len(refs) != 46 or archive_identity(archive) != req["archive"]
            or any(ref.collected_utc_ns >= req["cutoff_utc_ns"] for ref in refs)):
        raise ValueError("The original 46 causal snapshots changed")
    observed = json.loads(subprocess.check_output(["fincore", "--json", "--bytes", "-o", "RES,SIZE",
                                                    *(staged_path(ref.path, root=archive) for ref in refs)]))["fincore"]
    if len(observed) != len(refs) or any(row["res"] < row["size"] for row in observed):
        raise ValueError("Original causal archive is not entirely resident")
    root.mkdir()
    (root/"tmp").mkdir()
    shutil.copytree(RAW/"fonts", root/"fonts")
    (root/"offer.json").write_bytes(checked(OFFER, OFFER_PIN))
    command = ["/usr/bin/timeout", "--kill-after=2s", "45s", str(RELEASE/"venv/bin/python"), "-IB", __file__, "worker", str(root)]
    write(root/"binding.json", binding | dict(command=command, machine=machine, causal_snapshots=len(refs),
          causal_logical_bytes=sum(row["size"] for row in observed)))
    result = measure(command, environment_for(root), root/"candidate")
    write(root/"clock.json", result)
    from history_risk_0016_raw import roster
    write(root/"prediction-seal.json", roster(root) | {name: sha256((root/name).read_bytes()).hexdigest()
                                                       for name in ("binding.json", "clock.json", "offer.json")})


def worker(root):
    import empty_bootstrap as boot
    from exact_named_raw import parser, publish_active, write
    from history_risk_0016_raw import bundle_sha

    sys.addaudithook(deny_original)
    binding = read(root/"binding.json")
    enrolled = input_binding()
    if any(binding[key] != expected for key, expected in enrolled.items()):
        raise ValueError("The saved worker received a different scientific binding")
    bundle_sha(CHECKOUT, binding["sources"])
    checked(root/"offer.json", OFFER_PIN)
    data, native = packet(binding)
    _, specification, _, publication, _ = boot.load_runtime()
    from cumulative_grid_projection import saved_inventory_port
    from leo.storage.fast_scan import FastScanStore, FastSegmentSource
    from raw_cfo_north_trial import native_file
    from unified_short_bootstrap import Handoff

    args = parser().parse_args(changed_arguments(binding["raw_command"], root/"offer.json", root/"candidate"))
    req = binding["request"]
    handoff = Handoff(req["session"], req["inventory"], req["detector"][7:], native)
    counters = Counter(inventory_calls=0, waveform_attempts=0)

    def blocked(*_args, **_kwargs):
        counters["waveform_attempts"] += 1
        raise ValueError("The geographic audit only admits the original saved packet")

    with ExitStack() as stack:
        saved = stack.enter_context(saved_inventory_port(req | {"saved_inventory": binding["saved_inventory"],
                                                                "receiver": "native-20-8-held-history"}))
        original_inventory = FastScanStore.inventory

        def observed(store, *args, **options):
            counters["inventory_calls"] += 1
            return original_inventory(store, *args, **options)

        stack.enter_context(patch.object(FastScanStore, "inventory", observed))
        stack.enter_context(patch.object(FastSegmentSource, "windows", blocked))
        stack.enter_context(patch.object(FastSegmentSource, "__init__", blocked))
        receipt, _ = publish_active(args, publication, specification, handoff)
    if not saved or handoff.calls != 1 or counters["waveform_attempts"] or native_file(args.output).read_bytes() != data:
        raise ValueError("Expected a single verified handoff and the exact original native publication")
    write(args.output/"saved-omitted-witness.json", dict(receipt=receipt, verified_handoffs=handoff.calls,
          raw_acquisitions=0, waveform_attempts=counters["waveform_attempts"], inventory_calls=counters["inventory_calls"]))


def summarise_owners(before, after):
    from prospective_0316_solver import owner_delta

    return {arm: owner_delta(before[arm], after[arm]) | dict(
            containing_satellites=Counter(str(row[1]) for row in before[arm]),
            omitted_satellites=Counter(str(row[1]) for row in after[arm]),
            containing_roles=Counter(row[2] for row in before[arm]), omitted_roles=Counter(row[2] for row in after[arm]))
            for arm in ARMS}


def score(root, output):
    from aperture_trial import write
    from eight_ms_held_score import geographic_reference
    from history_risk_0016_cairo import active_renderer
    from history_risk_0016_raw import roster
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from raw_0016_best_score import position_sides
    from tools.pipeline_eval.qualification.paired_publication import evidence
    from tools.pipeline_eval.scoring import distance_km
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km

    sys.addaudithook(deny_original)
    binding, clock = (read(root/name) for name in ("binding.json", "clock.json"))
    sealed = root/"prediction-seal.json"
    if read(sealed) != roster(root) | {name: sha256((root/name).read_bytes()).hexdigest()
                                     for name in ("binding.json", "clock.json", "offer.json")}:
        raise ValueError("Results changed before saved provenance and geography checks")
    if clock["exit_code"]:
        write(output, dict(outcome="process_failure", clock=clock, binding=binding))
        return
    enrolled = input_binding()
    if any(binding[key] != value for key, value in enrolled.items()):
        raise ValueError("The finished worker changed its admitted scope")
    raw = json.loads(checked(RAW_SCORE, RAW_SCORE_PIN))
    named = pinned_gzip(HERE/"measurements/named-0016-translated-sealed.json.gz", NAMED_OMITTED)
    named_owners = pinned_gzip(HERE/"measurements/named-0016-translated-owners.json.gz", NAMED_OWNER_PIN)
    named_score = json.loads(checked(HERE/"measurements/named-0016-translated-score.json", NAMED_SCORE_PIN))
    used = root/"candidate"
    port, witness = (read(used/name) for name in ("saved-omitted-witness.json", "exact-named-raw-witness.json"))
    receipt = port["receipt"]
    complete = receipt["decision"] == "complete"
    observed = evidence(used, receipt, clock["started_unix_ns"], read_only=True)
    product = artifacts(used, receipt)
    result = witness["evidence"]
    req = binding["request"]
    if (port["raw_acquisitions"] or port["waveform_attempts"] or port["verified_handoffs"] != 1
            or result["detail"]["input_sha256"] != req["native"] or observed["raw_authority"] != req["authority"]
            or receipt["counts"] != dict(processed=713, invalid_capture=95, skipped_fast_score=0)
            or receipt["region"] != named["science"]["receipt"]["region"] or receipt["region"] != binding["omitted_offer"]
            or named_score["sealed_sha256"] != NAMED_OMITTED or named_owners["sealed_sha256"] != NAMED_OMITTED
            or set(observed["arms"]) != set(ARMS)):
        raise ValueError("Position publication does not bind the identical original, omitted offer and both c arms")
    store = FastStandardAnalysisStore(used)
    sidecars = position_sides(store, receipt, product, expected_points=None) if complete else None
    owners = result["owner_rows"] if complete else {arm: [] for arm in ARMS}
    if complete:
        if (len(product["images"]) != 8 or not active_renderer(witness["ports"])
                or not store.position_grid(receipt["run_id"])["matched_c_grid"]):
            raise ValueError("Incomplete Cairo or paired numerical publication")
        if any(canonical_digest({row[0]: row[1] for row in owners[arm]}) != observed["owners"][arm] for arm in ARMS):
            raise ValueError("Ordered owners do not bind the candidate match")
    elif (product["images"] or result["owner_rows"] or any(row["latlon"] is not None for row in observed["arms"].values())
          or store.position_grid(receipt["run_id"]) is not None or store.position_path(receipt["run_id"]) is not None):
        raise ValueError("Unexpected position evidence for a withhold")
    truth, reference = geographic_reference("weak")
    clearance = face_clearance_km(receipt["region"], truth)
    if clearance >= 0 or reference != named_score["reference_sha256"]:
        raise ValueError("Use the original sealed site reference and the proven omitted region")
    errors = {arm: dict(value, error_km=distance_km(truth, value["latlon"])) for arm, value in observed["arms"].items()}
    control = raw["native"]
    write(output, dict(outcome=receipt["decision"], false_fix=complete, clock=clock, port=port, publication=observed,
          clock_scope="saved physical 20/8 detection and inventory through process exit", binding=binding,
          control=dict(cairo_raw=control["process"]["clock"], cairo_arms=raw["reference_geographical_and_rf"]["runs"]["candidate"],
                       named_raw=raw["reused_stock"], named_arms=raw["reference_geographical_and_rf"]["runs"]["stock"]),
          omitted_arm_errors=errors, signed_site_reference_sha256=reference, omitted_face_clearance_km=clearance,
          omitted_center_distance_km=distance_km(truth, receipt["region"]["center"]),
          named_omitted=dict(clock=named["clock"], packet=named["named_detector"], outcome=named["outcome"],
                             false_fix=named_score["named_false_fix"], arms=named_score["named_translated"],
                             owners=named_owners["arms"]),
          owner_changes=summarise_owners(control["owners"], owners), omitted_owner_rows=owners, figures=product["images"],
          numerical=sidecars, route=witness["ports"], solver_clocks=witness["timing"], solver_recipe=witness["solver_recipe"],
          all_owned_rf_rms_hz={name: item["residual_rms_hz"] for name,item in result["detail"]["arms"].items()},
          pre_score_sha256=sha256(sealed.read_bytes()).hexdigest()))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "worker", "score"))
    cli.add_argument("root", type=Path)
    cli.add_argument("--output", type=Path)
    args = cli.parse_args()
    if args.action == "launch":
        launch(args.root)
    elif args.action == "worker":
        worker(args.root)
    elif args.output is not None and not args.output.resolve().is_relative_to(args.root.resolve()):
        score(args.root, args.output)
    else:
        cli.error("Use a fresh score file outside the pre-scoring seal")
