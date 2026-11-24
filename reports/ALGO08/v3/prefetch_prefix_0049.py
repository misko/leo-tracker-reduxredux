"""Pay both lookahead paths on the same six authenticated DS30-0049 members."""

import argparse
import json
import sys
from collections import Counter
from contextlib import ExitStack, contextmanager
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from time import time_ns
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]

from original_prefix_scaling import files, pinned  # noqa: E402

STAGE = Path("/tmp/leo-v3-ds30-0049-complete-idle01")
FACTORIAL = Path("/dev/shm/leo-v3-0049-factorial02")
OFFICIAL = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124/cases/DS30-0049")
BUILD = Path("/tmp/leo-v3-prefetch-live-0016-result01/build.json")
BUILD_PIN = "bb4d1466c6b3dbc3333ad3be71ce2dade103356fa5a8c6f5bb56bf599b66c282"
STAGE_PIN = "132a92c06c4e126023621027ae6a59ece97612f13715e9c9dc307a46e2ba8ba0"
FACTORIAL_PIN = "78072f6a27b4ce278f517179d87823fc819210fa40655bb3217e9362cf973d95"
PAIR_PIN = "7514497ea681194487e8d85aecf2d739e996abf2b90566d446f81fe38875c36b"
OFFER_PIN = "2698d6858da0a2d989d8c2185c9e3bbbba20d539988204c1f93a591eb9471236"
MANIFEST_PIN = "sha256:f73bcb8039b47bed2145436c25cb3241f53cc9bea9b7e528ac00ad90c660812c"
ORDER = ("ordinary-first", "slots-second", "slots-first", "ordinary-second")
ORIENTATIONS = {"forward": ORDER[:2], "reverse": ORDER[2:]}
COUNT, WINDOWS = 6, 384


def read(path, pin=None):
    return json.loads(path.read_bytes() if pin is None else pinned(path, pin))


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def enrollment(output):
    from exact_named_raw import staged_path
    from integrated_original_batch import load_build, original_argv
    from leo.contracts.digests import canonical_digest

    staged = read(STAGE / "result.json", STAGE_PIN)
    seal = read(FACTORIAL / "seal.json", FACTORIAL_PIN)
    accepted = read(FACTORIAL / "admission.json", seal["admission.json"])
    original = read(OFFICIAL / "pair.json", PAIR_PIN)
    authority = read(OFFICIAL / "authority.json", original["authority_sha256"])
    relative = f"attempt-{original['generation']:06d}"
    prior = OFFICIAL / "successor" / relative
    result = read(prior / "result.json", original["attempt_result_sha256"]["successor"])
    (detections,) = (prior / "publication/fast-scan-automatic-work").glob("*/detections.json")
    reference = read(detections, result["native_sha256"])
    offer = STAGE / "control/offer.json"
    pinned(offer, OFFER_PIN)
    if (
        not original["verified_pair"]
        or original["generation"] != 2
        or not original["same_lease"]
        or accepted["custody"] != STAGE_PIN
        or accepted["manifest"] != MANIFEST_PIN
        or accepted["public_pair"] != PAIR_PIN
        or authority["region_sha256"] != f"sha256:{OFFER_PIN}"
        or reference["source"]["raw_recording_authority_digest"]
        != authority["raw_authority_sha256"]
        or reference["source"]["input_manifest_sha256"] != authority["inventory_sha256"]
    ):
        raise ValueError("The retained stage and factorial must bind the original 0049 receipt")
    recording = staged_path(Path(staged["stage"]), root=STAGE)
    if recording.name != Path(authority["recording"]).name or recording.parent != STAGE:
        raise ValueError("Expected the retained local recording tree")
    source = staged_path(recording / f"{recording.name}-segment-00000000", root=recording)
    manifest = read(staged_path(source / "manifest.json", root=source), MANIFEST_PIN)
    members = manifest["chunks"][:COUNT]
    if members != accepted["members"] or len(members) != COUNT:
        raise ValueError("The six authenticated original member commitments changed")
    custody = {
        item["relative"]: (item["length"], item["sha256"]) for item in staged["verified_files"]
    }
    for number, row in enumerate(members):
        if (row["chunk_index"], row["first_sequence"], row["window_count"]) != (
            number,
            number * 64,
            64,
        ):
            raise ValueError("Expected six complete consecutive original members")
        for extent, pathkey in (
            ("index", "index_relative_path"),
            ("compressed", "payload_relative_path"),
        ):
            path = staged_path(source / row[pathkey], root=source)
            signed = row[f"{extent}_bytes"], row[f"{extent}_sha256"]
            if (
                custody.get(str(path.relative_to(STAGE))) != signed
                or path.stat().st_size != signed[0]
            ):
                raise ValueError("The local stage was incomplete or differed from signed custody")
    inventory = dict(
        schema_version=1,
        kind="research-original-recording-prefix",
        original_inventory_sha256=authority["inventory_sha256"],
        original_recording=authority["recording"],
        prefix_members=members,
        window_count=WINDOWS,
        segments=[
            dict(
                scope="segment-00000000",
                path=str(source),
                manifest_digest=MANIFEST_PIN,
                windows=WINDOWS,
            )
        ],
    )
    pin = canonical_digest(inventory)
    scope = dict(
        inventory=inventory,
        digest=pin,
        session="fast-" + pin[7:39],
        stop=WINDOWS,
        bytes=sum(row["compressed_bytes"] for row in members),
    )
    build, _, _ = load_build(BUILD, "sha256:" + BUILD_PIN, reuse_prefetched_snapshots=True)
    args = SimpleNamespace(
        recording=source,
        archive=output / "unused-catalogue",
        region=offer,
        bulk_root=output / "example",
    )
    command = original_argv(args, build, authority)[1:]
    return dict(
        case="DS30-0049",
        source=str(source),
        scopes={str(COUNT): scope},
        candidate_options=command,
        originals=authority,
        reference_native=result["native_sha256"],
        expected_probes=[p for p in reference["source"]["probes"] if p["visit_index"] < WINDOWS],
        expected_exclusions=[
            p for p in reference["provenance"]["excluded_windows"] if p["visit"] < WINDOWS
        ],
        order=ORDER,
        custody_sha256=STAGE_PIN,
        factorial_sha256=FACTORIAL_PIN,
        build_sha256=BUILD_PIN,
        source_pins={
            name: digest(HERE / name)
            for name in (
                "original_prefix_scaling.py",
                Path(__file__).name,
                "prefetch-prefix-0049-protocol.md",
            )
        },
    )


