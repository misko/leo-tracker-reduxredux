"""Qualify the guarded proof in the complete saved DS30-0008 publication."""

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
from time import perf_counter
from unittest.mock import patch

from aperture_trial import ARMS, RELEASE, archive_identity, read, write
from cold_track_row_transfer import GEOGRAPHIC, numeric_grid
from dense_full_short_crossover import file_sha
from dense_geographic_trial import host
import full_short_run
from regional_dense_pair import reference
from regional_probe_block import OrderedProbeScores, ProbeBlock
from regional_track_scores import TrackScores


HERE = Path(__file__).resolve().parent
ORDER = ("guarded", "stock")
RECEIPTS = "joint-research-receipt.json", "full-short-recipe.json"


@contextmanager
def guarded_projection(single, stock, block, original_projection):
    from dense_geographic_projection import checked_runtime
    from tools.pipeline_eval.variants.experimental.regional_veto_short_circuit import evaluate_terminal

    kernel, _ = checked_runtime()

    def evaluate(prepared, catalogue, region):
        points, original, meta = kernel._prepare_probe_scores(prepared, catalogue, region)
        scalar = TrackScores(stock, original)
        native = ProbeBlock(block, scalar)
        ordered = OrderedProbeScores(points, region.width_km, native, scalar, guaranteed_only=True)
        decision = evaluate_terminal(points, region.width_km,
                                     lambda point: ordered(point)["receiver_scores"])
        counts.update(block_positions=native.computed, block_calls=native.calls,
                      scalar_positions=scalar.native, fallbacks=scalar.fallbacks + int(ordered.failed),
                      consumed=ordered.cursor)
        if ordered.cursor != native.computed + scalar.native:
            raise ValueError("Guarded proof counted extra probe work")
        return dict(decision, **meta)

    with (original_projection(single) as counts,
          patch.object(kernel, "evaluate_veto", evaluate)):
        yield counts


def child(block, argv):
    if block == "stock":
        full_short_run.main(argv)
        return
    original = full_short_run.geographic_projection

    def project(single, track):
        return guarded_projection(single, track, Path(block), original)

    with patch.object(full_short_run, "geographic_projection", project):
        full_short_run.main(argv)


def invoke(mode, block, args):
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    start = perf_counter()
    subprocess.run(
        [sys.executable, "-BPs", str(Path(__file__)), "child",
         str(block) if mode == "guarded" else "stock", *args],
        check=True, timeout=100,
    )
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    return dict(elapsed_s=perf_counter() - start,
                cpu_s=(after.ru_utime - before.ru_utime) + (after.ru_stime - before.ru_stime))


def run(output, proof, stock, block):
    machine = host()
    source = read(proof / "source-lock.json")
    frozen = source["authority"]["files"]
    names = (stock.resolve(), block.resolve(), GEOGRAPHIC.resolve(), HERE / "regional_probe_block.py")
    if any(file_sha(p) != frozen[str(p)] for p in names):
        raise ValueError("Guarded source or native library differs from the proof")
    measured = {case: read(proof / f"{case}.json") for case in ("dense", "south-far")}
    for case, limit in (("dense", .9), ("south-far", 1.05)):
        data = measured[case]
        if (data["source_sha256"] != file_sha(proof / "source-lock.json")
                or data["median_ratios"]["cpu_s"] > limit
                or any(r["excess"] or r["visited"] != r["evaluated"] for r in data["runs"])
                or {r["arm"] for r in data["runs"]} != {"stock", "guarded"}):
            raise ValueError(f"The guarded proof did not qualify on {case}")
    saved = source["bindings"]["dense"]
    raw = reference()["raw"]
    binding, identity = raw["binding"], raw["holder"]
    archive, packet, region = Path(saved["archive"]["root"]), Path(saved["detection"]), Path(binding["region"])
    if (archive_identity(archive) != saved["archive"]
            or file_sha(packet) != saved["native_pin"].removeprefix("sha256:")
            or saved["native_pin"] != raw["raw_native_sha256"]
            or file_sha(region) != identity["offer_source_sha256"] or read(region) != saved["offer"]):
        raise ValueError("Dense saved input changed since the proof")
    recording = binding["command"][binding["command"].index("--recording") + 1]
    output.mkdir()
    os.environ["MPLCONFIGDIR"] = str(output / "fonts")
    subprocess.run([RELEASE / "venv/bin/python", "-Bc",
                    "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"], check=True)
    flags = ["--recording", recording, "--region", region, "--archive", archive,
             "--saved", packet, "--saved-digest", saved["native_pin"], "--track-graph", "installed",
             "--geographic-library", GEOGRAPHIC, "--regional-track-library", stock,
             "--reuse-cold-track-rows", "--reuse-grid-phase-states"]
    lock = dict(
        order=ORDER, machine=machine, binding=saved, command=list(map(str, flags)),
        recording_authority=identity["raw_authority"],
        files={str(p): file_sha(p) for p in (*names, Path(__file__), Path(full_short_run.__file__),
            region, *(proof / n for n in ("source-lock.json", "dense.json", "south-far.json")))},
    )
    write(output / "source-lock.json", lock)
    outputs = {}
    for mode in ORDER:
        destination = output / mode
        clocks = invoke(mode, block, [*flags, "--output", destination])
        value = read(destination / RECEIPTS[0])
        outputs[mode] = dict(process=clocks, files={n: file_sha(destination / n) for n in RECEIPTS},
                             expected_evidence=value["evidence"])
        print(mode, clocks, flush=True)
    write(output / "prediction-lock.json", dict(outputs=outputs, source_sha256=file_sha(output / "source-lock.json")))


