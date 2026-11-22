"""Compare the exact full-sky cavity table on saved verified detections."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from unittest.mock import patch

from leo.analysis.localization_v3 import family_cavity
from leo.application.localization_v3_engine import _json_value
from leo.contracts.algo08_region import Algo08Region
from leo.operations.tle_archive import TleArchiveReader
from solver_trial import measure
from tools.pipeline_eval.variants.algo08_cavity_projection import shared_projection


def audit():
    coarse = sha256()
    masks = sha256()
    nominations = []
    scores, data = family_cavity.coarse_phase_scores, family_cavity.family_data

    def score(*args, **kwargs):
        terms = scores(*args, **kwargs)
        for key, value in sorted(terms.items()):
            coarse.update(repr((key, value.shape, value.dtype.str)).encode())
            coarse.update(value.tobytes())
        return terms

    def exclude(context, family):
        result = data(context, family)
        masks.update(repr((family, result["held_ids"])).encode())
        masks.update(result["calibration_mask"].tobytes())
        return result

    def summarize():
        return dict(coarse_terms_sha256=coarse.hexdigest(), held_masks_sha256=masks.hexdigest(),
                    nominations_sha256=sha256(json.dumps(nominations, default=_json_value,
                                                          sort_keys=True).encode()).hexdigest())

    return score, exclude, nominations.append, summarize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("control", "shared"))
    for name in ("native", "archive", "assets", "region"):
        parser.add_argument(name, type=Path)
    parser.add_argument("native_sha256")
    args = parser.parse_args()
    raw = args.native.read_bytes()
    if sha256(raw).hexdigest() != args.native_sha256.removeprefix("sha256:"):
        raise ValueError("Native detections differ from their declared digest")
    offer = Algo08Region.parse(json.loads(args.region.read_bytes()))
    coarse, family, collect, finish = audit()
    with (
        shared_projection(enabled=args.mode == "shared", observe=collect) as metrics,
        patch.object(family_cavity, "coarse_phase_scores", coarse),
        patch.object(family_cavity, "family_data", family),
    ):
        result = measure("combined", json.loads(raw), TleArchiveReader(args.archive), args.assets, offer)
    result.update(mode=args.mode, projection_counters=metrics, cavity_audit=finish(),
                  native_sha256=args.native_sha256, region=offer.document())
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
