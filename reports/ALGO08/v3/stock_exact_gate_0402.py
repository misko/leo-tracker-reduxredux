"""Exercise exact gate preparation inside the installed named 0402 publication."""

import argparse
from collections import Counter
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import shutil
import sys
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

import numpy as np

HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

from exact_noise_gate_0402 import PreparedNoiseScreen
from named_roster_0402 import ARCHIVE_SHA, BASELINE, CUTOFF, PINS, STAGE, pinned, refs, trial_record
from prospective_0402_solver import ARMS, SETTINGS, inspect, invoke


PROFILE = STAGE.with_name("leo-v3-named-roster-0402-control01") / "roster.json"
PROFILE_SHA = "a074675d108d8edb3bc801ec542b6caf0ce979b4f00dc38b8bf20186fc3d8b02"
CLOCK_SHA = "47f78189857d8d8a0a03a26cd2ef824fa467514d921fd967328fb22223d0ff63"
RELEASE_SOURCES = {
    "feasible.py": "a9c5857fcba549f0c8059a544cae7912d4d640dba4af4778689e9aa577807d41",
    "family_cavity.py": "7a20ac84d4c245df95481d10425def01642cbf4d3f45f1f32b9188a78007b3ae",
    "retained_track_likelihood.py": "73c24d054d5676c7d7051779a6960f8f692ce0d97bc23d292470aa01f6110bcf",
    "polynomial_satellite_diagnostics.py": "8bf7d7935b74bba728d437d2652af636e5532be74d798ed4f56c6641be7352c5",
}


class WhiteProfile:
    """Retain the verified stock diagonal and its original scalar contractions."""

    def __init__(self, matrix, period, noise):
        self.matrix, self.period, self.noise = matrix, period, noise
        self.diagonal = np.diag(matrix)
        self.information = self.diagonal @ self.diagonal
        self.constants = {b: (self.information + 1 / b**2, np.log1p(b**2 * self.information)) for b in (300., 1000.)}

    def __call__(self, observed, predicted, bias_sigma):
        y, f = np.asarray(observed), np.atleast_2d(predicted)
        denominator, normalizer = self.constants[bias_sigma]
        raw = y - f
        alias = np.rint(-raw.mean(axis=1) / self.period)
        raw += alias[:, None] * self.period
        z = raw * self.diagonal
        bias = z @ self.diagonal / denominator
        innovations = z - bias[:, None] * self.diagonal
        residual = raw - bias[:, None]
        cost = np.sum(innovations**2, axis=1) + (bias / bias_sigma) ** 2
        cost += 0.0 + normalizer
        return dict(alias=alias, bias=bias, residual=residual, innovations=self.noise * innovations,
                    rms=np.sqrt(np.mean(residual**2, axis=1)), cost=cost)


class GateWork:
    """Reuse time and white-diagonal work for one unchanged cavity configuration."""

    def __init__(self, feasible, likelihood, counts):
        self.stock = feasible.batch_noise_screen
        self.stock_whitening = feasible.whitening
        self.stock_profile = feasible.profile
        self.likelihood, self.counts = likelihood, counts
        self.screens, self.whites, self.profiles = {}, {}, {}

    @staticmethod
    def time_key(times):
        return times.tobytes() if type(times) is np.ndarray and times.ndim == 1 and times.dtype == np.float64 else None

    def screen(self, residual, times):
        key = self.time_key(times)
        if key is None or type(residual) is not np.ndarray or residual.dtype != np.float64 or residual.shape != (1, len(times)):
            self.counts["screen_stock"] += 1
            return self.stock(residual, times)
        prepared = self.screens.get(key)
        if prepared is None:
            start = process_time_ns()
            prepared = self.screens[key] = PreparedNoiseScreen(times)
            self.counts["screen_setup_cpu_ns"] += process_time_ns() - start
            self.counts["screen_preparations"] += 1
        self.counts["screen_calls"] += 1
        return prepared(residual)

    def whitening(self, times, **kwargs):
        key = self.time_key(times)
        if kwargs or key is None:
            self.counts["white_stock"] += 1
            return self.stock_whitening(times, **kwargs)
        cached = self.whites.get(key)
        if cached is None:
            cached = self.whites[key] = self.stock_whitening(times)
            self.counts["white_preparations"] += 1
        self.counts["white_calls"] += 1
        return cached

    def profile(self, observed, predicted, inverse, logvolume=0.0, *, bias_sigma=1000.0):
        key = id(inverse)
        known = self.profiles.get(key)
        if known is None and (type(inverse) is np.ndarray and inverse.ndim == 2 and inverse.dtype == np.float64
                              and inverse.shape[0] == inverse.shape[1] and inverse.flags.c_contiguous):
            diagonal = np.diag(inverse)
            if np.count_nonzero(inverse) == len(diagonal) and np.all(diagonal == 1 / self.likelihood.NOISE):
                known = self.profiles[key] = WhiteProfile(inverse, self.likelihood.PERIOD, self.likelihood.NOISE)
                self.counts["profile_preparations"] += 1
        if (known is None or logvolume != 0.0 or bias_sigma not in (300., 1000.) or type(observed) is not np.ndarray
                or observed.ndim != 1 or type(predicted) is not np.ndarray or predicted.ndim not in (1, 2)
                or predicted.shape[-1] != len(observed) or inverse.shape[0] != len(observed)):
            self.counts["profile_stock"] += 1
            return self.stock_profile(observed, predicted, inverse, logvolume, bias_sigma=bias_sigma)
        self.counts["profile_calls"] += 1
        return known(observed, predicted, bias_sigma)


