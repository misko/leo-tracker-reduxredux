"""Size and verify literal CI16 frame support for deferred CFO work."""

import argparse
from collections import Counter
from contextlib import ExitStack
import ctypes as ct
from hashlib import sha256
import json
from pathlib import Path
from statistics import median

import numpy as np

from . import short_cfo_exact_cost as exact
from . import short_cfo_refine as ref
from . import tail_confirm as north
from .mixed_aperture_receiver import FULL_RULE


HERE = Path(__file__).resolve().parent
CFO = "fractional_tracking_cfo_hz"
FIELDS = ("candidate_rank", "integer_epoch_sample", "fractional_epoch_offset_samples", CFO,
          "fractional_exact_score", "fractional_control_score")
RAW_POSITIVE_CPU = {"north": .899563848, "weak": .319135976}
ORDER = (("gather", "refill"), ("refill", "gather")) * 2
DENSE = Path("/dev/shm/leo-held-anchor-selected-dense-01/original-detections.json")
DENSE_SHA = "ad13073239fe7e4e276debf3c667c0a997408d9efb5e07e309b5ab6fff4d0a85"
DENSE_RUN = Path("/dev/shm/leo-v3-mixed-final-0008-01/candidate")
DENSE_RUN_SHA = "dfbe0c40ae78187d583198ab97517c204708a5c7d899d0efe9f76f646a82205a"
OWNED = {"north": "933eccbd307e832148fdb028ba06b651b89bd8e6e4d222b52fa97268b247759a",
         "weak": "59794fecb9ba03db2ffa5979fa8643eea0b9d1b09e9069410a6c9b3173102d21"}
NORTH_RAW = Path("/dev/shm/leo-v3-north-cfo-final-03/containing")
NORTH_PACKET = "83d1c79b8acb8dc1d8720999af9791264558b2ac43505b6312e535fe832b91d0"


def build(root):
    source = ref.verified(exact.SOURCE, exact.SOURCE_PIN).decode()
    shared, body = source.split(exact.BODY_MARK, maxsplit=1)
    body = exact.BODY_MARK + body
    gather = exact.replace_once(exact.replace_once(body, exact.BODY_MARK, "int short_cfo_gather("), exact.LOAD, exact.GATHER)
    refill = exact.replace_once(body, exact.BODY_MARK, "int short_cfo_refill(")
    refill = exact.replace_once(refill, "const int16_t *iq, unsigned lane, unsigned epoch,",
                                "const int16_t *packed, int cells, unsigned epoch,")
    refill = exact.replace_once(refill, "!iq || !out || lane > 1", "!packed || !out")
    refill = exact.replace_once(refill, exact.LOAD,
                               "    if (!frames || refill_compact(w, packed, cells, epoch, offset)) return -1;")
    source_path = HERE / "compact_cfo_support.inc"
    extension = root / "compact-extension.inc"
    extension.write_text(shared + (HERE / "short_cfo_exact_cost.inc").read_text() + source_path.read_text() + gather + refill)
    return ref.build(root / "native", ref.PAYLOAD / "receiver.so", extension)


def native(path, name, types):
    fn = getattr(path, name)
    fn.argtypes = types
    fn.restype = ct.c_int
    return fn


class Compact:
    def __init__(self, binary):
        lib = ct.CDLL(str(binary))
        self.count = native(lib, "short_cfo_compact_count", [ct.c_uint, ct.c_double])
        self.pack = native(lib, "short_cfo_pack_support", [ct.c_void_p, ct.c_uint, ct.c_uint, ct.c_double, ct.c_void_p, ct.c_int])
        self.refill = native(lib, "short_cfo_refill", [ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_uint, ct.c_double, ct.c_double,
                            ct.POINTER(ct.c_double)])

    def retain(self, iq, lane, factor):
        cells = self.count(*factor[1:3])
        if cells <= 0:
            raise ValueError("Unsupported compact epoch/offset")
        packed = np.empty((cells, 2), dtype="<i2")
        if self.pack(iq.ctypes.data, lane, *factor[1:3], packed.ctypes.data, cells):
            raise ValueError("Native support packing refused the original stereo geometry")
        return packed

    def diagnose(self, receiver, packed, factor):
        verify = ct.cast(receiver.native.ctx, ct.POINTER(ct.c_void_p))[1]
        out = (ct.c_double * 8)()
        if self.refill(verify, packed.ctypes.data, len(packed), *factor[1:4], out):
            raise ValueError("Native packed support refill refused its bound geometry")
        return tuple(out)


def positives(packet):
    counters = Counter()
    session = packet["source"]["session_id"]
    output = {}
    for row in packet["source"]["probes"]:
        rx, counter = row["receiver_id"], row["valid_start_counter"]
        stream = row["edge"], row["channel"], row["actual_rf_hz"], rx
        short = FULL_RULE[counters[stream] % len(FULL_RULE)] == "short_primary"
        counters[stream] += 1
        if not short or not row["candidates"]:
            continue
        factor, = row["candidates"]
        if factor["candidate_rank"] != 0 or factor["passed_fractional_margin_gate"] is not True:
            raise ValueError("Expected one signed original short primary on each positive lane")
        oid = "sha256:" + sha256(f"{session}:{rx}:{counter}".encode()).hexdigest()
        if oid in output:
            raise ValueError("Signed receiver counter cannot repeat")
        output[oid] = dict(key=(row["visit_index"], rx), edge=row["edge"], counter=counter,
                           factor=tuple(factor[name] for name in FIELDS))
    return output


