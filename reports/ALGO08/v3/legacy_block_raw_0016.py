"""Measure an ordinary and mixed-map raw pair on the complete original DS30-0016."""

import argparse
import shutil
import sys
from collections import Counter
from hashlib import sha256
from inspect import getfile, unwrap
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
from runpy import run_path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]

from frame_portable_0016 import LIBRARIES, PRODUCER_CLOCK_PIN, seal  # noqa: E402
from visit_frame_raw_0016 import REFERENCE, checked, digest, references, resident  # noqa: E402

ORDER = ("ordinary", "indexed")
CENSUS = Path("/dev/shm/leo-original-frame-coverage-0016-01.json")
CENSUS_PIN = "6f9fc7a4469b34c744fea8fedc1ee3b04a6b9e61f9e1401c8a6fda9ff52c567b"
SOURCES = (
    "legacy_block_raw_0016.py",
    "legacy_block_raw_entry.py",
    "legacy_block_input.py",
    "legacy_block_seek.py",
    "legacy_block_seek.c",
    "zstd_structure.py",
    "exact_named_raw.py",
    "unified_short_bootstrap.py",
    "legacy_block_raw_score.py",
    "legacy-block-raw-0016-protocol.md",
)


def commands(previous, root, portable, build, plan_pin):
    if (
        Path(previous[5]).name != "exact_named_raw.py"
        or previous.count("--cairo-six-sheets") != 1
        or "--history-risk-route" not in previous
        or any(
            flag.startswith(("--portable-orbit", "--legacy-map", "--visit-frame"))
            for flag in previous
        )
    ):
        raise ValueError("Expected the qualified original-input history-risk raw scope")
    common = list(previous)
    common[5] = str(HERE / "legacy_block_raw_entry.py")
    common[common.index("--cairo-six-sheets")] = "--cairo-residual-layout"
    common[common.index("--output") + 1] = str(root / "ordinary")
    common.extend(portable.arguments())
    selected = common.copy()
    selected[selected.index("--output") + 1] = str(root / "indexed")
    selected.extend(
        (
            "--legacy-map-custody",
            str(root / "maps/custody.json"),
            "--legacy-map-custody-sha256",
            plan_pin,
            "--legacy-map-library",
            str(root / "maps/legacy-block.so"),
            "--legacy-map-library-sha256",
            build["binary_sha256"],
        )
    )
    return dict(zip(ORDER, (common, selected), strict=True))


def runtime_pins():
    from frame_portable_0016 import runtime_pins as portable_pins

    return portable_pins() | {f"reports/ALGO08/v3/{name}": digest(HERE / name) for name in SOURCES}