@contextmanager
def gate_binding(feasible, cavity, likelihood, counts, *, use_white=True):
    """Apply only inside the constrained optimizer; admission and final gates remain stock."""
    original, fit = cavity.constrained, feasible.feasible_fit

    def constrained(*args, **kwargs):
        work = GateWork(feasible, likelihood, counts)
        counts["constrained_calls"] += 1

        def run_fit(*values, **options):
            start = process_time_ns()
            whitening = work.whitening if use_white else work.stock_whitening
            profile = work.profile if use_white else work.stock_profile
            with (patch.object(feasible, "batch_noise_screen", work.screen),
                  patch.object(feasible, "whitening", whitening), patch.object(feasible, "profile", profile)):
                result = fit(*values, **options)
            counts["fit_cpu_ns"] += process_time_ns() - start
            counts["phase_fits"] += 1
            counts["visits"] += result["evaluations"]
            return result

        start = process_time_ns()
        with patch.object(feasible, "feasible_fit", run_fit):
            result = original(*args, **kwargs)
        counts["constrained_cpu_ns"] += process_time_ns() - start
        return result

    with patch.object(cavity, "constrained", constrained):
        yield


def validate_released_ports(feasible, cavity, likelihood, noise):
    for module in (feasible, cavity, likelihood, noise):
        path = Path(module.__file__)
        if sha256(path.read_bytes()).hexdigest() != RELEASE_SOURCES[path.name]:
            raise ValueError(f"Unrecognized installed {path.name} source")
    if (cavity.constrained is not feasible.constrained or feasible.profile is not likelihood.profile
            or feasible.whitening is not likelihood.whitening or feasible.batch_noise_screen is not noise.batch_noise_screen):
        raise ValueError("The original constrained gate ports are already modified")


def inputs():
    from leo.contracts.digests import canonical_digest

    req = pinned(STAGE / "request.json", PINS["request"])
    archive = STAGE / "tle"
    if (Path(req["local_archive"]["root"]).resolve() != archive or req["causal_cutoff_utc_ns"] != CUTOFF
            or Path(req["native_file"]).resolve() != STAGE / "named-detections.json"
            or canonical_digest({row.path.name: row.sha256 for row in refs(archive)}) != ARCHIVE_SHA):
        raise ValueError("Expected the authenticated original already-staged inputs")
    return req


def worker(output, *, binding=gate_binding, summarize_trial=trial_record):
    import empty_bootstrap as boot
    from dense_geographic_trial import host

    machine = host()
    runtime = boot.load_runtime()
    from aperture_trial import write
    from leo.analysis.localization_v3 import family_cavity, feasible
    from leo.analysis.research import polynomial_satellite_diagnostics, retained_track_likelihood

    inputs()
    validate_released_ports(feasible, family_cavity, retained_track_likelihood, polynomial_satellite_diagnostics)
    counts, observed = Counter(), {}
    policy = family_cavity.cavity_policy

    def observe(*args, **kwargs):
        result = policy(*args, **kwargs)
        if result["status"] == "complete":
            observed.update(accepted=result["accepted"], gain=result["selection_gain"], penalty=result["search_penalty"],
                            trials=[summarize_trial(row) for row in result["trials"]],
                            null_objective_replay_differences=result["null_objective_replay_differences"])
        return result

    with (patch.object(boot, "load_runtime", return_value=runtime), patch.object(family_cavity, "cavity_policy", observe),
          binding(feasible, family_cavity, retained_track_likelihood, counts)):
        invoke(STAGE / "request.json", "stock", output)
    write(output / "exact-gates.json", dict(machine=machine, counts=dict(counts), cavity=observed,
          release_sources=RELEASE_SOURCES, request_sha256=PINS["request"],
          driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
          screen_sha256=sha256((HERE / "exact_noise_gate_0402.py").read_bytes()).hexdigest(),
          protocol_sha256=sha256((HERE / "stock-exact-gate-0402-protocol.md").read_bytes()).hexdigest()))


