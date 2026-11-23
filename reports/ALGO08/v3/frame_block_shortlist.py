"""Measure blind coherent-pair nomination followed by the original short verifier."""

import argparse
from collections import Counter
from contextlib import ExitStack
import ctypes as ct
from hashlib import sha256
import json
from math import remainder
from pathlib import Path
from statistics import median
import subprocess
from time import perf_counter_ns, process_time_ns

import numpy as np

from .centered_primary import BUILD_PIN, ORIGINAL, PREFIX_PIN, RELEASE_BUILD, RELEASE_PIN, WEAK_PIN
from .mixed_aperture_receiver import INSTALLED_SHA, PILOT_SHA, NativePath, StereoSchedule, verified
from .mixed_aperture_trial import center, window
from .scout_readout_trial import check_machine, factor_bytes
from .short_primary_dead_work import (ARCHIVE, SHORT_OBJECTS, TILE_BUILD_PIN, TILE_PIN, TIMING_PIN, ShortTrace,
                                     north_rows, read_archive, replace_once, tile_source, traced)
from .sparse_cold_input import PAYLOAD, RELEASE
from .warm_six_prefetch import archived


HERE = Path(__file__).resolve().parent
REPEATS = 4
EARLY, LATE = (22, 8098), (20022, 28098)


class Trace(ct.Structure):
    _fields_ = [("count", ct.c_int), ("epoch", ct.c_int*4), ("signed_hz", ct.c_double*4),
                ("proposal_ns", ct.c_uint64)]


def timing_source(source, include):
    source = replace_once(source, "    clocks = 12,", "    clocks = 4,")
    source = replace_once(source, "static int detect_lane(", include + "\nstatic int detect_lane(")
    source = replace_once(source, "    if (!resident) input(w, iq, lane, center);",
                          "    uint64_t begin = block_cpu_now();\n"
                          "    if (!resident) input(w, iq, lane, center);")
    source = replace_once(source, "    principal_modes(w, low);",
                          "    if (w->stride == 4) coherent_frame_pairs(w, low);\n"
                          "    else principal_modes(w, low);")
    source = replace_once(source, "if (delay_decimate((float *)w->data,",
                          "if (delay_decimate_scout_used((float *)w->data,")
    source = replace_once(source, "static int detect_lane(",
                          "int delay_decimate_scout_used(const float *, const float *, int, int, float *);\n"
                          "static int detect_lane(")
    source = replace_once(source, "    double v[max_peaks][4];",
                          "    block_trace.proposal_ns = block_cpu_now() - begin;\n"
                          "    block_trace.count = done < 4 ? done : 4;\n"
                          "    for (int i = 0; i < block_trace.count; ++i) {\n"
                          "        block_trace.epoch[i] = request[i].epoch;\n"
                          "        block_trace.signed_hz[i] = request[i].hz;\n"
                          "    }\n"
                          "    double v[max_peaks][4];")
    return "#define _POSIX_C_SOURCE 200809L\n" + source


def two_fir_ranges(source):
    return replace_once(tile_source(source), "    for (int j = 22; j < 28098; j += 4) {",
                        f"    const int ranges[2][2] = {{{{{EARLY[0]}, {EARLY[1]}}}, {{{LATE[0]}, {LATE[1]}}}}};\n"
                        "    for (int pair = 0; pair < 2; ++pair)\n"
                        "    for (int j = ranges[pair][0]; j < ranges[pair][1]; j += 4) {")


def build(root):
    existing = json.loads(verified(ORIGINAL / "build-receipt.json", BUILD_PIN))
    release = json.loads(verified(RELEASE_BUILD, RELEASE_PIN))
    tile_recipe = json.loads(verified(ARCHIVE / "d97b-fir-tile-v1.json", TILE_BUILD_PIN))
    controls, commands = {}, []

    def run(args):
        commands.append(list(map(str, args)))
        subprocess.run(args, cwd=release["cwd"], check=True)

    relink = root / "released-relinked.so"
    run([*existing["relink"][:-1], relink])
    verified(relink, PREFIX_PIN)
    source = verified(SHORT_OBJECTS / "timing_first_receiver.c", TIMING_PIN).decode()
    tile = verified(SHORT_OBJECTS / "tile.c", TILE_PIN).decode()
    include_path = HERE / "frame_block_modes.inc"
    modified = timing_source(source, include_path.read_text())
    fir = root / "two_ranges.c"
    fir.write_text(two_fir_ranges(tile))
    fir_obj = fir.with_suffix(".o")
    run([*tile_recipe["build"]["commands"][2][:-4], "-c", fir, "-o", fir_obj])
    for label, text in (("plain", source), ("blocks", modified)):
        new_source = root / (label+".c")
        new_source.write_text(text)
        obj, library = new_source.with_suffix(".o"), new_source.with_suffix(".so")
        run([*existing["compile"][:-4], "-c", new_source, "-o", obj])
        parts = [obj if Path(part).name == "timing_first_receiver.o" else part for part in existing["relink"][:-2]]
        if label == "blocks":
            parts.append(fir_obj)
        run([*parts, "-o", library])
        controls[label] = library
    return controls, dict(commands=commands, source_sha256=TIMING_PIN, fir_source_sha256=TILE_PIN,
                          include_sha256=sha256(include_path.read_bytes()).hexdigest(),
                          libraries_sha256={label: sha256(path.read_bytes()).hexdigest() for label, path in controls.items()})