def census(cases, codec):
    loaded, result = {}, {}
    for case in cases:
        if case == "dense":
            packet_path, digest = DENSE, DENSE_SHA
            archived = ref.load(DENSE_RUN / "joint-research-receipt.json", DENSE_RUN_SHA)
            rows = archived["selected_rows"]
            terminal = DENSE_RUN / "fast-scan-automatic-work" / archived["receipt"]["run_id"] / "terminal.json"
            terminal = ref.load(terminal, archived["receipt"]["terminal_sha256"][7:])
            if terminal["native_sha256"] != "sha256:"+digest:
                raise ValueError("The dense saved owners bind a different detector")
            owner_digest = DENSE_RUN_SHA
        else:
            owner_digest = OWNED[case]
            seal = ref.load(Path(f"/dev/shm/leo-v3-owned-cfo-{case}01/numerical-seal.json"), owner_digest)
            packet_path, digest = Path(seal["request"]["packet"]), seal["request"]["native"][7:]
            rows = seal["runs"]["before"]["owners"]
            if rows != seal["runs"]["owned"]["owners"]:
                raise ValueError("The deferred roster is different from the accepted short roster")
        packet = ref.load(packet_path, digest)
        if rows["c0"] != rows["fitted_c"] or len({r[0] for r in rows["c0"]}) != len(rows["c0"]):
            raise ValueError("Need the original paired roster in exact order")
        owned = {r[0] for r in rows["c0"]}
        available = positives(packet)
        counts = Counter()
        for oid, row in available.items():
            count = codec.count(*row["factor"][1:3])
            row["cells"] = count
            counts[count] += 1
        stored = lambda count: (count if count > 0 else 200_000) * 4
        positive_bytes = sum(stored(r["cells"]) for r in available.values())
        owned_bytes = sum(stored(r["cells"]) for oid, r in available.items() if oid in owned)
        visits = len({r["key"][0] for r in available.values()})
        result[case] = dict(native_sha256=digest, owner_receipt_sha256=owner_digest, positives=len(available),
                           owners=len(owned), owned_positives=len(available.keys() & owned), visits=visits,
                           packed_ci16_bytes=positive_bytes, owned_ci16_bytes=owned_bytes,
                           packed_full_lane_bytes=len(available)*800_000, full_stereo_bytes=visits*1_600_000,
                           offset_index_bytes=8*(len(available)+1), complex_samples_histogram=dict(counts),
                           fallback_full_lanes=sum(n for count, n in counts.items() if count <= 0))
        loaded[case] = available, owned
    return loaded, result


def controls(codec, gather, paths):
    rng = np.random.default_rng(72)
    iq = rng.integers(-32768, 32768, (200_000, 2, 2), dtype=np.int16)
    verified = []
    for edge, receiver in paths.items():
        for index, offset in enumerate((0., .25, -1.5, 1.5, -.9999999999995, 9.99e-12)):
            lane = index % 2
            factor = (0, 13332*lane, offset, -360125. if lane == 0 else 415000., .3, .1)
            compact = codec.retain(iq, lane, factor)
            after = codec.diagnose(receiver, compact, factor)
            if exact.diag_bytes(after) != exact.diag_bytes(gather.diagnostics(receiver, iq, lane, (factor,))):
                raise ValueError("A signed native boundary changed under compact retention")
            verified.append(dict(edge=edge, lane=lane, offset=offset, cells=len(compact), diagnostics=after))
    return verified


