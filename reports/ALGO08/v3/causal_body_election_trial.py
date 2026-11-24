"""Compare exact prepared inputs on the current qualified saved physical request."""

import argparse
from collections import Counter
from contextlib import nullcontext
from hashlib import sha256
import json
import os
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REFERENCE = Path("/dev/shm/leo-v3-legacy-map-writer-0016-result01")
ADMISSION = "279b2b17080d58cc68fb739264ce53810f62d30b16f42e05a6ad7a2e485a6879"
SEAL = "76181d09ef8af9a90ea6b3d7a561e473c71969164ea1f3db2b14edfc9448a565"
WITNESS = "6317997a7a32554e8ba228c9004ed8c31b8d524e850c9adb5df9a58e640f63a8"
ORDER = ("control", "election", "election", "control")


def deny_backing(event, args):
    if event != "open" or not isinstance(args[0], (bytes, str)):
        return
    path = Path(os.path.abspath(os.fsdecode(args[0])))
    if path.is_relative_to("/srv/bulk") or path.is_relative_to("/mnt/qnap01"):
        raise ValueError(f"Saved preparation cannot open backing sources: {path}")


def enrolled():
    import empty_bootstrap as boot
    from combined_raw_research import Portable
    from exact_named_raw import staged_path
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader

    admission = json.loads(boot.checked(REFERENCE/"admission.json", ADMISSION))
    seal = json.loads(boot.checked(REFERENCE/"prediction-seal.json", SEAL))
    reference = json.loads(boot.checked(REFERENCE/"indexed/exact-named-raw-witness.json", WITNESS))
    request = admission["request"]
    packet_name, = [name for name in seal if name.endswith("/detections.json")]
    inventory_name, = [name for name in seal if "/fast-scan-inputs/" in name]
    if (seal[packet_name] != request["native"] or seal[inventory_name] != request["inventory"]
            or reference["raw_route"] != "history_risk_installed"
            or reference["solver_recipe"]["web_renderer"] != "ordinary Matplotlib orbit sheets, Cairo residuals, explicit position and track layout"):
        raise ValueError("The requested saved frame does not match the prepared original publication")
    packet = REFERENCE/packet_name
    native = json.loads(boot.checked(packet, request["native"][7:]))
    boot.bind_native(native, request["session"], request["inventory"], request["detector"][7:], expected=request["native"])
    if (native["source"]["raw_recording_authority_digest"] != request["authority"]
            or native["clock_anchor"]["before"]["realtime_ns"] != request["cutoff_utc_ns"]
            or native["provenance"]["window_count"] != 808):
        raise ValueError("The saved packet must bind to all original physical opportunities")
    request["saved_inventory"] = str(REFERENCE/inventory_name)
    boot.checked(Path(request["saved_inventory"]), request["inventory"][7:])
    offer = Algo08Region.parse(json.loads(boot.checked(Path(request["region"]), request["offer_sha256"])))
    archive = staged_path(Path(request["archive"]["root"]))
    refs = TleArchiveReader(archive).list_snapshots("space-track")
    if (len(refs) != 46 or any(ref.collected_utc_ns >= request["cutoff_utc_ns"] for ref in refs)
            or canonical_digest({ref.path.name: ref.sha256 for ref in refs}) != request["archive"]["snapshots_sha256"]):
        raise ValueError("The complete current causal archive must match the original seal")
    index = reference["ports"]["portable"]["transfers"][0]
    artifact = staged_path(Path(index["file"]))
    portable = Portable(artifact, index["sha256"], index["producer_sha256"])
    paths = [staged_path(ref.path, root=archive) for ref in refs] + [artifact, artifact.parent/"artifact-bind.json"]
    command = ["fincore", "--json", "--bytes", "-o", "RES,SIZE", *map(str, paths)]
    observed = json.loads(subprocess.check_output(command))["fincore"]
    if len(observed) != len(paths) or any(row["res"] < row["size"] for row in observed):
        raise ValueError("All original staged sources must already be resident")
    return native, archive, refs, offer, portable, request, reference


