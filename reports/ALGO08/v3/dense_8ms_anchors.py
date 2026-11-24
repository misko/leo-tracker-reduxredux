"""Compare complete signed receive work for the A/B/C dense member recipes."""

import argparse
from collections import Counter
from hashlib import sha256
from importlib import import_module
import json
from math import remainder
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from leo.contracts.digests import canonical_digest
from preloaded_saved_worker import read, write
from reports.ALGO08.v3 import live_stereo_0008 as live


ORDERS = (("mixed12", "mixed8", "primary8"), ("primary8", "mixed8", "mixed12"))
EIGHT = Path("/var/tmp/leo-v3-eight-ms-build-padded/8ms/short-primary.so")
HELPER_SHA = "e2b1c4198fc7c0b7ce85e13cc2ed6295b93800ce5a2820c0978757ad9bfc9944"
EARLIER_A = Path("/dev/shm/leo-live-stereo-0008-pair02/result.json")
EARLIER_A_SHA = "b19eda82126d41903e003b660242c3bf6ecc0b51efa5dca253f1a5b7c9dea35c"
EARLIER_B = Path("/var/tmp/leo-v3-eight-ms-measured.json")
EARLIER_B_SHA = "132737cdcfc293a50f673b5f066bf9cc912c3fa015a4323a435f973c5ba632f6"
PRIMARY_LEDGER = "9080bb1d5bb69d2df770593bc1878e6f151d1ba0a7cbbe320e365177552b0556"
PROTOCOL = HERE/"dense-8ms-anchors-protocol.md"


def checked_inputs():
    from full_short_run import EIGHT_MS_SHA
    from primary_anchor_8ms import ARTIFACT, LIBRARY_SHA256

    source = live.original
    spec = json.loads(source.verified(source.PAYLOAD/"spec.json", source.SPEC_SHA))
    source.verified(source.PAYLOAD/"paired-sha256.so", spec["paired_sha256"]["sha256"])
    for name in live.RUNTIME_MODULES:
        source.verified(Path(import_module(name).__file__), source.RUNTIME[name])
    source.verified(source.CACHE_LIBRARY, source.CACHE_SHA)
    source.verified(EIGHT, EIGHT_MS_SHA)
    source.verified(live.SHORT, live.SHORT_SHA)
    source.verified(ARTIFACT, LIBRARY_SHA256)
    source.verified(HERE/"primary_anchor_8ms.py", HELPER_SHA)
    source.verified(live.DENSE_STAGE/"staged.json", live.DENSE_STAGING)
    info = json.loads(source.verified(live.DENSE_STAGE/"result.json", live.DENSE_RECEIPT))
    member = info["original_member"]
    if (Path(info["source"]["path"]) != live.MEMBER or live.MEMBER.resolve(strict=True) != live.MEMBER
            or live.MEMBER.stat().st_dev != Path("/dev/shm").stat().st_dev
            or member["first_sequence"] != 0 or member["window_count"] != 64):
        raise ValueError("Only the already staged first original DS30-0008 member is authorized")
    return spec, member


def receiver(mode):
    from full_short_run import EIGHT_MS_SHA, checked_recipe
    from mixed_aperture_receiver import MixedApertureDetector
    from primary_anchor_8ms import ARTIFACT, RECIPE_FIELD, AnchorPrimaryMixer, bound_library, definition

    if mode not in ORDERS[0]:
        raise ValueError("Unknown signed aperture")
    recipe = checked_recipe(eight_ms=mode != "mixed12")
    if mode == "primary8":
        recipe[RECIPE_FIELD] = definition()
        return recipe, lambda: AnchorPrimaryMixer(EIGHT, EIGHT_MS_SHA, bound_library(ARTIFACT))
    binary, pin = (live.SHORT, live.SHORT_SHA) if mode == "mixed12" else (EIGHT, EIGHT_MS_SHA)
    return recipe, lambda: MixedApertureDetector(binary, pin, full_coverage=True)