def launch(root, driver=None):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    host()
    if root.absolute() != root.resolve() or not root.is_relative_to("/dev/shm"):
        raise ValueError("Expected a private tmpfs destination")
    root.mkdir()
    scratch, fonts = root / "tmp", root / "fonts"
    scratch.mkdir()
    fonts.mkdir()
    for path in (STAGE / "fonts").glob("fontlist-v*.json"):
        shutil.copyfile(path, fonts / path.name)
    env = environment(root)
    env["TMPDIR"] = str(scratch)
    command = [RELEASE / "venv/bin/python", "-IB", driver or __file__, "worker", root / "exact"]
    clock = measure(command, env, root / "exact")
    write(root / "exit.json", dict(timing=clock, command=list(map(str, command))))
    if clock["exit_code"]:
        raise RuntimeError("The only candidate process did not complete")


def compare(actual, old):
    for field in ("terminal", "selected_rows", "sidecars"):
        if actual[field] != old[field]:
            raise ValueError(f"The complete named publication changed at {field}")
    figures = [{name: dict(row, size=tuple(row["size"])) for name, row in run["figures"].items()} for run in (actual, old)]
    if figures[0] != figures[1]:
        raise ValueError("The complete named publication changed at figures")
    for field in ("arms", "artifacts", "owners", "raw_authority", "reason", "scientific_digests"):
        if actual["science"][field] != old["science"][field]:
            raise ValueError(f"The complete named science changed at {field}")
    a, b = (run["worker"]["receipt"] for run in (actual, old))
    if a["terminal_sha256"] != b["terminal_sha256"]:
        raise ValueError("The installed named terminal digest changed")
    if ({k: v for k, v in a["screened_nomination"].items() if k != "initial_screen_cpu_s"}
            != {k: v for k, v in b["screened_nomination"].items() if k != "initial_screen_cpu_s"}):
        raise ValueError("The original ordered screened finalist scores changed")


def evaluate(root, destination):
    from aperture_trial import read, write
    from leo.contracts.digests import canonical_digest

    request = inputs()
    old = pinned(BASELINE, PINS["scored"])["runs"]["stock"]
    old_clock = pinned(STAGE / "stock-clock.json", CLOCK_SHA)["timing"]
    old_profile = pinned(PROFILE, PROFILE_SHA)
    clock = read(root / "exit.json")["timing"]
    output = root / "exact"
    measured = read(output / SETTINGS["audit_name"])
    if clock["exit_code"] or old["process"] != old_clock:
        raise ValueError("Expected a completed candidate and the exact sealed stock clock")
    actual = inspect(output, "exact", measured["receipt"], clock, request, **SETTINGS)
    compare(actual, old)
    gate = read(output / "exact-gates.json")
    if gate["cavity"] != old_profile["cavity"]:
        raise ValueError("Original failed and constrained cavity proposals changed")
    counts = gate["counts"]
    if any(counts.get(k) != expected for k, expected in dict(
            constrained_calls=1, phase_fits=10, visits=393, screen_calls=82137, profile_calls=48732, white_calls=33405).items()):
        raise ValueError(f"Preparation did not cover the frozen original dependent gates: {counts}")
    if any(counts.get(name, 0) for name in ("screen_stock", "profile_stock", "white_stock")):
        raise ValueError("The constrained worker exercised an unsupported gate")
    write(destination, dict(gates=gate, stock_exit=old_clock, stock_solve=old["worker"]["solve"],
          exact_exit=clock, exact_solve=actual["worker"]["solve"], terminal=actual["terminal"],
          owners={a: dict(count=len(actual["selected_rows"][a]), sha256=canonical_digest(actual["selected_rows"][a])) for a in ARMS},
          sidecars=actual["sidecars"], figures=actual["figures"], scores=pinned(BASELINE, PINS["scored"])["scores"]["stock"],
          bindings=dict(stock_publication=PINS["scored"], stock_exit=CLOCK_SHA, stock_profile=PROFILE_SHA),
          paired_science_equal=True, waveform_calls=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("worker", "launch", "evaluate"):
        args = sub.add_parser(command)
        args.add_argument("root", type=Path)
        if command == "evaluate":
            args.add_argument("destination", type=Path)
    options = parser.parse_args()
    if options.command == "evaluate":
        evaluate(options.root, options.destination)
    else:
        (worker if options.command == "worker" else launch)(options.root)
