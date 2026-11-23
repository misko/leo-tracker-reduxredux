"""Time the distributed primary and certify native dependencies on saved waveforms."""

import argparse
from collections import Counter
from contextlib import ExitStack
import ctypes as ct
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
from statistics import median
from time import perf_counter_ns, process_time_ns

import numpy as np

from tools.pipeline_eval.variants.experimental.receiver_benchmark import read_archive
from tools.pipeline_eval.variants.experimental.receiver_brackets import read_physical

from . import full_short_score as score
from .distributed_aperture import FRAMES, SAMPLES, possible_input_dependencies, ranges_for_fir
from .eight_ms_primary import HERE, write
from .eight_ms_primary_trial import PRODUCTION_SHORT, WEAK_ARCHIVE, WEAK_LEDGER
from .mixed_aperture_receiver import INSTALLED_SHA, PILOT_SHA, NativePath, verified
from .mixed_aperture_trial import center, window
from .scout_readout_trial import check_machine, factor_bytes
from .sparse_cold_input import BINDING, BINDING_SHA, CACHE_LIBRARY, CACHE_SHA, WINDOWS

FULL, SHORT, BROAD, SELECTED = "full-20ms", "12ms", "full-fir", "selected-fir"
ARMS = (FULL, SHORT, BROAD, SELECTED)
ORDERS = ((FULL, SHORT, BROAD, SELECTED), (SELECTED, BROAD, SHORT, FULL), (SHORT, FULL, SELECTED, BROAD))
REPEATS = len(ORDERS)


def clock():
    return process_time_ns(), perf_counter_ns()


def finish(start):
    return tuple(now - then for now, then in zip(clock(), start, strict=True))


def library(path, pin):
    verified(path, pin)
    return path


def resident_dense(visits):
    from leo.storage.short_window import ShortWindowReader
    from tools.pipeline_eval.qualification.cache_residency import cache_snapshot, load_query

    packet = json.loads(verified(BINDING, BINDING_SHA))
    entry = packet["case"]["recording"]["segments"][0]
    root = Path("/srv/bulk") / Path(entry["path"]).parent
    archive = ShortWindowReader(root)
    if archive.manifest_sha256 != "sha256:" + entry["sha256"]:
        raise ValueError("The original dense manifest changed")
    members = tuple(chunk for chunk in archive.manifest.chunks if chunk.first_sequence < visits)
    if sum(chunk.window_count for chunk in members) != visits or len(members) != visits // 64:
        raise ValueError("Dense residency scope differs from the pinned decoded prefix")
    query = load_query(library(CACHE_LIBRARY, CACHE_SHA))
    checks = [cache_snapshot([(root, chunk.payload_relative_path, chunk.compressed_bytes)],
                             os.sysconf("SC_PAGE_SIZE"), query) for chunk in members]
    if any(r["observed_members"] != 1 or r["cached_pages"] != r["observed_file_pages"] for r in checks):
        return [], dict(state="skipped_incomplete_residency", members=checks)
    start = clock()
    rows = list(read_physical(BINDING, Path("/srv/bulk"), visits))
    return rows, dict(state="read_verified_resident_members", members=checks,
                      scheduled_visits=visits, loading_cpu_wall_ns=finish(start))


def fv_bound(arm, assets):
    """Retain each pilot asset's original 81 FIR coefficients."""
    return np.frombuffer(verified(assets / (arm + ".f32"), PILOT_SHA[arm]), dtype="<f4")