def score(output):
    from aperture_score import distance_km, references
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.contracts.fast_standard_analysis import PLOTS
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    seal = read(output / "prediction-lock.json")
    source = output / "source-lock.json"
    lock = read(source)
    if seal["source_sha256"] != file_sha(source):
        raise ValueError("The publication input seal changed")
    binding = lock["binding"]
    rows, products = {}, {}
    ref = reference()
    for mode in ORDER:
        path = output / mode
        sealed = seal["outputs"][mode]
        if any(file_sha(path / name) != digest for name, digest in sealed["files"].items()):
            raise ValueError("A published report changed after sealing")
        report = read(path / RECEIPTS[0])
        receipt, solve = report["receipt"], report["solve"]
        identifier = receipt["run_id"]
        store = FastStandardAnalysisStore(path)
        grid, route = store.position_grid(identifier), store.position_path(identifier)
        terminal = read(path / "fast-scan-automatic-work" / identifier / "terminal.json")
        actual = json.loads(json.dumps(artifacts(path, receipt)))
        proof, = report["early_regional"]
        work = solve["geographic_projector"]
        if mode == "guarded":
            good_work = (work["block_positions"] == 24 and work["scalar_positions"] == 1
                         and work["consumed"] == 25 and work["block_calls"] == 6
                         and not work["fallbacks"])
        else:
            good_work = work.get("track_score_native") == 25 and not work.get("track_score_fallbacks")
        science = {key: canonical_digest(
            {k: v for k, v in data.items() if k not in ("binding", "elapsed_seconds")})
            for key, data in (("grid", grid), ("path", route))}
        if (not good_work or terminal["native_sha256"] != binding["native_pin"]
                or terminal["region"] != binding["offer"] or receipt["decision"] != "complete"
                or canonical_digest(terminal) != receipt["terminal_sha256"]
                or terminal["arms"] != ref["arms"] or report["selected_rows"] != ref["selected_rows"]
                or not grid["complete"] or grid["evaluated_points"] != ref["grid_points"]
                or science != ref["science"] or actual != sealed["expected_evidence"]
                or set(actual["images"]) != set(PLOTS)):
            raise ValueError(f"Full saved publication comparison failed for {mode}")
        products[mode] = dict(terminal=terminal, grid=numeric_grid(grid), path=route,
                              images=actual["images"], proof=proof["result"])
        rows[mode] = dict(process=sealed["process"], solve_cpu_s=solve["cpu_s"],
                          proof_cpu_s=proof["cpu_s"], native_work=work, products=products[mode])
    if products["guarded"] != products["stock"]:
        raise ValueError("Published numerical and PNG outputs differ")
    truth = references()["DS30-0008"]
    geographic_error = {a: distance_km(products["stock"]["terminal"]["arms"][a]["latlon"], truth)
                        for a in ARMS}
    return dict(source=lock, prediction_sha256=file_sha(output / "prediction-lock.json"),
                science_exact=True, geographic_error_km=geographic_error, runs=rows)


if __name__ == "__main__":
    if sys.argv[1] == "child":
        child(sys.argv[2], sys.argv[3:])
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        operation = parser.add_subparsers(dest="mode", required=True)
        execute = operation.add_parser("run")
        for name in ("output", "proof", "stock", "block"):
            execute.add_argument(name, type=Path)
        verify = operation.add_parser("score")
        verify.add_argument("output", type=Path)
        verify.add_argument("receipt", type=Path)
        args = parser.parse_args()
        if args.mode == "run":
            run(args.output, args.proof, args.stock, args.block)
        else:
            write(args.receipt, score(args.output))
