"""Run an installed phase release with the stock Graph scaffold kept intact."""

import hashlib
import json
import runpy
import sys
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch


def checked(path, expected):
    if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
        raise ValueError("scaffold worker source or data differs from its plan")


def run(plan):
    attach_path = Path(plan["attach_path"])
    checked(attach_path, plan["attach_sha256"])
    checked("donors.json", plan["donor_sidecar_sha256"])
    sidecar = json.loads(Path("donors.json").read_bytes())
    algorithm = runpy.run_path(str(attach_path))
    root = Path(plan["install"])
    sys.path.insert(0, str(root))
    from leo.analysis.localization_v3 import scan

    from leo.application import localization_v3

    original_prepare, original_curvature = (
        localization_v3.prepare_native_scan,
        scan.active_curvature,
    )
    allowed = {}

    def locked_curvature(track):
        key = track.get("key")
        return allowed[key] if key in allowed else original_curvature(track)

    def prepare(document, archive, config, **options):
        begin_wall, begin_cpu = perf_counter(), process_time()
        stock = original_prepare(document, archive, config, **options)
        prep_wall, prep_cpu = perf_counter() - begin_wall, process_time() - begin_cpu
        if stock["status"] != "inputs_prepared":
            return stock
        if config.association_sigma * config.noise_sigma_hz != 450.0:
            raise ValueError("attachment gate differs from the installed native Graph threshold")
        began_wall, began_cpu = perf_counter(), process_time()
        tracks, proof = algorithm["attach"](
            stock["tracks"], sidecar["lanes"], sidecar["donors"], config.alias_spacing_hz
        )
        added_ids = {item["id"] for item in proof["attachments"]}
        noise = algorithm["extend_noise"](
            stock["noise"],
            [row for row in tracks["observations"] if row["observation_id"] in added_ids],
        )
        curved = set(proof["stock_curvature_keys"])
        allowed.update((t["key"], t["key"] in curved) for t in tracks["tracks"])
        if list(allowed) != [t["key"] for t in stock["tracks"]["tracks"]]:
            raise ValueError("stock discovery groups changed")
        norads = stock["sky"]["bank"]["norad"]
        proof.update(
            stock_sky_norads=len(norads),
            stock_sky_norad_sha256=hashlib.sha256(norads.tobytes()).hexdigest(),
            stock_preparation_wall_s=prep_wall,
            stock_preparation_cpu_s=prep_cpu,
            attachment_wall_s=perf_counter() - began_wall,
            attachment_cpu_s=process_time() - began_cpu,
            capture_duration_s=sidecar["duration_s"],
            unchanged_prepared_fields=sorted(k for k in stock if k not in ("tracks", "noise")),
            original_noise_weights=len(stock["noise"]["per_observation_noise_sigma_hz"]),
            added_noise_weights=len(added_ids),
        )
        Path("scaffold-proof.json").write_text(json.dumps(proof, allow_nan=False) + "\n")
        sidecar.clear()
        return dict(stock, tracks=tracks, noise=noise)

    with (
        patch.object(localization_v3, "prepare_native_scan", prepare),
        patch.object(scan, "active_curvature", locked_curvature),
    ):
        runpy.run_path(str(root / "__main__.py"), run_name="__main__")


if __name__ == "__main__":
    run(json.loads(Path("scaffold-runtime.json").read_bytes()))