def prepare(root, session, inventory_pin, inventory, expected, census):
    import empty_bootstrap as boot

    from reports.ALGO08.v3 import legacy_block_input as port
    from reports.ALGO08.v3 import legacy_block_seek as codec
    from reports.ALGO08.v3.seekable_member import write as write_map

    started = boot.now()
    out = root / "maps"
    out.mkdir()
    start = boot.now()
    usage = getrusage(RUSAGE_CHILDREN)
    library = out / "legacy-block.so"
    build = codec.build(library) | {"clock": boot.clock(start)}
    final = getrusage(RUSAGE_CHILDREN)
    build["compiler_cpu_s"] = (final.ru_utime - usage.ru_utime) + (final.ru_stime - usage.ru_stime)
    from leo.contracts.digests import canonical_json_bytes
    from leo.storage.writer import _fsync_directory
    from sparse_cold_input import frozen_function

    from tools.pipeline_eval.variants.experimental.paired_sha256 import paired_decoded_hashes

    boot.checked(boot.BASELINE, boot.BASELINE_PIN)
    spec = run_path(str(boot.BASELINE))["checked_spec"](boot.PAYLOAD)
    path = Path(getfile(unwrap(paired_decoded_hashes)))
    boot.checked(path, spec["sources"][str(path.relative_to(ROOT))])
    ingress = frozen_function(spec, "receiver_ingress.py", "compressed_input_buffer")
    paired = spec["paired_sha256"]
    paired_library = Path(paired["library"])
    boot.checked(paired_library, paired["sha256"])
    members, ordered, results, writes = [], [], [], Counter()
    with ingress(), paired_decoded_hashes(paired_library):
        for n, ((reader, chunk), seen) in enumerate(
            zip(port.ordered_members(inventory), census, strict=True)
        ):
            match = dict(
                segment=reader.path.name,
                member=chunk.payload_relative_path,
                manifest_sha256=reader.manifest_sha256[7:],
                compressed_sha256=chunk.compressed_sha256,
                compressed_bytes=chunk.compressed_bytes,
                windows=chunk.window_count,
                decoded_bytes=chunk.uncompressed_bytes,
            )
            if any(seen[key] != val for key, val in match.items()):
                raise ValueError(
                    "Previously observed eligibility does not bind the original member order"
                )
            data, hashes, costs = port.prepare_member(reader, chunk)
            ordered.extend(hashes)
            if (data is not None) != (
                seen["kind"] == "literal_only" and seen["sequence_count"] == 0
            ):
                raise ValueError(
                    "New authenticated census disagrees with the frozen legacy coverage"
                )
            if data is not None and costs["indexed_blocks"] != seen["compressed_blocks"]:
                raise ValueError("Original member block count changed")
            name, pin = None, None
            if data is not None:
                start = boot.now()
                name, pin = port.map_name(n), "sha256:" + sha256(data).hexdigest()
                write_map(out / name, data)
                writes.update(boot.clock(start))
            members.append(dict(port.member_identity(reader, chunk), map=name, map_sha256=pin))
            results.append(costs | {"ordinal": n, "map_bytes": 0 if data is None else len(data)})
    if (
        port.raw_authority(inventory_pin, ordered) != expected
        or len(ordered) != inventory["window_count"]
    ):
        raise ValueError("The installed complete readback changed the original signed recording")
    if (
        sum(row["map"] is not None for row in members),
        sum(row["windows"] for row in members if row["map"]),
        sum(row["encoded"] for row in members if row["map"]),
    ) != (5, 320, 393_072_334):
        raise ValueError(
            "This frozen simple path requires five independently eligible physical members"
        )
    start = boot.now()
    plan = dict(
        schema=port.SCHEMA,
        session=session,
        inventory=inventory_pin,
        windows=len(ordered),
        raw_authority=expected,
        members=members,
    )
    custody = out / "custody.json"
    write_map(custody, canonical_json_bytes(plan))
    _fsync_directory(out)
    _fsync_directory(root)
    plan_pin = digest(custody)
    writes.update(boot.clock(start))
    return (
        plan,
        plan_pin,
        dict(
            build=build,
            members=results,
            write_costs=dict(writes),
            custody_bytes=custody.stat().st_size,
            total=boot.clock(started),
        ),
    )


