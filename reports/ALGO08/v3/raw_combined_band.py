"""Select and measure the whole-raw refined receiver plus curvature proof."""

import argparse
from pathlib import Path

from empty_bootstrap import checked
from raw_0016_best_trial import FLAGS, HERE, PairInputs, command, condition, configuration, measure_mode, seal, sha
from raw_band_pair import Selection, selection
from raw_cfo_0016_trial import LIBRARY, WRAPPER, receiver_preflight
from short_cfo_raw import LIBRARY_SHA256, recipe
from short_raw_0180 import BULK, Workload


BASE = "4703df1957ed25a01d0ef1ea2efcdd16f59f62a1"
PROTOCOL = HERE/"raw-combined-0340-protocol.md"
PROTOCOL_SHA = "bd4eced395f182028c5cfd6ec5283ecc07e9806a6ef622faf339c1b02e86061c"
CURVATURE = "--prove-no-active-curvature"
CFO_FLAG = "--cfo-refinement-library"
COMBINED_FLAGS = (*FLAGS, CURVATURE, CFO_FLAG)
EXTRA_SOURCES = ("mixed_aperture_receiver.py", "short_cfo_raw.py", "short_cfo_refine.py", "short_cfo_refine.inc",
                 "combined_frontier_run.py", "regional_probe_block_binding.py")
BAND = Selection(512, 767, PairInputs(
    Workload("DS30-0340", BULK/"leo-dev/ds30-full-20261121/bindings/DS30-0340.json",
             "fc98b8cc9f9c9083bba9c2a0dac85268dea82e2528687d09f892252410604fac",
             555, 46, 686_440_127, 900_000_000, ("candidate", "stock"), True),
    9, 388, 1795037583783072733,
    "sha256:b7ee63e6113a65f1908832d198d84a9aff167458eb64535bac6f403a8a3818a1",
    "sha256:11725255cb210e62d3f1d558a09a111aa4606a89241c4d079c5c7c06d8766320",
))


def receiver_configuration():
    from full_short_run import RECIPE_SHA, checked_recipe
    from leo.contracts.digests import canonical_digest

    receiver = recipe(checked_recipe(), RECIPE_SHA)
    return dict(detector_recipe_sha256=canonical_digest(receiver), recipe=receiver, curvature_certificate=True)


def sealed(root, order):
    return seal(root, order) | {"preflight.json": sha((root/"preflight.json").read_bytes())}


def launch(root, selected=BAND):
    from aperture_trial import write
    from short_raw_diagnostic import pairs

    checked(PROTOCOL, PROTOCOL_SHA)
    picked = selection(selected, checkout=BASE, protocol_sha256=PROTOCOL_SHA)
    inputs = selected.inputs
    recording, manifests, total, libraries, residency, env = configuration(
        root, inputs, selection=picked, base=BASE, route_flags=COMBINED_FLAGS, extra_sources=EXTRA_SOURCES,
        extra_libraries=(("cfo_refinement", LIBRARY, LIBRARY_SHA256),), receiver_configuration=receiver_configuration(),
    )
    order = inputs.workload.order
    commands = {mode: command(mode, root, recording, libraries, pairs.NAMED_V3) for mode in order}
    candidate = commands["candidate"]
    candidate[2] = WRAPPER
    candidate.extend((CURVATURE, CFO_FLAG, libraries["cfo_refinement"]))
    write(root/"preflight.json", receiver_preflight(root, candidate, env, capabilities=(CURVATURE, "--exact-graph-reuse")))
    condition(root, manifests, total, residency, inputs)
    for mode in order:
        measure_mode(root, mode, commands[mode], env, residency)
    write(root/"prediction-seal.json", sealed(root, order))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    launch(cli.parse_args().root)
