"""Compare a chronological pair of genuine saved orbit preparations."""

import argparse
from contextlib import nullcontext
from hashlib import sha256
import json
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
WEAK = Path("/dev/shm/leo-v3-weak-all8-combined-result02")
MEDIUM = Path("/dev/shm/leo-exact-solver-0057-result01")
PINS = {
    WEAK / "seal.json": "b29c1e288400792af10176f5936fce7206ba7d5f5c817cf214ce08ad800e7cfc",
    MEDIUM / "binding.json": "761d1b75c58d5949d3da8a880b925f1968ef3ba10ef4f7a8fc611c4699f4d072",
    MEDIUM / "result.json": "621db1154873ac24ce68b2c0bdc128dc5a6bff2f67166cb78455ac06b2342eec",
}


def job(case):
    from aperture_trial import archive_identity
    from empty_bootstrap import bind_native, checked
    from leo.contracts.algo08_region import Algo08Region
    from leo.operations.tle_archive import TleArchiveReader

    if case == "weak":
        from preloaded_saved_worker import enrolled

        _, archive, offer, _, _, _, authenticated = enrolled(case)
        old = json.loads(checked(WEAK / "seal.json", PINS[WEAK / "seal.json"]))
        sealed_identity = old["execution"]["identity"]
        for key in ("archive", "cutoff_utc_ns", "authority", "offer_sha256", "session", "inventory", "issued"):
            if authenticated[key] != sealed_identity[key]:
                raise ValueError(f"Original weak packet differs in its {key}")
        identity = dict(sealed_identity)
        packet = WEAK / "selected-detections.json"
        terminal = old["science"]["terminal"]
    else:
        request = json.loads(checked(MEDIUM / "binding.json", PINS[MEDIUM / "binding.json"]))
        old = json.loads(checked(MEDIUM / "result.json", PINS[MEDIUM / "result.json"]))
        archive, offer = Path(request["archive"]["root"]), Path(request["region"])
        published = old["candidate"]["worker"]["receipt"]
        terminal = old["candidate"]["science"]["terminal_sha256"]
        packet = Path(request["packets"]["candidate"])
        identity = dict(archive=request["archive"], offer_sha256=request["region_sha256"],
                        cutoff_utc_ns=request["clock_cutoff_utc_ns"], authority=request["raw_authority"],
                        session=published["session_id"], inventory=request["input_manifest"],
                        issued=published["window_count"], native_sha256=request["native"]["candidate"])
    native = json.loads(checked(packet, identity["native_sha256"][7:]))
    offer = Algo08Region.parse(json.loads(checked(offer, identity["offer_sha256"])))
    detector = native["provenance"]["detector_sha256"]
    cutoff = identity["cutoff_utc_ns"]
    snapshots = TleArchiveReader(archive).list_snapshots("space-track")
    bind_native(native, identity["session"], identity["inventory"], detector[7:], expected=identity["native_sha256"])
    if (archive_identity(archive) != identity["archive"] or not snapshots
            or any(not 0 <= cutoff - row.collected_utc_ns <= 72 * 3_600_000_000_000
                   or not row.path.resolve(strict=True).is_relative_to("/dev/shm") for row in snapshots)
            or native["clock_anchor"]["before"]["realtime_ns"] != cutoff
            or native["source"]["raw_recording_authority_digest"] != identity["authority"]
            or native["provenance"]["window_count"] != identity["issued"]):
        raise ValueError("Require the original prepared archive and signed causal request")
    identity["cached_reference_terminal"] = terminal
    return native, archive, offer, identity


def run(mode, output):
    from portable_orbit_index_trial import begin, observed, settings, timing

    overall = begin()
    start = begin()
    config, native_parser, checks = settings()
    from aperture_trial import write
    from combined_raw_research import portable_factory
    from combined_raw_trial import PRODUCER
    from empty_bootstrap import RELEASE
    from historical_orbit_index import measure
    from leo.analysis.localization_v3 import phase_prior
    from leo.application import localization_v3
    from persistent_orbit_updates import OrbitUpdates
    from tools.pipeline_eval.variants.experimental.tle_records import batch_records

    cache = OrbitUpdates() if mode == "persist" else None
    startup = timing(start)
    alternate = RELEASE / "src/leo/analysis/localization_v3/phase_prior.py"
    previous_cutoff = None
    updates = []
    for request in ("weak", "medium"):
        start = begin()
        prepared_job = job(request)
        identity = prepared_job[3]
        cutoff = identity["cutoff_utc_ns"]
        if previous_cutoff is None:
            previous_cutoff = cutoff
        elif cutoff <= previous_cutoff:
            raise ValueError("Requests must be strictly chronological")
        loaded = timing(start)
        transferred, forecast = {}, {}
        start = begin()
        index = portable_factory(PRODUCER, transferred)
        transfer = transferred["transfers"][0]
        if (transfer["compatibility"]["fallback"] or transfer["loading"]["fallback"]
                or transfer["producer_cutoff_utc_ns"] > cutoff):
            raise ValueError("The trusted earlier index is required in both arms")
        scope = cache.request(phase_prior, alternate, cutoff) if cache is not None else nullcontext()
        start = begin()
        with (batch_records(Path(native_parser["library"])) as validation, scope as counts,
              patch.object(localization_v3, "forecast", observed(localization_v3.forecast, forecast))):
            result = measure(prepared_job, config, index)
        prepared_and_verified = timing(start)
        if not index.counts["sidecar_hit_bodies"] or validation["fallback"] or forecast["calls"] != 1:
            raise ValueError("Require the verified index, original native validator and one legal forecast")
        if counts is not None and (counts["incompatible_source"] or counts["original_unsupported"] or counts["evicted"]):
            raise ValueError(f"Ineligible saved cache support: {counts}")
        rss = getrusage(RUSAGE_SELF).ru_maxrss
        updates.append(dict(identity=identity, request=request, native_loading=loaded, preparation=result,
                            forecast=forecast, portfolio_index=transfer, cache=counts,
                            entries=None if cache is None else len(cache.results), rss_peak_kib=rss,
                            prepared_and_verified=prepared_and_verified))
        del prepared_job, index
    write(output, dict(mode=mode, requests=updates, startup=startup, installed_source_checks=checks,
                       timed_sequence=timing(overall), bindings={str(path): pin for path, pin in PINS.items()},
                       runtime_pins={path.name: sha256(path.read_bytes()).hexdigest() for path in (
                           Path(__file__).resolve(), HERE / "persistent_orbit_updates.py", alternate)},
                       waveform_reads=0, solver_invocations=0))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("ordinary", "persist"))
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    run(args.mode, args.output)
