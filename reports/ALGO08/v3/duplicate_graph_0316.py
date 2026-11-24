"""Run the frozen duplicate Graph rule on the existing medium physical saved comparison."""

import argparse
from collections import Counter
from contextlib import ExitStack
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
CONTROL = Path("/dev/shm/leo-v3-block-portable-0316-result01")
CONTROL_PIN = "4f960d24dce6efccecd834cfc5955cb9977872819d85c14fd0820a173b6b0aea"
TRACE_PIN = "1b95d3d9b74875c277659fd7b8e0b6547abeeabbfc7071a068aebc31c30c5b6d"
RUNTIME = Path("/dev/shm/leo-v3-block-portable-0316")
RUNTIME_COMMIT = "cc5cb9e27ff2c9d310722ca20661ce455dade62c"


def worker(root):
    git = ["git", "-c", f"safe.directory={RUNTIME}", "-C", str(RUNTIME)]
    if (subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip() != RUNTIME_COMMIT
            or subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"], text=True).strip()):
        raise ValueError("The matched physical control requires its original runtime checkout")
    sys.path.insert(0, str(RUNTIME / "reports/ALGO08/v3"))
    import empty_bootstrap as staged
    from aperture_trial import write
    from catalogue_block_portable_0316 import worker as run_original
    from duplicate_graph_proposals import stable_finalization

    counts = Counter()
    original = staged.load_runtime
    with ExitStack() as stack:
        def load():
            runtime = original()
            stack.enter_context(stable_finalization(counts))
            return runtime
        stack.enter_context(patch.object(staged, "load_runtime", load))
        run_original(root)
    write(root / "duplicate.json", dict(counts))


def validate_pair(clock, duplicates, old_worker, new_worker, old, new):
    if (clock["exit_code"] or not duplicates["calls"] or not new_worker["no_waveform"] or new_worker["handoffs"] != 1
            or new_worker["native_sha256"] != old_worker["native_sha256"] or old["receipt"]["region"] != new["receipt"]["region"]
            or old["receipt"]["tle_records"] != new["receipt"]["tle_records"]):
        raise ValueError("The full saved comparison changed its input, region or causal archive")


def compare(root):
    from aperture_trial import read, write
    from combined_raw_south import owner_delta
    from empty_bootstrap import checked
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from portable_orbit_0316_repair import without_timers
    from tools.pipeline_eval.qualification.paired_publication import evidence
    from triage_bounds import calibration_comparison

    previous = json.loads(checked(CONTROL / "combined.json", CONTROL_PIN))
    old = json.loads(checked(CONTROL / "portable/joint-research-receipt.json", TRACE_PIN))
    new = read(root / "portable/joint-research-receipt.json")
    control_clock, clock = (read(p / "portable.clock.json") for p in (CONTROL, root))
    old_worker, new_worker = (read(p / "portable/saved-0316-worker.json") for p in (CONTROL, root))
    duplicates = read(root / "duplicate.json")
    validate_pair(clock, duplicates, old_worker, new_worker, old, new)

    arms, outputs = {}, {}
    for key, path, research, timing in (("original", CONTROL, old, control_clock), ("filtered", root, new, clock)):
        target, receipt = path / "portable", research["receipt"]
        one = evidence(target, receipt, timing["started_unix_ns"], read_only=True)
        media = artifacts(target, receipt)
        store = FastStandardAnalysisStore(target)
        if receipt["decision"] == "complete":
            grid, line = store.position_grid(receipt["run_id"]), store.position_path(receipt["run_id"])
            if (not grid["matched_c_grid"] or not grid["complete"] or grid["planned_points"] != grid["evaluated_points"]
                    or any(doc["binding"]["position_png_sha256"] != media["images"]["position"]["sha256"] for doc in (grid,line))):
                raise ValueError("Published grid or path differs from the position image")
        arms[key] = one
        outputs[key] = dict(decision=receipt["decision"], terminal=receipt["terminal_sha256"], arms=one["arms"],
                            ordered_rows=canonical_digest(research["selected_rows"]), owners=one["owners"],
                            products=one["scientific_digests"], images=media["images"], clock=timing)
    geography = calibration_comparison(arms, "DS30-0316")
    if geography["runs"]["original"] != previous["geography"]["runs"]["candidate"]:
        raise ValueError("Physical control no longer reproduces the independently scored reference")
    old_proof, new_proof = (without_timers(doc["early_regional"]) for doc in (old, new))
    write(root / "comparison.json", dict(
        control_sha256=CONTROL_PIN, trace_sha256=TRACE_PIN, duplicates=duplicates, waveform_reads=0,
        detector=new_worker["native_sha256"], geography=geography, named=previous["geography"]["runs"],
        outputs=outputs, rank=read(root / "rank.json"), prepared=read(root / "portable-preparation.json"),
        same_proof=old_proof == new_proof, before_proof=old_proof, after_proof=new_proof,
        same_projection=old["solve"].get("geographic_projector") == new["solve"].get("geographic_projector"),
        same_handoff=old["solve"].get("prepared_exterior") == new["solve"].get("prepared_exterior"),
        owners=owner_delta(old["selected_rows"], new["selected_rows"]) if new["receipt"]["decision"] == "complete" else None))


def launch(root):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from empty_bootstrap import checked
    from full_short_physical import environment
    from portable_orbit_0316 import TARGET
    from short_raw_diagnostic import measure

    host()
    checked(CONTROL / "combined.json", CONTROL_PIN)
    checked(CONTROL / "portable/joint-research-receipt.json", TRACE_PIN)
    if root.parent.resolve(strict=True) != Path("/dev/shm"):
        raise ValueError("Expected tmpfs output")
    root.mkdir(mode=0o700)
    for name in ("tmp", "fonts"):
        (root / name).mkdir()
    for font in (TARGET / "fonts").glob("fontlist-*.json"):
        (root / "fonts" / font.name).write_bytes(font.read_bytes())
    env = environment(root)
    env.update(TMPDIR=str(root / "tmp"), XDG_CACHE_HOME=str(root / "tmp"))
    command = ["/usr/bin/timeout", "--kill-after=2s", "60s", RELEASE / "venv/bin/python", "-IB",
               __file__, "worker", root]
    clock = measure(command, env, root / "portable")
    write(root / "portable.clock.json", clock)
    if clock["exit_code"]:
        raise RuntimeError(clock["stderr_tail"])
    compare(root)


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "worker", "compare"))
    cli.add_argument("root", type=Path)
    args = cli.parse_args()
    {"launch": launch, "worker": worker, "compare": compare}[args.action](args.root)
