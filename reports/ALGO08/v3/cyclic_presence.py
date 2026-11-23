"""Measure one signed cyclic-comb shape as an empty short-lane screen."""

import argparse
from contextlib import ExitStack
import ctypes as ct
import gzip
import json
from math import ceil, isfinite
from pathlib import Path
from statistics import mean, median

import numpy as np

from .centered_primary import ORIGINAL, PREFIX_PIN
from .cyclic_carrier_trial import Scout, build, pilot_lines
from .mixed_aperture_receiver import INSTALLED_SHA, PILOT_SHA, NativePath, verified
from .mixed_aperture_trial import center, ordered
from .scout_readout_trial import factor_bytes
from .tail_confirm import (CACHE_LIBRARY, CACHE_SHA, PAYLOAD, RELEASE, check_machine, clock,
                           controls, digest, input_bytes, load_query, north_panel, since, weak_panel)


HERE = Path(__file__).resolve().parent
ARCHIVES = HERE / "measurements"
CYCLIC = "ebc4855207121295b0c5db4a9280b2bd6567786e57441b1bfaee26561ddeea8b"
CENTERED = "8f1bb1af5af5c17102bd1763f4d25afd3eba19dc519bb541069cbd4d7ab7d25d"
SOURCE = "23f113c45c9be13287fa347b95e9800b6729331f4e3ddee7ceb8f17d496b7570"
QUIET = "630281cbc0b9dc331846dd47420133843b0ae563275e413a1076ec7a4e0bfc36"
SIZE, REPEATS = 16384, 4


def shape(peaks):
    first, second, third, fourth = peaks
    if not all(map(isfinite, peaks)) or not first >= second >= third >= fourth >= 0:
        raise ValueError("Invalid ordered native comb peaks")
    return 1-float(fourth)/float(first) if first else 0.


def joined(cyclic, centered, name):
    legal = {(row["key"], row["lane"], row["iq_sha256"], row["metadata"]["edge"]): row
             for row in centered[name]["details"]}
    rows = []
    for observed in cyclic["raw"][name]:
        identity = tuple(observed[key] for key in ("key", "lane", "input_sha256", "edge"))
        label = legal.pop(identity)
        if name == "dense" and label["mode"] != "short_primary":
            continue
        first = observed["scans"][0]["measures"][str(SIZE)]
        rows.append(dict(key=identity[0], lane=identity[1], digest=identity[2], edge=identity[3],
                         factor=label["prefix"], score=shape(first["scores"]), peaks=first["scores"],
                         old_native_screen_cpu_ns=first["cpu_ns"], metadata=label["metadata"]))
    return rows


class TimedScout(Scout):
    def __init__(self, library):
        super().__init__(library, SIZE)
        surface = ct.CDLL(str(library)).cyclic_carrier_surface
        surface.argtypes = (ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_double, *([ct.c_void_p]*4))
        surface.restype = ct.c_int
        self.surface, self.bins, self.first = surface, np.empty(SIZE, dtype=np.float32), ct.c_int()

    def screen(self, iq, lane, tune, lines, weights):
        start = clock()
        n = self.use(self.work, iq.ctypes.data, lane, tune, lines.ctypes.data, weights.ctypes.data,
                     self.hz.ctypes.data, self.score.ctypes.data)
        if n != 4:
            raise ValueError("The original comb did not produce four scores")
        result = shape(self.score)
        return result, since(start)

    def normalized_surface(self, iq, lane, tune, lines, weights):
        start = clock()
        count = self.surface(self.work, iq.ctypes.data, lane, tune, lines.ctypes.data, weights.ctypes.data,
                             self.bins.ctypes.data, ct.byref(self.first))
        if not 0 < count <= SIZE:
            raise ValueError("The original cyclic comb surface changed size")
        values = self.bins[:count]
        peak = values.max()
        if peak == 0:
            values.copy()
        else:
            scaled = values/peak
            centered = scaled-scaled.mean()
            sigma = scaled.std()
            if sigma > 0:
                centered/sigma
        return since(start)