def close_to(epoch, hz, factor, max_samples, max_hz):
    return (abs(remainder(epoch - factor[1] - factor[2], 13333)) <= max_samples
            and abs(hz - factor[3]) <= max_hz)


def agree(original, proposed):
    if not original or not proposed:
        return original == proposed
    a, = proposed
    b, = original
    return a[0] == b[0] and close_to(a[1]+a[2], a[3], b, 2, 250)


def clocked(operation):
    cpu, wall = process_time_ns(), perf_counter_ns()
    outcome = operation()
    return outcome, (process_time_ns()-cpu, perf_counter_ns()-wall)


def controls(asset, libraries, resources):
    paths = {"full": PAYLOAD / "receiver.so", "released": ORIGINAL / "short-primary.so", **libraries}
    radios = {name: NativePath(path, asset, "full" if name == "full" else "short_primary")
              for name, path in paths.items()}
    for radio in radios.values():
        resources.callback(radio.close)
    read = radios["blocks"].native.lib.frame_block_read
    read.argtypes, read.restype = (ct.POINTER(Trace),), None
    return radios, read, ShortTrace(radios["released"])


def record_case(site, visits, libraries):
    probes, rows = [], []
    known, _ = archived("north") if site == "north" else (None, None)
    expected = [p for p in known["source"]["probes"] if p["visit_index"] < len(visits)] if known else None
    with ExitStack() as resources:
        engines = {edge: controls(np.frombuffer(verified(RELEASE/"assets"/(edge+".f32"), PILOT_SHA[edge]), dtype="<f4"),
                                 libraries, resources) for edge in sorted({r["edge"] for r, _ in visits})}
        for repeat in range(REPEATS):
            schedules = {}
            for index, (metadata, iq) in enumerate(visits):
                visit = window(dict(metadata, visit=index), iq)
                edge, frequency = metadata["edge"], center(visit)
                schedule = schedules.setdefault(metadata.get("case", site), StereoSchedule(full_coverage=True))
                _, kind = schedule.visit(edge, visit.target, visit.acquisition)
                radios, observe, reference_path = engines[edge]
                for lane in (0, 1):
                    nomination = Trace()

                    def direct():
                        return radios["released"].run(iq, lane, frequency)[0]

                    def proposed():
                        initial, native = radios["blocks"].run(iq, lane, frequency)
                        observed = initial if initial else direct()
                        return initial, observed, native

                    operations = {"released": direct, "policy": proposed,
                                  "plain": lambda: radios["plain"].run(iq, lane, frequency)[0]}
                    if kind == "full":
                        operations["anchor"] = lambda: radios["full"].run(iq, lane, frequency)[0]
                    order = tuple(operations)
                    shift = (repeat+index+lane) % len(order)
                    results = {name: clocked(operations[name]) for name in order[shift:]+order[:shift]}
                    observe(ct.byref(nomination))
                    stock, direct_clock = results["released"]
                    (candidate, policy, proposal_total), policy_clock = results["policy"]
                    plain, plain_clock = results["plain"]
                    oracle, oracle_clocks = traced(reference_path, iq, lane, frequency)
                    if factor_bytes(oracle) != factor_bytes(stock):
                        raise ValueError("The answer-key replay changed the actual released factor")
                    seeds = list(zip(nomination.epoch[:nomination.count], nomination.signed_hz[:nomination.count], strict=True))
                    anchor, anchor_clock = results.get("anchor", ((), (0, 0)))
                    if repeat == 0 and expected is not None:
                        from .mixed_aperture_trial import encoded, ordered

                        signed = ordered(anchor) if kind == "full" else stock
                        if factor_bytes(signed) != factor_bytes(encoded(expected[index*2+lane])):
                            raise ValueError("Released North stereo lane changed from its signed archive")
                        probes.append(signed)
                    rows.append(dict(index=index, repeat=repeat, lane=lane, edge=edge, iq_sha256=metadata["sha256"],
                                     kind=kind, center=frequency, stock=stock, candidate=candidate, policy=policy,
                                     seeds=seeds, anchor=anchor, anchor_clock=anchor_clock,
                                     direct_clock=direct_clock, policy_clock=policy_clock, proposal_and_verify=proposal_total,
                                     proposal_ns=nomination.proposal_ns, plain_clock=plain_clock,
                                     plain_exact=factor_bytes(plain) == factor_bytes(stock),
                                     oracle_verification_ns=sum(oracle_clocks[1:]) if stock else 0))
    return rows


