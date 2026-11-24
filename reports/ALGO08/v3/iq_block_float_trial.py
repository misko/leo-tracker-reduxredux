"""Feed one complete original member and reconstructed CI16 to the same 20/8 receiver."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from math import remainder, sqrt
from pathlib import Path
from statistics import mean, median
import subprocess
from unittest.mock import patch

import numpy as np

from . import empty_bootstrap as boot
from . import future_capture_storage as capture
from . import sparse_cold_input as frozen
from .full_short_cold import freeze
from .iq_block_float import COMPILE, SOURCE, Codec
from .mixed_aperture_receiver import INSTALLED_SHA, PILOT_SHA, MixedApertureDetector, NativePath
from .seekable_member_trial import clock, elapsed, window_from
from .short_cfo_refine import PERIOD


SHORT = Path("/var/tmp/leo-v3-eight-ms-build-padded/8ms/short-primary.so")
SHORT_PIN = "fe4ba7b7613654c268353f9e4a78c2bbb916904e06387ace304b0866818f0e3d"
REFERENCE = Path("/dev/shm/leo-v3-legacy-first-use-original-panel01/DS30-0016/fused/fast-scan-automatic-work"
                 "/algo08-v2-56f5b28446c41ce61e320ada30bd0562/detections.json")
REFERENCE_PIN = "aeb4658b886daaa4f8a93e99224fb4471f032f91feaa5ce58be2361d7009b4ac"
SAMPLE_GATE, CFO_GATE = 2., 250.


def summary(values):
    return dict(count=len(values), mean=mean(values), median=median(values),
                median_abs=median(map(abs, values)), rms=sqrt(mean(value*value for value in values)),
                max_abs=max(map(abs, values))) if values else {"count": 0}


def delta(stock, offered):
    offset = remainder(offered[1] + offered[2] - stock[1] - stock[2], PERIOD)
    hz = offered[3] - stock[3]
    return dict(epoch_samples=offset, cfo_hz=hz, exact=offered[4] - stock[4], control=offered[5] - stock[5],
                matched=abs(offset) <= SAMPLE_GATE and abs(hz) <= CFO_GATE)


def comparison(stock, offered):
    edits, flags = [], Counter()
    for old, new in zip(stock["lanes"], offered["lanes"], strict=True):
        if (old["visit"], old["rx"], old["mode"]) != (new["visit"], new["rx"], new["mode"]):
            raise ValueError("The original admission, aperture, or chronology changed")
        baseline = {row[0]: row for row in old["factors"]}
        candidate = {row[0]: row for row in new["factors"]}
        differences = {str(rank): delta(baseline[rank], candidate[rank]) for rank in sorted(baseline.keys() & candidate.keys())}
        selected = (old["selected_rank"], new["selected_rank"])
        flags["native_empty_to_nonempty"] += not baseline and bool(candidate)
        flags["native_nonempty_to_empty"] += bool(baseline) and not candidate
        flags["native_rank_set_changed"] += baseline.keys() != candidate.keys()
        flags["selected_rank_changed"] += selected[0] != selected[1]
        flags["continuation_keep_changed"] += old["kept"] != new["kept"]
        flags["continuation_votes_changed"] += old["votes"] != new["votes"]
        flags["short_support_changed"] += old["short_continuation"] != new["short_continuation"]
        flags["selected_same_rank_branch_changed"] += (
            selected[0] is not None and selected[0] == selected[1] and not differences[str(selected[0])]["matched"])
        edits.append(dict(visit=old["visit"], receiver=old["rx"], mode=old["mode"], selected=selected,
                          native=[sorted(baseline), sorted(candidate)], both=differences))
    matched = [d for row in edits for d in row["both"].values() if d["matched"]]
    selected_matched = [row["both"][str(row["selected"][0])] for row in edits
                        if row["selected"][0] is not None and row["selected"][0] == row["selected"][1]
                        and row["both"][str(row["selected"][0])]["matched"]]
    return dict(changes=dict(flags), both_ranked=sum(len(row["both"]) for row in edits), matched=len(matched),
                native_frequency=summary([row["cfo_hz"] for row in matched]),
                selected_frequency=summary([row["cfo_hz"] for row in selected_matched]),
                selected_epoch=summary([row["epoch_samples"] for row in selected_matched]),
                per_lane=edits)


def receive(windows, targets, full, pilot, codec=None, bits=None):
    from tools.pipeline_eval.variants import carrier_continuation

    mixer = MixedApertureDetector(SHORT, SHORT_PIN, full_coverage=True)
    continuation = carrier_continuation.Continuation()
    rows, lanes, calls, encoded_rows, samples_receipt = [], [], [], [], []
    native, follow, quantize, reconstruct = (Counter() for _ in range(4))
    suffix = np.empty_like(windows[0].samples) if codec is not None else None
    packed_hash, decoded_hash = sha256(), sha256()
    original_run = NativePath.run

    def record(path, samples, lane, center):
        factors, clock_pair = original_run(path, samples, lane, center)
        calls.append((lane, factors))
        return factors, clock_pair

    if codec is not None:
        for row in windows:
            started = clock()
            encoded, clips = codec.encode(row.samples, bits)
            quantize.update(elapsed(started))
            encoded_rows.append(encoded)
            packed_hash.update(memoryview(encoded))
            samples_receipt.append(dict(visit=row.index.sequence, shift=int(encoded[0]), clips=clips))
    geometry = []
    with (patch.object(NativePath, "run", record),
          mixer.detector("cancellation", "lower", binary=full, pilot=pilot) as detector):
        for visits, original in enumerate(windows):
            row = original.index
            admit = capture.qualified(row.acquisition)
            geometry.append(dict(visit=row.sequence, original_iq=row.iq_sha256, admit=admit))
            samples = original.samples
            if codec is not None:
                started = clock()
                codec.decode(encoded_rows[visits], bits, suffix)
                reconstruct.update(elapsed(started))
                samples = suffix
                data = memoryview(samples).cast("B")
                decoded_hash.update(data)
                changed = np.subtract(samples, original.samples, dtype=np.int32)
                samples_receipt[visits].update(
                    restored_sha256="sha256:" + sha256(data).hexdigest(), admitted=admit,
                    changed_words=int(np.count_nonzero(changed)), max_error=int(np.max(np.abs(changed))),
                    rms_error=float(np.sqrt(np.mean(np.square(changed)))),
                )
            if not admit:
                continue
            target = targets[row.target_id]
            before = mixer.visits["full"]
            calls.clear()
            started = clock()
            probes = detector(window_from(row, target, samples))
            native.update(elapsed(started))
            mode = "full" if mixer.visits["full"] != before else "short_primary"
            for (rx, factors), probe in zip(calls, probes, strict=True):
                if probe["receiver_id"] != rx or probe["visit_index"] != row.sequence:
                    raise ValueError("Receiver output changed original sequence")
                started = clock()
                preferred, kept, votes = continuation.select(probe)
                follow.update(elapsed(started))
                rank = probe["candidates"][0]["candidate_rank"] if probe["candidates"] else None
                lanes.append(dict(visit=row.sequence, rx=rx, mode=mode, factors=factors, selected_rank=rank,
                                  preferred=preferred, kept=kept, votes=votes,
                                  short_continuation=mode == "short_primary" and kept is not None))
            rows.extend(probes)
    counts = dict(
        native=dict(Counter(str(tuple(row[0] for row in lane["factors"])) for lane in lanes)),
        selected=dict(Counter("empty" if lane["selected_rank"] is None else str(lane["selected_rank"]) for lane in lanes)),
        continued=sum(lane["kept"] is not None for lane in lanes),
        short_continued=sum(lane["short_continuation"] for lane in lanes),
    )
    reduction = dict(probes=rows, lanes=lanes, chronology=geometry, counts=counts, engine=mixer.receipt(),
                     timing=dict(callback=dict(native), continuation=dict(follow)))
    if codec is not None:
        reduction["codec"] = dict(
            bits=bits, encoded_bytes=sum(row.size for row in encoded_rows), shifts=dict(Counter(row["shift"] for row in samples_receipt)),
            clips=sum(row["clips"] for row in samples_receipt), quantize=dict(quantize), reconstruct=dict(reconstruct),
            encoded_sha256="sha256:" + packed_hash.hexdigest(), reconstructed_sha256="sha256:" + decoded_hash.hexdigest(),
            visits=samples_receipt,
        )
    return reduction


def run(root):
    from tools.pipeline_eval.variants import carrier_continuation
    from tools.pipeline_eval.qualification import blind_compact_run

    if root.parent.resolve() != Path("/dev/shm") or root.exists():
        raise ValueError("Choose a fresh result directory in tmpfs")
    machine = capture.signed.check_machine()
    setup = clock()
    spec = json.loads(frozen.verified(frozen.PAYLOAD / "spec.json", frozen.SPEC_SHA))
    full, pilot = frozen.PAYLOAD / "receiver.so", frozen.RELEASE / "assets/lower.f32"
    hasher = frozen.PAYLOAD / "paired-sha256.so"
    pins = {full: INSTALLED_SHA, pilot: PILOT_SHA["lower"], SHORT: SHORT_PIN, hasher: spec["paired_sha256"]["sha256"],
            Path(carrier_continuation.__file__): boot.EXTRA_SOURCES[boot.CONTINUATION],
            Path(blind_compact_run.__file__): boot.EXTRA_SOURCES[boot.RECEIVER]}
    for path, pin in pins.items():
        frozen.verified(path, pin)
    ingress = frozen.frozen_function(spec, "receiver_ingress.py", "compressed_input_buffer")
    root.mkdir(mode=0o700)
    binary = root / "block-float.so"
    command = [*COMPILE, str(SOURCE), "-o", str(binary)]
    subprocess.run(command, check=True)
    codec = Codec(binary)
    up_front = elapsed(setup)
    reader, windows, source = capture.verified_source(ingress, hasher)
    targets = {item["target_id"]: item for item in reader.manifest.configuration["targets"]}
    stock = receive(windows, targets, full, pilot)
    variants = {str(bits): receive(windows, targets, full, pilot, codec, bits) for bits in (8, 10)}
    ref = json.loads(frozen.verified(REFERENCE, REFERENCE_PIN))
    expected = [row for row in ref["source"]["probes"] if row["visit_index"] < len(windows)]
    if stock["probes"] != expected or (len(windows), len(stock["probes"]), len(stock["lanes"])) != (64, 116, 116):
        freeze(root / "unqualified.json", dict(clock=up_front, reference=REFERENCE_PIN,
                                               source=source, stock=stock, variants=variants))
        raise ValueError("The 20/8 control must independently reproduce the original signed physical prefix")
    if any(arm["chronology"] != stock["chronology"] or
           arm["codec"]["reconstructed_sha256"] == source["decoded"] or
           arm["codec"]["encoded_bytes"] != (source["raw_bytes"]*bits//16 + len(windows))
           for bits, arm in ((int(key), value) for key, value in variants.items())):
        raise ValueError("The derived timeline, payload size or distinct sample authority is inconsistent")
    freeze(root / "result.json", dict(
        source=source, machine=machine, setup=up_front, order=["original", "8", "10"],
        binaries={str(path): pin for path, pin in pins.items()}, encode_command=command,
        experiment_source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        codec_sha256=sha256(binary.read_bytes()).hexdigest(), codec_source_sha256=sha256(SOURCE.read_bytes()).hexdigest(),
        baseline_reference=REFERENCE_PIN, baseline_verified=True, thresholds=dict(samples=SAMPLE_GATE, hz=CFO_GATE),
        original=stock, derived=variants, comparison={key: comparison(stock, value) for key, value in variants.items()},
    ))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    run(cli.parse_args().root)
