"""Run one original-file block reader control using the qualified positive-case worker."""

import argparse
from inspect import getfile, unwrap
import json
from pathlib import Path
from runpy import run_path
import os
import shutil
import sys

from legacy_block_0107_metadata import ARCHIVED, ENTRY, PINS, checked, digest, direct_tmpfs, metadata


POSITIVE = Path("/dev/shm/leo-v3-legacy-block-raw-0016-result02")
POSITIVE_PIN = "7e5f44b388a0674ab276282478122d218ef39adf9985acb31ef3e5a4d3b6afa0"
RECOVERY_PIN = "1805f687df04624cd4344e0b195a3d5e965bf07898c075e84312dc6c08e9ce87"
METADATA = Path("/dev/shm/leo-v3-legacy-block-0107-metadata01.json")
METADATA_PIN = "26300d7ae47235e650c0b370c31a49b3e93a606637da34941aa423eb00d55968"
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(ENTRY/"reports/ALGO08/v3"), str(ENTRY)]


def checked_json(path, pin):
    return json.loads(checked(direct_tmpfs(path), pin))


def released_paths():
    import empty_bootstrap as boot

    sys.path.extend((str(boot.RELEASE/"src"), str(boot.RELEASE)))
    return boot


def preparation(root, session, inventory_pin, inventory, expected, binary_pin):
    import empty_bootstrap as boot
    from leo.contracts.digests import canonical_json_bytes
    from leo.storage.writer import _fsync_directory
    from reports.ALGO08.v3 import legacy_block_input as port
    from reports.ALGO08.v3.seekable_member import write as write_map
    from sparse_cold_input import frozen_function
    from tools.pipeline_eval.variants.experimental.paired_sha256 import paired_decoded_hashes

    started = boot.now()
    output = root/"maps"
    output.mkdir()
    native = direct_tmpfs(POSITIVE/"maps/legacy-block.so")
    checked(native, binary_pin)
    os.link(native, output/"legacy-block.so")
    boot.checked(boot.BASELINE, boot.BASELINE_PIN)
    spec = run_path(str(boot.BASELINE))["checked_spec"](boot.PAYLOAD)
    wrapper = Path(getfile(unwrap(paired_decoded_hashes)))
    boot.checked(wrapper, spec["sources"][str(wrapper.relative_to(ENTRY))])
    ingress = frozen_function(spec, "receiver_ingress.py", "compressed_input_buffer")
    paired = spec["paired_sha256"]
    paired_library = Path(paired["library"])
    boot.checked(paired_library, paired["sha256"])
    ((reader, chunk),) = port.ordered_members(inventory)
    with ingress(), paired_decoded_hashes(paired_library):
        data, hashes, member_cost = port.prepare_member(reader, chunk)
    if len(hashes) != 29 or port.raw_authority(inventory_pin, hashes) != expected:
        raise ValueError("The released full traversal must authenticate the original ordered member")
    start_write = boot.now()
    map_name = port.map_name(0) if data is not None else None
    map_pin = "sha256:"+digest(data) if data is not None else None
    if map_name is not None:
        write_map(output/map_name, data)
    signed = dict(schema=port.SCHEMA, session=session, inventory=inventory_pin, windows=len(hashes),
                  raw_authority=expected, members=[port.member_identity(reader, chunk) | {"map": map_name, "map_sha256": map_pin}])
    custody = output/"custody.json"
    write_map(custody, canonical_json_bytes(signed))
    _fsync_directory(output)
    _fsync_directory(root)
    write_clock = boot.clock(start_write)
    return signed, "sha256:"+digest(custody.read_bytes()), dict(clock=boot.clock(started), member=member_cost,
        map_bytes=len(data) if data is not None else 0, custody_bytes=custody.stat().st_size, write=write_clock,
        decoder_reused=True, decoder_binary_sha256=binary_pin, ordinary_fallback=map_name is None)


