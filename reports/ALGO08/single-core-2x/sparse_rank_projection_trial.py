"""Audit dense and sparse all-observation ranking in the same frozen ad417 composition."""

import argparse
import json
import os
import runpy
import subprocess
from contextlib import ExitStack, nullcontext
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from time import process_time
from unittest.mock import patch

import numpy as np

HERE = Path(__file__).resolve().parent
MEASURE = HERE / "measurements"
SOURCE = HERE.parents[2] / "tools/pipeline_eval/variants/algo08_sparse_rank_projection.py"
SCAN_SHA = "49f1f2e9d73b967f694e48033b6d02ea2e1d66285f7941c4f282f5b238e79f89"
ARMS = ("c0", "fitted_c")


def same_science(reference, candidate):
    fields = ("cost_and_gates", "full_time_visibility", "scores", "ranked", "curves", "candidates")
    return all(reference[name] == candidate[name] for name in fields)


def rank(prepared, region, bound, mode):
    from leo.analysis.localization_v3 import position
    from leo.application.localization_v3_engine import _json_value
    from tools.pipeline_eval.variants import v5_core

    native = json.dumps(prepared["noise"], sort_keys=True) + "\n"
    digest = sha256(native.encode()).hexdigest()
    scan = v5_core.scan_context(prepared, region, digest, bound, "previous")
    stock_curve, stock_predictions, stock_residual = (
        scan.curve, scan.predictions, position.NormalPosition.residual,
    )
    fields = ("cost", "bias", "alias", "rms", "passing")
    inputs, horizons = sha256(), sha256()
    scores = []
    metrics = dict(curves=0, candidates=0, audit_cpu_s=0.0)

    def curve(index, *args, **kwargs):
        terms = stock_curve(index, *args, **kwargs)
        start = process_time()
        inputs.update(str(index).encode())
        for key in fields:
            inputs.update(np.ascontiguousarray(terms[key]).view(np.uint8))
        metrics["curves"] += 1
        metrics["candidates"] += len(terms["cost"])
        metrics["audit_cpu_s"] += process_time() - start
        return terms

    class ObservedElevation:
        def __init__(self, plane):
            self.plane = plane

        def __getitem__(self, key):
            selected = self.plane[key]
            start = process_time()
            horizons.update(np.ascontiguousarray(selected.min(axis=1) >= 0).view(np.uint8))
            metrics["audit_cpu_s"] += process_time() - start
            return selected

    def predictions(*args, **kwargs):
        f, e, h = stock_predictions(*args, **kwargs)
        return f, ObservedElevation(e), h

    def residual(problem, point):
        value = stock_residual(problem, point)
        start = process_time()
        scores.append(float(value @ value).hex())
        metrics["audit_cpu_s"] += process_time() - start
        return value

    apply = runpy.run_path(str(SOURCE))["sparse_rank_projection"]
    projection = apply(scan, expected_source_sha256=SCAN_SHA) if mode == "sparse" else nullcontext()
    start = process_time()
    with (projection as counts, patch.object(scan, "curve", curve),
          patch.object(scan, "predictions", predictions),
          patch.object(position.NormalPosition, "residual", residual)):
        ranked = v5_core.ranked_initial_nodes(scan)
    elapsed = process_time() - start
    data = json.dumps(ranked, default=_json_value, sort_keys=True, allow_nan=False)
    return dict(metrics, cpu_s=elapsed, cpu_less_audit_s=elapsed - metrics["audit_cpu_s"],
                cost_and_gates=inputs.hexdigest(), full_time_visibility=horizons.hexdigest(),
                scores=scores, ranked=sha256(data.encode()).hexdigest(),
                nodes=len(ranked), catalogue=len(scan.norads), curved_tracks=len(scan.curved),
                all_tracks=len(scan.tracks), projections=counts)


