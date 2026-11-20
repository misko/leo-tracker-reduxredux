"""Apply the prepared regression basis inside the installed constrained solver."""

import argparse
import shutil
import subprocess
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json
from ..variants import fit_work_projection
from . import fit_work_trial as trial

TARGET = "leo/analysis/localization_v3/feasible.py"
MANIFEST = "native/manifest.json"
KERNEL = "tools/pipeline_eval/variants/fit_work_projection.py"
STOCK = "86922fff38e147c38d1c4380d71715d490d642db771c11f69d943aecd97c53bd"
REPLACEMENTS = (
    (
        "def noise_slacks(residual, times):",
        "def noise_slacks(residual, times, screen=None):",
    ),
    (
        "    d = batch_noise_screen(r[None, :], times)",
        "    d = batch_noise_screen(r[None, :], times) if screen is None else screen(r[None, :])",
    ),
    (
        "def residual_slacks(residual, times):",
        "def residual_slacks(residual, times, screen=None):",
    ),
    (
        "**noise_slacks(r, times))",
        "**noise_slacks(r, times, screen))",
    ),
    (
        "def gate_slacks(p, x, entries=()):",
        "def gate_slacks(p, x, entries=(), *, screens=None):",
    ),
    (
        "    owners = {}\n",
        "    owners = {}\n    curved, linear = screens if screens is not None else ({}, {})\n",
    ),
    (
        '**noise_slacks(terms["innovations"][0], times),',
        '**noise_slacks(terms["innovations"][0], times, curved.get(sl.start)),',
    ),
    (
        'for k, v in residual_slacks(c["conditional_residual_hz"][sl][active], times).items()',
        "for k, v in residual_slacks(\n"
        '                    c["conditional_residual_hz"][sl][active], times,'
        " curved.get(sl.start)\n"
        "                ).items()",
    ),
    (
        '**noise_slacks(terms["innovations"][0], t["times"]),',
        '**noise_slacks(terms["innovations"][0], t["times"], linear.get(entry["track_index"])),',
    ),
    (
        "    from tools.pipeline_eval.variants.v5_direct_lifetime import dispose_model\n\n",
        "    from tools.pipeline_eval.variants.fit_work_projection import prepare\n"
        "    from tools.pipeline_eval.variants.v5_direct_lifetime import dispose_model\n\n",
    ),
    (
        "    output = {}\n    for arm in ARMS:",
        "    output = {}\n    screens = None\n    for arm in ARMS:",
    ),
    (
        "            fitted = feasible_fit(",
        "            if screens is None:\n"
        "                screens = prepare(p, entries, batch_noise_screen)\n"
        "            fitted = feasible_fit(",
    ),
    (
        "lambda z, p=p: np.asarray(list(gate_slacks(p, z, entries).values())) - 0.01,",
        "lambda z, p=p: np.asarray(\n"
        "                    list(gate_slacks(p, z, entries, screens=screens).values())\n"
        "                ) - 0.01,",
    ),
)


def revised_source(text):
    for original, candidate in REPLACEMENTS:
        if text.count(original) != 1:
            raise ValueError("unrecognized constrained phase-release source")
        text = text.replace(original, candidate, 1)
    compile(text, TARGET, "exec")
    return text


def stage(work, profile):
    plan_path = work / "plan.json"
    plan = trial.COMMON.read(plan_path)
    stock, base = plan["stock"], Path(plan["stock_root"])
    trial.verify_install(base, stock)
    if stock["files"][TARGET] != STOCK:
        raise ValueError("expected the qualified phase-release donor")
    if trial.COMMON.read(profile / "result.json")["status"] != "ok":
        raise ValueError("the development profile must publish both position arms")
    staged = work / "candidate"
    staged.mkdir(exist_ok=False)
    for name in stock["files"] | stock["compiler_sources"]:
        target = staged / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(base / name, target)
    node = staged / TARGET
    node.write_text(revised_source(node.read_text()))
    manifest = staged / MANIFEST
    manifest.write_text(manifest.read_text().replace(str(base) + "/", str(staged) + "/"))
    shutil.copyfile(Path(fit_work_projection.__file__), staged / KERNEL)
    files = whole_iq.receiver_identity(staged)
    new = {k for k, v in files.items() if v != stock["files"].get(k)}
    if new != {TARGET, MANIFEST, KERNEL} or set(files) != set(stock["files"]) | {KERNEL}:
        raise ValueError("staged profile changed outside its expected scientific source overlay")
    subprocess.run(
        [
            str(trial.pressure.direct.v5_lean.PYTHON),
            "-IB",
            "-c",
            "import runpy; from pathlib import Path; "
            "runpy.run_path(str(Path.cwd()))['activate'](Path.cwd()); "
            "from leo.analysis.localization_v4.backend import read_manifest, validate_manifest; "
            "validate_manifest(read_manifest(Path('native/manifest.json')), check_provider=True); "
            "from leo.analysis.localization_v3.feasible import constrained",
        ],
        cwd=staged,
        timeout=12,
        check=True,
    )
    save_json(
        work / "candidate-lock.json",
        dict(
            files=files,
            compiler_sources=stock["compiler_sources"],
            changed=sorted(new),
            source_recipe_sha256=trial.COMMON.sha(Path(__file__)),
            plan_sha256=trial.COMMON.sha(plan_path),
            development_profile_sha256=trial.COMMON.sha(profile / "profile.prof"),
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("profile", type=Path)
    args = parser.parse_args()
    stage(local_output(args.work), args.profile.resolve())
