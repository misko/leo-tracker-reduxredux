"""Measure an exact full-grid composition on the current DS30-0138 route."""

import argparse
from collections import Counter
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
import subprocess
import sys
from time import perf_counter_ns, process_time_ns, time_ns
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import history_risk_0138 as active
from inference_0138_profile import ORIGINAL, ORIGINAL_SEAL


PROJECTION = Path("/dev/shm/leo-grid-feature-projection-02/native-map.so")
TEMPLATE = "template.so"
PROTOCOL = HERE/"exact-grid-0138-protocol.md"


def clock():
    return process_time_ns(), perf_counter_ns()


def elapsed(start):
    end = clock()
    return dict(cpu_ns=end[0]-start[0], elapsed_ns=end[1]-start[1])


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def grid_body(grid):
    return {key: value for key, value in grid.items() if key != "elapsed_seconds"}


def deny_backing(event, arguments):
    if event == "open" and isinstance(arguments[0], (str, bytes)):
        path = Path(os.path.abspath(os.fsdecode(arguments[0])))
        if path.is_relative_to("/srv/bulk") or path.is_relative_to("/mnt/qnap01"):
            raise ValueError(f"Saved grid trial cannot open backing input {path}")


class PredictiveAudit:
    def __init__(self, ordinary):
        self.ordinary = ordinary
        self.counts = Counter()
        self.max_abs_delta = 0.

    def __call__(self, *args):
        from grid_predictive_reduction import reduced_predictive

        def original():
            start = process_time_ns()
            answer = self.ordinary(*args)
            self.counts["stock_cpu_ns"] += process_time_ns()-start
            return answer

        def candidate():
            start = process_time_ns()
            try:
                value, details = reduced_predictive(*args, include_residual=True)
                self.counts["reduced_cpu_ns"] += process_time_ns()-start
                self.counts["removed_bias_columns"] += details["biases"]
                self.counts["removed_zero_prefix_columns"] += details["prefix"]
                return value
            except (ValueError, ArithmeticError):
                self.counts["failure_cpu_ns"] += process_time_ns()-start
                self.counts["unsupported"] += 1
                return None

        if self.counts["calls"] % 2:
            test, result = candidate(), original()
        else:
            result, test = original(), candidate()
        self.counts["calls"] += 1
        if test is not None:
            diff = abs(test["objective"] - result["objective"])
            self.max_abs_delta = max(self.max_abs_delta, diff)
            self.counts["objective_differences"] += int(diff != 0.)
            self.counts["normalization_differences"] += int(test["normalization_constant"] != result["normalization_constant"])
        return result


def grid_port(original, native, template, observed, *, probe):
    """Compose the released grid wrapper with one exact candidate call."""
    from functools import partial

    from grid_feature_projection import bind_grid
    from leo.analysis.localization_v3 import marginal
    from leo.presentation import localization_v3 as presentation
    from tools.pipeline_eval.variants import algo08_posterior_handoff as handoff

    @contextmanager
    def port():
        sample = presentation.sample_position_grid

        def bind(base, geometry, prepared):
            accelerated, replace_geometry = bind_grid(native, base, geometry, prepared)

            def run(*args, **kwargs):
                with template.binding(marginal.JointMarginal.calculate.__globals__):
                    return accelerated(*args, **kwargs)

            return run, replace_geometry

        with original(bind=bind) as counters:
            accelerated = presentation.sample_position_grid
        with original() as stock_counts:
            ordinary = presentation.sample_position_grid

        def measured(score, endpoints, **kwargs):
            from leo.contracts.digests import canonical_digest

            if observed:
                raise ValueError("Expected one original diagnostic grid invocation")
            if not probe:
                start = clock()
                result = accelerated(score, endpoints, **kwargs)
                observed.update(exact=elapsed(start))
            else:
                def sweep(implementation):
                    for arm, position in endpoints.items():
                        score(arm, position)
                    start = clock()
                    grid = implementation(score, endpoints, **kwargs)
                    return grid, elapsed(start)

                reference, observed["ordinary"] = sweep(ordinary)
                result, observed["exact"] = sweep(accelerated)
                if canonical_digest(grid_body(result)) != canonical_digest(grid_body(reference)):
                    raise ValueError("Composed projection changed at least one standard grid field")
                comparison = PredictiveAudit(handoff.predictive_factor)
                with patch.object(handoff, "predictive_factor", comparison):
                    shadow, observed["shadow"] = sweep(ordinary)
                if canonical_digest(grid_body(result)) != canonical_digest(grid_body(shadow)):
                    raise ValueError("Paired predictive measurements changed the ordinary output")
                observed.update(predictive=dict(counts=dict(comparison.counts), max_abs_delta=comparison.max_abs_delta),
                                cpu_credit_s=(observed["ordinary"]["cpu_ns"]-observed["exact"]["cpu_ns"]) / 1e9)
            if not result["complete"] or result["evaluated_points"] != 179 or native.counts["grids"] != 1:
                raise ValueError("Expected actual acceleration on the full 179-point standard grid")
            observed.update(grid_sha256=canonical_digest(grid_body(result)), sampled_points=result["evaluated_points"],
                            projection=dict(native.counts), assembly=dict(template.counts),
                            exact_phase=dict(counters), ordinary_phase=dict(stock_counts))
            return result

        with patch.object(presentation, "sample_position_grid", measured):
            yield counters

    return port


