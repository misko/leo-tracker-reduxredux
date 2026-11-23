"""Capture only the original saved Graph and sky for blind Doppler probing."""

import argparse
from pathlib import Path
from time import process_time_ns
from unittest.mock import patch

from aperture_trial import archive_identity, configuration, read, solve, write
from arc_doppler_start_trial import source
from dense_full_short_crossover import TRACK_ASSET_PIN, file_sha
from dense_geographic_trial import host


HERE = Path(__file__).resolve().parent
NORTH = Path("/var/tmp/leo-north-short-regional-nov23")
OMISSIONS = {
    "north-near": ("north-mirror-outside-offer.json",
                   "eacc9fd6b5da3e9e38a7b13edee43aad63e229622c9973aa401a2dbb8c7f20d7"),
    "north-far": ("north-far-offer.json",
                  "6b48044ea39e5a32611da86c0aebe3efb922d072773456da3d9d75de9b687ed4"),
}
CASES = ("weak", "north-containing", *OMISSIONS)


def run(case, output):
    settings = host()
    publication, specification = configuration()
    from leo.contracts.algo08_region import Algo08Region
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core
    from unordered_doppler import prediction

    native, binding, _, _ = source("weak" if case == "weak" else "north")
    archive = Path(binding["archive"]["root"])
    offer = binding["offer"]
    if case in OMISSIONS:
        name, pin = OMISSIONS[case]
        path = NORTH / name
        if file_sha(path) != pin:
            raise ValueError("The original public omission offer changed")
        offer = Algo08Region.parse(read(path)).document()
        binding["offer_source_sha256"] = pin
    binding["containing_offer"] = binding.pop("offer")
    binding["evaluated_offer"] = offer
    binding["containing_terminal_sha256"] = binding.pop("terminal_sha256")

    original = algo08_position.solve
    evidence = {}

    class ProbesComplete(Exception):
        pass

    def observed(document, reader, assets, region):
        if (document is not native or reader.root != archive or region.document() != offer
                or file_sha(assets / "tracks.json") != TRACK_ASSET_PIN):
            raise ValueError("The installed graph, source packet, archive or offer changed")
        start = process_time_ns()

        def score(prepared, bound_region, _bound, _stages, **_options):
            if prepared["status"] != "inputs_prepared":
                raise ValueError("Expected the original graph and complete causal sky")
            evidence["preparation_cpu_ns"] = process_time_ns() - start
            evidence["cutoff_utc_ns"] = prepared["sky"]["metadata"]["cutoff_utc_ns"]
            evidence.update(prediction(prepared, bound_region))
            raise ProbesComplete()

        with patch.object(v5_core, "infer", score):
            return original(document, reader, assets, region)

    with patch.object(algo08_position, "solve", observed):
        try:
            solve(publication, specification, native, archive, offer)
        except ProbesComplete:
            pass
    if not evidence or archive_identity(archive) != binding["archive"]:
        raise ValueError("Probe run did not complete on the original archive")
    pins = {name: file_sha(HERE / name) for name in (
        "unordered-doppler-protocol.md", "unordered_doppler.py", "unordered_doppler_trial.py")}
    write(output, dict(case=case, binding=binding, host=settings, pins=pins, **evidence))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    parser.add_argument("output", type=Path)
    run(**vars(parser.parse_args()))
