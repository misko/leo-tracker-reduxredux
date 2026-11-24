"""Run one all-original indexed child against the sealed five-map ordinary control."""

import argparse
from collections import Counter
from contextlib import closing
from hashlib import sha256
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
from runpy import run_path
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]

import legacy_block_raw_0016 as base
from visit_frame_raw_0016 import checked, digest, read


CENSUS = Path("/dev/shm/leo-original-frame-coverage-0016-02.json")
CENSUS_PIN = "f7f570de3511e871cacb7eb2e5cc121f01b9d17f3ab11d37314cc5409caff8e4"
PREVIOUS = Path("/dev/shm/leo-v3-legacy-block-raw-0016-result02")
SOURCES = (Path(__file__).name, "legacy_block_all_entry.py", "legacy_block_multi.py", "legacy_block_exception.py",
           "legacy_block_all_score.py", "legacy-block-all-0016-protocol.md")


def qualified_control(pin):
    score = checked(PREVIOUS / "result.json", pin)
    plain = score["products"]["ordinary"]
    if (not score["qualified"] or score["case"] != "DS30-0016" or plain["process"]["exit_code"]
            or plain["receipt"]["decision"] != "complete" or len(plain["images"]) != 8
            or score["measured_input"]["totals"]["map_members"] != 5
            or score["prediction_seal_sha256"] != digest(PREVIOUS / "prediction-seal.json")):
        raise ValueError("Use only the separately qualified five-map raw benchmark and its sealed ordinary child")
    return score


def projected_command(original, output, folder, plan_pin, library_pin):
    if (Path(original[5]).name != "legacy_block_raw_entry.py" or "--history-risk-route" not in original
            or "--cairo-residual-layout" not in original or "--portable-orbit-index" not in original
            or any(flag.startswith(("--legacy-map", "--visit-frame")) for flag in original)):
        raise ValueError("The sealed ordinary argv does not match the original paired scientific experiment")
    command = list(original)
    command[5] = str(HERE / "legacy_block_all_entry.py")
    command[command.index("--output") + 1] = str(output)
    command.extend(("--legacy-map-custody", str(folder / "custody.json"), "--legacy-map-custody-sha256", plan_pin,
                    "--legacy-map-library", str(folder / "legacy-block.so"), "--legacy-map-library-sha256", library_pin))
    return command