def resident_rows(rows, scout, paths, pilots):
    result, anchors = [], []
    for index, (item, iq) in enumerate(rows):
        signal, mode = item["w"], item["mode"]
        edge, tune = signal.target["edge"], center(signal)
        for lane in (0, 1):
            record = dict(index=index, key=item["key"], lane=lane, digest=item["sha256"], edge=edge,
                          factor=None, score=None, clocks=[])
            for rep in range(REPEATS):
                if mode == "full":
                    detected, ticks = paths[edge, "full"].run(iq, lane, tune)
                    if factor_bytes(ordered(detected)) != factor_bytes(item["sealed"][lane]):
                        raise ValueError("The scheduled anchor differs from its sealed probe")
                    record["clocks"].append({"direct": ticks})
                    continue
                arms = ("direct", "screen", "surface")
                rotation = (index+lane+rep) % len(arms)
                times = {}
                for arm in arms[rotation:]+arms[:rotation]:
                    if arm == "direct":
                        factor, times[arm] = paths[edge, mode].run(iq, lane, tune)
                    elif arm == "screen":
                        value, times[arm] = scout.screen(iq, lane, tune, *pilots[edge])
                    else:
                        times[arm] = scout.normalized_surface(iq, lane, tune, *pilots[edge])
                if rep == 0:
                    record.update(factor=factor, score=value, peaks=scout.score.tolist())
                if record["factor"] != factor or record["score"] != value:
                    raise ValueError("Repeated signed measurements differ")
                if "sealed" in item and factor_bytes(factor) != factor_bytes(item["sealed"][lane]):
                    raise ValueError("The current short result differs from the sealed probe")
                record["clocks"].append(times)
            (anchors if mode == "full" else result).append(record)
    return result, anchors


def classify(rows, threshold):
    kept, missed, skipped, other = [], [], [], []
    for row in rows:
        identity = [row["key"], row["lane"]]
        positive = bool(row["factor"])
        if row["score"] < threshold:
            (missed if positive else skipped).append(identity)
        else:
            (kept if positive else other).append(identity)
    return dict(positive=len(kept)+len(missed), empty=len(other)+len(skipped), missed=missed,
                skipped=skipped, positive_kept=len(kept), empty_kept=len(other))


def roc(rows):
    thresholds = sorted({row["score"] for row in rows} | {0., 2.})
    return [[threshold, len(counts["missed"]), len(counts["skipped"])]
            for threshold in thresholds for counts in (classify(rows, threshold),)]


def summarize(rows, threshold):
    positives = [row["score"] for row in rows if row["factor"]]
    hindsight = min(positives) if positives else None
    output = dict(calibrated=classify(rows, threshold), hindsight_threshold=hindsight,
                  hindsight=classify(rows, hindsight) if hindsight is not None else None, roc=roc(rows),
                  radios=[classify([row for row in rows if row["lane"] == lane], threshold) for lane in (0, 1)])
    if rows and "clocks" in rows[0]:
        units = (0, 1)

        def average(data, arm, unit):
            return mean(ticks[arm][unit] for row in data for ticks in row["clocks"]) if data else None

        def paid(rep, unit, cutoff):
            return sum(row["clocks"][rep]["screen"][unit] +
                       (row["clocks"][rep]["direct"][unit] if row["score"] >= cutoff else 0) for row in rows)

        output.update(mean_lane_ns={name: [average(rows, name, unit) for unit in units]
                                   for name in ("direct", "screen", "surface")},
                      mean_empty_direct_ns=[average([row for row in rows if not row["factor"]], "direct", unit) for unit in units],
                      direct_ns=[median(sum(row["clocks"][rep]["direct"][unit] for row in rows) for rep in range(REPEATS)) for unit in units],
                      calibrated_ns=[median(paid(rep, unit, threshold) for rep in range(REPEATS)) for unit in units],
                      full_recall_ns=[median(paid(rep, unit, hindsight) for rep in range(REPEATS)) for unit in units] if hindsight is not None else None)
    return output


def budget(cpu_us, receipt):
    weak = receipt["cases"]["DS30-0016"]
    target = receipt["weak_target_reduction_s"] + weak["short_lanes"]*cpu_us*1e-6
    needed = ceil(target/receipt["weak_short_cpu_s_per_call"])
    return dict(screen_cpu_us=cpu_us, required_empty_skips=needed, signed_empty_lanes=weak["all_empty_short_lanes"])


