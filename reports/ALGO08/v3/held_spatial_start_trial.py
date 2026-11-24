"""Run two frozen saved regional start probes and score geography afterwards."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import perf_counter, process_time


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
DENSE = Path("/dev/shm/leo-v3-mixed-final-0008-01")
OMITTED = Path("/dev/shm/leo-v3-portable-omitted-0016-guarded-02")
REPAIRED = Path("/dev/shm/leo-v3-portable-repaired-0016-translated-01")
PINS = {
    "dense_binding": "71bb3459952cf21760764690f54e6536c154151257ba2cf854b1fa11b29870a5",
    "dense_control": "da352d9b4b08a7d79be2fb46735afc7b63f2fee8bb29c1c886e268fae012dd1d",
    "omitted_binding": "84a31908181a540fa305b90f6920b28ff61e50c1179606b400faf64ef4113861",
    "omitted_offer": "063764d149b15b5a61c86a7f02b2a639a564327afdb3dbb32f1ff236e4f5ca6c",
    "omitted_control": "246568330488c0cc61ec7f0d5137ebd0fe0278983b2b8787dda4e774ea62fdfc",
    "omitted_research": "f399c830c51e554c83da309bc548c7530a2ed4223b3657061456e64aae38e623",
}


def json_pin(path, pin):
    from empty_bootstrap import checked

    path = Path(path).resolve(strict=True)
    if not path.is_relative_to("/dev/shm"):
        raise ValueError("Scientific saved inputs must already reside in tmpfs")
    return json.loads(checked(path, pin.removeprefix("sha256:")))


def inputs(case):
    from empty_bootstrap import bind_native
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader

    if case == "dense":
        job = json_pin(DENSE/"binding.json", PINS["dense_binding"])
        source, native, pin = job, json_pin(job["packet"], job["native"]), job["native"]
        offer = Algo08Region.parse(json_pin(job["region"], job["offer_sha256"]))
        path, archive_pin = Path(job["archive"]["root"]), job["archive"]["snapshots_sha256"]
        projection = Path(job["libraries"]["geographic_library"])
        cutoff = job["cutoff_utc_ns"]
    else:
        job = json_pin(OMITTED/"ordinary/binding.json", PINS["omitted_binding"])
        source = job["saved"]
        native, pin = json_pin(source["packet"], source["native_sha256"]), source["native_sha256"]
        offer = Algo08Region.parse(json_pin(job["offer"], PINS["omitted_offer"]))
        path, archive_pin = Path(job["archive"]), "sha256:25bf630b8588a27a23f90de971041ce95b249ce5e1fd2f72144aa8b73945fafc"
        projection = Path(job["libraries"]["geographic_library"])
        cutoff = 1794568912154038024
    if (not path.resolve(strict=True).is_relative_to("/dev/shm") or not projection.resolve(strict=True).is_relative_to("/dev/shm")
            or native["clock_anchor"]["before"]["realtime_ns"] != cutoff):
        raise ValueError("The exact staged archive, coordinates or detector cutoff changed")
    bind_native(native, job["session"], job["inventory"], native["provenance"]["detector_sha256"][7:], expected=pin)
    reader = TleArchiveReader(path)
    snapshots = reader.list_snapshots("space-track")
    if (canonical_digest({s.path.name:s.sha256 for s in snapshots}) != archive_pin
            or any(not s.path.resolve(strict=True).is_relative_to("/dev/shm") for s in snapshots)):
        raise ValueError("The current archive is outside the staged signed capture evidence")
    return native, reader, offer, projection, dict(detector=pin, archive=archive_pin, cutoff_utc_ns=cutoff,
                                                  identity=source.get("authority", native["source"]["raw_recording_authority_digest"]))


def write(path, document):
    from leo.application.localization_v3_engine import _json_value

    with path.open("x") as stream:
        json.dump(document, stream, default=_json_value, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def run(case, output):
    from empty_bootstrap import RELEASE, checked, load_runtime

    _, spec, _, _, _ = load_runtime()
    from dense_geographic_trial import host
    from exact_graph_execution import graph_execution
    from full_short_run import geographic_projection
    from held_spatial_start import proposal, split, timed
    from historical_orbit_index import TRACK_PIN
    from leo.analysis.localization_v3.region import SearchRegion
    from leo.analysis.localization_v3.tracks import TrackConfig
    from leo.analysis.localization_v4.backend import read_manifest, validate_manifest
    from leo.application.localization_v3 import prepare_native_scan
    from tools.algo08_position import NativeBound
    from tools.pipeline_eval.variants.algo08_causal_reuse import CausalPreparationParser
    from tools.pipeline_eval.variants.algo08_causal_table import causal_table
    from tools.pipeline_eval.variants.experimental.preparation_gc import defer_collection
    from tools.pipeline_eval.variants.experimental.tle_records import batch_records

    machine = host()
    native, reader, operator, projection, identity = inputs(case)
    if output.resolve().parent != Path("/dev/shm"):
        raise ValueError("Use a new direct tmpfs output")
    tracks = TrackConfig(**json.loads(checked(RELEASE/"assets/tracks.json", TRACK_PIN))["config"])
    native_config = spec["tle_parser"]
    bound = NativeBound(validate_manifest(read_manifest(RELEASE/"assets/native/manifest.json"), check_provider=True)["binary"])
    parser = Path(native_config["library"])
    checked(parser, native_config["sha256"])
    region = SearchRegion(operator.center, width_km=operator.width_km)
    start = process_time(), perf_counter()
    training, held, visits = split(native)
    split_clock = timed(start)
    stage = process_time(), perf_counter()
    with (batch_records(parser) as parsed, causal_table(canonical_exports=True, previous_catalogues=True),
          graph_execution(enabled=True)):
        prepared = defer_collection(prepare_native_scan)(training, reader, tracks, element_parser=CausalPreparationParser(),
                    screen_latitude_deg=operator.screen_center[0], screen_longitude_deg=operator.screen_center[1])
    clock = timed(stage)
    if prepared["status"] == "inputs_prepared":
        with geographic_projection(projection):
            result = proposal(prepared, held, region, bound)
    else:
        result = dict(arms={}, support=dict(radio={}, coverage=0, sigma_hz=0), gate="fallback",
                      gate_failures=[prepared["status"]])
    if parsed["fallback"]:
        raise ValueError("The original staged strict parser used its compatibility path")
    write(output, dict(case=case, machine=machine, original=identity, sources={str(p.name):sha256(p.read_bytes()).hexdigest()
          for p in (HERE/"held_spatial_start.py", Path(__file__), HERE/"held-spatial-start-protocol.md")},
          split=split_clock, held_visits=len(visits), training_controls=clock, total=timed(start),
          train_observations=len(prepared["tracks"]["observations"]), native_parser_counts=parsed, proposal=result,
          original_waveform_reads=0, complete_solves=0))


def score(dense, omitted, output):
    from empty_bootstrap import checked
    from tools.pipeline_eval.scoring import distance_km

    dense_seal, omitted_seal = [json.loads(path.read_bytes()) for path in (dense, omitted)]
    if (dense_seal["case"], omitted_seal["case"]) != ("dense", "omitted"):
        raise ValueError("Unexpected pre-scoring receipt case order")
    # Geographic truth and existing terminal positions are opened only in this
    # separate, post-seal command.
    reference = json.loads(checked(HERE.parents[1]/"2026_11_21_ds30_full/reference-audit.json",
                    "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5"))
    scores = {}
    for snapshot in (dense_seal, omitted_seal):
        case = snapshot["case"]
        if case == "dense":
            earlier = json_pin(DENSE/"result.json", PINS["dense_control"])
            if earlier["inputs"]["native"] != snapshot["original"]["detector"] or not earlier["same_regional_proof"]:
                raise ValueError("The accepted original-final-fit control must use the same full dense packet and regional path")
            stock = earlier["solution"]
            coast = earlier["stages"]["cold_clocks"]["cpu_s"]
            solver = earlier["worker"]["solve"]["cpu_s"]
        else:
            earlier = json_pin(REPAIRED/"complete-scope.json", PINS["omitted_control"])
            if (earlier["native_sha256"] != snapshot["original"]["detector"] or not earlier["same_regional_evidence"]
                    or earlier["offer"] != json_pin(OMITTED/"offer.json", PINS["omitted_offer"])):
                raise ValueError("The repaired translated control must use the exact training-input authority and offer")
            stock = earlier["runs"]["portable"]["science"]["terminal"]["arms"]
            archived = json_pin(REPAIRED/"portable/selective/joint-research-receipt.json", PINS["omitted_research"])
            coast = archived["route_details"]["cold_clocks"]["cpu_s"]
            solver = archived["solve"]["cpu_s"]
        tag = "DS30-0008" if case == "dense" else "DS30-0016"
        truth = reference_point(reference, tag)
        arms = {arm: dict(error_km=distance_km(truth, item["latlon"]), held_rms_hz=item["held_rms_hz"],
                      current_error_km=distance_km(truth, stock[arm]["latlon"]), current_rf_rms_hz=stock[arm]["rf_rms_hz"])
                for arm, item in snapshot["proposal"]["arms"].items()}
        charged = snapshot["total"]["cpu_s"]
        prepared = snapshot["training_controls"]["cpu_s"]
        scores[case] = dict(current_cold_cpu_s=coast, current_solve_cpu_s=solver, paid_proposal_cpu_s=charged,
                           fallback_cpu_s=charged+solver, even_if_admitted_cold_headroom_cpu_s=coast-charged, arms=arms,
                           optimistic_headroom_if_training_preparation_were_free_cpu_s=coast-(charged-prepared),
                           gate=snapshot["proposal"]["gate"], support=snapshot["proposal"]["support"],
                           reasons=snapshot["proposal"]["gate_failures"])
    retained = [name for name, item in scores.items() if item["gate"] == "admit"]
    write(output, dict(scores=scores, accepted=retained, fallback_count=len(scores)-len(retained),
                       fallback_fraction=1-len(retained)/len(scores), sealed={str(p):sha256(p.read_bytes()).hexdigest() for p in (dense, omitted)}))


def reference_point(document, case):
    entry, = (row for row in document["cases"] if row["dataset_label"] == case)
    if not entry["authority_eligible"] or not entry["sealed_metadata_digests_verified"]:
        raise ValueError("The original DS30 reference is ineligible")
    return [entry["reference"][key] for key in ("latitude_deg", "longitude_deg")]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("dense", "omitted", "score"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--dense", type=Path)
    parser.add_argument("--omitted", type=Path)
    args = parser.parse_args()
    if args.mode == "score":
        score(args.dense, args.omitted, args.output)
    else:
        run(args.mode, args.output)