def worker(root, probe):
    import empty_bootstrap as boot

    sys.addaudithook(deny_backing)
    spec = json.loads((root/"grid-binding.json").read_bytes())
    for relative, expected in spec["sources"].items():
        if digest(HERE/relative) != expected:
            raise ValueError(f"Stale study source {relative}")
    boot.checked(root/TEMPLATE, spec["template_sha256"])
    ordinary, audit = boot.load_runtime, {}
    with _load_grid(boot, ordinary, root, probe, audit):
        active.worker(root, "routed")
    from aperture_trial import write

    write(root/"grid-audit.json", audit)


@contextmanager
def _load_grid(boot, ordinary, root, probe, audit):
    from contextlib import ExitStack

    with ExitStack() as stack:
        def load():
            runtime = ordinary()
            from grid_design_template import Designs
            from grid_feature_projection import Native, LIBRARY_SHA, supported_cpu
            import grid_phase_state_reuse as phase

            boot.checked(PROJECTION, LIBRARY_SHA)
            if not supported_cpu():
                raise ValueError("The existing native projection requires the measured x86 host")
            native, template = Native(PROJECTION), Designs(root/TEMPLATE)
            port = grid_port(phase.cached_predictive_grid, native, template, audit, probe=probe)
            stack.enter_context(patch.object(phase, "cached_predictive_grid", port))
            return runtime

        stack.enter_context(patch.object(boot, "load_runtime", load))
        yield


def prepare(root, probe, prior):
    from aperture_trial import write
    from empty_bootstrap import RELEASE
    from exact_named_route import checked_catalogue
    from grid_design_template import build
    from history_risk_route_trial import sources
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader

    sys.addaudithook(deny_backing)
    if root.parent.resolve(strict=True) != Path("/dev/shm") or root.exists():
        raise ValueError("Use a new output under tmpfs")
    if not probe:
        comparison = json.loads((prior/"score.json").read_bytes())
        if not all(comparison["parity"].values()) or comparison["grid"]["cpu_credit_s"] < .30:
            raise ValueError("The exact candidate must first clear the frozen grid gate")
    active.checked(ORIGINAL/"result.json", ORIGINAL_SEAL)
    bound, req = active.bound_request()
    _, refs = checked_catalogue(bound, req, TleArchiveReader, canonical_digest)
    paths = [r.path for r in refs] + [Path(req["native_file"]), Path(bound["portable"][0]), PROJECTION]
    residents = json.loads(subprocess.check_output(["fincore", "--json", "--bytes", "-o", "RES,SIZE", *paths]))["fincore"]
    if len(residents) != len(paths) or any(r["res"] < r["size"] for r in residents):
        raise ValueError("Expected the whole authenticated saved input to be resident")
    root.mkdir(mode=0o700)
    for name in ("tmp", "fonts"):
        (root/name).mkdir()
    for path in (ORIGINAL/"fonts").glob("fontlist-*.json"):
        os.link(path, root/"fonts"/path.name)
    compile_start = clock()
    build(root/TEMPLATE)
    compile_clock = elapsed(compile_start)
    argv = ["/usr/bin/timeout", "--kill-after=2s", "56s", str(RELEASE/"venv/bin/python"), "-IB",
            str(Path(__file__).resolve()), "probe-worker" if probe else "active-worker", str(root)]
    write(root/"grid-binding.json", dict(
        command=argv, template_sha256=digest(root/TEMPLATE), build=compile_clock,
        earlier_publication_sha256=ORIGINAL_SEAL, probe=probe,
        sources={p.name: digest(p) for p in (
            Path(__file__), PROTOCOL, HERE/"grid_design_template.py", HERE/"grid_design_template.c",
            HERE/"grid_feature_projection.py", HERE/"grid_predictive_reduction.py")},
        admitted_resident_objects=len(paths), admitted_resident_bytes=sum(r["size"] for r in residents)))
    write(root/"binding.json", dict(input=bound))
    write(root/"route-binding.json", dict(cutoff_utc_ns=req["causal_cutoff_utc_ns"], sources=sources("0138")))
    return argv


