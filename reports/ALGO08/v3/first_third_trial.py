"""Time full, verified-empty and bulk-drained paths to sealed prefix detections."""

import argparse
from collections import Counter, defaultdict
from contextlib import closing, contextmanager
from hashlib import sha256
from importlib.util import find_spec
import json
import os
from pathlib import Path
import resource
from statistics import mean
from tempfile import TemporaryDirectory
from time import perf_counter_ns, process_time_ns
from types import SimpleNamespace
from unittest.mock import patch

PREFIX = 128
MASKED = ("verified-empty", "bulk-drain", "stream-drain")
ARMS = ("paid", *MASKED)
HEAVY_RECEIPT = Path(__file__).resolve().with_name("measurements") / "acquisition-split-DS30-0008.json"
HEAVY_SHA = "b4bd3489b7b7c3477f7177ca5714f420ce2b8bf845f5c03315f3f8d8c4192421"
EXPERIMENTAL = "tools.pipeline_eval.variants.experimental"
READER_PINS = {
    "leo.storage.fast_scan": "db79b4e50c10a3b948c69c86a464fb57a226b0dbb2955cf90d8ae83db3f39527",
    "leo.storage.short_window": "0884ab7ca630d59dd041e50e0ef89cd847ca842c11097f8bde06b869645eafa2",
    "leo.scanner.fast_scan_analysis": "51f513ddeea44ca7caf3d8fd27988a9180f8f86078a3901804a0bc7ee351fe14",
    "tools.algo08_scan": "573d6608597f1619785688769e7504a4ad8ac30dd71fecd37876c678ed4aca53",
    f"{EXPERIMENTAL}.paired_sha256": "95485b5598d9f003c87cf1475418a75fc82cfecbce8518f8279b4f124b61240f",
    f"{EXPERIMENTAL}.receiver_ingress": "451ba186cbaa55c83ccb5af30e35ace8533a7a7d016be68d41f4904eb1848b93",
    f"{EXPERIMENTAL}.receiver_member_lookahead": "a458ed896c22ae74462ab8f06e82fa2f71d0c689bb37d1fd4d14845e58bdb86a",
}


def reader_sources():
    result = {}
    for name, expected in READER_PINS.items():
        path = Path(find_spec(name).origin).resolve()
        if sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Released source changed: {name}")
        result[name] = dict(path=str(path), sha256=expected)
    return result


def native_first_third(native):
    rows = native["source"]["probes"]
    stereo = list(zip(rows[::2], rows[1::2], strict=True))
    visits = [left["visit_index"] for left, _ in stereo]
    if (visits != sorted(set(visits))
            or any((left["receiver_id"], right["receiver_id"]) != (0, 1)
                   or left["visit_index"] != right["visit_index"] for left, right in stereo)):
        raise ValueError("Saved native stereo opportunities changed order")
    count = native["provenance"]["window_count"]
    if (len(stereo) != native["provenance"]["processed_windows"]
            or len(stereo) + native["provenance"]["invalid_capture"] != count):
        raise ValueError("Saved native stereo opportunities do not bind the original schedule")
    keep = len(stereo) // 3
    selected = Counter(sum(len(row["candidates"]) for row in pair) for pair in stereo[:keep])
    scheduled_cut = count // 3
    scheduled_pairs = [pair for pair in stereo if pair[0]["visit_index"] < scheduled_cut]
    scheduled_counts = Counter(sum(len(row["candidates"]) for row in pair) for pair in scheduled_pairs)
    return dict(scheduled=count, admitted=len(stereo), invalid=count - len(stereo), keep=keep,
                cutoff=visits[keep - 1] + 1 if keep else 0, kept_selected_by_visit=dict(selected),
                scheduled_cut_sensitivity=dict(cutoff=scheduled_cut, keep=len(scheduled_pairs),
                                               kept_selected_by_visit=dict(scheduled_counts)))


