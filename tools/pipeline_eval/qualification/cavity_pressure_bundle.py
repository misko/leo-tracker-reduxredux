"""Stage the measured constrained-refit lifetime change in the standalone bundle."""

import argparse
import shutil
import subprocess
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json
from . import cavity_pressure_trial as trial

TARGET = "leo/analysis/localization_v3/feasible.py"
MANIFEST = "native/manifest.json"
COMPILER_SOURCES = (
    "leo/analysis/localization_v4/native_bound.c",
    "tools/pipeline_eval/variants/orbit_projector.c",
)
STOCK_TARGET = "a9c5857fcba549f0c8059a544cae7912d4d640dba4af4778689e9aa577807d41"
IMPORT = "def constrained(scan, node, mask, powers, means, hyper, entries, pair):\n"
ROUND = "            reference = phase\n        output[arm] = summary(p, x, entries)\n"
END = "            minimum_gate_slack=min(gate_slacks(p, x, entries).values()),\n        )\n"


def release_source(text):
    edits = (
        (
            IMPORT,
            IMPORT
            + "    from tools.pipeline_eval.variants.v5_direct_lifetime import dispose_model\n\n",
        ),
        (
            ROUND,
            "            reference = phase\n"
            "            # The next phase model only needs the updated coordinates and phase.\n"
            "            if _epoch < 4:\n"
            "                dispose_model(p)\n"
            "                del p\n"
            "        output[arm] = summary(p, x, entries)\n",
        ),
        (END, END + "        dispose_model(p)\n        del p\n"),
    )
    for before, after in edits:
        if text.count(before) != 1:
            raise ValueError("standalone constrained refinement differs from its pinned source")
        text = text.replace(before, after, 1)
    compile(text, TARGET, "exec")
    return text


def stage(work):
    plan_file = work / "plan.json"
    plan = trial.direct.common.read(plan_file)
    original, candidate = Path(plan["runtime"]), work / "candidate"
    if plan["files"].get(TARGET) != STOCK_TARGET:
        raise ValueError("unexpected original constrained refinement source digest")
    if whole_iq.receiver_identity(original) != plan["files"]:
        raise ValueError("original installed standalone bundle changed")
    trace = work / "runs" / "DS29-0247" / trial.CONTROL / "attempt.json"
    original_attempt = trial.direct.common.read(trace)
    if (
        original_attempt["service_result"] != "oom-kill"
        or original_attempt["bundle_files"] != plan["files"]
        or original_attempt["plan_sha256"] != trial.direct.common.sha(plan_file)
        or original_attempt["kernel"]["MemoryPeak"] != str(plan["memory"])
    ):
        raise ValueError("reserve pressure evidence is missing or differs from the sealed stock")
    candidate.mkdir(exist_ok=False)
    for filename in plan["files"]:
        dest = candidate / filename
        dest.parent.mkdir(exist_ok=True, parents=True)
        shutil.copyfile(original / filename, dest)
    edited = candidate / TARGET
    edited.write_text(release_source(edited.read_text()))
    manifest = candidate / MANIFEST
    manifest.write_text(manifest.read_text().replace(str(original) + "/", str(candidate) + "/"))
    compiler_sources = {}
    for name in COMPILER_SOURCES:
        shutil.copyfile(original / name, candidate / name)
        compiler_sources[name] = trial.direct.common.sha(candidate / name)
    subprocess.run(
        [
            str(trial.direct.v5_lean.PYTHON),
            "-IB",
            "-c",
            "import runpy; from pathlib import Path; "
            "runpy.run_path(str(Path.cwd()))['activate'](Path.cwd()); "
            "from leo.analysis.localization_v4.backend import read_manifest, validate_manifest; "
            "validate_manifest(read_manifest(Path('native/manifest.json')), check_provider=True)",
        ],
        cwd=candidate,
        timeout=12,
        check=True,
    )
    files = whole_iq.receiver_identity(candidate)
    changed = {name for name, digest in files.items() if digest != plan["files"].get(name)}
    if set(files) != set(plan["files"]) or changed != {TARGET, MANIFEST}:
        raise ValueError("standalone changes exceed the constrained-refit release and relocation")
    save_json(
        work / "candidate-lock.json",
        dict(
            files=files,
            compiler_sources=compiler_sources,
            changed=sorted(changed),
            source_recipe_sha256=trial.direct.common.sha(Path(__file__)),
            plan_sha256=trial.direct.common.sha(plan_file),
            observed_oom_sha256=trial.direct.common.sha(trace),
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    args = parser.parse_args()
    stage(local_output(args.work))
