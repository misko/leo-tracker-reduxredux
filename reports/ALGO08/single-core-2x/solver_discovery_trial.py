"""Compare all-catalogue discovery on one saved verified detector receipt."""

import argparse
from functools import partial
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

import numpy as np

from leo.analysis.localization_v3 import discovery, position
from leo.application.localization_v3_engine import _json_value
from leo.contracts.algo08_region import Algo08Region
from leo.operations.tle_archive import TleArchiveReader
from tools import algo08_position
from tools.pipeline_eval.variants import algo08_causal_reuse, v5_core
from tools.pipeline_eval.variants.algo08_dense_discovery import dense_discovery


MODES = {
    "stock": {},
    "scratch": {"use_scratch": True},
    "repeat": {"reuse_associations": True},
    "combined": {"use_scratch": True, "reuse_associations": True},
}


def json_digest(data):
    return sha256(json.dumps(data, default=_json_value, sort_keys=True).encode()).hexdigest()


def rank(scan, mode):
    residual = position.NormalPosition.residual
    scores = []

    def record(model, point):
        values = residual(model, point)
        scores.append(float(values @ values))
        return values

    cpu, wall = process_time(), perf_counter()
    with (
        dense_discovery(scan, **MODES[mode]) as usage,
        patch.object(position.NormalPosition, "residual", record),
    ):
        ranked = v5_core.ranked_initial_nodes(scan)
    result = dict(cpu_s=process_time() - cpu, wall_s=perf_counter() - wall, **usage)
    result.update(scores=scores, ranked_sha256=json_digest(ranked),
                  owner_order_sha256=json_digest([discovery.signature(node) for node in ranked]))
    return ranked, result


def audit_curves(scan, mode):
    curve = scan.curve
    digest = sha256()
    curves = candidates = 0

    def record(index, *args, **kwargs):
        nonlocal curves, candidates
        terms = curve(index, *args, **kwargs)
        digest.update(str(index).encode())
        for name in ("alias", "bias", "cost", "rms", "passing", "residual", "innovations"):
            matrix = terms[name]
            digest.update(repr((name, matrix.shape, matrix.dtype.str)).encode())
            digest.update(matrix.tobytes())
        curves += 1
        candidates += len(terms["cost"])
        return terms

    with patch.object(scan, "curve", record), dense_discovery(scan, **MODES[mode]):
        v5_core.ranked_initial_nodes(scan)
    return dict(curves=curves, candidates=candidates, terms_sha256=digest.hexdigest())


def fit(scan, ranked):
    started = process_time()
    decision, branches = v5_core.fit_initial_nodes(scan, ranked[:3])
    arm_cpu = {"c0": process_time() - started}
    choice = decision["choices"][0]
    started = process_time()
    _, fitted, _ = position.refreshed(scan, scan.radio_sigma_hz, choice["node"], "fitted_c")
    arm_cpu["fitted_c"] = process_time() - started
    return dict(cpu_s=arm_cpu, branches=branches, c0_sha256=json_digest(decision),
                fitted_c_sha256=json_digest(fitted),
                fitted_c_offset_km=fitted["parameters"], fitted_c_score=fitted["score"])


def verify(results):
    for group, fields in (
        ("rankings", ("scores", "ranked_sha256", "owner_order_sha256")),
        ("fits", ("branches", "c0_sha256", "fitted_c_sha256")),
        ("audits", ("curves", "candidates", "terms_sha256")),
    ):
        rows = results[group]
        if "stock" in rows:
            for mode, values in rows.items():
                for key in fields:
                    if values[key] != rows["stock"][key]:
                        raise ValueError(f"{mode} changed {group}.{key}")


def measure(native, archive, assets, offer, modes, *, audits):
    reuse = partial(algo08_causal_reuse.prepare, algo08_position.prepare_native_scan, statistics={})
    results = {}

    def infer(prepared, region, bound, stages, **kwargs):
        if prepared["status"] != "inputs_prepared":
            raise ValueError(prepared["status"])
        noise = sha256((json.dumps(prepared["noise"], sort_keys=True) + "\n").encode()).hexdigest()
        start = process_time()
        scan = v5_core.scan_context(prepared, region, noise, bound, "previous")
        results.update(context_cpu_s=process_time() - start, catalogue=len(scan.norads),
                       curved=len(scan.curved), observations=len(prepared["tracks"]["observations"]),
                       rankings={}, fits={}, audits={})
        for mode in modes:
            ranked, results["rankings"][mode] = rank(scan, mode)
            if mode in ("stock", "combined"):
                results["fits"][mode] = fit(scan, ranked)
        if audits:
            for mode in ("stock", "scratch"):
                results["audits"][mode] = audit_curves(scan, mode)
        return dict(status="initial_complete")

    with patch.object(algo08_position, "prepare_native_scan", reuse), patch.object(v5_core, "infer", infer):
        _, _, results["orbit_policy"] = algo08_position.solve(native, archive, assets, offer)
    verify(results)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("native", "archive", "assets", "region"):
        parser.add_argument(name, type=Path)
    parser.add_argument("native_sha256")
    parser.add_argument("--modes", nargs="+", choices=MODES, default=tuple(MODES))
    parser.add_argument("--audit-curves", action="store_true")
    args = parser.parse_args()
    raw = args.native.read_bytes()
    if sha256(raw).hexdigest() != args.native_sha256.removeprefix("sha256:"):
        raise ValueError("Native detections differ from their declared digest")
    region = Algo08Region.parse(json.loads(args.region.read_bytes()))
    receipt = measure(json.loads(raw), TleArchiveReader(args.archive), args.assets, region,
                      args.modes, audits=args.audit_curves)
    receipt.update(native_sha256=args.native_sha256, region=region.document())
    print(json.dumps(receipt, default=_json_value, allow_nan=False))


if __name__ == "__main__":
    main()