def run(output):
    installed, short = PAYLOAD / "receiver.so", ORIGINAL / "short-primary.so"
    machine = check_machine()
    verified(installed, INSTALLED_SHA)
    verified(short, PREFIX_PIN)
    verified(CACHE_LIBRARY, CACHE_SHA)
    query = load_query(CACHE_LIBRARY)
    cyclic, centered = (json.loads(gzip.decompress(verified(ARCHIVES / path, pin))) for path, pin in
                        (("cyclic-carrier.json.gz", CYCLIC), ("centered-primary.json.gz", CENTERED)))
    if centered["receiver_sha256"]["prefix"] != PREFIX_PIN:
        raise ValueError("The archived actual short receiver changed")
    dense, old_weak = (joined(cyclic, centered, case) for case in ("dense", "weak"))
    if (len(dense), len(old_weak)) != (32, 36):
        raise ValueError("The original common signed lane enrollment changed")
    output.mkdir()
    library = output / "cyclic.so"
    build_receipt = build(library)
    if build_receipt["source_sha256"] != SOURCE:
        raise ValueError("The existing surface source changed")
    start, io = clock(), input_bytes()
    north, n_receipt = north_panel(query)
    weak, w_receipt = weak_panel(query)
    intake, storage = since(start), input_bytes()-io
    plants = [(row, iq) for row, iq in controls() if row["key"].split(":")[-1] in ("whole", "noise", "zero")]
    with ExitStack() as stack:
        scout = TimedScout(library)
        stack.callback(scout.close)
        paths, pilots = {}, {}
        for edge, pin in PILOT_SHA.items():
            asset = np.frombuffer(verified(RELEASE / "assets" / f"{edge}.f32", pin), dtype="<f4")
            lines, weights, _ = pilot_lines(asset)
            pilots[edge] = lines, weights
            for mode, binary in (("full", installed), ("short_primary", short)):
                path = NativePath(binary, asset, mode)
                stack.callback(path.close)
                paths[edge, mode] = path
        north_rows, anchor = resident_rows(north, scout, paths, pilots)
        weak_rows, _ = resident_rows(weak, scout, paths, pilots) if weak else (old_weak, [])
        plant_rows, _ = resident_rows(plants, scout, paths, pilots)
    if weak:
        old = {(row["key"], row["lane"], row["digest"]): row for row in old_weak}
        for row in weak_rows:
            archival = old.pop((row["key"], row["lane"], row["digest"]))
            if archival["peaks"] != row["peaks"] or factor_bytes(archival["factor"]) != factor_bytes(row["factor"]):
                raise ValueError("Archived comb or released short factors differ on identical weak I/Q")
    cohorts = dict(calibration=[row for row in north_rows if row["index"] < 32],
                   held_north=[row for row in north_rows if row["index"] >= 32],
                   dense=dense, weak=weak_rows, plants=plant_rows)
    threshold = min(row["score"] for row in cohorts["calibration"] if row["factor"])
    result = {name: summarize(rows, threshold) for name, rows in cohorts.items()}
    cost = result["held_north"]["mean_lane_ns"]["screen"][0]/1000
    historic_weak = [repeat["prefix"]["native"] for repeat in centered["weak"]["clocks"]]
    budget_reference = json.loads(verified(ARCHIVES / "quiet-cycle.json", QUIET))
    receipt = dict(threshold=threshold, summary=result, cohorts=cohorts, anchors=anchor, machine=machine,
                   measured_projection=budget(cost, budget_reference), projections=[budget(us, budget_reference) for us in (0, 66)],
                   archived_weak_screen_cpu_ns=mean(row["old_native_screen_cpu_ns"] for row in old_weak),
                   archived_weak_short_clocks=[{k: row[k]["short_primary"] for k in ("native_cpu_ns", "native_wall_ns", "native_calls")}
                                               for row in historic_weak],
                   intake_ns=intake, intake_storage_bytes=storage, source_sha256=digest(Path(__file__).read_bytes()),
                   north_input=n_receipt, weak_input=w_receipt, build=build_receipt,
                   pins=dict(cyclic=CYCLIC, short_receipt=CENTERED, installed=INSTALLED_SHA, short=PREFIX_PIN,
                             source=SOURCE, quiet_workload=QUIET, pilots=PILOT_SHA))
    (output / "receipt.json").write_text(json.dumps(receipt, sort_keys=True, allow_nan=False)+"\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=lambda path: Path(path).resolve())
    run(parser.parse_args().output)