def child(output, book, slots):
    import empty_bootstrap as boot
    from original_prefix_scaling import worker

    ordinary = boot.load_runtime
    measured, snapshots = [], []
    with ExitStack() as stack:

        def load():
            runtime = ordinary()
            import combined_frontier_run as frontier

            if slots:
                with patch.object(sys, "path", [*sys.path, str(ROOT)]):
                    from reports.ALGO08.v3 import prefetch_snapshots
                stack.enter_context(prefetch_snapshots.binding(frontier, snapshots))
            load_prefetch = frontier.load_prefetch

            def measured_prefetch():
                actual = load_prefetch()

                @contextmanager
                def scope():
                    with actual() as stats:
                        yield stats
                    measured.append(asdict(stats))

                return scope

            stack.enter_context(patch.object(frontier, "load_prefetch", measured_prefetch))
            return runtime

        stack.enter_context(patch.object(boot, "load_runtime", load))
        from integrated_original_entry import main

        worker(output, book, COUNT, entrypoint=main, preserve_lookahead=True)
    (stats,) = measured
    write(
        output / "prefetch.json",
        dict(prefetch=stats, slots=snapshots[0] if slots else [], enabled=slots),
    )


def compare(artifact, prefetch, book, enabled):
    from leo.contracts.digests import canonical_digest

    raw, live, opts = artifact
    scope = book["scopes"][str(COUNT)]
    calls = live["receiver"]["native"]["native_calls"]
    if live["receiver"]["issued"] != WINDOWS or calls != dict(full=92, short_primary=632):
        raise ValueError("The receiver did not own the frozen admitted aperture schedule")
    probes, excluded = live["before_selection"], raw["provenance"]["excluded_windows"]
    if (
        probes != book["expected_probes"]
        or excluded != book["expected_exclusions"]
        or len(probes) != 724
        or len(excluded) != 22
    ):
        raise ValueError("Actual native factors or original opportunity masks changed")
    signed = live["source"]
    members = scope["inventory"]["prefix_members"]
    fields = (
        ("member_sha256", "compressed_sha256"),
        ("raw_sha256", "uncompressed_sha256"),
        ("index_sha256", "index_sha256"),
        ("encoded", "compressed_bytes"),
        ("windows", "window_count"),
    )
    expected = [tuple(row[key] for _, key in fields) for row in members]
    observed = [tuple(row[key] for key, _ in fields) for row in signed["members"]]
    pin = canonical_digest([scope["digest"], live["iq"]])
    if (
        observed != expected
        or len(live["iq"]) != WINDOWS
        or signed["authority_mode"] != "verified-once"
        or signed["finished_raw_authority"] != pin
        or raw["source"]["raw_recording_authority_digest"] != pin
        or raw["source"]["session_id"] != scope["session"]
        or pin == book["originals"]["raw_authority_sha256"]
    ):
        raise ValueError(
            "The emitted detector did not bind a distinct, fully checked prefix identity"
        )
    expected_bytes = sum(row["compressed_bytes"] for row in members[1:])
    if (
        prefetch["submitted"],
        prefetch["hits"],
        prefetch["hit_bytes"],
        prefetch["submitted_bytes"],
        prefetch["fallback"],
    ) != (COUNT - 1, COUNT - 1, expected_bytes, expected_bytes, 0):
        raise ValueError("Lookahead did not stop at the authenticated prefix frontier")
    reused = sum(slot.get("reuses", 0) for slot in opts)
    if enabled != bool(reused):
        raise ValueError("The measured prefix did not activate the expected allocation path")
    return dict(
        prefix_raw_authority=pin,
        probes=len(probes),
        exclusions=len(excluded),
        full_lanes=live["receiver"]["native"]["native_calls"]["full"],
        short_lanes=live["receiver"]["native"]["native_calls"]["short_primary"],
        member_hashes=observed,
        slots=opts,
        prefetch=prefetch,
        decode_cost=dict(
            Counter(
                {
                    k: sum(row[k] for row in signed["members"])
                    for k in (
                        "native_read_cpu_ns",
                        "native_read_wall_ns",
                        "hash_cpu_ns",
                        "hash_wall_ns",
                    )
                }
            )
        ),
        receiver=live["receiver"]["acquire"],
        process_auth_blocks=sum(
            row["complete_encoded_auth"]["input_blocks"] for row in signed["members"]
        ),
    )