def held(codec, gather, positive, owner_ids, paths):
    from tools.pipeline_eval.qualification.cache_residency import load_query

    north.verified(north.CACHE_LIBRARY, north.CACHE_SHA)
    query = load_query(north.CACHE_LIBRARY)
    start = ref.clock()
    clips, scope = north.north_panel(query)
    intake = ref.since(start)
    right, = NORTH_RAW.glob("fast-scan-automatic-work/*/detections.json")
    reference = ref.load(right, NORTH_PACKET)
    expected = {(row["visit_index"], row["receiver_id"]): tuple(row["candidates"][0][k] for k in FIELDS)
                for row in reference["source"]["probes"] if row["candidates"]}
    rows = []
    for oid, record in positive.items():
        visit, lane = record["key"]
        if visit >= len(clips):
            continue
        item, iq = clips[visit]
        if (item["w"].acquisition["sample_start"] != record["counter"] or item["mode"] != "short_primary"
                or item["w"].target["edge"] != record["edge"]
                or ref.factor_bytes(item["sealed"][lane]) != ref.factor_bytes((record["factor"],))):
            raise ValueError("North original I/Q member and chosen short rows disagree")
        rows.append((oid, record, iq, ref.center(item["w"])))
    owner_rows = [row for row in rows if row[0] in owner_ids]
    if not rows or not owner_rows:
        raise ValueError("The staged North member must exercise genuine chosen owners")
    all_trials, first = [], None
    for order in ORDER:
        start = ref.clock()
        blocks = {oid: codec.retain(iq, row["key"][1], row["factor"]) for oid, row, iq, _ in rows}
        times = dict(pack=ref.since(start))
        for arm in order:
            start = ref.clock()
            diagnostics = []
            for oid, row, iq, tune in owner_rows:
                factor = row["factor"]
                path = paths[(arm, row["edge"])]
                diag = (gather.diagnostics(path, iq, row["key"][1], (factor,)) if arm == "gather"
                        else codec.diagnose(path, blocks[oid], factor))
                amended, status = ref.amend((factor,), diag, 1., tune)
                diagnostics.append((oid, row["key"], diag, amended[0], status, len(blocks[oid])))
            times[arm] = ref.since(start)
            if first is None:
                first = diagnostics
            for before, after in zip(first, diagnostics, strict=True):
                if (before[:2] != after[:2] or exact.diag_bytes(before[2]) != exact.diag_bytes(after[2])
                        or ref.factor_bytes((before[3],)) != ref.factor_bytes((after[3],)) or before[4:] != after[4:]
                        or ref.factor_bytes((after[3],)) != ref.factor_bytes((expected[after[1]],))):
                    raise ValueError("A held owner differs from exact gather or the genuine raw refined result")
        all_trials.append(dict(order=order, clocks=times))
    return dict(samples_opened="one signed North simulation member", physical_waveforms_opened=0,
                scope=scope, intake_ns=intake, positives=len(rows), owners=len(owner_rows),
                pack_bytes=sum(b.nbytes for b in blocks.values()), clocks=all_trials, exact=first)


def estimate(data, panels):
    times = {name: median(row["clocks"][name][0] for row in data["clocks"]) for name in ("pack", "gather", "refill")}
    pack, gather, refill = times["pack"]/data["positives"], times["gather"]/data["owners"], times["refill"]/data["owners"]
    result = {case: dict(pack_cpu_s=pack*panel["positives"]/1e9, refill_cpu_s=refill*panel["owned_positives"]/1e9,
                        gather_all_cpu_s=gather*panel["positives"]/1e9, historical_all_positive_cpu_s=RAW_POSITIVE_CPU.get(case))
              for case, panel in panels.items()}
    return dict(measured_ns_per_lane=dict(pack=pack, gather=gather, refill=refill), projections=result)


def run(root, *, census_only=False, prepared=None):
    machine = ref.check_machine()
    if root.resolve().parent != Path("/dev/shm"):
        raise ValueError("Use a fresh tmpfs directory")
    root.mkdir()
    if prepared is None:
        binary, build_receipt = build(root)
        codec = Compact(binary)
        loaded, panels = census(("dense", "north", "weak"), codec)
        if census_only:
            ref.save(root / "census.json", dict(build=build_receipt, panels=panels))
            return
    else:
        receipt = json.loads((prepared / "census.json").read_bytes())
        binary = prepared / "native/tail.so"
        build_receipt, panels = receipt["build"], receipt["panels"]
        ref.verified(binary, build_receipt["binary_sha256"])
        codec = Compact(binary)
        loaded, local = census(("north",), codec)
        if json.loads(json.dumps(local["north"])) != panels["north"]:
            raise ValueError("Prepared North scope changed")
    gather = exact.RefineEntry(binary, "short_cfo_gather")
    with ExitStack() as stack:
        paths, boundary = {}, {}
        assets = {edge: np.frombuffer(ref.verified(ref.RELEASE / "assets" / (edge+".f32"), pin), dtype="<f4")
                  for edge, pin in ref.PILOT_SHA.items()}
        for edge, asset in assets.items():
            for arm in ("gather", "refill"):
                path = ref.NativePath(ref.PAYLOAD / "receiver.so", asset, "full")
                stack.callback(path.close)
                paths[arm, edge] = path
            boundary[edge] = paths["gather", edge]
        deterministic = controls(codec, gather, boundary)
        positive, owners = loaded["north"]
        measured = held(codec, gather, positive, owners, paths)
    ref.save(root / "result.json", dict(machine=machine, build=build_receipt, panels=panels, measured=measured,
             controls=deterministic, costs=estimate(measured, panels), physical_waveform_reads=0, position_solves=0,
             source_sha256={name: sha256((HERE / name).read_bytes()).hexdigest() for name in (
                 "compact_cfo_support.py", "compact_cfo_support.inc", "compact-cfo-support-protocol.md")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    preflight = parser.add_mutually_exclusive_group()
    preflight.add_argument("--census-only", action="store_true")
    preflight.add_argument("--prepared", type=Path)
    run(**vars(parser.parse_args()))