def check_fir(paths, assets):
    wrapped = []
    for name in (BROAD, SELECTED):
        native = ct.CDLL(str(paths[name])).delay_decimate
        real = np.ctypeslib.ndpointer(dtype=np.float32, ndim=1, flags="C_CONTIGUOUS")
        native.argtypes = [real, real, ct.c_int, ct.c_int, real]
        native.restype = ct.c_int
        wrapped.append(native)
    rng = np.random.default_rng(20261123)
    active = np.zeros(SAMPLES // 4, dtype=bool)
    for a, b in ranges_for_fir():
        active[a:b] = True
    checked = 0
    for edge in sorted(PILOT_SHA):
        coeff = fv_bound(edge, assets)[4 * 13333:4 * 13333 + 81]
        for _ in range(3):
            signal = rng.integers(-32768, 32768, 2 * SAMPLES).astype(np.float32)
            value = [np.full((SAMPLES // 4, 2), np.nan, dtype=np.float32) for _ in wrapped]
            for native, target in zip(wrapped, value, strict=True):
                if native(signal, coeff, 81, 4, target.ravel()):
                    raise ValueError("The native FIR declined its original valid inputs")
            full, sparse = value
            if (full[active].tobytes() != sparse[active].tobytes()
                    or not np.isnan(sparse[10:-10][~active[10:-10]]).all()):
                raise ValueError("Selected FIR did not preserve scored samples or wrote across a skipped gap")
            checked += int(active.sum())
    return dict(checked_complex_outputs=checked, selected_vector_outputs=int(active.sum()),
                required_edge_outputs=20, full_complex_outputs=SAMPLES//4)


def select(factors):
    return max(factors, key=lambda f: (f[4] - f[5], -f[0]), default=None)


def factor_entry(factor):
    from tools.pipeline_eval.qualification.blind_compact_run import factor_candidate

    if factor is None:
        return None
    rank, epoch, offset, cfo, exact, control = factor
    return factor_candidate(rank, epoch, status="complete", offset=offset, cfo=cfo,
                            exact=exact, control=control, margin=exact-control)


def cohort(rows, paths, assets, *, dense):
    from tools.pipeline_eval.qualification.blind_compact_run import _probe

    timings, probes, native_factors = [], None, None
    rotated_rows = [(d, window(d, a)) for d, a in rows]
    for repeat in range(REPEATS):
        report, factors = {a: [] for a in ARMS}, {a: [] for a in ARMS}
        totals = {a: Counter() for a in ARMS}
        with ExitStack() as cleanup:
            engines, streams = {}, Counter()
            for edge in sorted({d["edge"] for d, _ in rows}):
                asset = fv_bound(edge, assets)
                for arm in ORDERS[repeat]:
                    start = clock()
                    engine = NativePath(paths[arm], asset, "full" if arm == FULL else "short_primary")
                    cpu, wall = finish(start)
                    cleanup.callback(engine.close)
                    engines[arm, edge] = engine
                    totals[arm].update(setup_cpu_ns=cpu, setup_elapsed_ns=wall)
                    totals[arm]["native_workspace_bytes_per_edge"] = engine.native.bytes
            for visit, (meta, ci) in enumerate(rotated_rows):
                edge, signed = meta["edge"], center(ci)
                stream = (edge, ci.target["channel"], ci.target["lnb_lo_hz"] + ci.acquisition["actual_if_center_hz"])
                anchor = dense and streams[stream] % 8 == 0
                streams[stream] += 1
                for lane in (0, 1):
                    call_order = ORDERS[repeat][::(-1 if (visit + lane) % 2 else 1)]
                    for arm in call_order:
                        start = clock()
                        run_arm = FULL if anchor else arm
                        data, cost = engines[run_arm, edge].run(ci.samples, lane, signed)
                        factor = select(data)
                        if not dense or arm == FULL:
                            factor = next((f for f in data if f[0] == 0), None)
                        chosen = factor_entry(factor)
                        report[arm].append(_probe(ci, lane, [] if chosen is None else [chosen]))
                        factors[arm].append(data)
                        span = finish(start)
                        key = "anchor" if anchor else "other"
                        totals[arm].update({key + "_native_cpu_ns": cost[0], key + "_native_elapsed_ns": cost[1],
                                            key + "_lanes": 1, "processing_cpu_ns": span[0],
                                            "processing_elapsed_ns": span[1]})
        if native_factors is not None and (native_factors != factors or probes != report):
            raise ValueError("Changing resident benchmark call order moved native factors")
        probes, native_factors = report, factors
        timings.append({arm: dict(counts) for arm, counts in totals.items()})

    if (any(factor_bytes(a) != factor_bytes(b) for a, b in zip(native_factors[BROAD], native_factors[SELECTED], strict=True))
            or probes[BROAD] != probes[SELECTED]):
        raise ValueError("Selected FIR changed a genuine distributed factor")
    discarded = np.ones(SAMPLES, bool)
    for a, b in possible_input_dependencies():
        discarded[max(0, a):min(SAMPLES, b)] = False
    with ExitStack() as cleanup:
        engines = {edge: NativePath(paths[SELECTED], fv_bound(edge, assets), "short_primary")
                   for edge in sorted({d["edge"] for d, _ in rows})}
        for engine in engines.values():
            cleanup.callback(engine.close)
        replaced = 0
        for meta, ci in rotated_rows:
            changed = ci.samples.copy()
            changed[discarded] = np.iinfo(np.int16).max
            for lane in (0, 1):
                engine = engines[meta["edge"]]
                old, now = (engine.run(data, lane, center(ci))[0] for data in (ci.samples, changed))
                if factor_bytes(old) != factor_bytes(now):
                    raise ValueError(f"A measured distributed lane depends on a discarded sample: {meta['key']}")
                replaced += 1

    return dict(probes=probes, factors=native_factors, timings=timings, replaced_sample_lanes=replaced,
                saturated_values_per_antenna=int(2 * discarded.sum()),
                median_native_other_cpu_ns={arm: median(row[arm]["other_native_cpu_ns"] for row in timings) for arm in ARMS})


def compare_weak(base, variant):
    entries = []
    for a, b in zip(base, variant, strict=True):
        a, b = map(score.selected, (a, b))
        delta = score.changes(a, b) if a is not None and b is not None else None
        matched = delta is not None and abs(delta["wrapped_timing_samples"]) <= 2 and abs(delta["signed_cfo_change_hz"]) <= 250
        entries.append(dict(stock_rank=None if a is None else a["candidate_rank"],
                            candidate_rank=None if b is None else b["candidate_rank"], delta=delta,
                            matched=matched, matched_same_rank=matched and delta["rank_equal"]))
    return score.counts(entries)


def run(build_path, installed, assets, short, weak, output, *, dense_visits):
    host = check_machine()
    built = json.loads(build_path.read_bytes())
    if tuple(built["frames"]) != FRAMES or tuple(map(tuple, built["selected_fir_ranges"])) != ranges_for_fir():
        raise ValueError("The baseline or distributed-aperture schedule changed")
    paths = {FULL: library(installed, INSTALLED_SHA), SHORT: library(short, PRODUCTION_SHORT)}
    pins = {FULL: INSTALLED_SHA, SHORT: PRODUCTION_SHORT}
    for arm in (BROAD, SELECTED):
        info = built["results"][arm]["primary"]
        pins[arm] = info["binary_sha256"]
        paths[arm] = library(Path(info["binary"]), pins[arm])
    library(weak, WEAK_ARCHIVE)
    weak_started = clock()
    weak_rows = list(read_archive(weak, 18))
    weak_clock = finish(weak_started)
    weak_expected = json.loads(verified(HERE / "measurements/mixed-aperture-receiver.json", WEAK_LEDGER))["panels"]["weak"]["input_sha256"]
    if [[r["key"], r["sha256"]] for r, _ in weak_rows] != weak_expected:
        raise ValueError("The previously sealed 18 stereo weak challenges changed")
    weak_result = cohort(weak_rows, paths, assets, dense=False)
    weak_result.update(loading_cpu_wall_ns=weak_clock, lane_input=weak_expected,
                       differences={f"{arm}-vs-{base}": compare_weak(weak_result["probes"][base], weak_result["probes"][arm])
                                    for base, arm in ((FULL, SHORT), (FULL, SELECTED), (SHORT, SELECTED))})
    dense_rows, residency = resident_dense(dense_visits)
    dense = {}
    if dense_rows:
        prior = json.loads(gzip.decompress(verified(HERE / "measurements/full-short-cold.json.gz", score.PRIOR_SHORT_RECEIPT_SHA)))
        hashes = prior["acquisition"]["repeats"][0][0]["decoded_iq_hashes"][:dense_visits]
        if [r["sha256"] for r, _ in dense_rows] != hashes:
            raise ValueError("Dense waveform hashes differ from the previously authenticated lanes")
        dense = cohort(dense_rows, paths, assets, dense=True)
        original = prior["detection_documents"]["stock"]
        old_probes = prior["detection_documents"]["full-short"]["source"]["probes"][:2 * dense_visits]
        stock_prefix = dict(original, source=dict(original["source"], probes=original["source"]["probes"][:2 * dense_visits]))
        if dense["probes"][SHORT] != old_probes:
            raise ValueError("The exact released 12 ms control did not reproduce its saved detector packet")
        session = original["source"]["session_id"]
        docs = {name: dict(source=dict(session_id=session, probes=dense["probes"][name])) for name in (SHORT, SELECTED)}
        overlays = score.compare_lanes(docs[SHORT], docs[SELECTED])
        if any(a != b for row, a, b in zip(overlays.values(), dense["probes"][SHORT], dense["probes"][SELECTED], strict=True)
               if row["slot"] == "full"):
            raise ValueError("An original full signed anchor changed")
        dense.update(selection_vs_12ms=score.counts(overlays.values()),
                     selection_by_slot={slot: score.counts([r for r in overlays.values() if r["slot"] == slot])
                                        for slot in ("full", "short_primary")},
                     owners={name: score.owner_score(score.compare_lanes(stock_prefix, doc)) for name, doc in docs.items()},
                     input_sha256=hashes)
    write(output, dict(machine=host, detector_pins=pins, build_sha256=sha256(build_path.read_bytes()).hexdigest(),
                       source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                       fir=check_fir(paths, assets), dense_precheck=residency, dense=dense, weak=weak_result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("build_path", "installed", "assets", "short", "weak", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--dense-visits", choices=(64, WINDOWS), type=int, default=WINDOWS)
    run(**vars(parser.parse_args()))
