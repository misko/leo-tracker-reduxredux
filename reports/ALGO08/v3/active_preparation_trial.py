"""Attribute the real DS30-0016 preparation port on a saved verified fix."""

import argparse
from collections import defaultdict
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import sys
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
PRIOR = Path("/dev/shm/leo-v3-positive-overhead-results-02")
BINDING_PIN = "8083521ce6f8d90642db704974146c3da2f5cff7408a4d85fab6c94f373ce630"
REFERENCE_PIN = "e17707d889c8e326373b89977dfa1bd708675ab89271fd527d02e1a8305e71e1"


@contextmanager
def bind_preparation(method, audit):
    import unified_short_bootstrap as cumulative

    renderer = cumulative.layout_renderer

    @contextmanager
    def entered(*args, **kwargs):
        from tools import algo08_position

        ordinary = algo08_position.prepare_native_scan
        with (renderer(*args, **kwargs),
              patch.object(algo08_position, "prepare_native_scan", method(ordinary, audit))):
            yield

    with patch.object(cumulative, "layout_renderer", entered):
        yield


def profile_preparation(ordinary, audit):
    from contextlib import ExitStack
    import cProfile
    import pstats

    def instrument(*values, **options):
        from leo.application import localization_v3 as application
        from leo.operations import localization_v3_inputs as inputs
        from leo.analysis.localization_v3 import orbits, phase_prior
        from tools.pipeline_eval.variants import algo08_causal_reuse as preparation

        times = defaultdict(list)

        def clock(obj, name):
            old = getattr(obj, name)

            def run(*args, **kwargs):
                cpu, wall = process_time_ns(), perf_counter_ns()
                try:
                    return old(*args, **kwargs)
                finally:
                    times[f"{obj.__name__}.{name}"].append((process_time_ns()-cpu, perf_counter_ns()-wall))

            return patch.object(obj, name, run)

        hooks = ((application, "prepare_tracks"), (application, "prepare_initial_sky"),
                 (application, "estimate_noise"), (application, "prepare_phase_history"),
                 (application, "forecast"), (inputs, "causal_catalogue"), (inputs, "genuine_previous"),
                 (inputs, "regional_bank"), (orbits, "ecef_states"), (phase_prior, "select_distribution"),
                 (preparation.CausalPreparationParser, "__call__"))
        detail = cProfile.Profile(timer=process_time_ns, timeunit=1e-9)
        with ExitStack() as scope:
            for obj, name in hooks:
                scope.enter_context(clock(obj, name))
            cpu, wall = process_time_ns(), perf_counter_ns()
            result = detail.runcall(ordinary, *values, **options)
            audit["measured_ns"] = (process_time_ns()-cpu, perf_counter_ns()-wall)
        audit["wall_and_cpu_samples_ns_inclusive"] = dict(times)
        stats = pstats.Stats(detail)
        audit["python_profile_top_80"] = [dict(path=path, line=line, function=fn, unique_calls=cc, calls=nc,
                                              self_cpu_s=tt, inclusive_cpu_s=ct)
                                           for (path, line, fn), (cc, nc, tt, ct, _) in
                                           sorted(stats.stats.items(), key=lambda pair: -pair[1][2])[:80]]
        return result

    return instrument


def work(mode, output):
    from aperture_trial import write
    from positive_fix_trial import worker

    audit = {}
    if mode == "profile":
        with bind_preparation(profile_preparation, audit):
            worker(PRIOR/"binding.json", "native", output)
    else:
        worker(PRIOR/"binding.json", "native", output)
    write(output/"preparation.json", audit)


def launch(root, mode):
    from aperture_trial import RELEASE, read, write
    from dense_geographic_trial import host
    from empty_bootstrap import checked
    from full_short_physical import environment
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from short_raw_diagnostic import measure, pairs
    import json
    import subprocess

    host()
    checked(PRIOR/"binding.json", BINDING_PIN)
    reference = json.loads(checked(PRIOR/"result.json", REFERENCE_PIN))["runs"]["native"]
    root.mkdir(exist_ok=True)
    env = environment(root)
    (root/"tmp").mkdir(exist_ok=True)
    env.update(TMPDIR=str(root/"tmp"), XDG_CACHE_HOME=str(root/"tmp"))
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root], text=True).strip() != "tmpfs":
        raise ValueError("The saved test requires tmpfs output")
    subprocess.run([RELEASE/"venv/bin/python", "-Bc",
                    "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    target = root/mode
    args = [RELEASE/"venv/bin/python", "-IB", __file__, mode, target, "--worker"]
    process = measure(args, env, target)
    write(root/f"{mode}-clock.json", process)
    if process["exit_code"]:
        raise RuntimeError(process["stderr_tail"])
    worker = read(target/"positive-fix.json")
    research = read(target/"joint-research-receipt.json")
    receipt = worker["receipt"]
    matches = pairs.evidence(target, receipt, process["started_unix_ns"], read_only=True)
    media = artifacts(target, receipt)
    if (worker["waveform_calls"] or receipt["terminal_sha256"] != reference["science"]["receipt"]["terminal_sha256"]
            or any(matches[name] != reference["science"][name] for name in
                   ("arms", "owners", "raw_authority", "scientific_digests"))
            or canonical_digest(research["selected_rows"]) != reference["owner_rows_sha256"]
            or canonical_digest(media["images"]) != canonical_digest(reference["figures"])):
        raise ValueError("The experiment changed approved science or official PNGs")
    write(root/f"{mode}-result.json", dict(worker=worker, clock=process, science=matches,
          figures=media, profile=read(target/"preparation.json"),
          source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), native_decode=worker["decode"]))


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("profile", "control"))
    cli.add_argument("root", type=Path)
    cli.add_argument("--worker", action="store_true")
    args = cli.parse_args()
    if args.worker:
        work(args.mode, args.root)
    else:
        launch(args.root, args.mode)
