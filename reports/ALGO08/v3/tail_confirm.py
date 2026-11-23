"""Audit a selected signed pilot on independent trailing samples of its visit."""

import argparse
from collections import Counter
from contextlib import ExitStack
import ctypes as ct
from hashlib import sha256
import json
from math import floor, isfinite
import os
from pathlib import Path
from statistics import mean, median
import subprocess
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.qualification.cache_residency import cache_snapshot, load_query
from tools.pipeline_eval.variants.experimental.receiver_benchmark import read_archive

from .anchor_exposure import PINS, bind, packet
from .centered_primary import ORIGINAL, PREFIX_PIN, RELEASE_BUILD, RELEASE_PIN, WEAK_PIN, match, plants
from .mixed_aperture_receiver import INSTALLED_SHA, PILOT_SHA, NativePath, StereoSchedule, verified
from .mixed_aperture_trial import center, encoded, ordered, window
from .public_short_prefetch import MANIFEST_SHA, RECORDING
from .scoped_window_trial import signed_member
from .scout_readout_trial import SOURCE_SHA, TWO_CARRIER, check_machine, factor_bytes
from .short_prefetch_residency import resident
from .sparse_cold_input import CACHE_LIBRARY, CACHE_SHA, PAYLOAD, RELEASE
from .warm_six_prefetch import ResidentTmpfsReads


SOURCE = "3f62918238ad9107474d2f1509e953c61776eb70123ecd880c514f6e6483a707"
HOLDOUT = Path(__file__).with_suffix(".inc")
WEAK_ARCHIVE = Path("/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_11_20_single_scan_glrt/satellite-reference.zip")
REPEATS = 4
GATE = 0.025


def digest(blob):
    return sha256(blob).hexdigest()


def bounds(frame, epoch, offset):
    start = (40000*frame + 1)//3 + epoch
    return floor(start+88+offset)-7, floor(start+88+64*44-1+offset)+8


def clock():
    return process_time_ns(), perf_counter_ns()


def since(start):
    return [after-before for after, before in zip(clock(), start, strict=True)]


def build(work, installed):
    verified(installed, INSTALLED_SHA)
    verified(TWO_CARRIER, SOURCE_SHA)
    original = verified(RELEASE_BUILD.with_name("portable_verifier.c"), SOURCE)
    recipe = json.loads(verified(RELEASE_BUILD, RELEASE_PIN))
    if subprocess.check_output(["cc", "--version"], text=True).splitlines()[0] != recipe["compiler"]:
        raise ValueError("The pinned compiler changed")
    flags = recipe["commands"][-2][:-4]
    overlays = {}
    for name, pin in recipe["overlay_sources"].items():
        if name.endswith(".inc"):
            include = Path(flags[-1]) / name
            overlays[str(include)] = digest(verified(include, pin))
    work.mkdir()
    source, binary = work / "tail.c", work / "tail.so"
    extension = HOLDOUT.read_bytes()
    source.write_bytes(original+b"\n"+extension)
    command = [*flags, "-shared", str(source), str(installed), "-Wl,-Bsymbolic-functions", "-Wl,-z,defs", "-lm", "-o", str(binary)]
    subprocess.run(command, cwd=recipe["cwd"], check=True)
    return binary, dict(command=command, binary_sha256=digest(binary.read_bytes()), source_sha256=SOURCE,
                        layout_sha256=SOURCE_SHA, extension_sha256=digest(extension), overlays=overlays,
                        build_recipe_sha256=RELEASE_PIN, installed_sha256=INSTALLED_SHA)


class Tail:
    def __init__(self, binary):
        call = ct.CDLL(binary).tail_confirm
        call.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_uint, ct.c_uint, ct.c_double, ct.c_double,
                         ct.POINTER(ct.c_double)]
        call.restype = ct.c_int
        self.call = call

    def score(self, context, iq, lane, hypothesis):
        if (iq.shape != (200_000, 2, 2) or iq.dtype != np.dtype("<i2") or not iq.flags.c_contiguous
                or lane not in (0, 1) or hypothesis[0] != 0):
            raise ValueError("The holdout requires one released stereo primary hypothesis")
        result = (ct.c_double*2)()
        verify = ct.cast(context.native.ctx, ct.POINTER(ct.c_void_p))[1]
        epoch, offset, hz = hypothesis[1:4]
        if self.call(verify, iq.ctypes.data, lane, epoch, offset, hz, result):
            raise ValueError("Unsupported selected hypothesis")
        if any(not isfinite(x) or not 0 <= x <= 1.00000000000001 for x in result):
            raise ValueError("The zero-residual score is outside its normalization")
        return tuple(result)


