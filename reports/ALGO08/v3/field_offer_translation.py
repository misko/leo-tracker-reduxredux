"""Replay the two frozen offer translations on one authenticated full field packet."""

import argparse
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


sys.path.insert(0, str(Path(__file__).resolve().parent))
from frozen_south_saved import CROSS_SHA, PINS, RUNTIME, charted, deny_original, digest, read


CASE = "DS30-0086"
STAGE = Path("/dev/shm/leo-v3-cfo-epoch-0086-saved01")
CAMPAIGN = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124")
PAIR_PIN = "407765fa47754cc99556143888b286e88f4674ab21836d3f437ac8af4c2ca439"
AUTHORITY_PIN = "602a2075d0acf1c0504fca56cb3941a03f7dfa20eb2dfce9edcc79f488f5a248"
OFFER_PIN = "2698d6858da0a2d989d8c2185c9e3bbbba20d539988204c1f93a591eb9471236"
BUILD_PIN = "30cc3b044040f2519677d67abfde731f83693612744d2236d1ba71bb5a31e4ab"
CATALOGUE_PIN = "68bfd52bcac791477997d6da402835d830f82172268f847d66dfa5fc8e2755f9"
OFFER_PINS = {
    "east": "72b9384ff9796196d4da34629bb5dcaf16e20b1476fe6de4071ad3ef73157473",
    "west": "69642aeb4117582c1e0d6d1860eaa5646a2a27e75d7bb3cdf4f192e500b08d83",
}


def translated_offer(original, direction):
    lat, lon = original["center"]
    half_width = original["width_km"] / 2
    offset = direction * half_width / (111.32 * math.cos(math.radians(lat)))
    return dict(original, center=[lat, lon + offset])


def source_binding(*, full_hashes=False):
    if digest(RUNTIME / "ds30_0049_saved_crossover.py") != CROSS_SHA:
        raise ValueError("The qualified saved-handoff source changed")
    sys.path.insert(0, str(RUNTIME))
    import ds30_0049_saved_crossover as cross
    import empty_bootstrap as boot

    batch = cross.batch
    _, spec, sources, publication, _ = boot.load_runtime()
    book, _, cutoff = batch.load_build(cross.BUILD, BUILD_PIN)
    pair = batch.document(CAMPAIGN / "cases" / CASE / "pair.json", PAIR_PIN)
    attempt = CAMPAIGN / "cases" / CASE / "successor" / "attempt-000001"
    recorded = batch.document(attempt / "result.json", pair["attempt_result_sha256"]["successor"])
    authority = batch.document(STAGE / "authority.json", AUTHORITY_PIN)
    release = read(attempt / "publication/algo08v3-successor-release.json")
    original = batch.document(CAMPAIGN / "offer.json", OFFER_PIN)
    receipt = recorded["evidence"]["receipt"]
    if (not pair["verified_pair"] or pair["generation"] != 1 or recorded["raw_identity"] != authority
            or pair["authority_sha256"] != batch.tagged(AUTHORITY_PIN) or recorded["outcome"] != "complete"
            or release["build_sha256"] != batch.tagged(BUILD_PIN)
            or release["authority_sha256"] != batch.tagged(AUTHORITY_PIN)
            or release["terminal_sha256"] != receipt["terminal_sha256"] or receipt["region"] != original
            or batch.tagged(OFFER_PIN) != authority["region_sha256"]):
        raise ValueError("Expected the exact completed field successor and original operator offer")
    recording, archive = Path(authority["recording"]), STAGE / "tle"
    sys.addaudithook(deny_original(recording, archive))
    inventory = batch.document(STAGE / "inventory.json", authority["inventory_sha256"])
    native = batch.document(STAGE / "native.json", recorded["native_sha256"])
    from integrated_original_entry import HELD_SHA
    from leo.contracts.algo08_region import Algo08Region
    from leo.operations.tle_archive import TleArchiveReader

    boot.bind_native(native, authority["session_id"], authority["inventory_sha256"], HELD_SHA,
                     expected=recorded["native_sha256"])
    batch.match_inventory(authority, authority["session_id"], authority["inventory_sha256"], inventory)
    batch.match_native(authority, native)
    if (release["portable_dispatch"] != "eligible" or cutoff >= authority["causal_cutoff_utc_ns"]
            or batch.archive_digest(archive, authority["causal_cutoff_utc_ns"]) != authority["archive_sha256"]):
        raise ValueError("Expected the full original causal archive and portable eligibility")
    references = TleArchiveReader(archive).list_snapshots("space-track")
    catalogue = batch.document(STAGE / "catalogue.json", CATALOGUE_PIN)
    if {ref.path.name: batch.tagged(ref.sha256) for ref in references} != {
        basename: batch.tagged(row["sha256"]) for basename, row in catalogue.items()
    }:
        raise ValueError("The archive bodies differ from the pinned local inventory")
    files = [batch.direct(ref.path) for ref in references]
    sizes = subprocess.check_output(["fincore", "-bno", "RES,SIZE", *files], text=True).splitlines()
    if len(sizes) != len(references) or any(int(res) < int(size) for res, size in map(str.split, sizes)):
        raise ValueError("The complete original archive must already be resident")
    if full_hashes:
        for ref in references:
            batch.checked(ref.path, ref.sha256)
    offers = {}
    for label, direction in (("east", 1), ("west", -1)):
        target = PINS / f"field-offer-translation-{label}.json"
        doc = batch.document(target, OFFER_PINS[label])
        if Algo08Region.parse(doc).document() != translated_offer(original, direction):
            raise ValueError("The frozen translation changed the original frame or screen")
        offers[label] = target
    audit = dict(case=CASE, bodies=len(files), archive_bytes=sum(ref.byte_size for ref in references),
                 archive_sha256=authority["archive_sha256"], native_sha256=recorded["native_sha256"],
                 inventory_sha256=authority["inventory_sha256"], validated_source_pins=len(book["sources"]),
                 original_offer_sha256=OFFER_PIN, translated_offers=OFFER_PINS, waveform_reads=0)
    return SimpleNamespace(batch=batch, spec=spec, sources=sources, publication=publication, cross=cross,
                           book=book, authority=authority, inventory=inventory, native=native, archive=archive,
                           recording=recording, original=original, recorded=recorded, offers=offers, audit=audit)


