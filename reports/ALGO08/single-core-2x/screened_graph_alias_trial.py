"""Test reviewed Graph canonicalization within the frozen e279 saved solver."""

import argparse
import json
import os
import runpy
import subprocess
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
MEASUREMENTS = HERE / "measurements"
CANONICAL = HERE.parents[2] / "tools/pipeline_eval/variants/experimental/graph_alias.py"
CANONICAL_SHA = "4e0754e3f303c0a2782fa6bcee4712114bb1c8bc5c0e158dba8be8a92e6968d3"
ARMS = {"c0", "fitted_c"}


def qualifies(errors, deployed):
    return (set(errors) == ARMS
            and all(errors[k] is not None and errors[k] <= deployed[k] for k in ARMS))


def controls(ordinary, deployed_factors):
    rows = {"deployment": ordinary["builds"]["baseline"],
            "covariance_on_candidate_factors": ordinary["builds"]["candidate"],
            "e279_on_candidate_factors": ordinary["graph"]}
    errors = dict(zip(rows, (ordinary["errors_km"][k] for k in ("baseline", "candidate", "graph")),
                      strict=True))
    if deployed_factors is not None:
        for key in ("pair_sha256", "archive", "offer", "specification", "reference_sha256"):
            if deployed_factors[key] != ordinary[key]:
                raise ValueError(f"Deployed-factor comparison differs on {key}")
        rows["e279_on_deployed_factors"] = deployed_factors["graph"]
        errors["e279_on_deployed_factors"] = deployed_factors["errors_km"]["graph"]
    return {key: {"errors_km": errors[key], **{k: row[k] for k in (
        "arms", "owners", "associated", "solver_cpu_s",
    ) if k in row}} for key, row in rows.items()}


def worker(scratch, frozen, output):
    from tools.pipeline_eval.qualification import experimental_publication as publication
    from tools.pipeline_eval.variants.experimental import lean_startup

    if not Path(publication.__file__).is_relative_to(frozen):
        raise ValueError("Expected the frozen graph publication module")
    spec = json.loads((frozen / "spec.json").read_bytes())
    if spec["startup"] != "lazy-exports" or not spec.get("graph_path"):
        raise ValueError("Expected the original lazy-startup native Graph composition")
    native = json.loads((scratch / "native.json").read_bytes())
    archive = Path((scratch / "archive.txt").read_text().strip())
    evidence = {}

    def from_saved(recording, _root, assets, archive_reader, offer):
        from leo.application import localization_v3
        from leo.application.localization_v3_engine import _json_value
        from leo.contracts.digests import canonical_digest
        from leo.operations.tle_archive import TleArchiveReader
        from tools import algo08_position

        if recording.name != "no-recording" or archive_reader != archive or evidence:
            raise ValueError("Expected one saved request")
        if sha256(CANONICAL.read_bytes()).hexdigest() != CANONICAL_SHA:
            raise ValueError("Canonical Graph rule differs from the reviewed source")
        scope = runpy.run_path(str(CANONICAL))["canonical_alias_proposals"]
        prepare_tracks = localization_v3.prepare_tracks
        selected_packet = algo08_position.selected_packet

        def prepare(*args, **kwargs):
            with scope() as changes:
                ready = prepare_tracks(*args, **kwargs)
            graph = dict(points=ready["graph_points"], tracks=len(ready["tracks"]),
                         curved=len(ready["curved_indices"]), proposals=dict(changes))
            graph["poly_coefficients_sha256"] = canonical_digest([
                [row["key"], [piece["coefficients_hz"].tolist() for piece in row["pieces"]]]
                for row in ready["tracks"]
            ])
            evidence["graph"] = graph
            return ready

        def packet(ready, signed, fit):
            arms = signed["arms"] if fit is None else fit["policy_arms"]
            evidence["calibration_c_hz_per_ghz"] = {
                "c0": 0.0, "fitted_c": float(arms["fitted_c"]["state"]["beta"][8]),
            }
            return selected_packet(ready, signed, fit)

        start_cpu, start_wall = process_time(), perf_counter()
        with (patch.object(localization_v3, "prepare_tracks", prepare),
              patch.object(algo08_position, "selected_packet", packet)):
            decision, selected, policy = algo08_position.solve(
                native, TleArchiveReader(archive), assets, offer,
            )
        evidence.update(solver_cpu_s=process_time() - start_cpu,
                        solver_wall_s=perf_counter() - start_wall, orbit_policy=policy)
        result = dict(status=decision["status"], reason=decision.get("reason"),
                      arms=decision["arms"])
        if selected is not None:
            result["owners"] = {k: v["owner_sha256"] for k, v in selected["arms"].items()}
            result["associated"] = {k: v["associated_points"] for k, v in selected["arms"].items()}
            result["science"] = {}
            for key in ("position_grid", "position_path", "objective_replay"):
                document = {name: value for name, value in selected[key].items()
                            if name not in ("binding", "elapsed_seconds")}
                result["science"][key] = canonical_digest(
                    json.loads(json.dumps(document, default=_json_value)),
                )
        return result

    ordinary_install = lean_startup.install
    with TemporaryDirectory() as directory, ExitStack() as stack:
        root = Path(directory)

        def adapt():
            ordinary_install()
            from tools import algo08_scan

            stack.enter_context(patch.object(algo08_scan, "analyze", from_saved))

        stack.enter_context(patch.object(lean_startup, "install", adapt))
        args = SimpleNamespace(recording=root / "no-recording", bulk_root=root,
                               archive=archive, region=scratch / "offer.json")
        result = publication.run(args, spec)
    receipt = dict(result=result, observations=evidence)
    output.write_text(json.dumps(receipt, indent=2, allow_nan=False))