def north_panel(query):
    from leo.storage.fast_scan import FastSegmentSource
    from leo.storage.scanner import ScannerIqStore

    chunk, before = signed_member(query)
    checked = ResidentTmpfsReads(RECORDING, query)
    scope = dict(path=str(RECORDING), manifest_digest="sha256:"+MANIFEST_SHA)
    schedule = StereoSchedule(full_coverage=True)
    saved, stock = (packet(*PINS["north"][kind]) for kind in ("12ms", "stock"))
    bind(stock, saved)
    rows = []
    with patch.dict(ScannerIqStore._read_regular.__globals__, {"os": checked}):
        for i, item in enumerate(FastSegmentSource(scope, stop_sequence=64).windows()):
            a, t = item.acquisition, item.target
            w = window(dict(edge=t["edge"], target=t, acquisition=a, visit=i), item.samples)
            visit = w.acquisition["global_visit"]
            saved_pair, stock_pair = (doc["source"]["probes"][2*i:2*i+2] for doc in (saved, stock))
            if any((row["visit_index"], row["receiver_id"], row["valid_start_counter"], row["edge"],
                    row["channel"], row["actual_rf_hz"])
                   != (visit, lane, a["sample_start"], t["edge"], t["channel"],
                       a["actual_if_center_hz"]+t["lnb_lo_hz"])
                   for lane, row in enumerate(saved_pair)):
                raise ValueError("The resident North rows differ from the signed paired probes")
            _, mode = schedule.visit(t["edge"], w.target, w.acquisition)
            rows.append((dict(w=w, mode=mode, key=f"North:{visit}", sha256=item.iq_sha256,
                              sealed=list(map(encoded, saved_pair)), named=list(map(encoded, stock_pair))), item.samples))
    _, after = signed_member(query)
    if not all(resident(state) for snapshot in (before, after) for state in snapshot.values()) or len(rows) != 64:
        raise ValueError("Unexpected public signed intake")
    return rows, dict(manifest_sha256=MANIFEST_SHA, signed_member=chunk, page_state=[before, after],
                      descriptor_reads=checked.calls, descriptor_bytes=checked.logical_bytes,
                      named_packet_sha256=PINS["north"]["stock"][1], short_packet_sha256=PINS["north"]["12ms"][1])


def weak_panel(query):
    path = WEAK_ARCHIVE

    def pages():
        return cache_snapshot([(path.parent, path.name, path.stat().st_size)], os.sysconf("SC_PAGE_SIZE"), query)

    before = pages()
    if not resident(before):
        return [], dict(reason="Saved weak fixture did not pass passive residency", page_state=before)
    verified(path, WEAK_PIN)
    rows = [(dict(w=window(row, iq), mode="short_primary", key=row["key"], sha256=row["sha256"]), iq)
            for row, iq in read_archive(path, 18)]
    after = pages()
    if not resident(after) or len(rows) != 18:
        raise ValueError("Unexpected saved weak fixture intake")
    return rows, dict(sha256=WEAK_PIN, page_state=[before, after], recording_family="weak DS26 archive")


def controls():
    for row, iq in plants():
        w = window(row, iq)
        yield dict(w=w, mode="short_primary", key=row["key"], sha256=row["sha256"]), iq
        if row["key"].endswith(":whole"):
            tail_only = iq.copy()
            tail_only[:120_000] = 0
            zero = np.zeros_like(iq)
            for label, samples in (("tail-only", tail_only), ("zero", zero)):
                yield dict(w=window(row, samples), mode="short_primary", key=f"{row['edge']}:{label}",
                           sha256=digest(samples.tobytes())), samples