def prepare(root, session, inventory_pin, inventory, expected, census, control, control_pin):
    import empty_bootstrap as boot
    from leo.contracts.digests import canonical_json_bytes, sha256_digest
    from leo.storage.writer import _fsync_directory
    from sparse_cold_input import frozen_function
    from tools.pipeline_eval.variants.experimental.paired_sha256 import paired_decoded_hashes
    from reports.ALGO08.v3 import legacy_block_input as port, legacy_block_multi as multi, legacy_block_seek as native
    from reports.ALGO08.v3.seekable_member import write as write_map

    original = control["admission"]
    old_plan = original["plan"]
    old_rows = old_plan["members"]
    if (old_plan["session"], old_plan["inventory"], old_plan["raw_authority"], old_plan["windows"]) != (
            session, inventory_pin, expected, inventory["window_count"]):
        raise ValueError("The earlier complete authentication named a different raw authority")
    started = boot.now()
    folder = root / "maps"
    folder.mkdir(mode=0o700)
    at, before = boot.now(), getrusage(RUSAGE_CHILDREN)
    library = folder / "legacy-block.so"
    build = native.build(library) | {"clock": boot.clock(at)}
    after = getrusage(RUSAGE_CHILDREN)
    build["compiler_cpu_s"] = (after.ru_utime-before.ru_utime) + (after.ru_stime-before.ru_stime)
    decoder = native.load(library)
    if not hasattr(decoder, "legacy_configure_origin") or not hasattr(decoder, "legacy_origin_replays"):
        raise ValueError("Build must include the reviewed exceptional-owner ABI")
    history = multi.load_history()
    boot.checked(boot.BASELINE, boot.BASELINE_PIN)
    spec = run_path(str(boot.BASELINE))["checked_spec"](boot.PAYLOAD)
    ingress = frozen_function(spec, "receiver_ingress.py", "compressed_input_buffer")
    paired = spec["paired_sha256"]
    paired_library = Path(paired["library"])
    boot.checked(paired_library, paired["sha256"])
    members, proofs, raw_hashes, writes = [], [], [], Counter()
    with ingress(), paired_decoded_hashes(paired_library):
        for ordinal, ((reader, chunk), old, seen) in enumerate(zip(port.ordered_members(inventory), old_rows, census, strict=True)):
            identity = port.member_identity(reader, chunk)
            if (any(old[key] != value for key, value in identity.items()) or reader.path.name != seen["segment"]
                    or chunk.payload_relative_path != seen["member"] or chunk.compressed_sha256 != seen["compressed_sha256"]):
                raise ValueError("A sealed member is not from the original capture or changed position")
            stage = boot.now()
            rows = native.read_rows(reader, chunk)
            raw_hashes.extend(row.iq_sha256 for row in rows)
            metadata_clock = boot.clock(stage)
            clocks, state = {}, "literal"
            if old["map"] is not None:
                stage = boot.now()
                if seen["sequence_count"] != 0:
                    raise ValueError("A retained literal map now has matched blocks")
                data = port.checked_file(PREVIOUS / "maps" / old["map"], old["map_sha256"], native.MAX_MAP)
                native.validate_map(reader, chunk, data, old["map_sha256"])
                clocks["reuse_literal"] = boot.clock(stage)
            else:
                if not seen["match_blocks"]:
                    raise ValueError("A planned exception member contains no original sequences")
                state = "exception"
                snapshots = []
                new_decode = boot.now()
                with native.one_member(reader.path, chunk, snapshots=snapshots), closing(port.stock_scope(reader, chunk)) as stream:
                    windows = tuple(stream)
                clocks["released_complete_verification"] = boot.clock(new_decode)
                frame, = snapshots
                if tuple(window.index for window in windows) != rows:
                    raise ValueError("Complete released verification changed the original signed opportunity order")
                limited = boot.now()
                try:
                    data = multi.seal(reader, chunk, frame, windows, history=history)
                except multi.UnsupportedExceptionLayout as error:
                    state, data = "ordinary", None
                    clocks["ordinary_fallback"] = str(error)
                clocks["exact_native_decode_and_map"] = boot.clock(limited)
                del frame, windows, snapshots
            name, pin = None, None
            if data is not None:
                at = boot.now()
                name, pin = port.map_name(ordinal), sha256_digest(data)
                write_map(folder / name, data)
                writes.update(boot.clock(at))
            members.append(dict(identity, map=name, map_sha256=pin, map_kind=state))
            proofs.append(dict(ordinal=ordinal, kind=state, clocks=clocks, original_index=metadata_clock,
                               bytes=0 if data is None else len(data)))
    if len(raw_hashes) != 808 or port.raw_authority(inventory_pin, raw_hashes) != expected:
        raise ValueError("The independently authenticated ordered index hashes no longer reproduce the raw authority")
    plan = dict(old_plan, members=members)
    at = boot.now()
    path = folder / "custody.json"
    write_map(path, canonical_json_bytes(plan))
    _fsync_directory(folder)
    _fsync_directory(root)
    writes.update(boot.clock(at))
    return plan, digest(path), dict(build=build, members=proofs, write_costs=dict(writes), total=boot.clock(started),
        prior_existing_literal_map_preparation=original["preparation"], ordinary_control_sha256=control_pin,
        admitted_kinds=dict(Counter(row["map_kind"] for row in members)), custody_bytes=path.stat().st_size)


