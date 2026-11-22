"""Run one stock predictive add-back and audit the selected evidence by identity."""

import argparse
from contextlib import nullcontext
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from time import process_time
from unittest.mock import patch

from PIL import Image

from leo.contracts.algo08_region import Algo08Region
from leo.operations.tle_archive import TleArchiveReader
from leo.presentation.fast_standard_analysis import render
from solver_trial import measure
from tools import algo08_position
from tools.pipeline_eval.variants import algo08_collapsed_linear


def inventory(arm, entries):
    result = {}
    by_track = {entry["component"]: entry for entry in entries}
    for role, rows in (("curved", arm["gates"]["tracks"]), ("predictive", arm.get("linear_gates", []))):
        for track in rows:
            norad = track.get("norad")
            if norad is None:
                entry = by_track[track["component"]]
                if track["observation_ids"] != entry["observation_ids"]:
                    raise ValueError("Predictive gate identities differ from its selected entry")
                norad = entry["norad"]
            for oid in track["observation_ids"]:
                if oid in result:
                    raise ValueError("Duplicate published observation in the evidence audit")
                result[oid] = dict(norad=int(norad), component=track["component"], role=role)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("control", "linear"))
    for name in ("native", "archive", "assets", "region"):
        parser.add_argument(name, type=Path)
    parser.add_argument("native_sha256")
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()
    raw = args.native.read_bytes()
    if sha256(raw).hexdigest() != args.native_sha256.removeprefix("sha256:"):
        raise ValueError("Native detections differ from their declared digest")
    offer = Algo08Region.parse(json.loads(args.region.read_bytes()))
    original_packet = algo08_position.selected_packet
    scientific_packet, selected, selected_entries, curved = None, None, None, None

    def selected_packet(prepared, signed, fit):
        nonlocal scientific_packet, selected, selected_entries
        if fit is None:
            selected, selected_entries = signed["arms"], signed["entries"]
        else:
            selected = fit["policy_arms"]
            selected_entries = fit["selected"]["entries"] if fit["accepted"] else fit["baseline_entries"]
        scientific_packet = original_packet(prepared, signed, fit)
        return scientific_packet

    def record_curved(signed):
        nonlocal curved
        curved = signed["arms"]

    binding = nullcontext() if args.mode == "control" else algo08_collapsed_linear.binding(record_curved)
    with binding, patch.object(algo08_position, "selected_packet", selected_packet):
        result = measure("combined", json.loads(raw), TleArchiveReader(args.archive), args.assets, offer)
    result.update(mode=args.mode, native_sha256=args.native_sha256, region=offer.document())
    if selected is not None:
        result["selected_owner_rows"] = {arm: inventory(record, selected_entries)
                                         for arm, record in selected.items()}
        for arm, owners in result["selected_owner_rows"].items():
            original_owners = {row["observation_id"]: row["norad"]
                               for row in scientific_packet["rows"][arm]}
            if original_owners != {oid: row["norad"] for oid, row in owners.items()}:
                raise ValueError("Owner audit differs from standard plotted evidence")
    if curved is not None:
        result["curved_incumbent_rows"] = {arm: inventory(record, []) for arm, record in curved.items()}
    if args.render and scientific_packet is not None:
        began = process_time()
        figures = render(scientific_packet, title="Saved detector evaluation")
        result["render_cpu_s"] = process_time() - began
        for payload in figures.values():
            Image.open(BytesIO(payload)).verify()
        result["verified_figures"] = sorted(figures)
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
