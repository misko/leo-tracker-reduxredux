"""Replay the exact selected North packet on its original near-omitted offer."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter, process_time


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

from aperture_trial import RELEASE, read, write
from empty_bootstrap import bind_native, checked
from raw_cfo_north_trial import ORDER, native_file, publish_saved


CONTAINING = Path("/dev/shm/leo-v3-continued-north-result01")
SEALED_SHA = "4411ba5508e7cec22d0ded179af3da1d50fc2c8a3e75c235852a646e66dfb424"
MIRROR = Path("/dev/shm/leo-v3-north-cfo-final-03/mirror-offer.json")
MIRROR_SHA = "eacc9fd6b5da3e9e38a7b13edee43aad63e229622c9973aa401a2dbb8c7f20d7"
SOURCES = ("continued_cfo_north_mirror.py", "continued-cfo-north-mirror-protocol.md", "raw_cfo_north_trial.py",
           "unified_short_bootstrap.py", "short_graph_guard.py", "named_survivor_fit.py", "isolated_salvage.py",
           "cumulative_grid_projection.py")


def enrollment():
    sealed = json.loads(checked(CONTAINING / "sealed.json", SEALED_SHA))
    binding = json.loads(checked(CONTAINING / "binding.json", sealed["binding_sha256"]))
    packet, raw = Path(sealed["packet"]), sealed["raw"]
    source = raw["native_sha256"]
    if not all(sealed["comparisons"].values()) or packet != native_file(CONTAINING / "containing"):
        raise ValueError("The mirror must use the exact qualified containing handoff")
    request = binding["request"]
    native = json.loads(checked(packet, source[7:]))
    bind_native(native, request["session"], request["inventory"], raw["detector_recipe_sha256"][7:], expected=source)
    if json.loads(checked(MIRROR, MIRROR_SHA)) != request["mirror_offer"]:
        raise ValueError("The mirror differs from the originally assigned near-omitted offer")
    libraries = {flag[2:].replace("-", "_"): str(checked_path(row)) for flag, row in binding["libraries"].items()}
    return request | dict(libraries=libraries, offer_sha256={ORDER[1]: MIRROR_SHA}), packet, native, raw


def checked_path(row):
    path = Path(row["path"])
    checked(path, row["sha256"])
    return path


def worker(root):
    started = process_time(), perf_counter()
    request, packet, native, raw = enrollment()
    binding = read(root / "binding.json")
    if binding["request"] != request or binding["native_sha256"] != raw["native_sha256"]:
        raise ValueError("The saved invocation differs from the frozen original data and offer")
    for name, pin in binding["source_sha256"].items():
        checked(HERE / name, pin)
    publish_saved(request, root / ORDER[1], MIRROR, packet, native, raw, started=started)


def launch(root):
    from dense_geographic_trial import host
    from full_short_physical import environment
    from north_held_anchor_pair import tmpfs
    from short_raw_diagnostic import measure

    machine = host()
    tmpfs(root.parent)
    request, _, _, raw = enrollment()
    checkout = HERE.parents[2]
    git = ["git", "-C", str(checkout)]
    if subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise ValueError("Commit the frozen mirror launch and verifier first")
    root.mkdir()
    (root / "fonts").mkdir()
    (root / "tmp").mkdir()
    env = environment(root)
    env.update(TMPDIR=str(root / "tmp"), XDG_CACHE_HOME=str(root / "tmp"))
    python = RELEASE / "venv/bin/python"
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=25)
    command = ["/usr/bin/timeout", "--kill-after=2s", "45s", python, "-Bsm",
               "reports.ALGO08.v3.continued_cfo_north_mirror", "worker", root]
    write(root / "binding.json", dict(request=request, machine=machine, command=list(map(str, command)),
          commit=subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip(),
          native_sha256=raw["native_sha256"], containing_sha256=SEALED_SHA,
          source_sha256={name: sha256((HERE / name).read_bytes()).hexdigest() for name in SOURCES}))
    clock = measure(command, env, root / ORDER[1])
    write(root / "clock.json", clock)
    if clock["exit_code"]:
        raise RuntimeError(clock["stderr_tail"])


def seal(root):
    from joint_publication import artifacts
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from tools.pipeline_eval.qualification.paired_publication import evidence

    request, original, _, raw = enrollment()
    binding, clock = (read(root / f"{key}.json") for key in ("binding", "clock"))
    target = root / ORDER[1]
    saved = read(target / "saved-refined-north.json")
    receipt = saved["receipt"]
    verified = evidence(target, receipt, clock["started_unix_ns"], read_only=True)
    if (clock["exit_code"] or binding["request"] != request or not saved["staged_inventory"] or saved["waveform_calls"]
            or saved["handoffs"] != 1 or saved["native_sha256"] != raw["native_sha256"]
            or verified["raw_authority"] != request["authority"] or receipt["region"] != request["mirror_offer"]
            or native_file(target).read_bytes() != original.read_bytes()):
        raise ValueError("The exact sealed native packet and original mirror must reach the standard terminal")
    images, grid_points = {}, None
    if receipt["decision"] == "complete":
        images = artifacts(target, receipt)["images"]
        store = FastStandardAnalysisStore(target)
        path, grid = store.position_path(receipt["run_id"]), store.position_grid(receipt["run_id"])
        if (len(images) != 8 or not grid["complete"] or not grid["matched_c_grid"]
                or any(row["binding"]["position_png_sha256"] != images["position"]["sha256"] for row in (path, grid))):
            raise ValueError("False fix missing its official matched evidence")
        grid_points = grid["evaluated_points"]
    write(root / "sealed.json", dict(binding_sha256=sha256((root / "binding.json").read_bytes()).hexdigest(),
          clock=clock, saved=saved, verified=verified, images=images, grid_points=grid_points))


def score(root):
    from north_interlaced_raw import NORTH, TRUTH_SHA
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km
    from tools.pipeline_eval.scoring import distance_km

    path = root / "sealed.json"
    result = read(path)["verified"]
    key = json.loads(checked(HERE.parent / "regional-release/scoring-key.json", TRUTH_SHA))
    (truth,) = {tuple(row["truth"]) for row in key["answers"].values() if row["recording"] == NORTH}
    clearance = face_clearance_km(result["receipt"]["region"], truth)
    if abs(clearance + 0.1) > 0.001:
        raise ValueError("Expected the original 100 m omitted simulation point")
    arms = {arm: dict(position=row["latlon"], rf_rms_hz=row["rf_rms_hz"],
                      error_m=1000*distance_km(truth, row["latlon"]) if row["latlon"] is not None else None)
            for arm, row in result["arms"].items()}
    write(root / "score.json", dict(sealed_sha256=sha256(path.read_bytes()).hexdigest(),
          decision=result["receipt"]["decision"], false_fix=result["receipt"]["decision"] == "complete",
          reason=result["reason"], truth_face_km=clearance, scoring_key_sha256=TRUTH_SHA, arms=arms))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("launch", "worker", "seal", "score"))
    cli.add_argument("root", type=Path)
    arguments = cli.parse_args()
    globals()[arguments.mode](arguments.root)