def worker(root, mode):
    from leo.storage.fast_scan import immutable_json
    from leo.storage.short_window import ShortWindowReader
    from reports.ALGO08.v3.seekable_member_trial import clock, elapsed

    started = clock()
    source = live.original
    spec, expected = checked_inputs()
    recipe, factory = receiver(mode)
    pin = canonical_digest(recipe)
    binding = elapsed(started)
    allowed = {expected[kind+"_relative_path"]: (expected[size], expected[digest]) for kind, size, digest in (
        ("index", "index_bytes", "index_sha256"), ("payload", "compressed_bytes", "compressed_sha256"))}
    opened = []
    original_member = ShortWindowReader._member

    def member(reader, name, size, digest):
        if reader.path != live.MEMBER or allowed.get(name) != (size, digest):
            raise ValueError("A receiver attempted to access a file outside the first signed member")
        data = original_member(reader, name, size, digest)
        opened.append([name, size, digest])
        return data

    ingress = source.frozen_function(spec, "receiver_ingress.py", "compressed_input_buffer")
    with patch.object(ShortWindowReader, "_member", member):
        record, probes = live.receive("unmasked", live.SHORT, "sha256:"+source.MANIFEST_SHA, ingress,
                                     create_mixer=factory, detector_pin=pin)
    counts = record["receiver"]["native_calls"]
    if (len(opened) != 2 or {row[0] for row in opened} != set(allowed) or record["chunk"] != expected
            or counts != {"full": 16, "short_primary": 112} or record["exclusions"] or record["issued"] != 64):
        raise ValueError("Each decoded authenticated visit must pay both original receiver lanes")
    root.mkdir()
    sealed = root/"member-detections.json"
    seal_clock = clock()
    detections = dict(probes=probes, analysis_sha256=record["analysis_sha256"], detector_sha256=pin,
                      sample_sha256=record["ordered_input_sha256"], manifest_sha256="sha256:"+source.MANIFEST_SHA)
    immutable_json(sealed, detections)
    digest = canonical_digest(detections)
    source.verified(sealed, digest)
    write(root/"scope.json", dict(record, arm=mode, receiver_recipe=recipe, checked_bindings=binding, opened=opened,
                                  detections_sha256=digest, seal_clock=elapsed(seal_clock), worker_through_seal=elapsed(started)))


def launch(root):
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    if root.parent.resolve(strict=True) != Path("/dev/shm"):
        raise ValueError("Use a fresh tmpfs result")
    checkout = HERE.parents[2]
    git = ["git", "-c", f"safe.directory={checkout}", "-C", str(checkout)]
    if subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise ValueError("The stage method must be committed before any of the six acquisitions")
    machine = live.check_machine()
    spec, chunk = checked_inputs()
    query = live.load_query(live.original.CACHE_LIBRARY)
    live.residency(query)
    root.mkdir()
    (root/"tmp").mkdir()
    paths = (Path(__file__), PROTOCOL, HERE/"live_stereo_0008.py", HERE/"primary_anchor_8ms.py")
    write(root/"binding.json", dict(orders=ORDERS, chunk=chunk, machine=machine, member=str(live.MEMBER),
          spec_sha256=live.original.SPEC_SHA, manifest_sha256=live.original.MANIFEST_SHA, paired_sha256=spec["paired_sha256"]["sha256"],
          prior_stage_sha256=live.DENSE_STAGING, prior_member_sha256=live.DENSE_RECEIPT,
          commit=subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip(),
          sources={path.name: sha256(path.read_bytes()).hexdigest() for path in paths}))
    env = environment(root) | {"TMPDIR": str(root/"tmp"), "XDG_CACHE_HOME": str(root/"tmp")}
    python = live.original.RELEASE/"venv/bin/python"
    for index, order in enumerate(ORDERS, 1):
        for mode in order:
            out = root/f"{index}-{mode}"
            command = ["/usr/bin/timeout", "--kill-after=2s", "20s", python, "-Bsm",
                       "reports.ALGO08.v3.dense_8ms_anchors", "worker", out, mode]
            prior = live.residency(query)
            spent = measure(command, env, out)
            write(root/(out.name+"-clock.json"), dict(clock=spent, resident_before=prior, resident_after=live.residency(query),
                                                      command=list(map(str, command))))
            if spent["exit_code"]:
                raise RuntimeError(spent["stderr_tail"])


def change(a, b, decisions):
    actual = []
    counts = Counter()
    for left, right, mode in zip(a, b, decisions, strict=True):
        if dict(left, candidates=[]) != dict(right, candidates=[]):
            raise ValueError("Signed probes differ in opportunity or timing metadata")
        before, after = left["candidates"], right["candidates"]
        counts.update(rows=1, left_positive=bool(before), right_positive=bool(after), same_row=before == after)
        if before == after:
            continue
        if before and after:
            x, y = before[0], after[0]
            epoch = y["integer_epoch_sample"]+y["fractional_epoch_offset_samples"]-x["integer_epoch_sample"]-x["fractional_epoch_offset_samples"]
            dt = remainder(epoch, 13_333)
            df = y["fractional_tracking_cfo_hz"]-x["fractional_tracking_cfo_hz"]
            counts.update(signed_matches=int(abs(dt) <= 2 and abs(df) <= 250), changed_factor=1)
        else:
            dt = df = None
            counts.update(lost=bool(before), gained=bool(after))
        actual.append(dict(visit=left["visit_index"], lane=left["receiver_id"], aperture=mode,
                           before=before, after=after, wrapped_timing_samples=dt, signed_cfo_hz=df))
    return dict(counts=dict(counts), changed=actual)


