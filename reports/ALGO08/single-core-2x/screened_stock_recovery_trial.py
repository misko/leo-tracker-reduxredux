"""Compare stock trim and recovery behind the existing screened nomination."""

import argparse
import gzip
import json
import os
import runpy
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
VARIANT = HERE.parents[2] / "tools/pipeline_eval/variants/algo08_screened_stock_recovery.py"
RECEIPT = HERE / "measurements/covariance-geographic-transfer.json"
TRACE = HERE / "measurements/portable-south-solver-attribution.json.gz"
SCREEN_SHA256 = "f276b8ee2f4c059d571da874b2fbef6f6b13d08078e30fd93950428f8c10fb70"


def sources():
    return runpy.run_path(str(HERE / "covariance_transfer_trial.py"))


def chosen_trims(notes):
    fields = ("start_index", "stop_index", "points", "norad", "alias")
    return [[dict(component=item["component"], **{k: item["selected"][k] for k in fields})
             for item in call["selected"]] for call in notes.get("salvage", [])]


def readout(notes):
    signed = notes.get("selected_before_cavity", {})
    return dict(
        initial_gate=notes.get("initial_gate"), trims=chosen_trims(notes),
        post_salvage_curved=[gate["curved"] for gate in notes.get("conservative_gates", [])
                             if gate["stage"] == "salvage_refit"],
        signed=signed, cavity=notes.get("cavity"),
        selection_used_cavity=notes.get("selection_used_cavity"),
    )


def worker(site, frozen, output, mode):
    from leo.application.localization_v3_engine import _json_value
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_screen_winner

    transfer = sources()
    variant = runpy.run_path(str(VARIANT))
    trace = runpy.run_path(str(HERE / "portable_south_solver_trace.py"))
    if transfer["digest"](Path(v5_screen_winner.__file__).read_bytes()) != SCREEN_SHA256:
        raise ValueError("Initial screen differs from the published solver")
    original = algo08_position.solve
    notes, diagnostics = {}, {}

    def solve(*args, **kwargs):
        with trace["traced"](notes, False):
            decision, packet, policy = original(*args, **kwargs)
        diagnostics["stage_wall_s"] = decision["metrics"]["stage_s"]
        return decision, packet, policy

    with (TemporaryDirectory() as directory, variant["screened_stock_recovery"]() as screen,
          patch.object(algo08_position, "solve", solve)):
        file = Path(directory) / "solve.json"
        transfer["worker"](site / "native.json", site / "tle", site / (mode + ".json"),
                           file, frozen / "spec.json")
        result = json.loads(file.read_bytes())
    transfer["write"](output, json.loads(json.dumps(
        dict(result, initial_screen=screen, stage_evidence=readout(notes), **diagnostics),
        default=_json_value, allow_nan=False,
    )))


def run(scratch, frozen, output, mode):
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.__main__ import THREAD_ENV
    from tools.pipeline_eval.qualification.paired_publication import verify_sources
    from tools.pipeline_eval.scoring import distance_km

    transfer = sources()
    archive = runpy.run_path(str(HERE / "complete_family_cavity_trial.py"))["verify_archive"]
    release = transfer["RELEASE"]
    locked = json.loads(RECEIPT.read_bytes())
    specification = json.loads((frozen / "spec.json").read_bytes())
    if canonical_digest(specification) != transfer["SPEC"] or locked["spec"] != transfer["SPEC"]:
        raise ValueError("Expected the original covariance freeze")
    verify_sources(frozen / "reports/ALGO08/single-core-2x/run-candidate", specification["sources"])
    queries = {row["case"]: row for row in locked["rows"] if row["mode"] == mode}
    env = os.environ.copy()
    for name in ("ALGO08_EVALUATION_LATITUDE", "ALGO08_EVALUATION_LONGITUDE", "ALGO08_REGION_FILE",
                 "ALGO08_EXPERIMENT_CONFIG"):
        env.pop(name, None)
    env.update(THREAD_ENV, PYTHONPATH=f"{frozen}:{release / 'src'}:{release}")
    command = [str(release / "venv/bin/python"), "-BPs", str(Path(__file__).resolve()), "worker"]
    predictions = []
    output.mkdir(parents=True, exist_ok=False)
    for case in (transfer["SOUTH"], transfer["INDIA"]):
        row, site = queries[case], scratch / case
        if (transfer["digest"]((site / "native.json").read_bytes()) != row["document_sha256"]
                or json.loads((site / (mode + ".json")).read_bytes()) != row["offer"]):
            raise ValueError("Staged region or detections differ from the previous solve")
        archive(transfer, row, site)
        prediction = output / (case + ".json")
        subprocess.run([*command, *map(str, (site, frozen, prediction, mode))], env=env,
                       timeout=150, check=True)
        predictions.append((row, prediction))
    scored = []
    for row, prediction in predictions:
        result = json.loads(prediction.read_bytes())
        for arm in result["arms"].values():
            arm["horizontal_error_km"] = distance_km(arm["latlon"], row["reference_latlon"])
        scored.append(dict(row, builds=dict(row["builds"], screened_stock_recovery=result)))
    summary = dict(frozen_spec=transfer["SPEC"], initial_screen_sha256=SCREEN_SHA256, rows=scored,
                   variant_sha256=transfer["digest"](VARIANT.read_bytes()))
    if mode == "matched-tile":
        stock = json.loads(gzip.decompress(TRACE.read_bytes()))["results"]["installed"]["stages"]
        observed = scored[0]["builds"]["screened_stock_recovery"]["stage_evidence"]
        summary["portable_south_deployed_trace_sha256"] = transfer["digest"](TRACE.read_bytes())
        summary["portable_south_matches_deployed_stages"] = {
            key: value == observed[key] for key, value in readout(stock).items()
        }
    transfer["write"](output / "score.json", summary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "worker"))
    parser.add_argument("evidence", type=Path)
    parser.add_argument("frozen", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("mode", choices=("matched-tile", "omitted-tile"))
    args = parser.parse_args()
    (run if args.action == "run" else worker)(args.evidence, args.frozen, args.output, args.mode)