def launch(root):
    import empty_bootstrap as boot

    sys.path.extend((str(boot.RELEASE / "src"), str(boot.RELEASE)))
    from aperture_trial import write
    from combined_raw_trial import PRODUCER, checked_producer
    from dense_geographic_trial import host
    from eight_ms_0107_pair import verified_scope
    from eight_ms_south_transfer import environment_for
    from exact_named_raw import staged_path
    from guarded_stage_checkpoint import staging_lock
    from history_risk_0016_raw import (
        RECORDING,
        STAGE,
        STAGING_LOCK,
        enrolled,
        readiness,
        require_custody,
    )
    from leo.operations.tle_archive import TleArchiveReader
    from leo.storage.fast_scan import FastScanStore
    from raw_0016_best_trial import measure_mode

    from reports.ALGO08.v3.history_risk_0016_cairo import measured_reference
    from tools.pipeline_eval.qualification.paired_publication import archive_identity

    if root.parent != Path("/dev/shm") or root.exists():
        raise ValueError("The trial requires a fresh private tmpfs output")
    started = boot.now()
    machine, historical = host(), references()
    req = historical["admission"]["request"]
    if Path(req["recording"]) != RECORDING:
        raise ValueError("The enrolled canonical recording is absent from the qualified comparison")
    verified_scope(STAGE / RECORDING.name, RECORDING)
    archive = staged_path(Path(req["archive"]["root"]))
    refs = TleArchiveReader(archive).list_snapshots("space-track")
    tlepaths = [staged_path(ref.path, root=archive) for ref in refs]
    if (
        len(refs) != 46
        or archive_identity(archive) != req["archive"]
        or any(ref.collected_utc_ns >= req["cutoff_utc_ns"] for ref in refs)
        or digest(staged_path(Path(req["region"]))) != "sha256:" + req["offer_sha256"]
    ):
        raise ValueError("Expected the complete signed original causal inputs and offer")
    indexpaths = [
        staged_path(path) for path in (PRODUCER.file, PRODUCER.file.parent / "artifact-bind.json")
    ]
    prior_build = checked(
        staged_path(PRODUCER.file.parent / "dense-export-clock.json"), PRODUCER_CLOCK_PIN
    )
    producer = checked_producer(req["cutoff_utc_ns"], {ref.sha256 for ref in refs})
    old = historical["admission"]["reference"]
    original = measured_reference(Path(old["root"]), Path(old["score"]), old["sha256"])
    libraries = original["admission"]["candidate_libraries"]
    for flag in LIBRARIES:
        row = libraries[flag]
        boot.checked(Path(row["path"]), row["sha256"])
        argv = historical["command"]
        if argv[argv.index(flag) + 1] != row["path"]:
            raise ValueError("The qualified scientific library has changed")
    causal = dict(tle=resident(tlepaths), index=resident(indexpaths))
    if prior_build["exit_code"] or not producer["overlapping_bodies"]:
        raise ValueError(
            "The portable input requires a complete previous producer and actual overlap"
        )
    census = checked(staged_path(CENSUS), CENSUS_PIN)
    signed = enrolled()
    with staging_lock(STAGING_LOCK):
        ready = readiness(STAGE, signed)
        if (
            not ready["ready"]
            or require_custody(STAGE, signed) != historical["admission"]["custody_sha256"]
        ):
            raise ValueError("The complete original signed stage is unavailable")
        wavepaths = [RECORDING / row["relative"] for row in signed["files"]]
        for path in wavepaths:
            staged_path(path, root=RECORDING)
        waveform = resident(wavepaths)
        session, inventory_pin, inventory = FastScanStore(RECORDING).inventory(
            RECORDING, verify_windows=False
        )
        if (session, inventory_pin, inventory["window_count"]) != (
            req["session"],
            req["inventory"],
            808,
        ):
            raise ValueError(
                "The mounted original must preserve its actual inventory and recording identity"
            )
        root.mkdir(mode=0o700)
        (root / "tmp").mkdir()
        shutil.copytree(REFERENCE / "fonts", root / "fonts")
        common = boot.clock(started)
        plan, plan_pin, prep = prepare(
            root, session, inventory_pin, inventory, req["authority"], census
        )
        paired = commands(historical["command"], root, PRODUCER, prep["build"], plan_pin)
        ready_start = boot.now()
        from exact_named_raw import portable_binding
        from legacy_block_raw_entry import parser

        for role in ORDER:
            args = parser().parse_args(paired[role][6:])
            if not portable_binding(args, req["cutoff_utc_ns"]) or bool(
                args.legacy_map_custody
            ) != (role == "indexed"):
                raise ValueError("The actual CLI did not expose the intended matched input options")
        write(
            root / "admission.json",
            dict(
                request=req,
                case="DS30-0016",
                machine=machine,
                sources=runtime_pins(),
                census_sha256=CENSUS_PIN,
                source_custody_sha256=historical["admission"]["custody_sha256"],
                wavepaths=list(map(str, wavepaths)),
                order=ORDER,
                causal=causal,
                waveform=waveform,
                prior_index_build=prior_build,
                producer=producer,
                prior_installed=historical["reused_stock"],
                map_custody_sha256=plan_pin,
                plan=plan,
                commands=paired,
                preparation=prep,
                shared_admission=common,
                ready_checks=boot.clock(ready_start),
            ),
        )
        for mode in ORDER:
            measure_mode(
                root, mode, paired[mode], environment_for(root), lambda: resident(wavepaths)
            )
        write(root / "causal-after.json", dict(tle=resident(tlepaths), index=resident(indexpaths)))
        write(root / "prediction-seal.json", seal(root))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "score"))
    cli.add_argument("root", type=Path)
    options = cli.parse_args()
    if options.action == "launch":
        launch(options.root)
    else:
        from legacy_block_raw_score import score

        score(options.root)
