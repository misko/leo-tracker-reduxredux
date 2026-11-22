"""Compare an opt-in complete-family cavity against the original saved solvers."""

import argparse
import json
import os
import runpy
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
TRANSFER = HERE / "covariance_transfer_trial.py"
VARIANT = HERE.parents[2] / "tools/pipeline_eval/variants/algo08_collapsed_cavity.py"
RECEIPT = HERE / "measurements/covariance-geographic-transfer.json"


def worker(site, frozen, output):
    from leo.application.localization_v3_engine import _json_value
    from tools import algo08_position

    transfer = runpy.run_path(str(TRANSFER))
    variant = runpy.run_path(str(VARIANT))
    original = algo08_position.solve
    diagnostics = {}

    def solve(*args, **kwargs):
        decision, packet, policy = original(*args, **kwargs)
        diagnostics.update(decision["metrics"]["complete_family_cavity"])
        return decision, packet, policy

    with (TemporaryDirectory() as directory, variant["collapsed_cavity"](),
          patch.object(algo08_position, "solve", solve)):
        file = Path(directory) / "solve.json"
        transfer["worker"](site / "native.json", site / "tle", site / "matched-tile.json",
                           file, frozen / "spec.json")
        result = json.loads(file.read_bytes())
    transfer["write"](output, json.loads(json.dumps(
        dict(result, complete_family_cavity=diagnostics), default=_json_value, allow_nan=False,
    )))


def verify_archive(transfer, row, site):
    from leo.operations.tle_archive import TleArchiveReader
    from tools.pipeline_eval.__main__ import encoded
    from tools.pipeline_eval.qualification.portable_v5_trials import preferred_history

    public, digest = transfer["public"], transfer["digest"]
    if row["dataset"] == "waveform-site":
        content = public("causal-authority.json", transfer["WAVEFORM_TREE"])
        history = json.loads(content).values()
    else:
        source = json.loads(public("authentic-history.json"))["snapshots"]
        entries = [{k: snap[k] for k in ("collected_utc_ns", "sha256")} for snap in source]
        history = preferred_history(entries, row["clock_cutoff_utc_ns"])
        content = encoded(history)
    reader = TleArchiveReader(site / "tle")
    snapshots = reader.list_snapshots("space-track")
    expected = {(s["collected_utc_ns"], s["sha256"]) for s in history}
    actual = {(s.collected_utc_ns, s.sha256) for s in snapshots}
    if digest(content) != row["history_sha256"] or actual != expected:
        raise ValueError("Staged orbit history differs from the released input")
    for snapshot in snapshots:
        reader.read(snapshot)


def run(scratch, frozen, output):
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.__main__ import THREAD_ENV
    from tools.pipeline_eval.qualification.paired_publication import verify_sources
    from tools.pipeline_eval.scoring import distance_km

    transfer = runpy.run_path(str(TRANSFER))
    release = transfer["RELEASE"]
    locked = json.loads(RECEIPT.read_bytes())
    specification = json.loads((frozen / "spec.json").read_bytes())
    if canonical_digest(specification) != transfer["SPEC"] or locked["spec"] != transfer["SPEC"]:
        raise ValueError("Expected the original covariance freeze")
    verify_sources(frozen / "reports/ALGO08/single-core-2x/run-candidate", specification["sources"])
    containing = {row["case"]: row for row in locked["rows"] if row["mode"] == "matched-tile"}
    env = os.environ.copy()
    for key in ("ALGO08_EVALUATION_LATITUDE", "ALGO08_EVALUATION_LONGITUDE", "ALGO08_REGION_FILE",
                "ALGO08_EXPERIMENT_CONFIG"):
        env.pop(key, None)
    env.update(THREAD_ENV, PYTHONPATH=f"{frozen}:{release / 'src'}:{release}")
    command = [str(release / "venv/bin/python"), "-BPs", str(Path(__file__).resolve()), "worker"]
    rows = []
    output.mkdir(parents=True, exist_ok=False)
    for case in (transfer["SOUTH"], transfer["INDIA"]):
        row, site = containing[case], scratch / case
        if (transfer["digest"]((site / "native.json").read_bytes()) != row["document_sha256"]
                or json.loads((site / "matched-tile.json").read_bytes()) != row["offer"]):
            raise ValueError("Staged containing request differs from the previous solve")
        verify_archive(transfer, row, site)
        prediction = output / (case + ".json")
        subprocess.run([*command, *map(str, (site, frozen, prediction))], env=env,
                       timeout=150, check=True)
        rows.append((row, prediction))
    scored = []
    for row, prediction in rows:
        result = json.loads(prediction.read_bytes())
        for arm in result["arms"].values():
            arm["horizontal_error_km"] = distance_km(arm["latlon"], row["reference_latlon"])
        scored.append(dict(row, builds=dict(row["builds"], complete_family_cavity=result)))
    transfer["write"](output / "score.json", dict(
        frozen_spec=transfer["SPEC"],
        original_receipt_sha256=transfer["digest"](RECEIPT.read_bytes()),
        variant_sha256=transfer["digest"](VARIANT.read_bytes()), rows=scored,
    ))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "worker"))
    parser.add_argument("evidence", type=Path)
    parser.add_argument("frozen", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    (run if args.action == "run" else worker)(args.evidence, args.frozen, args.output)