def runtime_pins():
    return base_runtime_pins() | {str((HERE / name).relative_to(ROOT)): digest(HERE / name) for name in SOURCES}


base_runtime_pins = base.runtime_pins


def reuse_maps(root, previous, session, inventory, expected, control_pin):
    from empty_bootstrap import clock, now
    from reports.ALGO08.v3 import legacy_block_input as port, legacy_block_multi as multi
    from leo.storage.writer import _fsync_directory

    start = now()
    book = read(previous / "admission.json")
    prior = read(previous / "indexed-clock.json")
    log = (previous / "indexed.stderr").read_text()
    plan = book["plan"]
    if (previous.resolve(strict=True) != Path("/dev/shm/leo-v3-legacy-all-0016-result01")
            or prior["clock"]["exit_code"] != 1 or (previous / "indexed").exists()
            or "legacy_block_all_entry.py" not in log or "in mapped_codec" not in log
            or "No module named 'tools.pipeline_eval.variants.experimental.receiver_benchmark'" not in log
            or (plan["session"], plan["inventory"], plan["raw_authority"], plan["windows"]) != (session, inventory, expected, 808)
            or book["preparation"]["admitted_kinds"] != {"literal": 5, "exception": 8}
            or book["preparation"]["ordinary_control_sha256"] != control_pin):
        raise ValueError("Reuse is authorized only for the sealed pre-acquisition import failure")
    source, folder = previous / "maps", root / "maps"
    folder.mkdir(mode=0o700)
    pins = {row["map"]: (row["map_sha256"], multi.MAX_SIDECAR) for row in plan["members"]}
    pins.update({"custody.json": (book["map_custody_sha256"], port.MAX_CUSTODY),
                 "legacy-block.so": (book["preparation"]["build"]["binary_sha256"], 2_000_000)})
    for name, (pin, limit) in pins.items():
        port.checked_file(source / name, pin, limit)
        (folder / name).hardlink_to(source / name)
    _fsync_directory(folder)
    _fsync_directory(root)
    if port.load_custody(folder / "custody.json", book["map_custody_sha256"]) != plan:
        raise ValueError("Prepared map custody changed during relocation")
    extra = dict(clock=clock(start), root=str(previous), before_waveform=True, failed_clock=prior["clock"],
                 admission_sha256=digest(previous / "admission.json"), clock_sha256=digest(previous / "indexed-clock.json"),
                 stderr_sha256=digest(previous / "indexed.stderr"))
    return plan, book["map_custody_sha256"], dict(book["preparation"], recovery_reuse=extra)


def launch(root, control_pin, *, reuse=None):
    control = qualified_control(control_pin)
    ordinary = control["admission"]["commands"]["ordinary"]

    def maps(root, session, inventory_pin, inventory, expected, census):
        if reuse is not None:
            return reuse_maps(root, reuse, session, inventory_pin, expected, control_pin)
        return prepare(root, session, inventory_pin, inventory, expected, census, control, control_pin)

    def command(_previous, root, _portable, build, plan_pin):
        return {"indexed": projected_command(ordinary, root / "indexed", root / "maps", plan_pin,
                                              build["binary_sha256"])}

    with (patch.object(base, "ORDER", ("indexed",)), patch.object(base, "prepare", maps),
          patch.object(base, "commands", command), patch.object(base, "runtime_pins", runtime_pins),
          patch.object(base, "CENSUS", CENSUS), patch.object(base, "CENSUS_PIN", CENSUS_PIN)):
        base.launch(root)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "score"))
    cli.add_argument("root", type=Path)
    cli.add_argument("--ordinary-control-sha256", required=True)
    cli.add_argument("--reuse-prepared", type=Path)
    arguments = cli.parse_args()
    if arguments.action == "launch":
        launch(arguments.root, arguments.ordinary_control_sha256, reuse=arguments.reuse_prepared)
    else:
        from legacy_block_all_score import score

        score(arguments.root, arguments.ordinary_control_sha256)
