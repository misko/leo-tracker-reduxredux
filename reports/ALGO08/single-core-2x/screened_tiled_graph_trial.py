"""Check the reviewed native Graph ABI against saved guarded-solver evidence."""

import argparse
import gzip
import json
import os
import runpy
import subprocess
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from leo.contracts.digests import canonical_digest
from tools.pipeline_eval.qualification.freeze_publication import NATIVE_LIBRARIES, freeze
from tools.pipeline_eval.qualification.paired_publication import archive_identity, verify_sources

from .screened_stock_salvage_trial import (
    INTEGRATED_SPEC,
    digest,
    read,
    require_spec,
    science_digest,
)
from .solver_fused_phase_trial import HELPER, RELEASE, saved_inputs

HERE = Path(__file__).resolve().parent
MEASUREMENTS = HERE / "measurements"
GRAPH_SPEC = "sha256:2a55dcaa7938ff5ec152f19b90ed9da02388be82d23a13fb2e8a3bf41a0350d3"
KEYS = ("status", "reason", "arms", "owners", "associated", "orbit_policy")


def changes(parent, successor):
    def options(spec):
        fields = {k: v for k, v in spec.items() if k not in ("sources", "detector", "graph_path")}
        return {k: v["sha256"] if isinstance(v, dict) else v for k, v in fields.items()}

    if (options(parent) != options(successor)
            or any(successor["sources"].get(k) != v for k, v in parent["sources"].items())):
        raise ValueError("Successor changes a non-Graph option or source pin")
    return {k: v for k, v in successor["sources"].items() if k not in parent["sources"]}


def run(bench, pair_path, output, evidence):
    parent = bench / "integration-screened-tiled-finish"
    graph = bench / "integration-covariance-graph"
    require_spec(parent, INTEGRATED_SPEC)
    require_spec(graph, GRAPH_SPEC)
    original = read(parent / "spec.json")
    reviewed = read(graph / "spec.json")
    libraries = (*NATIVE_LIBRARIES.keys(), "paired_sha256")
    options = {k: v for k, v in original.items()
               if k not in ("sources", "detector", "detector_sha256", *libraries)}
    for name in libraries:
        pin = (reviewed if name == "graph_path" else original)[name]
        options[name] = Path(pin["library"]), pin["sha256"]
    new = freeze(HERE.parents[2], output, Path(original["detector"]), original["detector_sha256"],
                 **options)
    added = changes(original, new)
    expected = {k: v for k, v in reviewed["sources"].items()
                if Path(k).name in ("graph-path.so", "graph_path.c", "graph_path.py")}
    if added != expected or len(added) != 3:
        raise ValueError("Successor does not use only the reviewed Graph source and binary")
    verify_sources(output / "reports/ALGO08/single-core-2x/run-candidate", new["sources"])
    write(evidence / "freeze.json", dict(spec=new, specification=canonical_digest(new),
                                       parent_specification=INTEGRATED_SPEC,
                                       graph_specification=GRAPH_SPEC, added_sources=added))

    physical_ref = MEASUREMENTS / "screened-tiled-0374-cpu-budget.json.gz"
    physical = read_compressed(physical_ref)
    covariance = bench / "integration-covariance-posterior"
    pair, _, _, physical_archive, roi, detections = saved_inputs(
        pair_path, covariance, None, expected_spec=physical["parent"]
    )
    if (digest(pair_path) != physical["pair_sha256"] or physical["successor"] != INTEGRATED_SPEC
            or canonical_digest(detections) != physical["native_sha256"]
            or roi != physical["region"] or pair["archive"] != physical["archive"]):
        raise ValueError("DS30-0374 reference does not bind the same detections, offer and archive")
    prior_physical = physical["new_solve"]
    physical_case = solve(output, detections, roi, physical_archive)
    if archive_identity(physical_archive) != physical["archive"]:
        raise ValueError("The physical archive changed during the solve")
    write(evidence / "DS30-0374.json", compare(physical_case, prior_physical, physical_ref, roi,
          physical["native_sha256"], physical["archive"]["snapshots_sha256"]))

    india_ref = MEASUREMENTS / "screened-stock-salvage.json.gz"
    india = read_compressed(india_ref)["sites"]["India"]
    plan, previous = india["plan"], india["guarded"]
    transfer = runpy.run_path(str(HERE / "covariance_transfer_trial.py"))
    verify_archive = runpy.run_path(str(HERE / "complete_family_cavity_trial.py"))["verify_archive"]
    site = bench / "portable-v5-geodiverse" / plan["case"]
    native = site / "native.json"
    if (digest(native) != plan["document_sha256"]
            or read(site / "matched-tile.json") != plan["offer"]):
        raise ValueError("India detections or offer do not match the released input")
    verify_archive(transfer, plan, site)
    india_case = solve(output, read(native), plan["offer"], site / "tle")
    verify_archive(transfer, plan, site)
    reads = ("solver_cpu_s", "solver_wall_s", "science")
    prior_india = previous["result"] | {key: previous[key] for key in reads}
    write(evidence / "India.json", compare(india_case, prior_india, india_ref, plan["offer"],
          plan["document_sha256"], plan["history_sha256"]))


def read_compressed(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, allow_nan=False, indent=2, sort_keys=True)
        stream.write("\n")


def solve(frozen, native, offer, archive):
    env = dict(os.environ, PYTHONPATH=f"{frozen}:{RELEASE / 'src'}:{RELEASE}",
               OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", OMP_NUM_THREADS="1")
    for key in ("ALGO08_EVALUATION_LATITUDE", "ALGO08_EVALUATION_LONGITUDE", "ALGO08_REGION_FILE",
                "ALGO08_EXPERIMENT_CONFIG"):
        env.pop(key, None)
    with TemporaryDirectory() as directory:
        scratch = Path(directory)
        detections, region, output = (scratch / name for name in ("native", "offer", "solved"))
        write(detections, native)
        write(region, offer)
        worker_args = (detections, frozen / "spec.json", archive, region, output)
        command = [str(RELEASE / "venv/bin/python"), "-BPs", str(HELPER), "worker",
                   *map(str, worker_args), "--evidence"]
        subprocess.run(command, env=env, timeout=90, check=True)
        return read(output)


def evidence_digests(result):
    if "science" in result:
        return result["science"]
    return {key: science_digest(value) for key, value in result.get("evidence", {}).items()}


def compare(result, previous, reference, offer, native_sha256, archive_sha256):
    science, old_science = evidence_digests(result), evidence_digests(previous)
    fields = (*KEYS, "solver_cpu_s", "solver_wall_s")
    return dict(
        matched={key: key in result and key in previous and result[key] == previous[key]
                 for key in KEYS} | {
            key: science.get(key) == old for key, old in old_science.items()
        },
        native_sha256=native_sha256, archive_sha256=archive_sha256, offer=offer,
        reference_sha256=sha256(reference.read_bytes()).hexdigest(),
        previous={k: previous.get(k) for k in fields} | {"science": old_science},
        native_graph={k: result.get(k) for k in (*fields, "graph_path")} | {"science": science},
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("bench", "pair_path", "output", "evidence"):
        parser.add_argument(arg, type=Path)
    args = parser.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=False)
    run(**vars(args))