def paid(engines, tail, edge, mode, iq, lane, tune, enabled):
    start = clock()
    raw, _ = engines[edge, mode].run(iq, lane, tune)
    current = ordered(raw) if mode == "full" else raw
    scores = None
    trailing = [0, 0]
    retained = current
    if enabled and mode == "short_primary" and current:
        hold_start = clock()
        scores = tail.score(engines[edge, "holdout"], iq, lane, current[0])
        retained = current if scores[0]-scores[1] >= GATE else ()
        trailing = since(hold_start)
    return current, retained, scores, since(start), trailing


def panel(rows, engines, tail, *, repeat_count, poison=False):
    details, totals = {}, []
    for repeat in range(repeat_count):
        times = {arm: [0, 0] for arm in ("short", "short_tail", "tail_only", "diagnostic_20ms")}
        for index, (row, iq) in enumerate(rows):
            w, mode, key = row["w"], row["mode"], row["key"]
            edge, tune = w.target["edge"], center(w)
            for lane in (0, 1):
                for enabled in (False, True) if (index+lane+repeat) % 2 else (True, False):
                    value = paid(engines, tail, edge, mode, iq, lane, tune, enabled)
                    if enabled:
                        tested, retained, scores, ticks, tail_ticks = value
                        add(times["short_tail"], ticks)
                        add(times["tail_only"], tail_ticks)
                    else:
                        current, _, _, ticks, _ = value
                        add(times["short"], ticks)
                if factor_bytes(current) != factor_bytes(tested):
                    raise ValueError("The trailing scorer altered the original acquisition")
                if "sealed" in row and factor_bytes(current) != factor_bytes(row["sealed"][lane]):
                    raise ValueError(f"The actual scheduled original factor disagrees at {key}/{lane}")
                identity = (key, lane)
                if repeat:
                    prior = details[identity]
                    if (prior["retained"], prior["scores"]) != (retained, scores):
                        raise ValueError("Repeated holdout decisions disagree")
                    continue
                raw20, ticks = engines[edge, "diagnostic"].run(iq, lane, tune)
                add(times["diagnostic_20ms"], ticks)
                if poison and mode == "short_primary" and current:
                    low, high = bounds(9, current[0][1], current[0][2])[0]-40, bounds(13, current[0][1], current[0][2])[1]+40
                    altered = iq.copy()
                    altered[:low] = -32_768
                    altered[high+1:] = 32_767
                    alt = tail.score(engines[edge, "holdout"], altered, lane, current[0])
                    if alt != scores:
                        raise ValueError("Changing samples outside the disjoint holdout changed its score")
                    altered[:120_000] = iq[:120_000]
                    altered[120_000:] = 0
                    original, _ = engines[edge, mode].run(altered, lane, tune)
                    if factor_bytes(original) != factor_bytes(current):
                        raise ValueError("Changing the entire tail changed the original short hypothesis")
                    integer = (*current[0][:2], 0., *current[0][3:])
                    if any(tail.score(engines[edge, "holdout"], altered, lane, hypothesis) != (0., 0.)
                           for hypothesis in (current[0], integer)):
                        raise ValueError("A zero tail produced spurious score or reused stale I/Q")
                details[identity] = dict(key=key, lane=lane, edge=edge, mode=mode, raw20=raw20, current=current,
                                         retained=retained, scores=scores, iq_sha256=row["sha256"],
                                         actual_rf_hz=w.acquisition["actual_if_center_hz"]+w.target["lnb_lo_hz"],
                                         sample_counter=w.acquisition["sample_start"], named=row.get("named", [None, None])[lane])
        totals.append(times)
    return dict(lanes=list(details.values()), timing_ns=totals)


def add(total, difference):
    for i, tick in enumerate(difference):
        total[i] += tick


def tables(rows, receiver=None):
    records = [row for row in rows if row["mode"] == "short_primary" and (receiver is None or row["lane"] == receiver)]
    output = dict(short_opportunities=len(records), short_positive=sum(bool(row["current"]) for row in records),
                  retained=sum(bool(row["retained"]) for row in records))
    alternatives = {"raw20_selected": lambda row: ordered(row["raw20"]), "raw20_any": lambda row: row["raw20"]}
    if records and records[0]["named"] is not None:
        alternatives["named_selected"] = lambda row: ordered(row["named"])
    for name, reference in alternatives.items():
        counts = Counter()
        for row in records:
            other, current = reference(row), row["current"]
            shared = current and any(match(factor, current[0])["hit"] for factor in other)
            if current:
                key = "shared" if shared else "short_only"
                counts[key] += 1
                counts[key+"_retained"] += bool(row["retained"])
                counts["unmatched_both_positive"] += bool(other and not shared)
            else:
                counts["full_only" if other else "both_empty"] += 1
        output[name] = dict(counts)
    return output


