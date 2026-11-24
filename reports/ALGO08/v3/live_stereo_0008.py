"""Time one authenticated DS30-0008 member with the frozen live stereo schedule."""

import argparse
from collections import Counter
from hashlib import sha256
from importlib import import_module
from importlib.util import module_from_spec, spec_from_file_location
import json
import os
from pathlib import Path
import subprocess

from leo.contracts.digests import canonical_digest
from leo.contracts.fast_scan_native import FastScanPolicyV2
from leo.scanner.fast_scan_analysis import valid_window_support
from leo.storage.fast_scan import FastSegmentSource
from tools.pipeline_eval.qualification.cache_residency import cache_snapshot, load_query
from tools.pipeline_eval.variants.experimental.paired_sha256 import paired_decoded_hashes

from . import sparse_cold_input as original
from .ci16_packed_storage_trial import DENSE_RECEIPT, DENSE_STAGE, DENSE_STAGING
from .full_short_cold import SHORT_SHA, check_machine, freeze
from .seekable_member_trial import SOURCE_FILES, clock, elapsed, window_from


HERE = Path(__file__).resolve().parent
ORDERS = (("unmasked", "masked"), ("masked", "unmasked"))
MEMBER = DENSE_STAGE / "fast8-auto-20261113-075937-d9ab96ee-1-lower-segment-00000000"
PREFIX_SHA = "sha256:f2fa76dbf734b90c212a61c02b6a074c4e6e7a8d3a12e7efa8e2fdf5833b3085"
CAPTURE_FILES = dict(zip(SOURCE_FILES, (6_812, 172_750, 77_442_779), strict=True))
PLANNER = Path("/dev/shm/leo-v3-whole-stereo-blocks/reports/ALGO08/v3/whole_stereo_blocks.py")
ARCHIVE = Path("/dev/shm/leo-held-anchor-selected-dense-01/original-detections.json")
SHORT = Path("/var/tmp/leo-mixed-aperture.pdUjDb1S/build-v2/short-primary.so")
SCHEDULE_SHA = "bf1f41110d1020b6acd737e00691ec9c04573e95774d9338300f0c554245b955"
RUNTIME_MODULES = ("tools.pipeline_eval.qualification.blind_compact_run", "leo.storage.fast_scan",
                   "leo.storage.short_window", "leo.scanner.fast_scan_analysis",
                   "tools.pipeline_eval.variants.experimental.paired_sha256")


def residency(query):
    if MEMBER.resolve(strict=True) != MEMBER or MEMBER.stat().st_dev != DENSE_STAGE.parent.stat().st_dev:
        raise ValueError("Expected the exact private tmpfs member")
    state = cache_snapshot([(MEMBER, name, size) for name, size in CAPTURE_FILES.items()],
                           os.sysconf("SC_PAGE_SIZE"), query)
    if (state["observed_members"] != len(CAPTURE_FILES)
            or state["cached_pages"] != state["observed_file_pages"]):
        raise ValueError("The complete private original must stay resident")
    return state


