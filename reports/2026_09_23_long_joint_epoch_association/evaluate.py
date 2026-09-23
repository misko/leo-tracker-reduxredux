"""Post-seal fixed-identity evaluation of every joint refinement arm."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from refine import digest, load


def verify_sources(source, helper, single, refinement, protocol):
    expected = {"helper": helper, "single": single, "tool": refinement, "protocol": protocol}
    for name, path in expected.items():
        if source["bindings"][name] != digest(path):
            raise ValueError(f"bound {name} source changed")


def run(args):
    if args.output.exists():
        raise FileExistsError("fresh results file required")
    source = json.loads(args.inference.read_text())
    if (
        digest(args.inference).removeprefix("sha256:")
        != args.inference.with_suffix(".sha256").read_text().strip()
    ):
        raise ValueError("inference seal mismatch")
    verify_sources(
        source,
        args.helper,
        args.single,
        Path(__file__).with_name("refine.py"),
        Path(__file__).with_name("PROTOCOL.md"),
    )
    conditional = json.loads(args.conditional_inference.read_text())
    if source["bindings"]["conditional_inference"] != digest(args.conditional_inference):
        raise ValueError("conditional inference changed")
    if (
        digest(args.conditional_inference).removeprefix("sha256:")
        != args.conditional_inference.with_suffix(".sha256").read_text().strip()
    ):
        raise ValueError("conditional seal mismatch")
    for binding in conditional["bindings"]["caches"]:
        root = args.cache_root / binding["session_id"]
        if (
            digest(root / "cache_receipt.json") != binding["receipt"]
            or digest(root / "state_cache.npz") != binding["cache"]
        ):
            raise ValueError("bound cache changed")
    helper, single = load(args.helper, "eval_helper"), load(args.single, "eval_single")
    for arm in source["arms"]:
        selected = [
            {
                "session_id": sid,
                "tracks": [row for row in arm["fixed_tracks"] if row["session_id"] == sid],
            }
            for sid in source["session_ids"]
        ]
        tracks, _ = helper.prepare(single, args.cache_root, source["session_ids"], selected)
        point = (arm["latitude_deg"], arm["longitude_deg"])
        held = helper.score(single, tracks, point, arm["taus_s"], arm["scale_s"], True)
        if not np.isclose(
            held["penalized_objective_rmse_hz"],
            arm["penalized_objective_rmse_hz"],
            atol=1e-8,
            rtol=0,
        ):
            raise ValueError("fixed-identity training replay differs from seal")
        total = sum(row["weight_s"] for row in held["rows"])
        for name, cap in (("capped800", 800.0), ("uncapped", np.inf)):
            arm[f"reserved_{name}_rmse_hz"] = float(
                np.sqrt(
                    sum(
                        row["weight_s"] * min(cap, row["evaluation_rms_hz"]) ** 2
                        for row in held["rows"]
                    )
                    / total
                )
            )
        arm["reference_error_km"] = single.haversine_km(point, single.REFERENCE)
    source["reference_coordinate"] = list(single.REFERENCE)
    source["evaluation_tool"] = digest(__file__)
    source["inference_seal"] = digest(args.inference)
    raw = json.dumps(source, indent=2, sort_keys=True) + "\n"
    args.output.write_text(raw)
    args.output.with_suffix(".sha256").write_text(hashlib.sha256(raw.encode()).hexdigest() + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("inference", "conditional-inference", "helper", "single", "cache-root", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
