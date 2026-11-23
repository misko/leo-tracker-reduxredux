"""Measure and check two fixed signed-primary aperture builds on saved lanes."""

import argparse
from collections import Counter
from contextlib import ExitStack
import gzip
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter_ns, process_time_ns

import numpy as np

from tools.pipeline_eval.variants.experimental.receiver_benchmark import read_archive
from tools.pipeline_eval.variants.experimental.receiver_brackets import read_physical

from . import full_short_score as scoring
from .eight_ms_primary import HERE, SHAPES, write
from .mixed_aperture_receiver import INSTALLED_SHA, PILOT_SHA, MixedApertureDetector, NativePath, verified
from .mixed_aperture_trial import center, encoded, window
from .scout_readout_trial import check_machine, factor_bytes
from .sparse_cold_input import BINDING, BINDING_SHA, WINDOWS


ARMS = tuple(SHAPES)
REPEATS = 3
PRODUCTION_SHORT = "06570a53032c770d99cc9678b8660e1bb502b71f30fc47c8b1a4a8e31bc19ba9"
WEAK_ARCHIVE = "0f025d0f5c80f5425a3c6fa90bc77a0e5628eb8cf7bc7ac7dab7fdd6c1d2e9d9"
WEAK_LEDGER = "fe5ad540777c619b7cb55a143946c359712cd15b2e182d79a967ef7826118aa4"


def clock():
    return process_time_ns(), perf_counter_ns()


def elapsed(start):
    return tuple(now-then for now, then in zip(clock(), start, strict=True))


def arm_order(visit, repeat):
    return ARMS if (visit+repeat) % 2 == 0 else ARMS[::-1]


def documents(probes, session):
    return {arm: {"source": dict(session_id=session, probes=rows)} for arm, rows in probes.items()}


def check_tail(short, unchanged, samples, lane, signed_center):
    got, _ = short.run(samples, lane, signed_center)
    if factor_bytes(got) != factor_bytes(unchanged):
        raise ValueError("The 8 ms primary depends on the original post-aperture input")


def dense_timings(windows, paths, pins, installed, assets):
    runs, packet = [], None
    edges = sorted({ci.target["edge"] for ci in windows})
    for repeat in range(REPEATS):
        detectors, handles, setup = {}, {}, {}
        emitted = {arm: [] for arm in ARMS}
        callback = {arm: [0, 0] for arm in ARMS}
        with ExitStack() as closers:
            for arm in arm_order(0, repeat):
                start = clock()
                detectors[arm] = MixedApertureDetector(paths[arm], pins[arm], full_coverage=True)
                handles[arm] = {edge: closers.enter_context(detectors[arm].detector(
                    "cancellation", edge, binary=installed, pilot=assets / (edge+".f32"))) for edge in edges}
                setup[arm] = elapsed(start)
            for i, ci in enumerate(windows):
                edge = ci.target["edge"]
                for arm in arm_order(i, repeat):
                    start = clock()
                    emitted[arm].extend(handles[arm][edge](ci))
                    for k, value in enumerate(elapsed(start)):
                        callback[arm][k] += value
        if packet is not None and packet != emitted:
            raise ValueError("Alternating call order changed the signed factors")
        packet = emitted
        runs.append({arm: dict(native=detectors[arm].receipt(), setup_cpu_wall_ns=setup[arm],
                               callback_cpu_wall_ns=callback[arm]) for arm in ARMS})
    return packet, runs


def checked_shortouts(windows, probes, native, assets):
    edges = sorted({ci.target["edge"] for ci in windows})
    order, hits = Counter(), 0
    with ExitStack() as closer:
        engines = {edge: NativePath(native, np.frombuffer(verified(assets / (edge+".f32"), PILOT_SHA[edge]),
                                                       dtype="<f4"), "short_primary") for edge in edges}
        for engine in engines.values():
            closer.callback(engine.close)
        for ci, left, right in zip(windows, probes[::2], probes[1::2], strict=True):
            stream = tuple(left[name] for name in ("channel", "actual_rf_hz", "edge"))
            rank = order[stream]
            order[stream] += 1
            if rank % 8 == 0:
                continue
            changed = ci.samples.copy()
            changed[SHAPES["8ms"][0]:] = np.iinfo(np.int16).max
            for lane, probe in enumerate((left, right)):
                check_tail(engines[left["edge"]], encoded(probe), changed, lane, center(ci))
                hits += 1
    return hits


