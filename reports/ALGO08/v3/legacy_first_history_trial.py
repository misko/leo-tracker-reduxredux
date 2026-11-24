"""Time exact owned output and prefix SHA reuse on the staged DS30-0016 member."""

import argparse
from contextlib import ExitStack, closing
import json
import os
from pathlib import Path
import subprocess

import numpy as np

from leo.contracts.digests import sha256_digest
from leo.storage.short_window import ShortWindowReader
from tools.pipeline_eval.qualification.cache_residency import load_query

from . import legacy_first_map_input as first, legacy_fused_map as fused, sparse_cold_input as release
from . import legacy_block_multi as multi, legacy_block_seek as core
from .full_short_run import EIGHT_MS_SHA
from .legacy_fused_map_trial import (
    CENSUS, CENSUS_PIN, MAP_PIN, NAMES, ORDINAL, ORIGINAL, SHORT, analyze, verified_reader,
)
from .mixed_aperture_receiver import INSTALLED_SHA, PILOT_SHA, NativePath
from .zstd_physical_structure import view_for

SHA_SOURCE = (Path(__file__).resolve().parents[3]
              / "tools" / "pipeline_eval" / "variants" / "experimental" / "paired_sha256.c")
ARMS = ("released", "rebuilt", "owned", "prefix", "combined")
ORDERS = (ARMS, ARMS[::-1])


def member_clock(census, original, native, history, hasher, replay, arm, output):
    owned = arm in ("owned", "combined")
    hash_prefix = arm in ("prefix", "combined")
    start = core.clock()
    with core.one_member(ORIGINAL.path, original):
        reader, chunk = verified_reader(census)
        with closing(fused.FusedMember(reader, chunk, history, hasher, allow_literal=True,
                                       owned_windows=owned, hash_prefix=hash_prefix)) as member:
            evidence, receiver = analyze(reader, chunk, ((row.index, row.samples) for row in member.windows()), native)
            begin_seal = core.clock()
            raw, pin = member.sidecar()
            proof = first.reopen(member, dict(map_sha256=pin), raw, multi, replay)
            fused.publish(output, raw)
            seal = core.elapsed(begin_seal)
            audit = member.audit()
            if bool(audit["owned_window_capacity"]) != owned:
                raise ValueError("Member switched away from the configured owned-window experiment")
    timing = core.elapsed(start)
    if pin != MAP_PIN or audit["exceptional_ordinals"] != [120, 135, 676]:
        raise ValueError("First analysis changed the independently bound replay map")
    return evidence, dict(timing=timing, signed_receiver=receiver, verification_and_history=audit,
                          seal_reopen_and_sync=seal, reopened=proof, map=pin, map_bytes=len(raw))


def run(root):
    priority = subprocess.check_output(("ionice", "-p", str(os.getpid())), text=True).strip()
    if (root.parent.resolve() != Path("/dev/shm") or os.sched_getaffinity(0) != {2}
            or os.getpriority(os.PRIO_PROCESS, 0) != 15 or priority != "best-effort: prio 7"
            or not Path(ShortWindowReader.windows.__code__.co_filename).is_relative_to(release.RELEASE)):
        raise ValueError("Use pinned installed storage under the shared CPU2 Gauss lease")
    census = json.loads(release.verified(CENSUS, CENSUS_PIN))[ORDINAL]
    release.verified(release.CACHE_LIBRARY, release.CACHE_SHA)
    cache, view = view_for(ORIGINAL.path, NAMES, load_query(release.CACHE_LIBRARY))
    if view is None or cache["filesystem"] != "tmpfs" or any(
            (ORIGINAL.path / name).resolve(strict=True) != ORIGINAL.path / name for name in NAMES):
        raise ValueError("Only the currently resident original member may be opened")
    release_spec = json.loads(release.verified(release.PAYLOAD / "spec.json", release.SPEC_SHA))
    ingress = release.frozen_function(release_spec, "receiver_ingress.py", "compressed_input_buffer")
    standard_hash, full = release.PAYLOAD / "paired-sha256.so", release.PAYLOAD / "receiver.so"
    release.verified(standard_hash, release_spec["paired_sha256"]["sha256"])
    release.verified(full, INSTALLED_SHA)
    release.verified(SHORT, EIGHT_MS_SHA)
    pilot = np.frombuffer(release.verified(release.RELEASE / "assets/lower.f32", PILOT_SHA["lower"]), dtype="<f4")
    reader, chunk = verified_reader(census)
    root.mkdir(mode=0o700)
    owned_lib, replay_lib, hash_lib = (root / name for name in ("history.so", "replay.so", "hash.so"))
    builds = dict(history=fused.build(owned_lib), replay=core.build(replay_lib))
    hash_command = ["cc", "-O3", "-std=c11", "-fPIC", "-shared", "-Wall", "-Wextra", "-Werror",
                    "-Wno-deprecated-declarations", str(SHA_SOURCE), "-o", str(hash_lib), "-lcrypto"]
    subprocess.run(hash_command, check=True)
    builds["hash"] = dict(command=hash_command, source=sha256_digest(SHA_SOURCE.read_bytes()),
                          binary=sha256_digest(hash_lib.read_bytes()), standard=sha256_digest(standard_hash.read_bytes()))
    history, replay = fused.load(owned_lib), core.load(replay_lib)
    reference, repeats = None, []
    with ExitStack() as stack:
        paths = {"full": full, "short_primary": SHORT}
        native = {mode: NativePath(path, pilot, mode) for mode, path in paths.items()}
        for engine in native.values():
            stack.callback(engine.close)
        stack.enter_context(ingress())
        for i, order in enumerate(ORDERS):
            measured = {}
            for arm in order:
                hasher = standard_hash if arm in ("released", "owned") else hash_lib
                evidence, measured[arm] = member_clock(census, chunk, native, history, hasher, replay,
                                                       arm, root / f"{i}-{arm}.map")
                if reference is None:
                    reference = evidence
                if evidence != reference:
                    raise ValueError("Owned-window or hash experiment changed the original signed receiver")
            repeats.append(measured)
    post_cache, view = view_for(ORIGINAL.path, NAMES, load_query(release.CACHE_LIBRARY))
    if view is None:
        raise ValueError("Original staged input changed residency")
    (root / "result.json").write_text(json.dumps(dict(
        source=core.identity(reader, chunk), cache=cache, post_cache=post_cache, orders=ORDERS,
        builds=builds, exact=reference, repeats=repeats,
        machine=dict(cpu=[2], nice=15, ionice=priority)),
        indent=2, sort_keys=True, allow_nan=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    run(parser.parse_args().out)
