"""Price exact delayed SGP4 materialization on two saved causal preparations."""

import argparse
from contextlib import contextmanager
from functools import partial
from hashlib import sha256
from inspect import unwrap
import json
from math import pi
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
import sys
from time import perf_counter, process_time
from unittest.mock import patch


HOUR_NS = 3_600_000_000_000
INPUTS_PIN = "d23c4b2470b9c81f9714633d430d63ee477980cfe4c96848acb7619693174e22"
CAUSAL_PIN = "5076a2182ba9f551f54df78ba1dee53eb223e922d7aac86088fcd4cf429dc6a8"
PARSER_PIN = "3146dcb19ec88ef5e03f0b29c04fa6773c3fd575aa2c22ccbbca6ddc6ca48143"
EXPORTER_PIN = "43a57182525d1b04148981ba316046a6ffd36931d98132bdac24777eecbc998d"
REGIONAL_PORT = "tools/pipeline_eval/variants/experimental/regional_bound_guard.py"
REGIONAL_PIN = "d8a81c561bf8652d1e8521bcbf4b357198a483f5cb364613772e2e3ec1f77aad"


class UnsupportedExport(ValueError):
    """The pinned exporter could reject an unelected indexed record."""


def export_supported(satellite):
    return (0 <= satellite.inclo <= pi and 0 <= satellite.nodeo <= 2*pi
            and 0 <= satellite.argpo <= 2*pi and 0 <= satellite.mo <= 2*pi)


class SourceIndex:
    """Keep validated immutable records by authenticated body and exact line pair."""

    def __init__(self):
        self.bodies = {}
        self.pairs = {}

    def catalogue(self, digest, text):
        from tools.pipeline_eval.variants import algo08_causal_reuse as installed

        cached = self.bodies.get(digest)
        if cached is not None:
            return cached
        # This pilot is bounded to two inventories. Keep the original parser and
        # native epoch conversion authoritative when admitting an unseen body.
        names, numbers, pairs, epochs = [], [], [], []
        for record in installed.parse_element_set_records(text):
            lines = record.first_line, record.second_line
            occurrence = self.pairs.get(lines)
            if occurrence is None:
                try:
                    satellite = installed.Satrec.twoline2rv(*lines)
                except (ValueError, RuntimeError) as error:
                    raise installed.ElementSetError(
                        f"unparsable element set for catalog object {record.satellite_number}"
                    ) from error
                epoch, = installed.ElementSetCatalogue((), (), (satellite,)).element_epoch_utc_ns()
                if not export_supported(satellite):
                    raise UnsupportedExport(f"Uncertified historical export for {record.satellite_number}")
                occurrence = lines, int(satellite.satnum), epoch
                self.pairs[lines] = occurrence
            pair, number, epoch = occurrence
            names.append(record.name)
            numbers.append(number)
            pairs.append(pair)
            epochs.append(epoch)
        result = installed.PreparedCatalogue(tuple(names), tuple(numbers), tuple(pairs), tuple(epochs))
        self.bodies[digest] = result
        return result

    def size(self):
        size = sys.getsizeof
        pairs = 0
        for entry in self.pairs.values():
            pair, number, epoch = entry
            pairs += size(entry) + size(pair) + sum(map(size, pair)) + size(number) + size(epoch)
        rows = sum(size(cat) + size(cat.names) + sum(map(size, cat.names)) + size(cat.satellite_numbers)
                   + size(cat.satellites) + size(cat.epochs) for cat in self.bodies.values())
        return pairs + rows + size(self.pairs) + size(self.bodies) + sum(map(size, self.bodies))


class VerifiedIndexReader:
    """Index only the body just authenticated by the ordinary archive reader."""

    def __init__(self, reader, index):
        self.reader, self.index = reader, index
        self.original_read = reader.read
        self.active = None
        self.reads = self.bytes = self.hits = 0
        self.stats = {}

    def list_snapshots(self, provider):
        return self.reader.list_snapshots(provider)

    def read(self, snapshot):
        self.active = None
        text = self.original_read(snapshot)
        self.active = snapshot.sha256, text
        self.reads += 1
        self.bytes += snapshot.byte_size
        return text

    def parse(self, text):
        if self.active is None or text is not self.active[1]:
            raise ValueError("Elected metadata must come from this just-verified body")
        digest, _ = self.active
        self.active = None
        self.hits += digest in self.index.bodies
        return self.index.catalogue(digest, text)

    __call__ = parse