def prepare(job, config, candidate):
    import empty_bootstrap as boot
    from causal_body_election import binding
    from combined_raw_research import portable_factory
    from exact_graph_execution import graph_execution
    from exact_named_raw import staged_path
    from held_adaptive_0160 import catalogue_scope
    from historical_orbit_index import elected_elements, fingerprint, VerifiedIndexReader
    from leo.application.localization_v3 import prepare_native_scan
    from leo.operations.tle_archive import TleArchiveReader
    from tools.pipeline_eval.variants.algo08_causal_table import causal_table
    from tools.pipeline_eval.variants.experimental.preparation_gc import defer_collection

    native, archive, refs, offer, portable, request, _ = job
    tle, reads, portable_audit, election, graph = Counter(), [], {}, {}, {}
    verify = catalogue_scope(archive, refs, request["cutoff_utc_ns"], TleArchiveReader.read,
                             tle, resident=lambda path: staged_path(path, root=archive))
    reader = TleArchiveReader(archive)

    def read(ref):
        result = verify(reader, ref)
        reads.append([ref.path.name, len(result)])
        return result

    with (patch.object(reader, "read", read), graph_execution(enabled=True, audit=graph),
          causal_table(canonical_exports=True, previous_catalogues=True),
          elected_elements() as satellites):
        started = boot.now()
        with binding(election) if candidate else nullcontext():
            index = portable_factory(portable, portable_audit)
            wrapped = VerifiedIndexReader(reader, index)
            result = defer_collection(prepare_native_scan)(
                native, wrapped, config, element_parser=wrapped.parse,
                screen_latitude_deg=offer.screen_center[0], screen_longitude_deg=offer.screen_center[1])
        timing = boot.clock(started)
    transfers = portable_audit["transfers"]
    if (len(transfers) != 1 or transfers[0]["compatibility"]["fallback"] or transfers[0]["loading"]["fallback"]
            or index.counts["sidecar_hit_bodies"] != 19 or sum(tle.values()) != 177_013_672 or len(reads) != 99):
        raise ValueError("The ordinary paid causal attachment or read coverage changed")
    if candidate and (not election["admissible_source"] or election["counts"]["history_success"] != 1
                      or election["counts"]["initial_success"] != 1 or election["counts"]["projection_fallback"]):
        raise ValueError("The proposed election did not cover the complete original preparation")
    return dict(clock=timing, election=election, graph=graph, portable=portable_audit, satellites=satellites,
                fingerprint=fingerprint(result), authenticated_read_order=reads)


def trial(output):
    import empty_bootstrap as boot

    sys.addaudithook(deny_backing)
    _, specification, _, _, _ = boot.load_runtime()
    from historical_orbit_index import TRACK_PIN
    from leo.analysis.localization_v3.tracks import TrackConfig
    from tools.pipeline_eval.variants.experimental.tle_records import batch_records

    job = enrolled()
    config_file = boot.RELEASE/"assets/tracks.json"
    config = TrackConfig(**json.loads(boot.checked(config_file, TRACK_PIN))["config"])
    parser = specification["tle_parser"]
    library = Path(parser["library"])
    boot.checked(library, parser["sha256"])
    source = HERE/"causal_body_election.py"
    profile_order = []
    with batch_records(library):
        for mode in ORDER:
            profile_order.append(dict(mode=mode, **prepare(job, config, mode == "election")))

    first = profile_order[0]
    if any(row[key] != first[key] for row in profile_order
           for key in ("authenticated_read_order", "fingerprint", "satellites")):
        raise ValueError("Original numeric preparation, signed evidence or causal read order changed")
    cpu = [row["clock"]["cpu_s"] for row in profile_order]
    gain = [cpu[0]-cpu[1], cpu[3]-cpu[2]]
    spent = getrusage(RUSAGE_SELF)
    result = dict(enrolled_admission_sha256=ADMISSION, evidence_seal_sha256=SEAL, reference_witness_sha256=WITNESS,
                  protocol_sha256=sha256((HERE/"causal-body-election-protocol.md").read_bytes()).hexdigest(),
                  source_sha256=sha256(source.read_bytes()).hexdigest(), waveform_reads=0, numerical_solves=0,
                  input_blocks=spent.ru_inblock, major_faults=spent.ru_majflt, preparation=profile_order,
                  preparation_cpu_gains_s=gain, advances=min(gain) >= 0.1)
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    trial(cli.parse_args().output)