def launch(root):
    boot = released_paths()
    from aperture_trial import write
    from combined_raw_trial import PRODUCER
    from dense_geographic_trial import host
    from eight_ms_0107_pair import verified_scope
    from eight_ms_south_transfer import environment_for
    from exact_named_raw import portable_binding, staged_path
    from legacy_block_raw_0016 import commands, seal
    from legacy_block_raw_entry import parser
    from leo.storage.fast_scan import FastScanStore
    from raw_0016_best_trial import measure_mode
    from visit_frame_raw_0016 import resident

    common_start = boot.now()
    if root.exists() or direct_tmpfs(root.parent) != Path("/dev/shm"):
        raise ValueError("Use a fresh private tmpfs output")
    qualified = checked_json(POSITIVE/"result.json", POSITIVE_PIN)
    recovered = checked_json(POSITIVE/"recovery.json", RECOVERY_PIN)
    pinbook = qualified["admission"]
    if (not qualified["qualified"] or qualified["case"] != "DS30-0016" or host() != pinbook["machine"]
            or sum(row["map"] is not None for row in pinbook["plan"]["members"]) != 5):
        raise ValueError("Require the qualified five-map positive trial on this exact host")
    sources = recovered["sources"]
    for path, pin in sources.items():
        checked(direct_tmpfs(ENTRY/path), pin)
    current, frozen = metadata(ENTRY), checked_json(METADATA, METADATA_PIN)
    if any(json.dumps(current[key], sort_keys=True) != json.dumps(frozen[key], sort_keys=True)
           for key in ("case", "request", "files", "geometry", "portable", "prior_ordinary_command")):
        raise ValueError("The frozen tiny assignment was modified")
    req = current["request"]
    recording = Path(req["recording"])
    stage = Path(current["signed_stage"])
    verified_scope(stage, recording)
    wavepaths = [staged_path(Path(row["path"]), root=recording) for row in current["files"].values()]
    session, inventory_pin, inventory = FastScanStore(recording).inventory(recording, verify_windows=False)
    if (session, inventory_pin, inventory["window_count"]) != (req["session"], req["inventory"], 29):
        raise ValueError("Canonical original identity differs from the verified tiny recording")
    for flag in ("--short-binary", "--geographic-library", "--regional-track-library", "--frontier-block-library"):
        old, comparison = current["prior_ordinary_command"], pinbook["commands"]["ordinary"]
        if old[old.index(flag)+1] != comparison[comparison.index(flag)+1]:
            raise ValueError(f"The positive and tiny control use different original libraries: {flag}")
    root.mkdir(mode=0o700)
    (root/"tmp").mkdir()
    shutil.copytree(POSITIVE/"fonts", root/"fonts")
    common = boot.clock(common_start)
    binary_pin = pinbook["preparation"]["build"]["binary_sha256"]
    plan, pin, prep = preparation(root, session, inventory_pin, inventory, req["authority"], binary_pin)
    ready_start = boot.now()
    pair = commands(current["prior_ordinary_command"], root, PRODUCER, {"binary_sha256": binary_pin}, pin)
    for mode, command in pair.items():
        args = parser().parse_args(command[6:])
        if not portable_binding(args, req["cutoff_utc_ns"]) or bool(args.legacy_map_custody) != (mode == "indexed"):
            raise ValueError("The generic CLI must use the same portable options and optional detached input")
    order = tuple(reversed(pinbook["order"]))
    prior = checked_json(ARCHIVED, PINS[ARCHIVED])["clocks"]["DS30-0107"]["stock"]
    write(root/"admission.json", dict(metadata=current, positive_result_sha256=POSITIVE_PIN, recovered_source_sha256=RECOVERY_PIN,
          sources=sources, order=order, commands=pair, plan=plan, map_custody_sha256=pin, preparation=prep,
          ready_checks=boot.clock(ready_start), shared_admission=common, installed_prior=prior, machine=host()))
    try:
        for mode in order:
            measure_mode(root, mode, pair[mode], environment_for(root), lambda: resident(wavepaths))
    finally:
        write(root/"prediction-seal.json", seal(root))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    opts = cli.parse_args()
    launch(opts.root)
