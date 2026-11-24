"""Measure independent lag-peak disagreement and exact pre-carrier timing expansion."""

import argparse
from collections import Counter
from contextlib import ExitStack, closing
import ctypes as ct
from hashlib import sha256
from itertools import product
import json
from math import isfinite
import os
from pathlib import Path
from statistics import median
import subprocess
import sys
from unittest.mock import patch

from . import all_visit_timing as existing
from .mixed_aperture_receiver import PILOT_SHA, StereoSchedule
from .timing_only_oracle import asset_for, one
from .whole_group_receiver_bound import (FULL_BUILD, FULL_BUILD_SHA, SHORT_BUILD, SHORT_BUILD_SHA,
                                        SOURCE_SHA, measure, receiver)


HERE = Path(__file__).resolve().parent
PACK = Path("/dev/shm/leo-anchored-cfo-raw-pack01")
CONTROL_FULL = "f13593d12d91c631cf66377431080c42ca2f0b9553de4b8bc767390e2243f32c"
NARROW = Path("/dev/shm/leo-v3-all-visit-timing-pack01/short.so")
NARROW_PIN = "ad2bd4b05516b195c68d23a790e007cbea33734c55d1015903196568f6140228"
DISTANCES = (0, 1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 1666)
CONTRASTS = (1., 1.05, 1.10, 1.20, 1.35, 1.50, 2., 3., None)
MODES = {"cue": 1, "expanded": 2, "routed": 3}


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def write(path, document):
    with path.open("x") as stream:
        json.dump(document, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def overlay(source, extension):
    start = source.index("static void find_times(")
    end = source.index("static double bin_hz(", start)
    original = source[start:end]
    loop = "    for (int k = 0; k < lags; ++k) {\n"
    after = "    }\n    int radius ="
    body = original.split(loop, 1)[1].split(after, 1)[0].replace("w->time_score", "score")
    helper = "static void score_lag(TimingFirst *w, double *score, int k, int packed) {\n" + body + "}\n\n"
    original = one(original, loop + original.split(loop, 1)[1].split(after, 1)[0],
                   loop + "        score_lag(w, w->time_score, k, packed);\n")
    updated = source[:start] + helper + original + extension + "\n" + source[end:]
    a = updated.index("static int find_carriers(")
    b = updated.index("/* At a proposed native carrier", a)
    carrier = one(updated[a:b], "Seed *all)", "Seed *all, int timing_rows)")
    carrier = one(carrier, "i < clocks", "i < timing_rows")
    updated = updated[:a] + carrier + updated[b:]
    updated = one(updated, "    find_times(w, epochs);\n    Seed seeds[2 * clocks];",
                  "    const int timing_rows = cross_lag_times(w, epochs);\n    Seed seeds[2 * clocks];")
    return one(updated, "center, seeds), done = 0;", "center, seeds, timing_rows), done = 0;")


class Cue(ct.Structure):
    _fields_ = [("contrast", ct.c_double), ("distance", ct.c_int), ("expanded", ct.c_int)]


def setup(engine):
    engine.set_rule = engine.lib.set_cross_lag_rule
    engine.set_rule.argtypes = (ct.c_int, ct.c_int, ct.c_double)
    engine.set_rule.restype = None
    engine.get_cue = engine.lib.read_cross_lag_cue
    engine.get_cue.argtypes = (ct.POINTER(Cue),)
    engine.get_cue.restype = None
    return engine


def evaluate(engine, iq, lane, center, arm, rule):
    if arm in MODES:
        distance, contrast = rule
        engine.set_rule(MODES[arm], distance, float("inf") if contrast is None else contrast)
    factors, blob, cpu = measure(engine, iq, lane, center)
    out = dict(factors=factors, blob=blob.hex(), cpu_ns=cpu)
    if arm in MODES:
        value = Cue()
        engine.get_cue(ct.byref(value))
        out["cue"] = dict(distance=value.distance, contrast=value.contrast if isfinite(value.contrast) else None,
                          expanded=bool(value.expanded))
    return out


def train(binary, assets):
    import numpy as np

    rng = np.random.default_rng(4841)
    at = np.arange(200_000)
    for edge in PILOT_SHA:
        asset = asset_for(assets, edge)
        synthesis = asset[4 * 13333 + 81:].view(np.complex64)
        with closing(setup(receiver(binary, asset, "short"))) as engine:
            for strength, center in ((80, -50_000), (500, 60_000), (1500, 0), (0, 0)):
                iq = rng.normal(0, 19, (len(at), 2, 2)).astype(np.int16)
                for lane in (0, 1):
                    waveform = strength * synthesis[(3 * at - 2215 - 3201 * lane) % 40_000]
                    waveform *= np.exp(2j * np.pi * (-250000 + 381000 * lane) * at * 1e-7)
                    iq[:, lane, 0] += np.rint(waveform.real).astype(np.int16)
                    iq[:, lane, 1] += np.rint(waveform.imag).astype(np.int16)
                    for arm in MODES:
                        run = evaluate(engine, iq, lane, center, arm, (2, 1.20))
                        if bool(run["factors"]) != bool(strength):
                            raise ValueError("Unexpected result on preregistered site-free scout plants")


def build(root, assets):
    link = json.loads(existing.checked(SHORT_BUILD, SHORT_BUILD_SHA))["relink"]
    full = json.loads(existing.checked(FULL_BUILD, FULL_BUILD_SHA))
    timing, = (arg for arg in link if Path(arg).name == "timing_first_receiver.o")
    source = existing.checked(Path(timing).with_suffix(".c"), SOURCE_SHA["short"]).decode()
    existing.checked(existing.PROFILE, existing.PROFILE_SHA)
    root.mkdir()
    feedback = root / "profile"
    feedback.mkdir()
    c = root / "timing_first_receiver.c"
    c.write_text(overlay(source, (HERE / "cross_lag_timing.inc").read_text()))
    obj = c.with_suffix(".o")
    link_args = [str(obj) if arg == timing else str(existing.PROFILE) if Path(arg).name == "portable_verifier.o" else arg
                 for arg in link[1:-1] if not arg.startswith("-fprofile-use") and arg != "-fno-profile-values"]
    commands = []

    def run(command):
        commands.append(list(map(str, command)))
        subprocess.run(command, cwd=full["cwd"], check=True)

    for phase in ("generate", "use"):
        binary = root / ("short.so" if phase == "use" else "instrumented.so")
        pgo = [f"-fprofile-{phase}={feedback}", "-fno-profile-values"]
        strict = ["-Werror=missing-profile", "-Werror=coverage-mismatch"] if phase == "use" else []
        run([*full["commands"][-2][:-4], *pgo, *strict, "-c", c, "-o", obj])
        run([link[0], *pgo, *link_args, binary])
        if phase == "generate":
            run([sys.executable, "-Bm", "reports.ALGO08.v3.cross_lag_timing", "train", binary, assets])
    write(root / "build.json", {"sha256": digest(root / "short.so"), "generated_sha256": digest(c), "commands": commands,
                               "scorer_sha256": digest(Path(__file__)), "extension_sha256": digest(HERE / "cross_lag_timing.inc")})


def triggered(cue, rule):
    distance, contrast = rule
    return (cue["contrast"] is None or cue["distance"] > distance or contrast is None or cue["contrast"] < contrast)


def frontier(rows):
    scored = []
    for rule in product(DISTANCES, CONTRASTS):
        stats = Counter()
        for row in rows:
            output = row["result"]
            reference, narrow = output["ordinary"], output["cue"]
            bad = reference["blob"] != narrow["blob"]
            buy = triggered(narrow["cue"], rule)
            stats["wrong"] += bad
            stats["rescued"] += buy and bad
            stats["false_expansion"] += buy and not bad
            stats["expansions"] += buy
            stats["cpu_ns"] += output["expanded" if buy else "cue"]["cpu_ns"]
        scored.append(dict(rule=list(rule), **stats))
    choices = [row for row in scored if row["rescued"] == row["wrong"]]
    selected = min(choices, key=lambda row: (row["cpu_ns"], row["expansions"],
                                             -row["rule"][0], row["rule"][1] or float("inf")))
    return selected, scored


def capture(case, stage, assets, rule=None):
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import valid_window_support
    from leo.storage.fast_scan import FastSegmentSource
    from .zstd_wide_huffman import CASES, admit

    _, _, reader, chunk, hold, hashes, admitted = admit(case)
    pinned = {"ordinary": PACK / "short.so", "narrow": NARROW, "full": PACK / "full.so", "cue": stage / "short.so"}
    built = json.loads((stage / "build.json").read_bytes())
    for name, pin in (("ordinary", existing.ORIGINAL_SHORT), ("narrow", NARROW_PIN), ("full", CONTROL_FULL), ("cue", built["sha256"])):
        existing.checked(pinned[name], pin)
    source = FastSegmentSource(dict(path=str(reader.path), manifest_digest=CASES[case][1][0]), stop_sequence=64)
    schedule = StereoSchedule(full_coverage=True)
    policy = FastScanPolicyV2()
    rows, issued, invalid, anchors = [], [], [], []
    with ExitStack() as scope:
        from leo.storage.short_window import ScannerIqStore

        scope.enter_context(patch.object(ScannerIqStore, "_read_regular", staticmethod(hold.read)))
        engines = {}
        for window in source.windows():
            iq, target, acquisition = window.samples, window.target, window.acquisition
            issued.append(window.iq_sha256)
            if not valid_window_support(acquisition, window.sample_rate_hz, iq.shape, (0, 1), policy):
                invalid.append(window.sequence)
                continue
            edge = target["edge"]
            if edge not in engines:
                asset = asset_for(assets, edge)
                engines[edge] = {mode: scope.enter_context(closing(receiver(path, asset, "full" if mode == "full" else "short")))
                                 for mode, path in pinned.items()}
                setup(engines[edge]["cue"])
            _, aperture = schedule.visit(edge, target, acquisition)
            center = target["rf_center_hz"] - target["lnb_lo_hz"] - acquisition["actual_if_center_hz"]
            for lane in (0, 1):
                common = dict(visit=window.sequence, lane=lane, counter=acquisition["sample_start"], iq_sha256=window.iq_sha256)
                if aperture == "full":
                    anchors.append(dict(common, **evaluate(engines[edge]["full"], iq, lane, center, "full", None)))
                    continue
                modes = ("ordinary", "narrow", "cue", "expanded") + (("routed",) if rule else ())
                trials = []
                for repetition in range(3):
                    shift = (window.sequence + lane + repetition) % len(modes)
                    trials.append({arm: evaluate(engines[edge]["cue" if arm in MODES else arm], iq, lane, center,
                                                 arm, rule or (0, 1.)) for arm in (*modes[shift:], *modes[:shift])})
                result = {arm: dict(trials[0][arm], cpu_ns=median(run[arm]["cpu_ns"] for run in trials)) for arm in modes}
                for run in trials:
                    if run["cue"]["blob"] != run["narrow"]["blob"] or run["expanded"]["blob"] != run["ordinary"]["blob"]:
                        raise ValueError(f"Timing reuse changed the native bytes on signed lane {window.sequence}/{lane}")
                    if rule:
                        buy = triggered(run["cue"]["cue"], rule)
                        if bool(run["routed"]["cue"]["expanded"]) != buy or run["routed"]["blob"] != run["expanded" if buy else "cue"]["blob"]:
                            raise ValueError("The actual native routing differs from the frozen weight-free rule")
                rows.append(dict(common, result=result))
    if tuple(issued) != hashes or len(issued) != len(invalid) + (len(rows) + len(anchors)) // 2:
        raise ValueError("Partial visit, invalid stereo order or original hash drift")
    best, roc = frontier(rows)
    return dict(case=case, rule=rule, native_members=chunk.model_dump(mode="json"), resident=admitted,
                iq=issued, invalid=invalid, anchors=anchors, shortlist=rows, cheapest_zero_change=best, roc=roc,
                built=built, source=str(reader.path), manifest_sha256=reader.manifest_sha256)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("train", "build", "development", "routed-dense", "held"))
    cli.add_argument("path", type=Path)
    cli.add_argument("assets", type=Path)
    cli.add_argument("--build", type=Path)
    cli.add_argument("--frozen", type=Path)
    cli.add_argument("--sha256")
    args = cli.parse_args()
    if args.mode in ("train", "build"):
        (train if args.mode == "train" else build)(args.path, args.assets)
        return
    if os.sched_getaffinity(0) != {2}:
        raise ValueError("Use the shared Gauss CPU2 slot")
    rule = None
    if args.mode != "development":
        decision = json.loads(existing.checked(args.frozen, args.sha256))
        if decision["case"] != "DS30-0008" or decision["rule"] is not None:
            raise ValueError("A sealed dense development decision is required")
        rule = decision["cheapest_zero_change"]["rule"]
    write(args.path, capture("DS30-0016" if args.mode == "held" else "DS30-0008", args.build, args.assets, rule))


if __name__ == "__main__":
    main()