def phase_history(reader, elements, metadata, *, element_parser, export, distinct):
    """Mirror the installed phase-history election before canonical TLE export."""
    cutoff = metadata["causal_cutoff_utc_ns"]
    snapshots = [s for s in reader.list_snapshots("space-track") if cutoff-72*HOUR_NS <= s.collected_utc_ns <= cutoff]
    unique = {}
    for snapshot in snapshots:
        if snapshot.sha256 not in unique or snapshot.collected_utc_ns < unique[snapshot.sha256].collected_utc_ns:
            unique[snapshot.sha256] = snapshot
    history, sources = {number: [] for number in elements}, []
    for snapshot in sorted(unique.values()):
        catalogue = element_parser(reader.read(snapshot))
        sources.append(dict(collected_utc_ns=snapshot.collected_utc_ns, sha256=snapshot.sha256))
        for number, pair, epoch in zip(catalogue.satellite_numbers, catalogue.satellites,
                                       catalogue.element_epoch_utc_ns(), strict=True):
            if str(number) in elements and epoch <= cutoff:
                history[str(number)].append(dict(pair=pair, epoch=int(epoch), collected_utc_ns=snapshot.collected_utc_ns,
                                                  snapshot_sha256=snapshot.sha256))
    for number, rows in history.items():
        kept = distinct(rows)
        for row in kept:
            row["lines"] = list(export(row.pop("pair")))
        history[number] = kept
    return dict(case="SCAN", origin_utc_ns=metadata["anchor_utc_ns"], cutoff_utc_ns=cutoff, past_versions=history,
                sources=sources, history_window_hours=72, candidates=len(elements), genuine_distinct_epochs=True,
                no_following_TLE_or_GPS=True, archive_access_is_read_only=True)


@contextmanager
def elected_elements():
    from leo.operations import causal_tle_catalogue as causal
    from leo.operations import localization_v3_inputs as inputs

    catalogue_type, original_export = causal.ElementSetCatalogue, inputs.export_tle
    satellites, counts = {}, {"coarse_latest": 0, "distinct_scan_objects": 0}

    def materialize(pair):
        satellite = satellites.get(pair)
        if satellite is None:
            satellite = inputs.Satrec.twoline2rv(*pair)
            satellites[pair] = satellite
        return satellite

    def latest(names, numbers, pairs):
        # Both installed and research exterior observers may capture the
        # same causal result at different levels. Its original construction
        # is the first point where all of them can receive native objects.
        counts["coarse_latest"] = len(pairs)
        return catalogue_type(names, numbers, tuple(map(materialize, pairs)))

    def export(value):
        return original_export(materialize(value) if type(value) is tuple else value)

    def past(reader, elements, metadata, *, element_parser):
        return phase_history(reader, elements, metadata, element_parser=element_parser,
                             export=export, distinct=inputs.distinct_epochs)

    with (patch.object(causal, "ElementSetCatalogue", latest), patch.object(inputs, "export_tle", export),
          patch.object(inputs, "prepare_phase_history", past)):
        yield counts
    counts["distinct_scan_objects"] = len(satellites)


def installed_guard():
    from empty_bootstrap import PAYLOAD, RELEASE
    from leo.operations import causal_tle_catalogue as causal
    from leo.operations import localization_v3_inputs as inputs
    from sgp4 import exporter
    from tools.pipeline_eval.variants import algo08_causal_reuse as installed

    paths = ((Path(inputs.__file__).resolve(), RELEASE/"src/leo/operations/localization_v3_inputs.py", INPUTS_PIN),
             (Path(causal.__file__).resolve(), RELEASE/"src/leo/operations/causal_tle_catalogue.py", CAUSAL_PIN),
             (Path(installed.__file__).resolve(), PAYLOAD/"tools/pipeline_eval/variants/algo08_causal_reuse.py", PARSER_PIN),
             (Path(exporter.__file__).resolve(), RELEASE/"venv/lib/python3.12/site-packages/sgp4/exporter.py", EXPORTER_PIN))
    return installed.accelerated and all(path == expected and sha256(path.read_bytes()).hexdigest() == pin
                                         for path, expected, pin in paths)


def preparation_port(ordinary, original):
    from empty_bootstrap import PAYLOAD

    base = unwrap(ordinary)
    if not isinstance(base, partial) or base.func is not original:
        return None
    if ordinary is base:
        return "causal"
    code = getattr(ordinary, "__code__", None)
    if (code is not None and code.co_name == "prepare" and getattr(ordinary, "__wrapped__", None) is base
            and (path := Path(code.co_filename).resolve()) == PAYLOAD/REGIONAL_PORT
            and sha256(path.read_bytes()).hexdigest() == REGIONAL_PIN):
        return "regional"
    return None