def worker(label, output):
    if os.sched_getaffinity(0) != {2} or os.nice(0) < 15 or output.exists() or not output.is_absolute():
        raise ValueError("Require CPU 2, nice 15 and a fresh saved publication root")
    bind = source_binding()
    from legacy_first_map_acceleration import checked_artifacts
    from unified_short_bootstrap import Handoff

    book, batch, authority = bind.book, bind.batch, bind.authority
    receiver = bind.native["provenance"]["detector_sha256"].removeprefix("sha256:")
    handoff = Handoff(authority["session_id"], authority["inventory_sha256"], receiver, bind.native)
    portable, fast = (book["native"][name] for name in ("--portable-orbit-index", "--legacy-first-map-fast"))
    acceleration = checked_artifacts(Path(fast["path"]), batch.tagged(fast["sha256"]))
    options = SimpleNamespace(output=output, recording=bind.recording, archive=bind.archive, region=bind.offers[label],
                              archive_sha256=authority["archive_sha256"], history_risk_route=True,
                              cairo_six_sheets=True, cairo_residual_layout=False,
                              portable_orbit_index=Path(portable["path"]), portable_orbit_index_sha256=batch.tagged(portable["sha256"]),
                              portable_orbit_producer_sha256=book["portable_producer"]["sha256"].removeprefix("sha256:"))
    terminal, rows, audit = charted(bind.publication, bind.spec, bind.sources, options, handoff, authority,
                                    bind.inventory, acceleration, bind.cross)
    submitted = bind.recorded["native_sha256"]
    batch.checked(bind.cross.one(output, "fast-scan-automatic-work/*/detections.json"), submitted)
    checked_terminal = batch.document(output / "fast-scan-automatic-work" / terminal["run_id"] / "terminal.json",
                                      terminal["terminal_sha256"])
    if (terminal["region"] != read(options.region) or checked_terminal["region"] != terminal["region"]
            or checked_terminal["native_sha256"] != submitted or handoff.calls != 1):
        raise ValueError("The archived packet and translated offer must reach the signed terminal")
    batch.write(output / "field-translation-worker.json", dict(mode=f"{label}:integrated", receipt=terminal,
                submitted_native_sha256=submitted, waveform_reads=0, verified_handoffs=handoff.calls,
                ordered_owners=rows, audit=audit))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("probe", *OFFER_PINS))
    cli.add_argument("output", nargs="?", type=Path)
    args = cli.parse_args()
    if args.mode == "probe":
        print(json.dumps(source_binding(full_hashes=True).audit, sort_keys=True))
    else:
        worker(args.mode, args.output)
