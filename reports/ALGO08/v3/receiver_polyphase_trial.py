"""Measure full and half-grid timing inverse transforms against installed ALGO08v3."""

import argparse
import json
import math
import subprocess
from collections import Counter
from itertools import combinations
from pathlib import Path

from tools.pipeline_eval.variants.experimental import receiver_build
from tools.pipeline_eval.variants.experimental.receiver_benchmark import benchmark, digest, read_archive
from tools.pipeline_eval.variants.experimental.receiver_brackets import read_physical
from tools.pipeline_eval.variants.experimental.receiver_cfo_peak_bound import (
    TIMING_SOURCE_SHA, V3_SHA,
)
from tools.pipeline_eval.variants.experimental.receiver_tracking import agree, measured_epoch, PERIOD

from .receiver_refine_pgo_trial import exports, train


EXPERIMENTS = Path(receiver_build.__file__).parent
POLYPHASE = EXPERIMENTS / "receiver_polyphase_timing.inc"


def replace_once(source, original, replacement):
    if source.count(original) != 1:
        raise ValueError(f"unexpected pinned source near {original!r}")
    return source.replace(original, replacement, 1)


def overlay(source, arm):
    if arm not in ("full_grid", "half_grid"):
        raise ValueError(f"unrecognized polyphase arm: {arm}")
    declarations = """
    fftwf_plan folded_inverse;
    Sample *odd_rotation;
"""
    marker = "    fftwf_plan plans[3];"
    source = replace_once(source, marker, marker + declarations)
    marker = '#include "receiver_fftw.inc"'
    source = replace_once(source, marker, marker + """
static int prepare_polyphase(TimingFirst *);
static void release_polyphase(TimingFirst *);
""")
    source = replace_once(source, "    release_fft(w);", "    release_polyphase(w);\n    release_fft(w);")
    source = replace_once(source, "if (!prepare_fft(w))", "if (!prepare_fft(w) || !prepare_polyphase(w))")
    marker = '#include "receiver_spectral_vectors.inc"'
    source = replace_once(source, marker, marker + f"\n#define timing_fold_both {int(arm == 'full_grid')}\n"
                          + POLYPHASE.read_text())
    marker = "static void find_times(TimingFirst *w, int *epochs) {"
    return replace_once(source, marker, marker + """
    if (w->folded_inverse && __builtin_cpu_supports("avx2")) {
        find_polyphase_times(w, epochs);
        return;
    }
""")


def stage_profile(source):
    signatures = receiver_build.PROFILE_SIGNATURES["timing_first_receiver.c"][:-1]
    source = receiver_build.profile_source(source, [*signatures, ("static int detect_lane(", "TIMING")])
    source = replace_once(source, "        if (delay_decimate(", "        PROFILE(DECIMATE);\n"
                          "        if (delay_decimate(")
    marker = """    if (delay_refine_bank((float *)w->data, (float *)(w->pilot + first), request, done, lo, hi, v))
        return -1;"""
    return replace_once(source, marker, "{ PROFILE(REFINE);\n" + marker + "\n    }\n") + (
        EXPERIMENTS / "receiver_profile.c").read_text()


def build(args):
    installed = args.installed
    if digest(installed.read_bytes()) != V3_SHA:
        raise ValueError("unexpected installed ALGO08v3 receiver bytes")
    archive = json.loads((args.archive / "build.json").read_bytes())
    compiler_id = subprocess.check_output(["cc", "--version"], text=True).splitlines()[0]
    if compiler_id != archive["compiler"]:
        raise ValueError("unexpected compiler version")
    original, = (Path(value).with_suffix(".c") for value in archive["commands"][-1]
                 if Path(value).name == "timing_first_receiver.o")
    original = original.read_bytes()
    if digest(original) != TIMING_SOURCE_SHA:
        raise ValueError("unexpected installed timing source")
    recipe = json.loads(args.history.read_bytes())["build"]["builds"]["packed"]
    args.work.mkdir()
    binaries, receipts = {}, {}
    stock = original.decode()
    for arm in ("stock", "full_grid", "half_grid", "stock_stages", "half_grid_stages"):
        source_arm = arm.removesuffix("_stages")
        source = stock if source_arm == "stock" else overlay(stock, source_arm)
        if arm.endswith("_stages"):
            source = stage_profile(source)
        work = args.work / arm
        work.mkdir()
        (work / "timing_first_receiver.c").write_text(source)
        binary, receipt = train(work, archive, recipe, args)
        binaries[arm], receipts[arm] = binary, receipt
        expected = exports(installed)
        if arm.endswith("_stages"):
            expected |= {"experimental_receiver_profile_read", "experimental_receiver_profile_reset",
                         "receiver_stats"}
        if exports(binary) != expected:
            raise ValueError(f"unexpected receiver exports from {arm}")
    if receipts["stock"]["library_sha256"] != V3_SHA:
        raise ValueError("fresh PGO stock did not reproduce installed bytes")
    if receipts["stock"]["timing_sha256"] != recipe["timing_object_sha256"]:
        raise ValueError("fresh PGO stock timing object differs from the archived object")
    return binaries, dict(compiler=compiler_id, installed_sha256=V3_SHA,
                          polyphase_source_sha256=digest(POLYPHASE.read_bytes()), arms=receipts)