def measure(publication, specification, native, inventory, archive, offer, arm):
    from aperture_trial import read
    from leo.contracts.digests import canonical_digest, sha256_digest
    from leo.storage.fast_scan import FastSegmentSource, immutable_json
    from tools import algo08_scan
    from tools.pipeline_eval.qualification import blind_compact_run as blind
    from tools.pipeline_eval.variants.experimental.paired_sha256 import PairedSha256
    from tools.pipeline_eval.variants.experimental.receiver_member_lookahead import MemberHints, hinted_windows
    from first_third_ingress import admitted_prefix, drained_windows, scope_chunks

    original_source = native["source"]
    entry = inventory["segments"][0]
    if canonical_digest(inventory) != original_source["input_manifest_sha256"] or entry["windows"] < PREFIX:
        raise ValueError("The inventory no longer binds the short sample scope")
    before = [row for row in original_source["probes"] if row["visit_index"] < PREFIX]
    if len(before) % 2:
        raise ValueError("Expected complete stereo probes")
    variant = arm in MASKED
    scoped = dict(segments=[entry], window_count=PREFIX)
    library_pin = specification["paired_sha256"]
    library = Path(library_pin["library"])
    if sha256_digest(library.read_bytes()) != "sha256:" + library_pin["sha256"] or not PairedSha256(library).hardware:
        raise ValueError("The paired decoded SHA-256 implementation differs")
    source_hashes, contexts, callbacks, admitted, members = [], [], [], [], []
    stats, hints = Counter(), MemberHints()
    plan = None

    class Bounded(FastSegmentSource):
        def __init__(self, segment):
            super().__init__(segment, stop_sequence=PREFIX)
            chunks = list(scope_chunks(self))
            if len(chunks) != 2 or sum(c.window_count for c in chunks) != PREFIX:
                raise ValueError("The short timing sample must cover two complete signed members")
            members.extend(dict(index=c.index_sha256, compressed=c.compressed_sha256,
                                decoded=c.uncompressed_sha256, compressed_bytes=c.compressed_bytes,
                                decoded_bytes=c.uncompressed_bytes) for c in chunks)

        def windows(self):
            if arm in ("bulk-drain", "stream-drain"):
                chunks = list(scope_chunks(self))
                following = {c.first_sequence: d for c, d in zip(chunks, chunks[1:])}
                stream = hinted_windows(drained_windows(self, plan, library, stats, streamed=arm == "stream-drain"),
                                        self, following, hints,
                                        os.posix_fadvise, os.POSIX_FADV_WILLNEED)
            else:
                stream = super().windows()
            with closing(stream):
                for w in stream:
                    source_hashes.append(w.iq_sha256)
                    yield w

    history_type = blind.Continuation

    def continuation():
        state = history_type()
        contexts.append(state)
        return state

    original_detector = algo08_scan.detector

    @contextmanager
    def detector(*args, **kwargs):
        with original_detector(*args, **kwargs) as stock:
            history, = contexts

            def visit(w):
                index = w.acquisition["global_visit"]
                admitted.append(index)
                start, wall = process_time_ns(), perf_counter_ns()
                paid = plan is None or index < plan.cutoff
                if paid:
                    probes = stock(w)
                else:
                    probes = [blind._probe(w, lane, []) for lane in w.receiver_ids]
                    for probe in probes:
                        history.select(probe)
                callbacks.append((index, paid, process_time_ns()-start, perf_counter_ns()-wall,
                                  sum(len(row["candidates"]) for row in probes)))
                return probes

            yield visit

    def analyze(_recording, root, assets, _causal_archive, _region):
        nonlocal plan
        for name, expected in algo08_scan.PINS.items():
            if sha256_digest((assets / name).read_bytes()) != "sha256:" + expected:
                raise ValueError(f"Unqualified ALGO08 asset {name}")
        start_use = resource.getrusage(resource.RUSAGE_SELF)
        start, wall = process_time_ns(), perf_counter_ns()
        if variant:
            plan = admitted_prefix([entry], [PREFIX])
            stats["plan_cpu_ns"] = process_time_ns() - start
        doc = algo08_scan.acquire(original_source["session_id"], original_source["input_manifest_sha256"], scoped, assets)
        path = root / "detections.json"
        immutable_json(path, doc)
        got = read(path)
        expected_rows = [row if plan is None or row["visit_index"] < plan.cutoff else dict(row, candidates=[])
                         for row in before]
        bound = got["source"]
        digest = canonical_digest([original_source["input_manifest_sha256"], source_hashes])
        if (len(source_hashes) != PREFIX or bound["probes"] != expected_rows
                or got["clock_anchor"] != native["clock_anchor"] or got["delivery_clocks"] != native["delivery_clocks"][:PREFIX]
                or bound["raw_recording_authority_digest"] != digest
                or bound["analysis_manifest_sha256"] != canonical_digest([
                    "cancellation", digest, specification["detector_sha256"], expected_rows])):
            raise ValueError("The candidate failed clock, integrity or released empty-probe parity")
        stock_visits = [row["visit_index"] for row in before if row["receiver_id"] == 0]
        if (admitted != stock_visits or (plan is not None and
                (plan.count != PREFIX or plan.admitted != len(admitted)
                 or plan.keep != sum(paid for _, paid, *_ in callbacks)))):
            raise ValueError("Authenticated cutoff or admission differs from released scheduling")
        if (arm in ("bulk-drain", "stream-drain")
                and (stats["metadata_only_rows"] != PREFIX - plan.cutoff or stats["bulk_members"] < 1)):
            raise ValueError("The chosen sample did not exercise actual metadata-only drainage")
        end_use = resource.getrusage(resource.RUSAGE_SELF)
        paid_cpu = sum(cpu for _, paid, cpu, *_ in callbacks if paid)
        return dict(arm=arm, cpu_ns=process_time_ns()-start, elapsed_ns=perf_counter_ns()-wall,
                    input_blocks=end_use.ru_inblock-start_use.ru_inblock, peak_rss_kib=end_use.ru_maxrss,
                    plan=None if plan is None else dict(scheduled=plan.count, admitted=plan.admitted,
                                                        keep=plan.keep, cutoff=plan.cutoff),
                    paid_cpu_ns=paid_cpu, callbacks=callbacks, components=dict(stats),
                    explicit_lookahead_hints=hints.submitted, members=members,
                    window_sha256=source_hashes, scoped_raw_digest=digest,
                    sealed_sha256=canonical_digest(got), detections_sha256=bound["analysis_manifest_sha256"],
                    selected=sum(len(row["candidates"]) for row in expected_rows))

    with TemporaryDirectory() as directory:
        scratch = Path(directory)
        region = scratch / "region.json"
        region.write_text(json.dumps(offer))
        root = scratch / "output"
        root.mkdir()
        args = SimpleNamespace(recording=Path(entry["path"]), bulk_root=root, archive=archive, region=region)
        with (patch.object(algo08_scan, "analyze", analyze), patch.object(algo08_scan, "detector", detector),
              patch.object(algo08_scan, "FastSegmentSource", Bounded), patch.object(blind, "Continuation", continuation)):
            return publication.run(args, specification)


