"""Replay a frozen solver against new offers using one paired publication's detections."""
import argparse
from hashlib import sha256
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import perf_counter, process_time

from leo.contracts.algo08_region import Algo08Region
from leo.contracts.digests import canonical_digest
from leo.storage.fast_scan import immutable_json
from .residual_attribution_trial import ARMS, RELEASE, read, saved_native, write
from .solver_fused_phase_trial import saved_inputs


def archive_identity(archive):
    from tools.pipeline_eval.qualification.paired_publication import archive_identity as identify

    return identify(archive)


def check_anchor(result, original):
    if (result["status"] != "ok" or result["arms"] != original["arms"]
            or result.get("owners") != original["owners"]):
        raise ValueError("Original offer did not reproduce published positions, RF residuals and assignments")


def deployed_worker(native, archive, offer, output):
    from leo.operations.tle_archive import TleArchiveReader
    from tools import algo08_position

    if not Path(algo08_position.__file__).resolve().is_relative_to(RELEASE):
        raise ValueError("Expected the installed deployed ALGO08v2 solver")
    document = read(native)
    region = Algo08Region.parse(read(offer))
    causal_archive = TleArchiveReader(archive)
    start_cpu, start_wall = process_time(), perf_counter()
    decision, packet, policy = algo08_position.solve(document, causal_archive, RELEASE / "assets", region)
    result = dict(status=decision["status"], reason=decision.get("reason"), arms=decision["arms"],
                  orbit_policy=policy, solver_cpu_s=process_time() - start_cpu,
                  solver_wall_s=perf_counter() - start_wall)
    if packet is not None:
        result["owners"] = {arm: packet["arms"][arm]["owner_sha256"] for arm in ARMS}
        result["associated"] = {arm: packet["arms"][arm]["associated_points"] for arm in ARMS}
    write(output, result)


def replay(pair_path, frozen, expected_spec, offers, output, *, method="candidate"):
    if method not in ("baseline", "candidate"):
        raise ValueError("Expected baseline or candidate saved detections")
    pair_digest = sha256(pair_path.read_bytes()).hexdigest()
    pair, original, spec, archive, anchor, native = saved_inputs(
        pair_path, frozen, None, expected_spec=expected_spec)
    if method == "baseline":
        baseline = pair["runs"]["baseline"]
        if (Path(baseline["launcher"]).resolve() != RELEASE / "run"
                or baseline["receipt"]["decision"] != "complete"
                or baseline["receipt"]["region"] != anchor
                or baseline["raw_authority"] != original["raw_authority"]):
            raise ValueError("Expected the original deployed publication on the same waveform and offer")
        original = baseline
        native = saved_native(pair_path, "baseline", original)
    parsed = [Algo08Region.parse(read(path)).document() for path in offers]
    if len({canonical_digest(region) for region in [anchor, *parsed]}) != 1 + len(parsed):
        raise ValueError("Repeated regional offer")
    env = os.environ.copy()
    for key in ("ALGO08_EVALUATION_LATITUDE", "ALGO08_EVALUATION_LONGITUDE",
                "ALGO08_REGION_FILE", "ALGO08_EXPERIMENT_CONFIG"):
        env.pop(key, None)
    env.update(OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", OMP_NUM_THREADS="1")
    command = [str(RELEASE / "venv/bin/python"), "-BPs"]
    worker_spec = []
    if method == "baseline":
        checkout = Path(__file__).resolve().parents[3]
        env["PYTHONPATH"] = f"{RELEASE / 'src'}:{RELEASE}:{checkout}"
        command.extend(("-m", f"{__package__}.replay_region_offers", "--deployed-worker"))
    else:
        env["PYTHONPATH"] = f"{frozen}:{RELEASE / 'src'}:{RELEASE}"
        command.extend((str(Path(__file__).with_name("residual_attribution_trial.py")), "worker"))
        worker_spec.append(str(spec))
    results = []
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        saved = root / "detections.json"
        write(saved, native)
        for index, region in enumerate([anchor, *parsed]):
            offered, result_path = root / f"offer-{index}.json", root / f"result-{index}.json"
            write(offered, region)
            subprocess.run([*command, str(saved), *worker_spec, str(archive), str(offered), str(result_path)],
                           env=env, check=True, timeout=180)
            result = read(result_path)
            if index == 0:
                check_anchor(result, original)
            results.append(dict(region=region, result=result))
    if (archive_identity(archive) != pair["archive"] or canonical_digest(read(spec)) != expected_spec
            or sha256(pair_path.read_bytes()).hexdigest() != pair_digest):
        raise ValueError("Frozen input changed during the replay")
    immutable_json(output, dict(method=method, pair_sha256=pair_digest, candidate_specification_digest=expected_spec,
                                archive=pair["archive"], raw_authority=original["raw_authority"],
                                native_sha256=canonical_digest(native), results=results))


def main():
    if sys.argv[1:2] == ["--deployed-worker"]:
        cli = argparse.ArgumentParser(description="Run the installed solver on one saved detection file")
        cli.add_argument("--deployed-worker", action="store_true")
        for field in ("native", "archive", "region", "output"):
            cli.add_argument(field, type=Path)
        args = cli.parse_args()
        deployed_worker(args.native, args.archive, args.region, args.output)
        return
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("pair", type=Path)
    cli.add_argument("frozen", type=Path)
    cli.add_argument("expected_spec")
    cli.add_argument("output", type=Path)
    cli.add_argument("offers", nargs="+", type=Path)
    cli.add_argument("--method", choices=("baseline", "candidate"), default="candidate")
    args = cli.parse_args()
    replay(args.pair, args.frozen, args.expected_spec, args.offers, args.output, method=args.method)


if __name__ == "__main__":
    main()
