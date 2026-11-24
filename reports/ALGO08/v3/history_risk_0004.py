"""Compare the frozen saved history-risk and installed-v3 routes on DS30-0004."""

import argparse
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import history_risk_0138 as prior
from history_risk_weak_physical import deny_original


CASE = "DS30-0004"
PANEL = Path("/tmp/ds30-v2-stage-all-6cdbac") / CASE
PAIR_PIN = "74a02df80e45c189b74a43589c5fe7135d5bbe5b6efaf45380205c2b4743cd1d"
TERMINAL_PIN = "e65eae61795046d35155432a98fa38db7c67d69fad5af5683cf9c67963a529c3"
NATIVE_PIN = "5980b46075defacdeb5bd594b4f66afa1342c118d4627e34ea3d1075e9830f14"
INVENTORY_PIN = "78b5ba15f4b94ccc1405acd6cc1a8574b5bf6f7b848422255ccfd138d27a76d3"
OFFER_PIN = "2698d6858da0a2d989d8c2185c9e3bbbba20d539988204c1f93a591eb9471236"
AUTHORITY = "sha256:3cb8fbc1a8776cc7225bc71cecc43225d0d076e8b4b36ec4ac008dea1a76599c"
ARCHIVE = "sha256:0c9bdf4a80768161252ce2c28b4e96991276b6dc64ed3d6ff44d613a78b00ea2"
DETECTOR = "2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5"
SPEC = "sha256:6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f"
CUTOFF = 1794550608803299095
ISSUED, ADMITTED, FACTORS = 6772, 6769, 5852
DONOR = prior.SHM / "leo-held-anchor-selected-dense-01/tle"
DONOR_COUNT, DONOR_BYTES = 47, 84_051_499
SESSION = "fast-" + INVENTORY_PIN[:32]
PACKET_NAME = "algo08-v2-ab565e23b58b989acf189a5c809b680a/detections.json"
PROTOCOL = HERE / "history-risk-0004-protocol.md"


def read(path):
    return json.loads(path.read_bytes())


def measurement_gates(result):
    named, routed = (result["coverage"][arm]["decision"] for arm in ("named", "routed"))
    sizes = {arm: value["grid_points"] for arm, value in result["coverage"].items()}
    science = result["scientific"]["runs"]
    changes = {key: science["routed"]["horizontal_error_km"][key] - science["named"]["horizontal_error_km"][key]
               for key in ("c0", "fitted_c")} if named == routed == "complete" else None
    return dict(same_standard_decision=named == routed,
                same_original_named_terminal=result["prior_named_terminal_equal"],
                both_complete_grids=all(n == 179 for n in sizes.values()) if changes is not None else None,
                both_position_regressions_within_250m=all(value <= .25 for value in changes.values())
                if changes is not None else None,
                routed_minus_named_error_km=changes)


def original_inputs():
    from causal_0138 import checked

    pair = json.loads(checked(PANEL/"pair.json", PAIR_PIN))
    installed = pair["runs"]["candidate"]
    receipt = installed["receipt"]
    if (pair["candidate_specification_digest"] != SPEC or pair["candidate_specification"]["detector_sha256"] != DETECTOR
            or pair["archive"]["snapshots_sha256"] != ARCHIVE or installed["raw_authority"] != AUTHORITY
            or receipt["session_id"] != SESSION or receipt["window_count"] != ISSUED
            or receipt["terminal_sha256"] != "sha256:"+TERMINAL_PIN
            or receipt["counts"] != dict(processed=ADMITTED, invalid_capture=ISSUED-ADMITTED, skipped_fast_score=0)):
        raise ValueError("Original named-100 pair has different signed support")
    pub = PANEL/"candidate"
    work = pub/"fast-scan-automatic-work"
    terminal = json.loads(checked(work/receipt["run_id"]/"terminal.json", TERMINAL_PIN))
    paths = {"named-detections.json": (work/PACKET_NAME, NATIVE_PIN),
             "inventory.json": (pub/"fast-scan-inputs"/(SESSION+".json"), INVENTORY_PIN),
             "operator-offer.json": (Path(pair["region"]), OFFER_PIN)}
    payload = {key: checked(path, pin) for key, (path, pin) in paths.items()}
    native, inventory, offer = map(json.loads, payload.values())
    source = native["source"]
    manifests = [[str(Path(row["path"])/"manifest.json"), row["manifest_digest"]] for row in inventory["segments"]]
    if (terminal["native_sha256"] != "sha256:"+NATIVE_PIN or terminal["region"] != offer
            or receipt["region"] != offer or inventory["window_count"] != ISSUED
            or source["session_id"] != SESSION or source["raw_recording_authority_digest"] != AUTHORITY
            or source["input_manifest_sha256"] != "sha256:"+INVENTORY_PIN
            or native["clock_anchor"]["before"]["realtime_ns"] != CUTOFF
            or native["provenance"]["processed_windows"] != ADMITTED
            or native["provenance"]["detector_sha256"] != "sha256:"+DETECTOR
            or len(source["probes"]) != 2*ADMITTED
            or sum(len(row["candidates"]) for row in source["probes"]) != FACTORS
            or manifests != [[row["path"], row["sha256"]] for row in pair["cache_observation"]["manifests"]]):
        raise ValueError("The exact saved packet, region, or manifest sequence changed")
    return pair, payload, manifests, paths