def budget(sweeps, full, heavy):
    measured = {name: [v for sweep in sweeps for v in sweep if v["arm"] == name] for name in ARMS}
    by_selected = defaultdict(list)
    for receipt in measured["paid"]:
        for _, _, cpu, _, selected in receipt["callbacks"]:
            by_selected[selected].append(cpu)
    pooled = mean(cpu for clocks in by_selected.values() for cpu in clocks)

    def stratified(counts):
        return sum(by_count * mean(by_selected[int(count)]) for count, by_count in counts.items())

    price = stratified(full["kept_selected_by_visit"])
    alternative = stratified(full["scheduled_cut_sensitivity"]["kept_selected_by_visit"])
    keep = full["keep"]
    skipped = full["scheduled"] - full["cutoff"]

    def outside(row):
        return row["cpu_ns"] - row["paid_cpu_ns"] - row["components"].get("plan_cpu_ns", 0)

    plan = mean(row["components"]["plan_cpu_ns"] for row in measured["verified-empty"]) * full["scheduled"]/PREFIX
    tail = PREFIX - measured["verified-empty"][0]["plan"]["cutoff"]
    candidates = {}
    for arm in MASKED:
        differences = [outside(next(r for r in sweep if r["arm"] == "verified-empty"))
                       - outside(next(r for r in sweep if r["arm"] == arm)) for sweep in sweeps]
        credit = mean(differences) * skipped / tail / 1e9
        empty_cpu = mean(cpu for row in measured[arm] for _, paid, cpu, *_ in row["callbacks"] if not paid)
        empty_s = empty_cpu * (full["admitted"] - keep) / 1e9
        candidates[arm] = dict(paired_outside_delta_ns=differences, extrapolated_credit_cpu_s=credit,
                               extrapolated_empty_callback_cpu_s=empty_s,
                               projected_full_acquisition_cpu_s=heavy["outside_detector_cpu_s"] + price/1e9
                               + plan/1e9 + empty_s - credit)
    baseline_callbacks = sum(group["cpu_s"] for group in heavy["detector_groups"].values())
    return dict(per_stereo_cpu_ns={name: dict(n=len(times), mean=mean(times), min=min(times), max=max(times))
                                  for name, times in by_selected.items()},
                kept_callback_cpu_s_stratified=price/1e9, kept_callback_cpu_s_pooled=pooled*keep/1e9,
                scheduled_cut_callback_cpu_s_stratified=alternative/1e9,
                extrapolated_metadata_plan_cpu_s=plan/1e9,
                full_stock_callback_cpu_s=baseline_callbacks,
                full_attributable_outside_cpu_s=heavy["outside_detector_cpu_s"],
                candidates=candidates)


