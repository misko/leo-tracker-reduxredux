"""Measure the regional solution after assigning a single antenna to each channel."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

from leo.contracts.algo08_region import Algo08Region
from leo.operations.tle_archive import TleArchiveReader
from solver_trial import measure
from leo.analysis.localization_v3 import family_cavity
from tools.pipeline_eval.variants.experimental.channel_lane import project, time_arcs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("native", "archive", "assets", "region"):
        parser.add_argument(name, type=Path)
    parser.add_argument("digest")
    parser.add_argument("flip", type=int, choices=(0, 1))
    parser.add_argument("--policy", default="one-antenna-per-channel",
                        choices=("all", "one-antenna-per-channel", "stereo-alternate-channels", "first-last-quarters"))
    args = parser.parse_args()
    raw = args.native.read_bytes()
    if sha256(raw).hexdigest() != args.digest.removeprefix("sha256:"):
        raise ValueError("Saved detections differ from control")
    original = json.loads(raw)
    if args.policy == "first-last-quarters" and args.flip != 0:
        parser.error("The time-only schedule has no antenna assignment")
    if args.policy == "all":
        candidate = original
    elif args.policy == "first-last-quarters":
        candidate = time_arcs(original)
    else:
        candidate = project(original, args.flip, args.policy)
    region = Algo08Region.parse(json.loads(args.region.read_bytes()))
    cpu, wall = process_time(), perf_counter()
    families = {}
    nominate = family_cavity.nominate_families

    def observe(signed):
        for row, window in zip(signed["base"].rows, signed["base"].slices, strict=True):
            points = int(signed["keep"][window].sum())
            if points:
                index = str(row["candidate_index"])
                families[index] = families.get(index, 0) + points
        return nominate(signed)

    try:
        with patch.object(family_cavity, "nominate_families", observe):
            result = measure("combined", candidate, TleArchiveReader(args.archive), args.assets, region)
    except (ValueError, AssertionError) as exc:
        result = dict(cpu_s=process_time()-cpu, wall_s=perf_counter()-wall, evidence=None,
                      decision=dict(status="failed", reason=f"{type(exc).__name__}: {exc}"))
    result["input"] = dict(parent_sha256=args.digest, policy=args.policy, flip=args.flip, region=region.document(),
                           assigned_windows=candidate["provenance"]["window_count"])
    result["points_per_curved_family_before_cavity"] = sorted(families.values(), reverse=True)
    for label, doc in (("all", original), ("selected", candidate)):
        probes = doc["source"]["probes"]
        result["input"][label] = dict(lanes=len(probes), factors=sum(len(p["candidates"]) for p in probes))
    result["input"]["warmup_lanes"] = candidate["provenance"].get("warmup_lanes", 0)
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