def receive(arm, short, manifest_pin, ingress):
    from full_short_raw import RECIPE_SHA
    from live_stereo_blocks import bind
    from mixed_aperture_receiver import MixedApertureDetector

    policy = FastScanPolicyV2()
    probes, windows, exclusions = [], [], []
    callbacks = Counter()
    start = clock()
    mixer = MixedApertureDetector(short, SHORT_SHA, full_coverage=True)
    recipe = {"detector": "sha256:" + RECIPE_SHA}
    if arm == "masked":
        recipe = bind(mixer, recipe["detector"])
    with (ingress(), paired_decoded_hashes(original.PAYLOAD / "paired-sha256.so"),
          mixer.detector("cancellation", "lower", binary=original.PAYLOAD / "receiver.so",
                         pilot=original.RELEASE / "assets/lower.f32") as identify):
        raw = FastSegmentSource({"path": str(MEMBER), "manifest_digest": manifest_pin}, stop_sequence=64)
        chunk = raw.reader.manifest.chunks[0]
        for window in raw.windows():
            visit = window.acquisition["global_visit"]
            if window.sequence != len(windows) or visit != window.sequence:
                raise ValueError("Expected the original ordered global visits 0 through 63")
            windows.append([visit, window.iq_sha256])
            if not valid_window_support(window.acquisition, window.sample_rate_hz, window.samples.shape,
                                        raw.receiver_ids, policy):
                exclusions.append(visit)
                continue
            before = clock()
            probes.extend(identify(window_from(window, window.target, window.samples)))
            callbacks.update(elapsed(before))
        if (chunk.chunk_index, chunk.first_sequence, chunk.window_count, len(windows)) != (0, 0, 64, 64):
            raise ValueError("Expected a complete independently authenticated first member")
        ordered_input = canonical_digest(windows)
        probe_digest = canonical_digest(probes)
        ancestry = recipe["detector"] if arm == "unmasked" else canonical_digest(recipe)
        analysis = canonical_digest([manifest_pin, ordered_input, ancestry, probe_digest])
    spent = elapsed(start)
    return dict(arm=arm, timing=spent, callback=dict(callbacks), receiver=mixer.receipt(), recipe=recipe,
                probe_sha256=probe_digest, analysis_sha256=analysis, ordered_input_sha256=ordered_input,
                chunk=chunk.model_dump(mode="json"), issued=len(windows), exclusions=exclusions,
                admitted=len(probes)//2, probes=len(probes), selected=sum(len(row["candidates"]) for row in probes)), probes


def compare_archive(original_rows, masked_rows, decisions):
    expected, selected, removed = [], Counter(), 0
    for index, (visit, mode, keep) in enumerate(decisions):
        pair = original_rows[index * 2:index * 2 + 2]
        if ([(row["visit_index"], row["receiver_id"]) for row in pair] != [(visit, 0), (visit, 1)]
                or mode not in ("full", "short_primary") or (mode == "full" and not keep)):
            raise ValueError("The independent frozen schedule and original order differ")
        selected[mode if keep else "skip"] += sum(len(row["candidates"]) for row in pair)
        removed += not keep
        expected.extend(pair if keep else [dict(row, candidates=[]) for row in pair])
    if len(expected) != len(original_rows) or expected != masked_rows:
        raise ValueError("Live output differs from the exact independently masked archived probes")
    return dict(omitted_visits=removed, reference_factors_by_mode=dict(selected),
                schedule_sha256=canonical_digest(decisions), projected_probe_sha256=canonical_digest(expected))


def verify_archive(rows, planner_pin):
    path = PLANNER
    original.verified(path, planner_pin)
    spec = spec_from_file_location("archived_whole_stereo_planner", path)
    planner = module_from_spec(spec)
    spec.loader.exec_module(planner)
    archived = planner.load_checked(ARCHIVE, planner.NATIVE_SHA)
    source, detector = archived["source"], archived["provenance"]["detector_sha256"]
    if planner.signature(source, detector, source["probes"]) != source["analysis_manifest_sha256"]:
        raise ValueError("Archived original mixed detector signature changed")
    prefix = [row for row in source["probes"] if row["visit_index"] < 64]
    if prefix != rows["unmasked"] or canonical_digest(prefix) != PREFIX_SHA:
        raise ValueError("Original waveform replay no longer matches the signed dense prefix")
    decisions = [row for row in planner.schedule(archived) if row[0] < 64]
    return compare_archive(prefix, rows["masked"], decisions) | dict(
        archived_packet_sha256=planner.NATIVE_SHA, archive_analysis_sha256=source["analysis_manifest_sha256"],
        archive_recording_sha256=source["raw_recording_authority_digest"], original_probe_sha256=PREFIX_SHA)


def trial(output, short):
    from full_short_raw import RECIPE_SHA, recipe
    from live_stereo_blocks import PLANNER_SHA
    from mixed_aperture_receiver import INSTALLED_SHA

    if output.parent.resolve(strict=True) != DENSE_STAGE.parent or not output.name:
        raise ValueError("Expected a fresh tmpfs output")
    machine = check_machine()
    output.mkdir(mode=0o700)
    spec = json.loads(original.verified(original.PAYLOAD / "spec.json", original.SPEC_SHA))
    original.verified(original.PAYLOAD / "paired-sha256.so", spec["paired_sha256"]["sha256"])
    original.verified(original.CACHE_LIBRARY, original.CACHE_SHA)
    for name in RUNTIME_MODULES:
        original.verified(Path(import_module(name).__file__), original.RUNTIME[name])
    original.verified(HERE / "live_stereo_blocks.py", SCHEDULE_SHA)
    if canonical_digest(recipe()) != "sha256:" + RECIPE_SHA or INSTALLED_SHA != spec["detector_sha256"]:
        raise ValueError("The unfiltered mixed detector or its native anchor changed")
    status = subprocess.check_output(["findmnt", "-n", "-o", "FSTYPE", "-T", MEMBER], text=True).strip()
    if status != "tmpfs":
        raise ValueError("The private original is no longer on tmpfs")
    query = load_query(original.CACHE_LIBRARY)
    custody, rows, runs = [], {}, []
    ingress = original.frozen_function(spec, "receiver_ingress.py", "compressed_input_buffer")
    for order in ORDERS:
        for arm in order:
            custody.append(residency(query))
            record, measured = receive(arm, short, "sha256:" + original.MANIFEST_SHA, ingress)
            if arm in rows and rows[arm] != measured:
                raise ValueError("Repeating the same route changed ordered probes")
            rows[arm] = measured
            runs.append(record)
    custody.append(residency(query))
    freeze(output / "live-before-reference.json", dict(rows=rows, runs=runs))
    audit = verify_archive(rows, PLANNER_SHA)
    previous = json.loads(original.verified(DENSE_STAGE / "result.json", DENSE_RECEIPT))
    original.verified(DENSE_STAGE / "staged.json", DENSE_STAGING)
    if (len({record["ordered_input_sha256"] for record in runs}) != 1
            or any(record["chunk"] != previous["original_member"] for record in runs)):
        raise ValueError("The runs disagree on signed member bytes, digest or chronology")
    for record in runs:
        masked = record["arm"] == "masked"
        skips = audit["omitted_visits"] if masked else 0
        counts = record["receiver"]
        if (record["exclusions"] or counts["native_calls"] != {"full": 16, "short_primary": 112-2*skips}
                or counts["visits"].get("skip", 0) != skips or record["selected"] !=
                (67-audit["reference_factors_by_mode"]["skip"] if masked else 67)):
            raise ValueError("The paid native calls or factors differ from the frozen prefix")
    freeze(output / "result.json", dict(recording="DS30-0008", source=previous["source"], filesystem=status,
           orders=ORDERS, machine=machine, runs=runs, residency=custody, science=audit,
           prior_stage_sha256=DENSE_STAGING, prior_member_receipt_sha256=DENSE_RECEIPT,
           runtime_sha256=original.SPEC_SHA, runner_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
           runtime_modules={name: original.RUNTIME[name] for name in RUNTIME_MODULES},
           paired_digest_sha256=spec["paired_sha256"]["sha256"],
           ingress_sha256=spec["sources"][f"{original.EXPERIMENTAL}/receiver_ingress.py"],
           live_schedule_sha256=SCHEDULE_SHA, mixed_receiver_sha256=recipe()["callback_sha256"],
           manifest_bytes=CAPTURE_FILES["manifest.json"], boundary="fresh receiver setup to complete verified member"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--short-library", type=Path, default=SHORT)
    args = parser.parse_args()
    trial(args.output, args.short_library)
