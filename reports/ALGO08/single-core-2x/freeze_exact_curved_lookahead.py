"""Compose the reviewed exact detector, curved design and next-member hint."""

import argparse
from pathlib import Path

from tools.pipeline_eval.qualification.experimental_publication import (
    CURVED_DESIGN_SHA256,
    CURVED_DESIGN_SOURCE,
    MEMBER_LOOKAHEAD_SHA256,
    MEMBER_LOOKAHEAD_SOURCE,
)
from tools.pipeline_eval.qualification.freeze_publication import ENTRY

from .freeze_curved_design import (
    SAVED_SHA256,
    SAVED_SOLVES,
    publication_targets,
    release_solver_source_pins,
    stage_successor,
    verify_saved_solves,
)
from .screened_stock_salvage_trial import digest, read, require_spec
from .screened_tiled_graph_trial import MEASUREMENTS, write
from .sparse_fir_successor import RECEIVER, SOURCE

PARENT = "sha256:a546069457b70491949d3b500f65cffd26939e693d9079ddc6b37a55d26e2afa"
RECEIVER_SHA256 = "2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5"
ENTRY_SHA256 = "2a6fb84d59d1fba485d270b38a2a0553b59c1977373520dcce0e3488c6859690"
TRANSFER = MEASUREMENTS / "fractional-score-transfer.json"
TRANSFER_SHA256 = "41baffea57fa8203849b660af55d0be5a7fda10095d0ce5c4e7bed0d9298c5e9"
INGRESS = MEASUREMENTS / "full-member-lookahead.json"
INGRESS_SHA256 = "58f2967e945532efc998126f4c078bf11d484c89f6a1d8c395a8c9ba8f9b7361"
PREFIX_BYTES = 16 * 1024**2


def verify_receiver_transfer(path):
    if digest(path) != TRANSFER_SHA256:
        raise ValueError("Receiver transfer evidence differs from the reviewed comparison")
    evidence = read(path)
    if (evidence["all_factor_specification"] != PARENT
            or evidence["preferred_receiver"] != "all-factor exact"
            or evidence["measured"].keys() != {"DS30-0008", "public-south"}):
        raise ValueError("Expected the two matched all-factor exact prefix controls")
    for row in evidence["measured"].values():
        if (row["binaries"]["exact"] != RECEIVER_SHA256 or row["visit_count"] != 128
                or row["probe_sha256"]["exact"] != row["probe_sha256"]["deployed"]):
            raise ValueError("All-factor exact prefix differs from deployed probe bytes")


def verify_ingress_trial(path, hasher):
    if digest(path) != INGRESS_SHA256:
        raise ValueError("Read-ahead evidence differs from the reviewed private trial")
    evidence = read(path)
    cold, warm = (evidence["results"][kind]["pairs"] for kind in ("cold", "warm"))
    if (evidence["hasher_sha256"] != hasher or len(cold) != 3 or len(warm) != 2
            or evidence["hint_prefix_bytes"] != PREFIX_BYTES):
        raise ValueError("Read-ahead trial differs from the paired ingress and prefix geometry")
    matching = ("raw_authority", "acquisition_sha256", "probes_sha256", "selected", "input_blocks")
    for pair in [*cold, *warm]:
        control, hint = pair["control"], pair["hint"]
        if (any(control[field] != hint[field] for field in matching)
                or control["hints"] is not None or hint["hints"]["attempts"] != 2
                or hint["hints"]["submitted"] != 2
                or hint["hints"]["submitted_bytes"] != 2 * PREFIX_BYTES):
            raise ValueError("Read-ahead changed a matched acquisition or its hint budget")


def freeze(parent, output, receipt, launcher_source=None):
    parent, output, receipt = publication_targets(parent, output, receipt)
    require_spec(parent, PARENT)
    original = read(parent / "spec.json")
    if (Path(original["detector"]) != parent / RECEIVER
            or original["detector_sha256"] != RECEIVER_SHA256
            or digest(parent / RECEIVER) != RECEIVER_SHA256
            or original["sources"].get(str(RECEIVER)) != RECEIVER_SHA256
            or original.get("fractional_score_selection", False)
            or original["ingress"] != "paired-sha256" or original["schedule"] != "all"):
        raise ValueError("Expected the frozen all-factor exact parent with paired SHA-256 ingress")
    verify_receiver_transfer(TRANSFER)
    verify_ingress_trial(INGRESS, original["paired_sha256"]["sha256"])
    verify_saved_solves(SAVED_SOLVES)
    release_pins = release_solver_source_pins()
    sources = {path: (SOURCE / path, pin) for path, pin in (
        (ENTRY, ENTRY_SHA256), (CURVED_DESIGN_SOURCE, CURVED_DESIGN_SHA256),
        (MEMBER_LOOKAHEAD_SOURCE, MEMBER_LOOKAHEAD_SHA256),
    )}
    if launcher_source is not None:
        sources[ENTRY] = launcher_source, ENTRY_SHA256
    spec, fingerprint, changed = stage_successor(
        parent, output, original, {"curved_design": True, "member_lookahead": True}, sources,
    )
    write(receipt, dict(
        specification=fingerprint, parent_specification=PARENT, spec=spec,
        changed_files=changed, release_solver_sources=release_pins,
        receiver_sha256=RECEIVER_SHA256,
        evidence={path.name: sha for path, sha in (
            (TRANSFER, TRANSFER_SHA256), (INGRESS, INGRESS_SHA256), (SAVED_SOLVES, SAVED_SHA256),
        )},
    ))
    return spec


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("parent", "output", "receipt"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--launcher-source", type=Path,
                        help="Use a historical launcher with the reviewed byte digest")
    freeze(**vars(parser.parse_args()))