def worker(native, archive, offer, frozen, output, first):
    from tools.pipeline_eval.variants.experimental import lean_startup

    release_install = lean_startup.install
    result = {}
    order = (first, "sparse" if first == "dense" else "dense")

    def rank_only(prepared, region, bound, _stages, **_kwargs):
        if prepared["status"] != "inputs_prepared" or result:
            raise ValueError("Expected one prepared matched ranking")
        for mode in order:
            result[mode] = rank(prepared, region, bound, mode)
        if not same_science(result["dense"], result["sparse"]):
            raise ValueError("Sparse ranking changed the all-catalogue science")
        return dict(status="ranked", arms={arm: {"latlon": None} for arm in ARMS})

    with ExitStack() as stack, TemporaryDirectory() as directory:
        def install_then_rank():
            release_install()
            from tools import algo08_position

            ordinary = algo08_position.solve

            def solve(*args, **kwargs):
                from tools.pipeline_eval.variants import v5_core

                with patch.object(v5_core, "infer", rank_only):
                    return ordinary(*args, **kwargs)

            stack.enter_context(patch.object(algo08_position, "solve", solve))

        scope = runpy.run_path(str(HERE / "residual_attribution_trial.py"))["worker"]
        stack.enter_context(patch.object(lean_startup, "install", install_then_rank))
        scope(native, frozen / "spec.json", archive, offer, Path(directory) / "output.json")
    output.write_text(json.dumps(dict(order=order, results=result), indent=2))


def run(bench, output):
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.qualification.paired_publication import archive_identity

    from . import covariance_transfer_trial as transfer
    from .complete_family_cavity_trial import verify_archive
    from .screened_stock_salvage_trial import read, require_spec
    from .solver_fused_phase_trial import RELEASE

    frozen = bench / "integration-restored-scout-graph"
    previous = read(MEASURE / "restored-scout-0008-solver-profile.json")
    require_spec(frozen, previous["specification"])
    dense = bench / "restored-graph-profile-0008"
    native, offer = dense / "native.json", dense / "offer.json"
    archive = Path(previous["archive"]["root"])
    if (canonical_digest(read(native)) != previous["native_sha256"]
            or read(offer) != previous["offer"]
            or archive_identity(archive) != previous["archive"]):
        raise ValueError("Dense saved input differs from the measured ad417 profile")
    public = read(MEASURE / "covariance-geographic-transfer.json")
    india = next(r for r in public["rows"] if r["case"] == transfer.INDIA
                 and r["mode"] == "matched-tile")
    site = bench / "portable-v5-geodiverse" / transfer.INDIA
    verify_archive(vars(transfer), india, site)
    if (transfer.digest((site / "native.json").read_bytes()) != india["document_sha256"]
            or read(site / "matched-tile.json") != india["offer"]):
        raise ValueError("India saved input differs from the published control")
    env = dict(os.environ, PYTHONPATH=f"{frozen}:{RELEASE / 'src'}:{RELEASE}",
               OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
    command = [str(RELEASE / "venv/bin/python"), "-BPs", str(Path(__file__).resolve())]
    output.mkdir(parents=True, exist_ok=False)
    controls = {"DS30-0008": (native, archive, offer, "dense"),
                "India": (site / "native.json", site / "tle", site / "matched-tile.json", "sparse")}
    results = {}
    for case, (document, tle, region, order) in controls.items():
        path = output / (case + ".json")
        subprocess.run([*command, *map(str, (document, tle, region, frozen, path, order))],
                       env=env, check=True, timeout=100)
        results[case] = read(path)
    transfer.write(output / "summary.json", dict(
        specification=previous["specification"], dense_native=previous["native_sha256"],
        india_native=india["document_sha256"], variant_sha256=transfer.digest(SOURCE.read_bytes()),
        results=results,
    ))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args().paths
    if len(args) == 2:
        run(*map(Path, args))
    else:
        native, archive, offer, frozen, output, first = args
        worker(*map(Path, (native, archive, offer, frozen, output)), first)
