"""Replay a frozen solver against new offers using one paired publication's detections."""
import argparse
from hashlib import sha256
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from leo.contracts.algo08_region import Algo08Region
from leo.contracts.digests import canonical_digest
from leo.storage.fast_scan import immutable_json
from tools.pipeline_eval.qualification.paired_publication import archive_identity
from .residual_attribution_trial import RELEASE, read, write
from .solver_fused_phase_trial import saved_inputs


def check_anchor(result, original):
    if (result["status"] != "ok" or result["arms"] != original["arms"]
            or result.get("owners") != original["owners"]):
        raise ValueError("Original offer did not reproduce published positions, RF residuals and assignments")


def replay(pair_path, frozen, expected_spec, offers, output):
    pair_digest = sha256(pair_path.read_bytes()).hexdigest()
    pair, original, spec, archive, anchor, native = saved_inputs(
        pair_path, frozen, None, expected_spec=expected_spec)
    parsed = [Algo08Region.parse(read(path)).document() for path in offers]
    if len({canonical_digest(region) for region in [anchor, *parsed]}) != 1 + len(parsed):
        raise ValueError("Repeated regional offer")
    env = os.environ.copy()
    for key in ("ALGO08_EVALUATION_LATITUDE", "ALGO08_EVALUATION_LONGITUDE",
                "ALGO08_REGION_FILE", "ALGO08_EXPERIMENT_CONFIG"):
        env.pop(key, None)
    env.update(PYTHONPATH=f"{frozen}:{RELEASE/'src'}:{RELEASE}",
               OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", OMP_NUM_THREADS="1")
    command = [str(RELEASE/"venv/bin/python"), "-BPs",
               str(Path(__file__).with_name("residual_attribution_trial.py")), "worker"]
    results = []
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        saved = root / "detections.json"
        write(saved, native)
        for index, region in enumerate([anchor, *parsed]):
            offered, result_path = root / f"offer-{index}.json", root / f"result-{index}.json"
            write(offered, region)
            subprocess.run([*command, str(saved), str(spec), str(archive), str(offered), str(result_path)],
                           env=env, check=True, timeout=180)
            result = read(result_path)
            if index == 0:
                check_anchor(result, original)
            results.append(dict(region=region, result=result))
    if (archive_identity(archive) != pair["archive"] or canonical_digest(read(spec)) != expected_spec
            or sha256(pair_path.read_bytes()).hexdigest() != pair_digest):
        raise ValueError("Frozen input changed during the replay")
    immutable_json(output, dict(pair_sha256=pair_digest, candidate_specification_digest=expected_spec,
                                archive=pair["archive"], raw_authority=original["raw_authority"],
                                native_sha256=canonical_digest(native), results=results))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("pair", type=Path)
    cli.add_argument("frozen", type=Path)
    cli.add_argument("expected_spec")
    cli.add_argument("output", type=Path)
    cli.add_argument("offers", nargs="+", type=Path)
    args = cli.parse_args()
    replay(args.pair, args.frozen, args.expected_spec, args.offers, args.output)