def launch(root, probe, prior):
    from aperture_trial import write
    from full_short_physical import environment

    argv = prepare(root, probe, prior)
    env = environment(root) | {"TMPDIR": str(root/"tmp"), "XDG_CACHE_HOME": str(root/"tmp")}
    initial, before = time_ns(), getrusage(RUSAGE_CHILDREN)
    start = perf_counter_ns()
    with (root/"candidate.stdout").open("x") as stdout, (root/"candidate.stderr").open("x") as stderr:
        child = subprocess.run(argv, env=env, stdout=stdout, stderr=stderr, check=False)
    finish, after = perf_counter_ns(), getrusage(RUSAGE_CHILDREN)
    write(root/"clock.json", dict(started_unix_ns=initial, elapsed_s=(finish-start)/1e9, exit_code=child.returncode,
                                  cpu_s=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
                                  input_blocks=after.ru_inblock-before.ru_inblock, major_faults=after.ru_majflt-before.ru_majflt))
    if child.returncode:
        raise ValueError("Saved worker failed; its charged clock and stderr are sealed")
    score(root)


def score(root):
    from aperture_trial import write
    from exact_named_route_score import parity
    from held_adaptive_0160_score import verified

    sys.addaudithook(deny_backing)
    request = json.loads(active.checked(active.STAGE/"request.json", active.REQUEST_PIN))
    previous = json.loads(active.checked(ORIGINAL/"result.json", ORIGINAL_SEAL))
    before = verified(ORIGINAL/"routed/candidate", previous["clock"], "worker.json", request)
    paid = json.loads((root/"clock.json").read_bytes())
    after = verified(root/"candidate", paid, "worker.json", request)
    same = parity(before, after)
    if not all(same.values()):
        raise ValueError(f"Grid-only composition changed a standard product or science: {same}")
    route = json.loads((root/"risk-route.json").read_bytes())["solves"]
    original = json.loads((ORIGINAL/"routed/risk-route.json").read_bytes())["solves"]
    a, = route
    b, = original
    fit, = a["lean_attempts"]
    old_fit, = b["lean_attempts"]
    if (a["choice"]["route"] != b["choice"]["route"] or fit["exterior"] != old_fit["exterior"]
            or fit["decision"] != old_fit["decision"]):
        raise ValueError("The unchanged geographic decision or ordinary route changed")
    write(root/"score.json", dict(binding=json.loads((root/"grid-binding.json").read_bytes()), outcome=after["terminal"],
        parity=same, owner_counts={arm: len(rows) for arm, rows in after["rows"].items()},
        figures=after["products"]["images"], clock=paid, original_clock=previous["clock"],
        geographic=fit["exterior"], evidence=fit["standard_evidence_clocks"],
        original_evidence=old_fit["standard_evidence_clocks"],
        grid=json.loads((root/"grid-audit.json").read_bytes()), waveform_reads=0))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("probe", "active", "probe-worker", "active-worker", "score"))
    cli.add_argument("root", type=Path)
    cli.add_argument("--prior", type=Path)
    args = cli.parse_args()
    if args.action in ("probe", "active"):
        launch(args.root, args.action == "probe", args.prior)
    elif args.action.endswith("worker"):
        worker(args.root, args.action == "probe-worker")
    else:
        score(args.root)