def occupied():
    """Require the read-free experiment to begin in an established storage deferral."""
    active = max(
        (folder for folder in OFFICIAL.parent.iterdir() if (folder / "events").is_dir()),
        key=lambda folder: (folder / "events").stat().st_mtime_ns,
    )
    latest = max((active / "events").glob("*.json"))
    state = read(latest)
    age = (time_ns() - latest.stat().st_mtime_ns) / 1e9
    gate = dict(case=active.name, event=latest.name, sha256=digest(latest), age_s=age, body=state)
    return gate, state["state"] == "deferred_storage_busy" and 0 <= age < 6


def launch(root, orientation):
    import empty_bootstrap as boot

    sys.path.extend((str(boot.RELEASE / "src"), str(boot.RELEASE)))
    from dense_geographic_trial import host
    from eight_ms_south_transfer import environment_for
    from short_raw_diagnostic import measure
    from visit_frame_raw_0016 import resident

    if root.parent != Path("/tmp") or root.exists():
        raise ValueError("Use a new private tmpfs output")
    machine = host()
    gate, deferral = occupied()
    if not deferral:
        raise RuntimeError(f"No natural storage deferral in the latest official event: {gate!r}")
    book = enrollment(root)
    pathset = files(book, book["scopes"][str(COUNT)])
    first = resident(pathset)
    root.mkdir(mode=0o700)
    for name in ("tmp", "fonts", "unused-catalogue"):
        (root / name).mkdir()
    binding = root / "binding.json"
    write(binding, book)
    pin = digest(binding)
    gate, deferral = occupied()
    if not deferral:
        raise RuntimeError(f"The official storage deferral ended during admission: {gate!r}")
    results, native = {}, set()
    order = ORIENTATIONS[orientation]
    for role in order:
        before = resident(pathset)
        output = root / role
        command = [
            "/usr/bin/timeout",
            "-k",
            "1s",
            "7s",
            str(boot.RELEASE / "venv/bin/python"),
            "-IB",
            __file__,
            "child",
            str(output),
            "--binding",
            str(binding),
            "--binding-sha256",
            pin,
            "--role",
            role,
        ]
        clock = measure(command, environment_for(root), output)
        write(
            root / f"{role}-clock.json",
            dict(
                clock=clock,
                lease_deferral=gate,
                before=before,
                after=resident(pathset),
                command=command,
            ),
        )
        if clock["exit_code"]:
            raise RuntimeError(clock["stderr_tail"])
        doc, live, activity = (
            read(output / name) for name in ("detections.json", "worker.json", "prefetch.json")
        )
        result = compare(
            (doc, live, activity["slots"]), activity["prefetch"], book, role.startswith("slots")
        )
        packet = digest(output / "detections.json")
        native.add(packet)
        results[role] = dict(
            result,
            clock=clock,
            native_sha256=packet,
            detector_seconds=(live["detector_published_unix_ns"] - clock["started_unix_ns"]) / 1e9,
        )
    if len(native) != 1:
        raise ValueError("The complete signed detector documents differ")
    write(
        root / "result.json",
        dict(
            case=book["case"],
            source_pins=book["source_pins"],
            binding_sha256=pin,
            windows=WINDOWS,
            order=order,
            machine=machine,
            cache_at_start=first,
            waveform_bytes=book["scopes"][str(COUNT)]["bytes"],
            arms=results,
        ),
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "child"))
    cli.add_argument("root", type=Path)
    cli.add_argument("--binding", type=Path)
    cli.add_argument("--binding-sha256")
    cli.add_argument("--role", choices=ORDER)
    cli.add_argument("--orientation", choices=tuple(ORIENTATIONS), default="forward")
    args = cli.parse_args()
    if args.action == "launch":
        launch(args.root, args.orientation)
    else:
        child(args.root, read(args.binding, args.binding_sha256), args.role.startswith("slots"))