def guarded_preparation(ordinary, audit, *, index_factory=SourceIndex):
    """One guarded, scan-local build through the installed preparation caller."""
    from tools.pipeline_eval.variants import algo08_causal_reuse as installed

    port = preparation_port(ordinary, installed.prepare) if installed_guard() else None
    attempts = audit.setdefault("attempts", [])

    def prepare(document, reader, config, **options):
        start = process_time(), perf_counter()
        if port is None:
            attempts.append(dict(guard=False, fallback="unrecognized installed preparation or exporter"))
            return ordinary(document, reader, config, **options)
        index = index_factory()
        staged = VerifiedIndexReader(reader, index)
        try:
            # The installed regional veto recognizes the concrete archive reader
            # and captures the elected causal catalogue for its own later use.
            with (elected_elements() as materialized, patch.object(reader, "read", staged.read),
                  patch.object(installed, "CausalPreparationParser", return_value=staged)):
                prepared = ordinary(document, reader, config, **options)
        except UnsupportedExport as error:
            attempts.append(dict(guard=True, port=port, fallback=str(error), abandoned_cpu_s=process_time()-start[0],
                                 abandoned_elapsed_s=perf_counter()-start[1]))
            return ordinary(document, reader, config, **options)
        attempts.append(dict(guard=True, port=port, fallback=None, cpu_s=process_time()-start[0], elapsed_s=perf_counter()-start[1],
                             source_pairs=len(index.pairs), bodies=len(index.bodies), verified_reads=staged.reads,
                             verified_bytes=staged.bytes, **materialized))
        return prepared

    return prepare


DENSE = Path("/dev/shm/leo-held-anchor-selected-dense-01")
WEAK = Path("/dev/shm/leo-v3-raw-0016-best-results-01")
TRACK_PIN = "a7a252b2fd9a9fe7c617f4565b171c159846705803f4fb80ab755ba9ea94710a"
NATIVE_PINS = {"DS30-0008": "ad13073239fe7e4e276debf3c667c0a997408d9efb5e07e309b5ab6fff4d0a85",
               "DS30-0016": "c09de017909fdc6ffa9b0720b29f3a3fbb84b0785c110f15414ef3fc5bd37589"}
REQUEST_PINS = {"DS30-0008": "8abec0e2f60def947cd03883662611c3fcfdbd5f255eb0ba60e8306085abf502",
                "DS30-0016": "bfd940c22e7cfac17040dbc95e4908ed3224370b5d19d27298d8412afc08e774"}


def case_inputs(case):
    from empty_bootstrap import bind_native, checked
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader

    dense = case == "DS30-0008"
    root = DENSE if dense else WEAK
    request = json.loads(checked(root/("request.json" if dense else "admission.json"), REQUEST_PINS[case]))
    packet, = [root/"original-detections.json"] if dense else (root/"candidate").glob("fast-scan-automatic-work/*/detections.json")
    offer_path = root/("operator-offer.json" if dense else "offer.json")
    offer = Algo08Region.parse(json.loads(checked(offer_path, request["offer_sha256"])))
    native = json.loads(checked(packet, NATIVE_PINS[case]))
    raw = native["source"]["raw_recording_authority_digest"]
    authority = request["authority" if dense else "raw_authority"]
    bind_native(native, request["session"], request["inventory"], native["provenance"]["detector_sha256"][7:],
                expected="sha256:"+NATIVE_PINS[case])
    reader = TleArchiveReader(root/"tle")
    snapshots = reader.list_snapshots("space-track")
    archive_pin = request["archive"]["snapshots_sha256" if dense else "sha256"]
    cutoff = request["cutoff_utc_ns"]
    if (archive_pin != canonical_digest({s.path.name: s.sha256 for s in snapshots}) or not snapshots
            or raw != authority or native["clock_anchor"]["before"]["realtime_ns"] != cutoff
            or any(not s.path.resolve(strict=True).is_relative_to("/dev/shm")
                   or not 0 <= cutoff-s.collected_utc_ns <= 72*HOUR_NS for s in snapshots)):
        raise ValueError("Only the original signed, fully staged causal inventories are eligible")
    return native, reader.root, offer, dict(native=NATIVE_PINS[case], archive=archive_pin, cutoff_utc_ns=cutoff,
             authority=raw, body_digests=sorted({s.sha256 for s in snapshots}), snapshot_count=len(snapshots))


def fingerprint(prepared):
    from leo.application.localization_v3_engine import _prepared_values
    from leo.contracts.digests import canonical_digest

    if prepared["status"] != "inputs_prepared":
        raise ValueError("Expected genuine active preparation")
    normalized = _prepared_values(prepared)
    bank = normalized["sky"].pop("bank")
    return dict(document=canonical_digest(normalized), bank={name: dict(dtype=array.dtype.str, shape=list(array.shape),
                sha256=sha256(array.tobytes(order="C")).hexdigest()) for name, array in bank.items()},
        regional=len(bank["norad"]), tracks=len(normalized["tracks"]["tracks"]),
        history=sum(map(len, normalized["phase_history"]["past_versions"].values())))