def match_factors(reference, candidate):
    """Match at most two factors exclusively, preferring the closest full-rate epoch."""
    compatible = [(i, j) for i, a in enumerate(reference) for j, b in enumerate(candidate)
                  if agree(a, b)]
    pairs = [(), *((match,) for match in compatible)]
    pairs.extend((a, b) for a, b in combinations(compatible, 2)
                 if a[0] != b[0] and a[1] != b[1])

    def priority(matches):
        error = sum(abs(math.remainder(measured_epoch(reference[i]) - measured_epoch(candidate[j]),
                                       PERIOD)) for i, j in matches)
        return -len(matches), error

    return min(pairs, key=priority)


def outcomes(observations):
    counts, changed = Counter(), []
    maximum_delta = [0.] * 4
    for reference, candidate in zip(*observations, strict=True):
        if reference[:2] != candidate[:2]:
            raise ValueError("unmatched lane identity")
        key, lane, left, old_selection = reference
        _, _, right, new_selection = candidate
        pairs = match_factors(left, right)
        counts.update(("reference", f[0]) for f in left)
        counts.update(("candidate", f[0]) for f in right)
        counts.update(("matched", left[i][0]) for i, _ in pairs)
        counts.update(("matched_candidate", right[j][0]) for _, j in pairs)
        old, new = old_selection[1], new_selection[1]
        counts["reference_continued"] += old is not None
        counts["candidate_continued"] += new is not None
        counts["matching_continued"] += (old, new) in pairs
        counts["lanes_missing_factor"] += len(pairs) < len(left)
        counts["lanes_adding_factor"] += len(pairs) < len(right)
        for i, j in pairs:
            a, b = left[i], right[j]
            differences = [abs(math.remainder(measured_epoch(a) - measured_epoch(b), PERIOD)),
                           *(abs(a[k] - b[k]) for k in (3, 4, 5))]
            maximum_delta = list(map(max, zip(maximum_delta, differences, strict=True)))
        if left != right or old_selection != new_selection:
            changed.append(dict(key=key, lane=lane, installed=left, candidate=right, matches=pairs,
                                continuations=[old_selection, new_selection]))
    for name in ("reference", "candidate", "matched", "matched_candidate"):
        counts[name + "_by_rank"] = [counts.pop((name, rank), 0) for rank in (0, 1)]
    return dict(counts=counts, changed=changed, maximum_matched_epoch_hz_exact_control_delta=maximum_delta)


def retry_cost(observations, reference_clocks, total_cpu):
    routes = {name: [] for name in ("oracle_factor_availability", "oracle_factor_bytes", "fewer_than_two")}
    for index, (reference, candidate) in enumerate(zip(*observations, strict=True)):
        left, right = reference[2], candidate[2]
        if len(match_factors(left, right)) < max(len(left), len(right)):
            routes["oracle_factor_availability"].append(index)
        if left != right:
            routes["oracle_factor_bytes"].append(index)
        if len(right) < 2:
            routes["fewer_than_two"].append(index)
    return {name: dict(lanes=len(lanes), additional_native_cpu_s=[
        sum(clock[i] for i in lanes) / 1e9 for clock in reference_clocks],
        candidate_over_installed_cpu_after_retry=[
            (candidate + sum(clock[i] for i in lanes) / 1e9) / installed
            for clock, (installed, candidate) in zip(reference_clocks, total_cpu, strict=True)
    ]) for name, lanes in routes.items()}


def measure(args, variants):
    arms = ("full_grid", "half_grid")
    groups = {"weak": list(read_archive(args.weak, 18)),
              "dense": list(read_physical(args.binding, args.bulk, 48))}
    runs = {}
    for name, group in groups.items():
        comparisons = {}
        for arm in arms:
            receipt = benchmark((args.installed, variants[arm]), group, args.assets, args.repeats,
                                include_observations=True)
            observations = receipt.pop("observations")
            receipt["factors"] = outcomes(observations)
            receipt["retry"] = retry_cost(observations, receipt.pop("reference_lane_cpu_ns"),
                                          receipt["total_cpu_s"])
            comparisons[arm] = receipt
        profiled = benchmark((variants["stock_stages"], variants["half_grid_stages"]),
                             group, args.assets, args.repeats)
        if profiled["factor_digests"] != comparisons["half_grid"]["factor_digests"]:
            raise ValueError("instrumentation changed sample results")
        runs[name] = dict(
            inputs=[(row["key"], row["sha256"]) for row, _ in group],
            comparisons=comparisons,
            stages=profiled["profiles"],
        )
    return runs


def run(args):
    variants, built = build(args)
    return dict(build=built, runs=measure(args, variants))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("archive", "history", "work", "installed", "assets", "weak", "binding", "bulk"):
        parser.add_argument(key, type=lambda value: Path(value).resolve())
    parser.add_argument("--repeats", type=int, choices=range(1, 6), default=5)
    print(json.dumps(run(parser.parse_args()), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
