"""Measure the replayable predecessor election on one authenticated saved request."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def price_previous(original, audit):
    """Separate the stock predecessor election from its required verification and export."""
    from leo.operations import localization_v3_inputs as inputs
    from portable_orbit_index_trial import begin, observed, timing

    def price(reader, snapshots, elements, cutoff, *, element_parser):
        def parse(text):
            cat = counted_parse(text)
            audit["records"] += len(cat)
            return cat

        export, read, parse_stats = {}, {}, {}
        counted_parse = observed(element_parser, parse_stats)
        audit.update(records=0, snapshots=len(snapshots))
        start = begin()
        with (patch.object(reader, "read", observed(reader.read, read)),
              patch.object(inputs, "export_tle", observed(inputs.export_tle, export))):
            result = original(reader, snapshots, elements, cutoff, element_parser=parse)
        inclusive = timing(start)
        audit.update(inclusive=inclusive, verify=read, parse=parse_stats, export=export,
                     selector_and_receipt_cpu_ns=inclusive["cpu_ns"]
                     - sum(scope["cpu_ns"] for scope in (read, parse_stats, export)),
                     genuine_receipt=result["receipt"]["catalogue_sha256"])
        return result

    return price


def audit(output):
    from portable_orbit_index_trial import settings

    config, validator, runtime = settings()
    from aperture_trial import write
    from combined_raw_research import Portable, portable_factory
    from empty_bootstrap import bind_native
    from exact_named_route import bind, checked_catalogue, read
    from historical_orbit_index import measure
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest
    from leo.operations import localization_v3_inputs as inputs
    from leo.operations.tle_archive import TleArchiveReader
    from tools.pipeline_eval.variants.experimental.tle_records import batch_records

    bound = bind("0160")
    request = read(Path(bound["request"]))
    archive, _ = checked_catalogue(bound, request, TleArchiveReader, canonical_digest)
    document, offer = (read(Path(request[key])) for key in ("native_file", "offer_file"))
    bind_native(document, request["session"], request["inventory"], request["detector_sha256"],
                expected="sha256:"+request["native_sha256"])
    if document["clock_anchor"]["before"]["realtime_ns"] != request["causal_cutoff_utc_ns"]:
        raise ValueError("Original cutoff changed")
    prior, port = {}, {}
    file, pin, producer = bound["portable"]
    with batch_records(Path(validator["library"])) as native:
        checked_index = portable_factory(Portable(Path(file), pin, producer), port)
        with patch.object(inputs, "genuine_previous", price_previous(inputs.genuine_previous, prior)):
            result = measure((document, archive, Algo08Region.parse(offer), None), config, checked_index)
    transfer, = port["transfers"]
    if native["fallback"] or transfer["compatibility"]["fallback"] or transfer["loading"]["fallback"]:
        raise ValueError("The original exact route bindings must be used")
    write(output, dict(case=bound["case"], verified_request=bound["packets"][bound["request"]],
                       predecessor=prior, preparation=result, portable=port, runtime=runtime,
                       driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), waveform_reads=0))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    audit(cli.parse_args().output)