def weak_timings(rows, paths, historical, assets):
    from tools.pipeline_eval.qualification.blind_compact_run import factor_candidate

    repeats, document = [], None
    input_bins = [(row, window(row, samples)) for row, samples in rows]
    with ExitStack() as closer:
        engines = {arm: {} for arm in (*ARMS, "historical")}
        for edge in sorted({row["edge"] for row, _ in rows}):
            asset = np.frombuffer(verified(assets / (edge+".f32"), PILOT_SHA[edge]), dtype="<f4")
            for arm, path in (*paths.items(), ("historical", historical)):
                native = NativePath(path, asset, "short_primary")
                closer.callback(native.close)
                engines[arm][edge] = native
        for repeat in range(REPEATS):
            collection, spans = {a: [] for a in ARMS}, {a: [0, 0] for a in ARMS}
            for visit, (row, ci) in enumerate(input_bins):
                for lane in (0, 1):
                    for arm in arm_order(2*visit+lane, repeat):
                        factors, spent = engines[arm][row["edge"]].run(ci.samples, lane, center(ci))
                        collection[arm].append(factors)
                        for k, value in enumerate(spent):
                            spans[arm][k] += value
            if document is not None and document != collection:
                raise ValueError("Repeated weak primary outputs changed")
            document = collection
            repeats.append(spans)
        detail = []
        for i, (row, ci) in enumerate(input_bins):
            edge, tune = row["edge"], center(ci)
            altered = ci.samples.copy()
            altered[SHAPES["8ms"][0]:] = np.iinfo(np.int16).max
            for lane in (0, 1):
                reference, _ = engines["historical"][edge].run(ci.samples, lane, tune)
                before, after = (document[arm][2*i+lane] for arm in ARMS)
                if factor_bytes(reference) != factor_bytes(before):
                    raise ValueError("The rebuilt reference changed a weak 12 ms output")
                check_tail(engines["8ms"][edge], after, altered, lane, tune)
                a, b = [factor_candidate(f[0], f[1], status="complete", offset=f[2], cfo=f[3], exact=f[4],
                                         control=f[5], margin=f[4]-f[5]) if f else None
                        for f in (before[0] if before else None, after[0] if after else None)]
                delta = scoring.changes(a, b) if a is not None and b is not None else None
                matched = delta is not None and abs(delta["wrapped_timing_samples"]) <= 2 and abs(delta["signed_cfo_change_hz"]) <= 250
                detail.append(dict(case=row["case"], edge=edge, id=row["key"], sample_sha256=row["sha256"], rx=lane,
                                   factors={"12ms": a, "8ms": b}, delta=delta, matched=matched,
                                   matched_same_rank=matched and delta["rank_equal"],
                                   stock_rank=0 if a is not None else None, candidate_rank=0 if b is not None else None))
        workspaces = {arm: {edge: receiver.native.bytes for edge, receiver in engines[arm].items()} for arm in ARMS}
    return dict(repeats_cpu_wall_ns=repeats, native_workspace_bytes=workspaces, records=detail,
                tail_checks=len(detail), historical_12ms_checks=len(detail), summary=scoring.counts(detail),
                by_antenna={lane: scoring.counts([row for row in detail if row["rx"] == lane]) for lane in (0, 1)})


def measure(build, installed, assets, historical, weak, output):
    host = check_machine()
    recorded = json.loads(build.read_bytes())
    verified(installed, INSTALLED_SHA)
    verified(historical, PRODUCTION_SHORT)
    verified(weak, WEAK_ARCHIVE)
    verified(BINDING, BINDING_SHA)
    paths = {arm: Path(row["binary"]) for arm, row in recorded["primary"].items()}
    pins = {arm: row["binary_sha256"] for arm, row in recorded["primary"].items()}
    if pins["12ms"] != PRODUCTION_SHORT or pins["8ms"] == PRODUCTION_SHORT:
        raise ValueError("The matched rebuild did not reproduce the exact 12 ms DSO or produce a distinct 8 ms DSO")
    for arm, path in paths.items():
        verified(path, pins[arm])
    baseline = json.loads(gzip.decompress(verified(HERE / "measurements/full-short-cold.json.gz",
                                                   scoring.PRIOR_SHORT_RECEIPT_SHA)))
    stock, prior = (baseline["detection_documents"][arm] for arm in ("stock", "full-short"))
    start = clock()
    dense = list(read_physical(BINDING, Path("/srv/bulk"), WINDOWS))
    weak_rows = list(read_archive(weak, 18))
    loader = elapsed(start)
    expected = baseline["acquisition"]["repeats"][0][0]["decoded_iq_hashes"]
    weak_expected = json.loads(verified(HERE / "measurements/mixed-aperture-receiver.json", WEAK_LEDGER))["panels"]["weak"]["input_sha256"]
    if (len(dense) != WINDOWS or [row["sha256"] for row, _ in dense] != expected or len(weak_rows) != 18
            or [[row["key"], row["sha256"]] for row, _ in weak_rows] != weak_expected):
        raise ValueError("The authenticated dense prefix or weak challenge selection changed")
    windows = [window(row, samples) for row, samples in dense]
    measured, repetitions = dense_timings(windows, paths, pins, installed, assets)
    if measured["12ms"] != prior["source"]["probes"]:
        raise ValueError("The rebuilt 12 ms reference differs from the prior full-short evidence")
    tails = checked_shortouts(windows, measured["8ms"], paths["8ms"], assets)
    docs = documents(measured, stock["source"]["session_id"])
    raced = scoring.compare_lanes(docs["12ms"], docs["8ms"])
    if tails != 336 or any(reference != candidate for lane, reference, candidate in
                          zip(raced.values(), measured["12ms"], measured["8ms"], strict=True)
                          if lane["slot"] == "full"):
        raise ValueError("The genuine primary audit or full-aperture anchors changed")
    owners = {arm: scoring.owner_score(scoring.compare_lanes(stock, doc)) for arm, doc in docs.items()}
    weak_evidence = weak_timings(weak_rows, paths, historical, assets)
    write(output, dict(machine=host, input_sha256=dict(dense_binding=BINDING_SHA, weak_archive=WEAK_ARCHIVE,
          chronological_dense_iq_sha256=expected, previous_prefix=scoring.PRIOR_SHORT_RECEIPT_SHA),
          build_sha256=sha256(build.read_bytes()).hexdigest(), build=recorded, loading_cpu_wall_ns=loader,
          dense=dict(repeats=repetitions, tail_checks=tails, exact_historical_12ms=True, probes=measured,
                     owners_vs_installed=owners, by_antenna={n: scoring.counts([r for r in raced.values() if r["rx"] == n])
                     for n in (0, 1)}, by_slot={slot: scoring.counts([r for r in raced.values() if r["slot"] == slot])
                     for slot in ("full", "short_primary")}, selection=scoring.counts(raced.values()), lanes=raced),
          weak=weak_evidence, source_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("build", "installed", "assets", "historical", "weak", "output"):
        parser.add_argument(name, type=Path)
    measure(**vars(parser.parse_args()))