def local_causal():
    from causal_0138 import snapshot_digest
    from exact_named_route import resident_path
    from leo.operations.tle_archive import TleArchiveReader

    reader = TleArchiveReader(resident_path(DONOR))
    refs = reader.list_snapshots("space-track")
    if (len(refs) != DONOR_COUNT or sum(ref.byte_size for ref in refs) != DONOR_BYTES
            or snapshot_digest(refs) != ARCHIVE or any(ref.collected_utc_ns >= CUTOFF for ref in refs)):
        raise ValueError("The already staged donor differs from the original pre-capture archive")
    census = json.loads(subprocess.check_output(
        ["fincore", "--json", "--bytes", "-o", "RES,SIZE", *(resident_path(ref.path) for ref in refs)]
    ))["fincore"]
    if len(census) != len(refs) or any(row["res"] < row["size"] for row in census):
        raise ValueError("The signed local causal archive is no longer resident")
    if any(len(reader.read(ref)) != ref.byte_size for ref in refs):
        raise ValueError("A causal donor extent changed during original digest verification")
    return dict(root=str(DONOR), snapshots_sha256=ARCHIVE, snapshots=len(refs), bytes=DONOR_BYTES)


def stage_inputs(stage):
    from aperture_trial import write
    from dense_geographic_trial import host
    from exact_named_route import resident_path

    machine = host()
    if resident_path(stage.parent) != prior.SHM or stage.exists():
        raise ValueError("Require a fresh private local saved-input stage")
    start, cpu = perf_counter_ns(), process_time_ns()
    pair, payload, manifests, paths = original_inputs()
    catalogue = local_causal()
    stage.mkdir(mode=0o700)
    for name, body in payload.items():
        with (stage/name).open("xb") as handle:
            handle.write(body)
        (stage/name).chmod(0o444)
    request = dict(case=CASE, recording=pair["recording"], original_archive=pair["archive"], local_archive=catalogue,
                   native_file=str(stage/"named-detections.json"), native_sha256=NATIVE_PIN,
                   inventory="sha256:"+INVENTORY_PIN, offer_file=str(stage/"operator-offer.json"), offer_sha256=OFFER_PIN,
                   local_libraries={}, session=SESSION, raw_authority=AUTHORITY, manifests=manifests,
                   detector_sha256=DETECTOR, causal_cutoff_utc_ns=CUTOFF, original_pair_sha256=PAIR_PIN)
    write(stage/"request.json", request)
    write(stage/"projection.json", dict(
        case=CASE, original_pair_sha256=PAIR_PIN, terminal_sha256=TERMINAL_PIN, cutoff_utc_ns=CUTOFF,
        request_sha256=prior.digest(stage/"request.json"), source={key: [str(path), pin] for key,(path,pin) in paths.items()},
        archive=catalogue, donor_archive_reused_without_copy=True, signed_probes=2*ADMITTED, factors=FACTORS,
        no_waveform=True, no_original_archive=True, portable_mode="request-specific SourceIndex",
        protocol_sha256=prior.digest(PROTOCOL), machine=machine,
        preparation=dict(elapsed_ns=perf_counter_ns()-start, cpu_ns=process_time_ns()-cpu)))


@contextmanager
def binding(stage):
    import duration_heldout
    from causal_0138 import checked
    from exact_named_route import resident_path

    proof = read(resident_path(stage/"projection.json"))
    request = resident_path(stage/"request.json")
    request_pin = proof["request_sha256"]
    req = json.loads(checked(request, request_pin))
    files = {stage/"inventory.json": INVENTORY_PIN, stage/"named-detections.json": NATIVE_PIN,
             stage/"operator-offer.json": OFFER_PIN}
    if (proof["case"] != CASE or req["case"] != CASE or req["original_pair_sha256"] != PAIR_PIN
            or req["native_sha256"] != NATIVE_PIN or req["causal_cutoff_utc_ns"] != CUTOFF
            or req["local_archive"]["root"] != str(DONOR) or req["original_archive"]["snapshots_sha256"] != ARCHIVE
            or proof["protocol_sha256"] != prior.digest(PROTOCOL)):
        raise ValueError("Staged request and previously frozen inputs diverged")

    def enroll():
        for path, pin in files.items():
            checked(resident_path(path), pin)
        return dict(case=CASE, stage=str(stage), request=str(request), archive=str(DONOR), inventory=str(stage/"inventory.json"),
                    packets={str(path): pin for path, pin in files.items()}, issued=ISSUED, admitted=ADMITTED,
                    sources=prior.source_pins(), portable=None), req

    with (patch.multiple(prior, CASE=CASE, CUTOFF=CUTOFF, NATIVE_PIN=NATIVE_PIN, ISSUED=ISSUED, ADMITTED=ADMITTED,
                         STAGE=stage, REQUEST_PIN=request_pin, KEY="0004", DRIVER=Path(__file__).resolve(),
                         PROTOCOL=PROTOCOL, bound_request=enroll),
          patch.multiple(duration_heldout, PANEL=PANEL, PAIR_PIN=PAIR_PIN)):
        yield


def run(action, output, arm=None):
    if action == "worker":
        if arm not in prior.ORDER or output.name != arm:
            raise ValueError("Expected exactly one bound worker arm")
        with binding(output.parent.with_name(output.parent.name+"-inputs")):
            prior.worker(output, arm)
        return
    stage = output.with_name(output.name+"-inputs")
    if action == "stage":
        stage_inputs(stage)
        return
    with binding(stage):
        if action == "launch":
            prior.launch(output)
        else:
            from aperture_trial import write
            from tools.pipeline_eval import scoring

            distance = scoring.distance_km
            with patch.object(scoring, "distance_km", side_effect=lambda p, q: None if q is None else distance(p, q)):
                prior.score(output)
            write(output/"gates.json", measurement_gates(read(output/"result.json")))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("stage", "launch", "worker", "score"))
    parser.add_argument("output", type=Path)
    parser.add_argument("arm", choices=prior.ORDER, nargs="?")
    arguments = parser.parse_args()
    sys.addaudithook(deny_original)
    run(**vars(arguments))