def run(output):
    from aperture_trial import DENSE, configuration, inputs, machine, read, write

    publication, specification = configuration()
    readers = reader_sources()
    settings = machine()
    if (settings["cpu"] != [2] or settings["nice"] < 15 or "prio 7" not in settings["ionice"]
            or any(value != "1" for value in settings["threads"].values())):
        raise RuntimeError("Expected CPU 2 and one low-priority numerical thread")
    native, archive, offer, _, identity = inputs("DS30-0008")
    payload = HEAVY_RECEIPT.read_bytes()
    if sha256(payload).hexdigest() != HEAVY_SHA:
        raise ValueError("Measured full acquisition attribution changed")
    heavy = json.loads(payload)
    if heavy["detection_file_sha256"] != identity["native_sha256"].removeprefix("sha256:"):
        raise ValueError("Full attribution does not describe the saved detection packet")
    inventory = read(DENSE.parent / "baseline/fast-scan-inputs" / (native["source"]["session_id"] + ".json"))
    sweeps = [[measure(publication, specification, native, inventory, archive, offer, arm) for arm in order]
              for order in (ARMS, ARMS[::-1])]
    flat = [row for sweep in sweeps for row in sweep]
    if len({r["scoped_raw_digest"] for r in flat}) != 1 or len({r["sealed_sha256"] for r in flat if r["arm"] in MASKED}) != 1:
        raise ValueError("Matched prefix traversals or sealed empty suffixes differed")
    full = native_first_third(native)
    write(output, dict(machine=settings, identity=identity, full_scope=full, sweeps=sweeps,
                       full_attribution_source_sha256=HEAVY_SHA, reader_sources=readers,
                       projection=budget(sweeps, full, heavy)))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    run(cli.parse_args().output)