def score(root):
    from anchor_primary_dense_prefix import check_candidates
    from whole_stereo_blocks import load_checked

    source = live.original
    binding = read(root/"binding.json")
    for name, pin in binding["sources"].items():
        source.verified(HERE/name, pin)
    results, packets = {}, {}
    for index, order in enumerate(ORDERS, 1):
        for mode in order:
            name = f"{index}-{mode}"
            recorded = read(root/name/"scope.json")
            packet = json.loads(source.verified(root/name/"member-detections.json", recorded["detections_sha256"]))
            measured = read(root/(name+"-clock.json"))
            if (recorded["arm"] != mode or measured["clock"]["exit_code"] or canonical_digest(recorded["receiver_recipe"]) !=
                    packet["detector_sha256"] or recorded["probe_sha256"] != canonical_digest(packet["probes"]) or
                    any(row["unavailable"] or row["cached_pages"] != row["observed_file_pages"]
                        for row in (measured["resident_before"], measured["resident_after"]))):
                raise ValueError("A paid acquisition failed its memoized recipe or signed sample admission")
            if mode in packets and packets[mode] != packet:
                raise ValueError("Fresh reversed order changed the signed observations")
            packets[mode] = packet
            results[name] = dict(scope=recorded, measured=measured)
    old_a = json.loads(source.verified(EARLIER_A, EARLIER_A_SHA))
    old_b = json.loads(source.verified(EARLIER_B, EARLIER_B_SHA))
    ledger = load_checked(HERE/"measurements/primary-schedule.json.gz", PRIMARY_LEDGER)
    ordered = canonical_digest([[i, digest] for i, digest in enumerate(old_b["input_sha256"]["chronological_dense_iq_sha256"][:64])])
    first, second, third = (packets[mode]["probes"] for mode in ORDERS[0])
    old_a_run = next(row for row in old_a["runs"] if row["arm"] == "unmasked")
    if (canonical_digest(first) != live.PREFIX_SHA or first != old_b["dense"]["probes"]["12ms"][:128]
            or second != old_b["dense"]["probes"]["8ms"][:128] or ordered != old_a_run["ordered_input_sha256"]
            or any(packet["sample_sha256"] != ordered for packet in packets.values())
            or len({packet["detector_sha256"] for packet in packets.values()}) != 3):
        raise ValueError("The paired signed acquisitions differ from the archived pre-history input or recipe")
    by_stream = Counter()
    decisions = []
    for left, middle, right, measured in zip(first, second, third, ledger["costs_and_factors"][:128], strict=True):
        stream = tuple(left[name] for name in ("receiver_id", "edge", "channel", "actual_rf_hz"))
        anchor = by_stream[stream] % 8 == 0
        by_stream[stream] += 1
        decisions.append("full" if anchor else "short_primary")
        if measured["metadata"] != dict(left, candidates=[]):
            raise ValueError("The archived first-scan anchor lacks matching signed chronology")
        if anchor:
            check_candidates(middle["candidates"], measured["full"], right["candidates"])
            if middle != left or right["candidates"] != measured["primary"]:
                raise ValueError("The observed anchor differs from one of the archived native control measurements")
        elif middle != right:
            raise ValueError("The anchor helper changed a genuine independent 8 ms short factor")
    impacts = dict(aperture=change(first, second, decisions), anchor=change(second, third, decisions))
    write(root/"result.json", dict(binding=binding, results=results, packets=packets, impact=impacts,
         archives=dict(mixed12=EARLIER_A_SHA, both_apertures=EARLIER_B_SHA, first_scan_ledger=PRIMARY_LEDGER),
         exact_original_iq_and_earlier_primary_controls=True, waveform_visits_per_arm=64,
         raw_full_publications=0, optional_cfo_tail_calls=0, held_selector_calls=0))


if __name__ == "__main__":
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("action", choices=("launch", "score", "worker"))
    args.add_argument("root", type=Path)
    args.add_argument("mode", nargs="?", choices=ORDERS[0])
    options = args.parse_args()
    if options.action == "worker" and options.mode:
        worker(options.root, options.mode)
    elif options.action in ("launch", "score"):
        dict(launch=launch, score=score)[options.action](options.root)
    else:
        args.error("Worker requires one frozen aperture mode")