def run(bench, pair_path, output, source):
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.qualification.paired_publication import archive_identity
    from tools.pipeline_eval.scoring import distance_km

    from .residual_attribution_trial import saved_native
    from .screened_stock_salvage_trial import digest, read, require_spec
    from .solver_fused_phase_trial import RELEASE, saved_inputs

    ordinary_path = bench / "screened-graph-dense.json"
    ordinary = read(ordinary_path)
    freeze = read(MEASUREMENTS / "screened-tiled-graph-freeze.json")
    frozen = bench / "integration-screened-tiled-graph"
    require_spec(frozen, freeze["specification"])
    if (ordinary["specification"] != freeze["specification"]
            or digest(pair_path) != ordinary["pair_sha256"]):
        raise ValueError("The stored e279 control differs from the published pair")
    inventory = read(MEASUREMENTS / "covariance-ds30-two-pairs.json")
    pair, _, _, archive, offer, native = saved_inputs(
        pair_path, bench / "integration-covariance-posterior", None,
        expected_spec=inventory["candidate_specification_digest"],
    )
    if source == "baseline":
        native = saved_native(pair_path, "baseline", pair["runs"]["baseline"])
    elif canonical_digest(native) != ordinary["native_digest"]:
        raise ValueError("Candidate detections differ from the saved e279 control")
    if offer != ordinary["offer"] or pair["archive"] != ordinary["archive"]:
        raise ValueError("The matched offer or archive differs")

    env = dict(os.environ, PYTHONPATH=f"{frozen}:{RELEASE / 'src'}:{RELEASE}",
               OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", OMP_NUM_THREADS="1")
    for k in ("ALGO08_EVALUATION_LATITUDE", "ALGO08_EVALUATION_LONGITUDE", "ALGO08_REGION_FILE",
              "ALGO08_EXPERIMENT_CONFIG"):
        env.pop(k, None)
    interpreter = RELEASE / "venv/bin/python"
    worker_args = [str(interpreter), "-BPs", str(Path(__file__).resolve()), "worker"]
    with TemporaryDirectory() as directory:
        scratch = Path(directory)
        for file, blob in (("native.json", native), ("offer.json", offer)):
            (scratch / file).write_text(json.dumps(blob, allow_nan=False))
        (scratch / "archive.txt").write_text(str(archive))
        raw = scratch / "result.json"
        subprocess.run([*worker_args, *map(str, (scratch, frozen, raw))], env=env,
                       check=True, timeout=130)
        result = read(raw)
    if archive_identity(archive) != ordinary["archive"]:
        raise ValueError("The bound causal archive changed during replay")
    errors = {k: distance_km(v["latlon"], ordinary["reference"])
              for k, v in result["result"]["arms"].items()}
    matched = qualifies(errors, ordinary["errors_km"]["baseline"])
    deployed_control = bench / "screened-graph-dense-deployed.json"
    compared = controls(ordinary, read(deployed_control) if deployed_control.is_file() else None)
    receipt = dict(case=ordinary["case"], baseline_e279_sha256=digest(ordinary_path),
                   native_digest=canonical_digest(native), detector_source=source,
                   canonical_source_sha256=CANONICAL_SHA, arms_at_least_as_good_as_deployed=matched,
                   frozen_sha256=freeze["specification"], errors_km=errors, controls=compared,
                   offer=offer, archive=ordinary["archive"], pair_sha256=ordinary["pair_sha256"],
                   reference_sha256=ordinary["reference_sha256"], **result)
    output.write_text(json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "worker"))
    parser.add_argument("input", type=Path)
    parser.add_argument("bundle_or_pair", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--source", choices=("candidate", "baseline"), default="candidate")
    args = parser.parse_args()
    if args.action == "worker":
        worker(args.input, args.bundle_or_pair, args.output)
    else:
        run(args.input, args.bundle_or_pair, args.output, args.source)