def summarize(rows, mixed):
    totals, counts = [], Counter()
    for repeat in range(REPEATS):
        clock = Counter()
        for row in rows:
            if row["repeat"] != repeat:
                continue
            if mixed and row["kind"] == "full":
                for arm in ("direct", "live", "oracle", "tolerance_repair", "byte_repair", "free_winner_after_proposal"):
                    clock[arm] += row["anchor_clock"][0]
                for arm in ("direct_wall", "live_wall"):
                    clock[arm] += row["anchor_clock"][1]
                clock["anchor"] += row["anchor_clock"][0]
                if repeat == 0:
                    counts.update(anchors=1, anchor_secondaries=sum(f[0] == 1 for f in row["anchor"]))
                continue
            a, b, c = row["stock"], row["candidate"], row["policy"]
            direct, live = row["direct_clock"][0], row["policy_clock"][0]
            proposal_and_verify = row["proposal_and_verify"][0]
            oracle = row["oracle_verification_ns"]
            clock.update(direct=direct, live=live, direct_wall=row["direct_clock"][1], live_wall=row["policy_clock"][1],
                         oracle=oracle, plain=row["plain_clock"][0], nomination=row["proposal_ns"],
                         proposal_and_verify=proposal_and_verify, live_retry=direct if not b else 0,
                         free_winner_after_proposal=row["proposal_ns"]+oracle,
                         tolerance_repair=proposal_and_verify+(0 if agree(a, b) else direct),
                         byte_repair=proposal_and_verify+(0 if factor_bytes(a) == factor_bytes(b) else direct))
            if repeat == 0:
                counts.update(short=1, incumbent_positive=bool(a), candidate_positive=bool(b), policy_positive=bool(c),
                              candidate_match=bool(a and agree(a, b)), policy_match=bool(a and agree(a, c)),
                              candidate_lost=bool(a and not b), candidate_changed=bool(a and b and not agree(a, b)),
                              policy_changed=bool(a and c and not agree(a, c)), policy_extra=bool(c and not a),
                              empty_retry=not b, plain_exact=row["plain_exact"],
                              byte_retries=factor_bytes(a) != factor_bytes(b),
                              strict_seed=bool(a and any(close_to(ep, hz, a[0], 2, 250) for ep, hz in row["seeds"])),
                              wide_seed=bool(a and any(close_to(ep, hz, a[0], 6, 2250) for ep, hz in row["seeds"])))
        totals.append(dict(clock))
    return dict(counts=counts, repeats_ns=totals, median_ms={key: median(row.get(key, 0) for row in totals)*1e-6
                                                            for key in totals[0]})


def run(weak, output):
    host = check_machine()
    verified(PAYLOAD / "receiver.so", INSTALLED_SHA)
    verified(weak, WEAK_PIN)
    output.mkdir()
    libraries, recipe = build(output)
    rows = {}
    for site, load in (("weak", lambda: list(read_archive(weak, 18))), ("north", north_rows)):
        data, load_clock = clocked(load)
        evaluated = record_case(site, data, libraries)
        rows[site] = dict(load_clock_ns=load_clock, all_rows=evaluated,
                          forced_short=summarize(evaluated, False), mixed=summarize(evaluated, True))
    with (output / "receipt.json").open("x") as stream:
        json.dump(dict(host=host, recipe=recipe, repeats=REPEATS, cases=rows,
                       source_sha256=sha256(Path(__file__).read_bytes()).hexdigest()), stream, indent=2,
                  sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("weak", "output"):
        cli.add_argument(name, type=Path)
    run(**vars(cli.parse_args()))