def measure(job, config, index=None):
    from contextlib import nullcontext
    from leo.application.localization_v3 import prepare_native_scan
    from leo.operations.tle_archive import TleArchiveReader
    from tools.pipeline_eval.variants.algo08_causal_reuse import CausalPreparationParser
    from tools.pipeline_eval.variants.algo08_causal_table import causal_table
    from tools.pipeline_eval.variants.experimental.preparation_gc import defer_collection

    native, archive, offer, _ = job
    reader = TleArchiveReader(archive)
    bodies, pairs = (len(index.bodies), len(index.pairs)) if index else (0, 0)
    with (causal_table(canonical_exports=True, previous_catalogues=True) as steady,
          elected_elements() if index is not None else nullcontext() as orbit):
        start = process_time(), perf_counter()
        if index is None:
            parser = CausalPreparationParser()
        else:
            reader = VerifiedIndexReader(reader, index)
            parser = reader.parse
        prepared = defer_collection(prepare_native_scan)(native, reader, config, element_parser=parser,
                    screen_latitude_deg=offer.screen_center[0], screen_longitude_deg=offer.screen_center[1])
        clock = dict(cpu_s=process_time()-start[0], elapsed_s=perf_counter()-start[1])
    if index is None:
        if parser.stats["fallback_calls"]:
            raise ValueError("The ordinary accelerated source parser did not cover the full stage")
        source = dict(ordinary_parser=parser.stats, distinct_source_objects=len(parser.elements))
    else:
        source = dict(orbit, new_bodies=len(index.bodies)-bodies, new_pairs=len(index.pairs)-pairs,
                      total_bodies=len(index.bodies), retained_pairs=len(index.pairs), retained_index_bytes=index.size(),
                      verified_reads=reader.reads, verified_bytes=reader.bytes, index_hits=reader.hits)
    return dict(preparation=clock, source=source, science=fingerprint(prepared), installed_export=steady)


def run(output):
    from empty_bootstrap import PAYLOAD, RELEASE, checked, load_runtime

    _, spec, _, _, checks = load_runtime()
    from leo.analysis.localization_v3.tracks import TrackConfig
    from tools.pipeline_eval.variants.experimental.tle_records import batch_records

    if not installed_guard() or not spec["defer_preparation_gc"]:
        raise ValueError("Expected the original accelerated causal preparation")
    native = spec["tle_parser"]
    checked(Path(native["library"]), native["sha256"])
    config = TrackConfig(**json.loads(checked(RELEASE/"assets/tracks.json", TRACK_PIN))["config"])
    jobs = {case: case_inputs(case) for case in NATIVE_PINS}
    if jobs["DS30-0008"][3]["cutoff_utc_ns"] >= jobs["DS30-0016"][3]["cutoff_utc_ns"]:
        raise ValueError("Cross-capture reuse requires chronological enrollment")
    shared = SourceIndex()
    dense, weak = jobs.values()
    results = {}
    with batch_records(Path(native["library"])) as validation:
        for name, job, index in (("dense_ordinary", dense, None), ("dense_cold", dense, shared),
                ("dense_fresh", dense, shared), ("weak_ordinary", weak, None), ("weak_transfer", weak, shared),
                ("weak_fresh", weak, shared), ("weak_cold", weak, SourceIndex())):
            previous = dict(validation)
            result = measure(job, config, index)
            result["native_validation"] = {key: value-previous[key] for key, value in validation.items()}
            result["peak_rss_kib_so_far"] = getrusage(RUSAGE_SELF).ru_maxrss
            results[name] = result
    for name, result in results.items():
        ordinary = results[name.split("_")[0]+"_ordinary"]
        if result["science"] != ordinary["science"]:
            raise ValueError(f"Prepared arrays or scientific evidence changed: {name}")
        source = ordinary["source"]["ordinary_parser"]
        if (result["native_validation"]["fallback"] or not name.endswith("_ordinary")
                and result["source"]["verified_reads"] != source["snapshot_hits"] + source["snapshot_misses"]):
            raise ValueError(f"Unexpected validator fallback or archive read count: {name}")
    document = dict(cases={case: job[3] for case, job in jobs.items()}, results=results,
        checked_sources=checks, native_parser_sha256=native["sha256"], track_config_sha256=TRACK_PIN,
        io_stats=dict(input_blocks=getrusage(RUSAGE_SELF).ru_inblock, major_faults=getrusage(RUSAGE_SELF).ru_majflt),
        source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), solver_invocations=0, waveform_reads=0)
    with output.open("x") as stream:
        json.dump(document, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output)