def summarize(panel_result):
    rows, timing = panel_result["lanes"], panel_result["timing_ns"]
    all_lanes = tables(rows)
    n = all_lanes["short_positive"]
    marginals = [time["short_tail"][0]-time["short"][0] for time in timing]
    holdout = mean([time["tail_only"][0] for time in timing])/n if n else None
    return dict(overall=all_lanes, radios=[tables(rows, receiver=i) for i in (0, 1)],
                paid_anchor_lanes=sum(row["mode"] == "full" for row in rows),
                medians_ns={arm: [median(time[arm][i] for time in timing) for i in (0, 1)]
                            for arm in ("short", "short_tail", "tail_only")},
                diagnostic_20ms_ns=timing[0]["diagnostic_20ms"],
                paired_marginal_cpu_ns=median(marginals), positive_mean_holdout_cpu_ns=holdout,
                projected_dense_holdout_cpu_s=6380*holdout/1e9 if holdout is not None else None)


def decision(north, weak):
    north = north.get("overall", {}).get("named_selected", {})
    weak = weak.get("overall", {}).get("raw20_selected", {})
    return dict(north_excess_rejection=bool(north.get("short_only") and 2*north["short_only_retained"] <= north["short_only"]),
                north_shared_retention=bool(north.get("shared") and 100*north["shared_retained"] >= 95*north["shared"]),
                weak_shared_retention=bool(weak.get("shared") and 100*weak["shared_retained"] >= 95*weak["shared"]))


def input_bytes():
    return int(dict(row.split(": ", 1) for row in Path("/proc/self/io").read_text().splitlines())["read_bytes"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=lambda path: Path(path).resolve())
    args = parser.parse_args()
    machine = check_machine()
    installed, short = PAYLOAD / "receiver.so", ORIGINAL / "short-primary.so"
    verified(short, PREFIX_PIN)
    query = load_query(CACHE_LIBRARY)
    verified(CACHE_LIBRARY, CACHE_SHA)
    initial_io = input_bytes()
    start = clock()
    binary, build_receipt = build(args.work, installed)
    build_ticks = since(start)
    start = clock()
    northern, north_receipt = north_panel(query)
    weak, weak_receipt = weak_panel(query)
    intake_ticks = since(start)
    output = dict(machine=machine, build=build_receipt, north_input=north_receipt, weak_input=weak_receipt,
                  stage_outside_ns=dict(compile=build_ticks, intake=intake_ticks), threshold=GATE,
                  short_sha256=PREFIX_PIN, pilot_sha256=PILOT_SHA, source_sha256=digest(Path(__file__).read_bytes()))
    tail = Tail(binary)
    engines = {}
    with ExitStack() as stack:
        start = clock()
        for edge, pin in PILOT_SHA.items():
            asset = np.frombuffer(verified(RELEASE / "assets" / (edge+".f32"), pin), dtype="<f4")
            for label in ("short_primary", "full", "holdout", "diagnostic"):
                engine = NativePath(short if label == "short_primary" else installed, asset,
                                    "short_primary" if label == "short_primary" else "full")
                engines[edge, label] = engine
                stack.callback(engine.close)
        output["stage_outside_ns"]["contexts"] = since(start)
        for label, rows in (("controls", list(controls())), ("north", northern), ("weak", weak)):
            if rows:
                result = panel(rows, engines, tail, repeat_count=1 if label == "controls" else REPEATS,
                               poison=label == "controls")
                output[label] = dict(result, summary=summarize(result))
    output["gate_result"] = decision(*(output.get(label, {}).get("summary", {}) for label in ("north", "weak")))
    output["process_storage_input_bytes"] = input_bytes()-initial_io
    print(json.dumps(output, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
