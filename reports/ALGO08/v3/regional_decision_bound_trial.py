"""Price a guarded track-contribution certificate at the real regional stage."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from time import process_time_ns, perf_counter_ns
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
STAGED = Path("/dev/shm/leo-held-anchor-selected-dense-01")
SCORES, BLOCK, GEOGRAPHIC = (STAGED/f"{name}_library.so" for name in ("regional_track", "frontier_block", "geographic"))
CASES = ("dense", "medium", "south-far", "south-near")
SOURCE_PINS = {"dense": "f4750387b41c8247e6195a162a5653f11c2fd2281b23faa857cddbb1bc29255a",
               "medium": "621db1154873ac24ce68b2c0bdc128dc5a6bff2f67166cb78455ac06b2342eec"}
SOUTH_OFFERS = {"south-far": "a5127d5844ca98f58a157ec2b6b962f60ec2894c58b8122a0ee244b248a5eb62",
                "south-near": "0c89bd52594b706b2772fbcf6ea627065eeb3d94eb6266f35de09ebb6b7a5d2a"}
BATCH = 8


def assignment(case):
    from aperture_trial import archive_identity, read
    from dense_full_short_crossover import file_sha
    from leo.contracts.algo08_region import Algo08Region

    if case in SOURCE_PINS:
        number = "0008" if case == "dense" else "0057"
        root = Path(f"/dev/shm/leo-exact-solver-{number}-result01")
        if file_sha(root/"result.json") != SOURCE_PINS[case]:
            raise ValueError("Signed saved position source changed")
        result = read(root/"result.json")
        source = result["input"]
        archive, region = source["archive"], Path(source["region"])
        if case == "dense":
            path, pin, control = Path(source["packet"]), source["native"], result["proof"]
            offer_pin = source["offer_sha256"]
        else:
            path, = (root/"candidate/fast-scan-automatic-work").glob("*/detections.json")
            pin, control = source["native"]["candidate"], result["candidate"]["science"]["regional"]
            offer_pin = source["region_sha256"]
    else:
        root = Path("/var/tmp/leo-full-short-south-transfer-final")
        sealed = Path("/dev/shm/leo-v3-bilateral-veto.TSftonZt/south-far.json")
        if file_sha(sealed) != "55e1e0d7ccfb073f0149f8a28f0f3733474b9b33aaeaca04aeee446eed124ee1":
            raise ValueError("Southern far provenance changed")
        source = read(sealed)
        region = root/("far-offer.json" if case == "south-far" else "near-offer.json")
        path, = (root/"containing/fast-scan-automatic-work").glob("*/detections.json")
        archive, pin, offer_pin = source["archive"], source["native_pin"], SOUTH_OFFERS[case]
        control = source["stock_decision"] if case == "south-far" else dict(would_withhold=False, stop="inside_score", probes_evaluated=25)
    actual = archive_identity(Path(archive["root"]))
    if (actual != {k: archive[k] for k in actual} or file_sha(path) != pin[7:] or file_sha(region) != offer_pin
            or subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", archive["root"]], text=True).strip() != "tmpfs"):
        raise ValueError("Expected the original saved detector, offer and resident archive")
    return dict(archive=archive, packet=str(path), native_sha256=pin, control=control,
                offer=Algo08Region.parse(read(region)).document(), offer_sha256=offer_pin)


class TrackBatch:
    def __init__(self, packed, order):
        import numpy as np

        slices = [np.s_[packed.offset[i]:packed.offset[i+1]] for i in order]
        sizes = [h.stop-h.start for h in slices]
        self.order = order
        self.offset = np.r_[np.int64(0), np.cumsum(sizes, dtype=np.int64)]
        self.index = np.concatenate([packed.index[h] for h in slices])
        self.observed = np.concatenate([packed.observed[h] for h in slices])
        self.scale, self.base = packed.scale[order], packed.base[order]
        self.score = np.empty(len(order))
        self.owner = np.empty(len(order), dtype=np.int64)
        self.raw, self.phase = np.empty(max(sizes)), np.empty(max(sizes))
        self.packed, self.log_prior = packed, np.log(packed.catalogue)

    def __call__(self, arrays):
        f, h, d = arrays
        args = (self.offset, self.index, self.observed, self.scale, self.base, f, h, d)
        output = (self.raw, self.phase, self.score, self.owner)
        answer = self.packed.call(len(self.order), *f.shape, *(a.ctypes.data for a in args), self.packed.noise,
                                  self.log_prior, *(a.ctypes.data for a in output))
        if answer:
            raise ValueError("The original native score refused this batch")
        return list(map(float, self.score))


class Receiver:
    def __init__(self, packed, kernel):
        import numpy as np

        self.packed, self.kernel = packed, kernel
        self.metrics = Counter()
        self.tracks = len(packed.tracks)
        ordinary = list(range(self.tracks))
        self.order = sorted(ordinary, key=lambda i: -len(packed.tracks[i]["values"]))
        self.full = TrackBatch(packed, ordinary)
        self.batches = [TrackBatch(packed, self.order[i:i+BATCH]) for i in range(0, self.tracks, BATCH)]
        self.first, self.last = packed.index[packed.offset[:-1]], packed.index[packed.offset[1:]-1]
        self.records = []
        self.count = packed.counts[1]

    def project(self, point):
        import numpy as np

        begin = process_time_ns()
        f, h, d = self.kernel.phase_linear_frequency(self.packed.geometry, *point["latlon"])
        self.metrics.update(projection_cpu_ns=process_time_ns()-begin, projections=1, cells=f.size)
        if (f.ndim != 2 or f.shape != h.shape or f.shape != d.shape or f.shape[0] != len(self.packed.labels)
                or f.dtype != np.float64 or d.dtype != np.float64 or h.dtype != np.int8
                or not all(a.flags.c_contiguous and a.flags.aligned for a in (f, h, d)) or self.packed.last >= f.shape[1]):
            raise ValueError("Expected the released fused native projection domain")
        return f, h, d

    def evaluate(self, batch, arrays):
        begin = process_time_ns()
        contributions = batch(arrays)
        self.metrics.update(track_cpu_ns=process_time_ns()-begin, track_calls=len(contributions))
        return contributions

    def score(self, point):
        return sum(self.evaluate(self.full, self.project(point))) / self.count

    def caps(self, horizon):
        from regional_decision_bound import mixture_cap

        counts = ((horizon[:, self.first] >= 0) & (horizon[:, self.last] >= 0)).sum(axis=0)
        caps = [mixture_cap(float(b), int(n), self.packed.catalogue) for b, n in zip(self.packed.base, counts, strict=True)]
        return caps, counts.tolist()

    def loses(self, point, witness):
        from regional_decision_bound import below

        arrays = self.project(point)
        started = process_time_ns()
        caps, counts = self.caps(arrays[1])
        caps_ordered = [caps[i] for i in self.order]
        self.metrics["bound_cpu_ns"] += process_time_ns()-started
        scores = []
        for batch in (*self.batches, None):
            started = process_time_ns()
            proven = below(scores, caps_ordered[len(scores):], self.count, witness)
            self.metrics["bound_cpu_ns"] += process_time_ns()-started
            if proven or batch is None:
                self.records.append(dict(xy=point["xy_km"], proven=proven, evaluated=len(scores),
                                         cap=caps, possible_orbits=counts, inside=witness))
                return proven
            scores.extend(self.evaluate(batch, arrays))


def stage(kernel, base, points, width, mode):
    from bilateral_veto_disproof import disprove as original_disprove
    from regional_decision_bound import disprove
    from regional_probe_block import OrderedProbeScores, ProbeBlock
    from regional_track_scores import TrackScores
    from tools.pipeline_eval.variants.experimental.regional_veto_short_circuit import evaluate_terminal

    start, wall = process_time_ns(), perf_counter_ns()
    decision, probe = None, None
    if mode != "guarded":
        probe = Receiver(TrackScores(SCORES, base, only_receiver=1), kernel)
        decision = (original_disprove(points, width, probe.score) if mode == "one" else
                    disprove(points, width, probe.score, probe.loses))
    fallback, visited = None, []
    if decision is None:
        started = process_time_ns()
        packed = TrackScores(SCORES, base)
        block = ProbeBlock(BLOCK, packed)
        score = OrderedProbeScores(points, width, block, packed, guaranteed_only=True)

        def visit(point):
            row = score(point)
            visited.append(row)
            return row["receiver_scores"]

        decision = evaluate_terminal(points, width, visit)
        if score.failed or packed.fallbacks:
            raise ValueError("Released guarded native fallback changed")
        fallback = dict(cpu_ns=process_time_ns()-started, block_positions=block.computed, scalar=packed.native)
    record = dict(mode=mode, cpu_ns=process_time_ns()-start, elapsed_ns=perf_counter_ns()-wall, decision=decision,
                  native=None if probe is None else dict(probe.metrics), released=fallback,
                  exteriors=[] if probe is None else probe.records)
    return record, visited


def compare(kernel, packed, width, points, control):
    from regional_track_scores import TrackScores
    from leo.contracts.digests import canonical_digest

    stock, original_rows = stage(kernel, packed, points, width, "guarded")
    one, one_rows = stage(kernel, packed, points, width, "one")
    bound, fallback_rows = stage(kernel, packed, points, width, "bounded")
    chosen = stock["decision"]
    for candidate, rows in ((one, one_rows), (bound, fallback_rows)):
        if candidate["decision"]["would_withhold"] != chosen["would_withhold"] or (rows and rows != original_rows):
            raise ValueError("A measured shortcut changed the released decision or fallback rows")
    if any(chosen.get(key) != control.get(key) for key in ("stop", "would_withhold", "probes_evaluated")):
        raise ValueError(f"Original saved diagnostic drifted: {chosen!r}")
    lookup = {tuple(p["xy_km"]): p for p in points}
    audit = Receiver(TrackScores(SCORES, packed, only_receiver=1), kernel)
    for row in bound["exteriors"]:
        exact = audit.evaluate(audit.full, audit.project(lookup[tuple(row["xy"])]))
        if any(value > upper for value, upper in zip(exact, row["cap"], strict=True)):
            raise ValueError("A proposed cap was below the genuine native mixture score")
        full = sum(exact)/audit.count
        if row["proven"] and not full < row["inside"]:
            raise ValueError("A purported proof failed the genuine complete receiver score")
        row["native_full_score"] = full
    return dict(guarded=stock, one_receiver=one, bounded=bound, released_rows_sha256=canonical_digest(original_rows),
                audited_receiver_tracks=audit.tracks)


def run(case, output):
    from aperture_trial import configuration, read, solve, write
    from combined_frontier_run import BLOCK_SHA
    from dense_geographic_projection import checked_runtime
    from dense_geographic_trial import host
    from dense_full_short_crossover import file_sha
    from full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA, geographic_projection
    from prepared_exterior import handoff
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core
    from tools.pipeline_eval.variants.experimental import regional_bound_guard

    machine = host()
    publication, spec = configuration()
    if any(file_sha(path) != pin for path, pin in ((SCORES, TRACK_SCORES_SHA), (BLOCK, BLOCK_SHA), (GEOGRAPHIC, GEOGRAPHIC_SHA))):
        raise ValueError("The pinned native regional libraries changed")
    job = assignment(case)
    archive = Path(job["archive"]["root"])
    kernel, _ = checked_runtime()
    original = algo08_position.solve
    result = {}

    class Finished(BaseException):
        pass

    def intercept(document, reader, assets, region):
        with handoff(reader) as (live, _, _), geographic_projection(GEOGRAPHIC):
            def proof(prepared, view, *_args, **_kwargs):
                tracks = prepared["tracks"]
                causal = live.match(tracks, reader)
                if causal is None or region.document() != job["offer"]:
                    raise ValueError("Expected the original prepared catalogue and supplied region")

                def evaluate(data, catalogue, offer):
                    start = process_time_ns()
                    points, base, meta = kernel._prepare_probe_scores(data, catalogue, offer)
                    setup = process_time_ns()-start
                    result.update(compare(kernel, base, offer.width_km, points, job["control"]),
                                  geometry_setup_cpu_ns=setup, meta=meta)
                    return dict(result["guarded"]["decision"], **meta)

                with patch.object(kernel, "evaluate_veto", evaluate):
                    regional_bound_guard.causal_probes(tracks, reader, view, catalogue=causal, terminal_only=True)
                raise Finished

            with patch.object(v5_core, "infer", proof):
                return original(document, reader, assets, region)

    with patch.object(algo08_position, "solve", intercept):
        try:
            solve(publication, spec, read(Path(job["packet"])), archive, job["offer"])
        except Finished:
            pass
    if not result:
        raise ValueError("The saved proof did not run")
    write(output, dict(case=case, source=job, machine=machine, waveform_reads=0, position_fits=0,
                       runner_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), **result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    run(args.case, args.output)
