"""Run one matched site-free PGO refinement comparison against installed v3."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from tools.pipeline_eval.variants.experimental.receiver_benchmark import benchmark, digest, read_archive
from tools.pipeline_eval.variants.experimental.receiver_brackets import read_physical
from tools.pipeline_eval.variants.experimental.receiver_cfo_peak_bound import V3_SHA, build_trace
from tools.pipeline_eval.variants.experimental.receiver_refine_bound import build_audit


def exports(binary):
    symbols = subprocess.check_output(["nm", "-D", "--defined-only", binary], text=True)
    return {line.split()[-1] for line in symbols.splitlines() if line.strip()}


def train(work, archive, history, args):
    timing = work / "timing_first_receiver.o"
    source = timing.with_suffix(".c")
    feedback = work / "feedback"
    feedback.mkdir()
    template, _, use_template, _ = history["commands"]
    link = archive["commands"][-1]
    link_objects = [timing if Path(item).name == timing.name else item for item in link[1:-2]]
    enclosure = work / "enclosure.o"
    if enclosure.exists():
        link_objects.append(enclosure)
    trainer = Path(__file__).resolve().parents[1] / "single-core-2x/receiver_mixer_profile_trial.py"
    commands = []
    training_result = None
    for mode, previous in (("generate", template), ("use", use_template)):
        binary = work / f"{mode}.so"
        compile_cmd = [previous[0], f"-fprofile-{mode}={feedback}", *previous[2:-4],
                       "-c", source, "-o", timing]
        # Keep training and feedback compile flags identical to the archived recipe.
        link_cmd = [*compile_cmd[:3], *link_objects, "-o", binary]
        subprocess.run(compile_cmd, check=True, cwd=archive["cwd"])
        subprocess.run(link_cmd, check=True, cwd=archive["cwd"])
        commands.extend([compile_cmd, link_cmd])
        if mode == "generate":
            command = [sys.executable, trainer, "train", binary, args.assets]
            result = subprocess.run(command, check=True, text=True, stdout=subprocess.PIPE)
            training_result = json.loads(result.stdout)
            profile, = feedback.rglob("timing_first_receiver.gcda")
    return binary, dict(library_sha256=digest(binary.read_bytes()),
                        timing_sha256=digest(timing.read_bytes()),
                        source_sha256=digest(source.read_bytes()),
                        feedback_sha256=digest(profile.read_bytes()),
                        training_script_sha256=digest(trainer.read_bytes()), training=training_result,
                        commands=[[str(arg) for arg in command] for command in commands])


def run(args):
    args.work.mkdir()
    installed = args.installed.resolve()
    if digest(installed.read_bytes()) != V3_SHA:
        raise ValueError("unexpected installed receiver")
    archive = json.loads((args.archive / "build.json").read_bytes())
    compiler_path = Path(subprocess.check_output(["which", "cc"], text=True).strip()).resolve()
    # The GCC driver includes argv[0] in its version banner.
    compiler_id = subprocess.check_output(["cc", "--version"], text=True).splitlines()[0]
    if compiler_id != archive["compiler"]:
        raise ValueError(f"{compiler_id!r} differs from archived compiler")
    history = json.loads(args.history.read_bytes())["build"]["builds"]["packed"]
    folders = {arm: args.work / arm for arm in ("control", "guard")}
    build_trace(args.archive, folders["control"], instrument=lambda source: source)
    build_audit(args.archive, folders["guard"], pruning=True)
    arms, builds = {}, {}
    for arm, folder in folders.items():
        arms[arm], builds[arm] = train(folder, archive, history, args)
        public = exports(installed)
        found = exports(arms[arm])
        if public - found:
            raise ValueError("the replacement receiver lost required public symbols")
        builds[arm]["additional_exports"] = sorted(found - public)
    if (builds["control"]["library_sha256"] != V3_SHA
            or builds["control"]["timing_sha256"] != history["timing_object_sha256"]):
        raise ValueError("fresh stock PGO did not reproduce the installed ALGO08v3 bytes")
    if builds["control"]["training"] != builds["guard"]["training"]:
        raise ValueError("PGO arm changed generated training factor counts")

    weak = list(read_archive(args.weak, 18))
    dense = list(read_physical(args.binding, args.bulk, 48))
    pairs = dict(installed_control=(installed, arms["control"]), installed_guard=(installed, arms["guard"]),
                 fresh_control_guard=(arms["control"], arms["guard"]))
    runs = {name: {pair: benchmark(binaries, group, args.assets, args.repeats)
                   for pair, binaries in pairs.items()}
            for name, group in (("weak", weak), ("dense", dense))}
    for group in runs.values():
        for evidence in group.values():
            if evidence["changed"] or evidence["changed_continuation"] or len(
                    set(evidence["factor_digests"])) != 1:
                raise ValueError("PGO variant changed output bytes or continuation")
    return dict(installed_sha256=V3_SHA, compiler_id=compiler_id,
                compiler_sha256=digest(compiler_path.read_bytes()), builds=builds, runs=runs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("archive", "history", "work", "installed", "assets", "weak", "binding", "bulk"):
        parser.add_argument(key, type=lambda value: Path(value).resolve())
    parser.add_argument("--repeats", type=int, choices=range(1, 6), default=5)
    print(json.dumps(run(parser.parse_args()), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
