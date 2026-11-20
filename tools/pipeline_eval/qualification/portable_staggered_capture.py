"""Chronological saved-capture adapter for the persistent staggered detector."""

import json
import os
from contextlib import ExitStack
from pathlib import Path
from time import monotonic, process_time
from unittest.mock import patch


def capture(job, *, visits_per_segment=None):
    # These are local modules inside the relocated application.
    import native_bridge
    import staggered_packets
    from mode_assets.staggered_native import RfStagger, StaggeredLane

    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import analyze_window
    from leo.storage import short_window
    from leo.storage.fast_scan import FastSegmentSource

    main, helper = job["cpus"]
    staggered_packets.MAIN, staggered_packets.HELPER = main, helper
    os.sched_setaffinity(0, {main})
    out = Path(job["out"])
    library = Path(__file__).resolve().parent / "mode_assets/libleo-staggered-native.so"
    sha = native_bridge._sha(library)
    if sha != job["detector_sha256"]:
        raise ValueError("staggered detector differs from the packaged request")
    baseline = short_window.ShortWindowReader._member
    verified = []

    def member(reader, name, size, digest):
        if any(chunk.payload_relative_path == name for chunk in reader.manifest.chunks):
            path = short_window.confined_path(reader.path, reader.path / name, must_exist=True)
            return native_bridge.AuthenticatedMember(path, size, digest, verified)
        return baseline(reader, name, size, digest)

    start, cpu = monotonic(), process_time()
    counter, policy, previous_visit = RfStagger(), FastScanPolicyV2(), None
    with ExitStack() as stack:
        stack.enter_context(patch.object(short_window.ShortWindowReader, "_member", member))
        detector = stack.enter_context(StaggeredLane(library, job["edge"], helper_cpu=helper))
        receipt = stack.enter_context((out / "staggered-visits.jsonl").open("x"))
        lanes = [stack.enter_context((out / f"lane-{i}.jsonl").open("x")) for i in range(2)]
        for index, asset in enumerate(job["segments"]):
            path = Path(asset["path"]).parent
            expected = "sha256:" + asset["sha256"]
            source = FastSegmentSource(
                dict(path=str(path), manifest_digest=expected), stop_sequence=visits_per_segment
            )
            if source.receiver_ids != (0, 1):
                raise ValueError("staggered mode needs both physical receiver lanes")
            output, count, detector_ns = lanes[index % 2], 0, 0
            for window in source.windows():
                if window.target["edge"] != job["edge"]:
                    raise ValueError("pilot edge changed in the physical stream")
                retune = json.loads(window.acquisition.get("retune_receipt") or "{}")
                frame = (
                    index,
                    window,
                    retune.get("utc_clock_bracket"),
                    retune.get("host_delivery_clock"),
                )
                visit = window.acquisition["global_visit"]
                if previous_visit is not None and (
                    visit <= previous_visit
                    or (visits_per_segment is None and visit != previous_visit + 1)
                ):
                    raise ValueError("physical visits must reach the RF counter in capture order")
                previous_visit = visit
                packet, audit = staggered_packets.run_visit(
                    frame, counter, detector, analyze_window, policy
                )
                output.write(native_bridge.encoded(packet) + "\n")
                receipt.write(native_bridge.encoded(audit) + "\n")
                detector_ns += audit.get("cpu_ns", 0)
                count += 1
            if count != (asset["windows"] if visits_per_segment is None else visits_per_segment):
                raise ValueError("staggered lane did not account for each scheduled visit")
            output.write(
                native_bridge.encoded(
                    dict(
                        kind="segment",
                        segment=index,
                        count=count,
                        path=str(path),
                        manifest_digest=expected,
                        radio_id=source.radio["serial"],
                        library_sha256="sha256:" + sha,
                        detector_cpu_s=detector_ns / 1e9,
                    )
                )
                + "\n"
            )
        for lane, stream in enumerate(lanes):
            stream.write(native_bridge.encoded(dict(kind="worker", worker=lane)) + "\n")
    if native_bridge._sha(library) != sha:
        raise ValueError("staggered detector changed during the capture replay")
    native_bridge.save(
        out / "staggered-resources.json",
        dict(
            wall_s=monotonic() - start,
            cpu_s=process_time() - cpu,
            main_cpu=main,
            helper_cpu=helper,
            compressed_chunks=len(verified),
            compressed_bytes=sum(verified),
        ),
    )
