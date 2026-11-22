"""Freeze the tested packed receiver with the previously verified graph solver."""

import argparse
from pathlib import Path

from leo.contracts.digests import canonical_digest
from tools.pipeline_eval.qualification.freeze_publication import NATIVE_LIBRARIES, freeze

from .screened_stock_salvage_trial import digest, read, require_spec
from .screened_tiled_graph_trial import MEASUREMENTS, write

LIBRARIES = (*NATIVE_LIBRARIES, "paired_sha256")
RESTORED_RECEIVER = "6f2cc95d835ffcff8226a925dddca9d5b03d8fe6b06c159b165ac0807b805a91"


def fixed_options(spec):
    fields = {k: v for k, v in spec.items() if k not in ("detector", "detector_sha256")}
    return {k: v["sha256"] if k in LIBRARIES else v for k, v in fields.items()}


def run(parent, binary, output, receipt, restored_scout_build=None):
    if restored_scout_build is None:
        reference = read(MEASUREMENTS / "screened-tiled-graph-freeze.json")
        receiver = read(MEASUREMENTS / "receiver-packed-cancellation.json")["builds"]["candidate"]
        expected = [receiver["reference_sha256"], receiver["candidate_sha256"]]
        if expected != read(MEASUREMENTS / "receiver-packed-cancellation-austin.json")["binary_sha256"]:
            raise ValueError("Native and Austin receiver trials disagree on their binaries")
    else:
        reference = read(MEASUREMENTS / "packed-graph-freeze.json")
        build = read(restored_scout_build)
        expected = [build["packed_sha256"], build["corrected_sha256"]]
        if expected != [reference["spec"]["detector_sha256"], RESTORED_RECEIVER]:
            raise ValueError("Unexpected scout object restoration")
    require_spec(parent, reference["specification"])
    original = read(parent / "spec.json")
    pins = [original["detector_sha256"], digest(binary)]
    if pins != expected:
        raise ValueError("Receiver pins differ from the measured input and successor binaries")
    options = {k: v for k, v in original.items()
               if k not in ("sources", "detector", "detector_sha256", *LIBRARIES)}
    for k in LIBRARIES:
        if k in original:
            options[k] = Path(original[k]["library"]), original[k]["sha256"]
    new = freeze(parent, output, binary, pins[1], **options)
    if fixed_options(new) != fixed_options(original):
        raise ValueError("Successor changed a solver, source, or publication setting")
    fingerprint = canonical_digest(new)
    require_spec(output, fingerprint)
    write(receipt, dict(parent_specification=reference["specification"],
                        specification=fingerprint, spec=new))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("parent", "binary", "output", "receipt"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--restored-scout-build", type=Path,
                        help="Use the measured receiver built with the original scout arithmetic")
    run(**vars(parser.parse_args()))
