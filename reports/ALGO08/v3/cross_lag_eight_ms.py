"""Transfer the frozen timing gate to the all-visit 20/8 ms member receiver."""

import argparse
from collections import Counter
from contextlib import nullcontext
import ctypes as ct
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

from . import cross_lag_timing as gate, live_stereo_0008 as live


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
EIGHT = Path("/var/tmp/leo-v3-eight-ms-build-padded/8ms/short-primary.so")
EIGHT_SHA = "fe4ba7b7613654c268353f9e4a78c2bbb916904e06387ace304b0866818f0e3d"
BUILD_SHA = "b2324c7cfe3c60eecd59a98eda6b8d508c46e01df6ac81375db2f5f500493a30"
SOURCE_SHA = "0d6c837a78b7363e7b2e0037f15324d32caa0400db1657578f0cdc2f7bd3aa2e"
VERIFIER_SHA = "51f37c4be088bfd51b26d27cba18d236e238ceb12a2af2d9f5e855074e2db590"
CURRENT = Path("/dev/shm/leo-receiver-ceiling-0169-results01")
SCOPE_SHA = "95a438f0904e4568b6f2a3618b7fbf691c29d0e2d352fd3727cc83d35b72aa9a"
ORDERS = (("ordinary", "routed"), ("routed", "ordinary"))
RULE = (1666, 1.1)
ARCHIVES = {
    "0169": (Path("/dev/shm/leo-independent-8ms-0169-result02/measured8.json"),
             "0c6055720b8f4d0a50c7e446165256f0a1431a6d9a7734358e7f2a41f0c12c19"),
    "0008": (Path("/dev/shm/leo-v3-dense-8ms-anchors-result01/1-mixed8/member-detections.json"),
             "6dd91695c6b8504ee71621d20899bdbfbdd824dc6860c00539bb81c83a119c1e"),
}


def build(path, assets):
    receipt = EIGHT.with_name("build-receipt.json")
    original = json.loads(gate.existing.checked(receipt, BUILD_SHA))["relink"]
    verifier, = (Path(arg) for arg in original if Path(arg).name == "portable_verifier.o")
    gate.existing.checked(EIGHT, EIGHT_SHA)
    with (patch.object(gate, "SHORT_BUILD", receipt), patch.object(gate, "SHORT_BUILD_SHA", BUILD_SHA),
          patch.object(gate, "SOURCE_SHA", {"short": SOURCE_SHA}), patch.object(gate.existing, "PROFILE", verifier),
          patch.object(gate.existing, "PROFILE_SHA", VERIFIER_SHA)):
        gate.build(path, assets)


def assignment(case):
    source = live.original
    if case == "0169":
        scope = json.loads(source.verified(CURRENT / "scope.json", SCOPE_SHA))
        return Path(scope["entry"]["path"]), scope["entry"]["manifest_digest"], scope["member"]
    original = json.loads(source.verified(live.DENSE_STAGE / "result.json", live.DENSE_RECEIPT))
    return live.MEMBER, "sha256:" + source.MANIFEST_SHA, original["original_member"]


def residency(case):
    member, _, item = assignment(case)
    capture = {"manifest.json": (member / "manifest.json").stat().st_size,
               item["index_relative_path"]: item["index_bytes"], item["payload_relative_path"]: item["compressed_bytes"]}
    if not member.resolve(strict=True).is_relative_to("/dev/shm"):
        raise ValueError("Only the admitted tmpfs source may be read")
    with (patch.object(live, "MEMBER", member), patch.object(live, "CAPTURE_FILES", capture)):
        return live.residency(live.load_query(live.original.CACHE_LIBRARY))


def worker(output, case, arm, build_path):
    import mixed_aperture_receiver as mixed
    from full_short_run import checked_recipe
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import immutable_json
    from leo.storage.short_window import ShortWindowReader

    source = live.original
    recipe = checked_recipe(eight_ms=True)
    binary, pin = EIGHT, EIGHT_SHA
    paid = []
    ordinary = mixed.NativePath

    def configure(path, asset, mode):
        engine = ordinary(path, asset, mode)
        if mode == "short_primary":
            binding = gate.setup(SimpleNamespace(lib=engine.native.lib))
            binding.set_rule(3, *RULE)
            once = engine.run

            def run(samples, lane, center):
                result = once(samples, lane, center)
                cue = gate.Cue()
                binding.get_cue(ct.byref(cue))
                paid.append(bool(cue.expanded))
                return result

            engine.run = run
        return engine

    if arm == "routed":
        build = json.loads((build_path / "build.json").read_bytes())
        binary, pin = build_path / "short.so", build["sha256"]
        recipe = dict(recipe, short_timing_expansion=dict(short_binary_sha256=pin, original_8ms_sha256=EIGHT_SHA,
                                                         max_distance=RULE[0], minimum_contrast=RULE[1], samples=80_000))
    source.verified(binary, pin)
    member, manifest, chunk = assignment(case)
    paths = {chunk["index_relative_path"]: (chunk["index_bytes"], chunk["index_sha256"]),
             chunk["payload_relative_path"]: (chunk["compressed_bytes"], chunk["compressed_sha256"])}
    read = ShortWindowReader._member
    opened = []

    def allow(reader, name, size, digest):
        if reader.path != member or paths.get(name) != (size, digest):
            raise ValueError("A read escaped the enrolled physical first member")
        opened.append(name)
        return read(reader, name, size, digest)

    specification = json.loads(source.verified(source.PAYLOAD / "spec.json", source.SPEC_SHA))
    source.verified(source.PAYLOAD / "paired-sha256.so", specification["paired_sha256"]["sha256"])
    ingress = source.frozen_function(specification, "receiver_ingress.py", "compressed_input_buffer")
    mode = patch.object(mixed, "NativePath", configure) if arm == "routed" else nullcontext()
    with patch.object(live, "MEMBER", member), patch.object(ShortWindowReader, "_member", allow), mode:
        acquired, probes = live.receive("unmasked", binary, manifest, ingress,
            create_mixer=lambda: mixed.MixedApertureDetector(binary, pin, full_coverage=True), detector_pin=canonical_digest(recipe))
    calls = {"full": 16, "short_primary": 86 if case == "0169" else 112}
    if (set(opened) != set(paths) or len(opened) != len(paths) or acquired["chunk"] != chunk
            or acquired["receiver"]["native_calls"] != calls or (arm == "routed" and len(paid) != calls["short_primary"])):
        raise ValueError("Original 64-visit read, two-scan anchors or all-visit stereo coverage changed")
    output.mkdir()
    immutable_json(output / "signed.json", dict(probes=probes, acquisition=acquired, recipe=recipe, expanded=paid))


def anchor_lanes(probes):
    counters = Counter()
    for row in probes:
        key = tuple(row[name] for name in ("edge", "channel", "actual_rf_hz", "receiver_id"))
        if counters[key] % 8 == 0:
            yield row
        counters[key] += 1


def launch(root, case, build_path):
    from short_raw_diagnostic import measure

    if os.sched_getaffinity(0) != {2} or root.parent.resolve() != Path("/dev/shm"):
        raise ValueError("Use a new tmpfs result and the shared Gauss CPU2 lock")
    archive, archive_pin = ARCHIVES[case]
    archived = json.loads(live.original.verified(archive, archive_pin))
    archived = archived["packet"]["source"]["probes"] if case == "0169" else archived["probes"]
    expected_anchors = list(anchor_lanes(archived))
    if len(expected_anchors) != 16:
        raise ValueError("Expected 16 original full anchor lanes")
    root.mkdir()
    comparisons = []
    for number, order in enumerate(ORDERS):
        pair = {}
        for arm in order:
            path = root / f"{number}-{arm}"
            before = residency(case)
            result = measure([sys.executable, "-Bm", "reports.ALGO08.v3.cross_lag_eight_ms", "worker",
                              str(path), case, str(build_path), "--arm", arm], dict(os.environ), path)
            after = residency(case)
            if result["exit_code"]:
                raise RuntimeError(result["stderr_tail"])
            pair[arm] = dict(launch=result, result=json.loads((path / "signed.json").read_bytes()), before=before, after=after)
        a, b = (pair[arm]["result"] for arm in ORDERS[0])
        if a["probes"] != archived or list(anchor_lanes(b["probes"])) != expected_anchors:
            raise ValueError("Archived 8 ms control or its 16 full anchor bytes differ")
        for key in ("ordered_input_sha256", "exclusions", "admitted", "issued", "probes", "chunk"):
            if a["acquisition"][key] != b["acquisition"][key]:
                raise ValueError(f"Both actuated acquisition scopes must match on {key}")
        mismatches = [[left, right] for left, right in zip(a["probes"], b["probes"], strict=True) if left != right]
        saved = a["acquisition"]["timing"]["cpu_ns"] - b["acquisition"]["timing"]["cpu_ns"]
        comparisons.append(dict(order=order, runs=pair, changed=mismatches, acquisition_cpu_saving_ns=saved))
    passed = all(not pair["changed"] and pair["acquisition_cpu_saving_ns"] > 0 for pair in comparisons)
    gate.write(root / "result.json", dict(case=case, threshold=RULE, passed=passed, comparisons=comparisons,
               archived_probes_sha256=archive_pin, build=json.loads((build_path / "build.json").read_bytes()),
               source_sha256=gate.digest(Path(__file__))))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("build", "launch", "worker"))
    cli.add_argument("path", type=Path)
    cli.add_argument("case_or_assets")
    cli.add_argument("built", type=Path, nargs="?")
    cli.add_argument("--arm", choices=ORDERS[0])
    args = cli.parse_args()
    if args.mode == "build":
        build(args.path, Path(args.case_or_assets))
    elif args.mode == "worker":
        worker(args.path, args.case_or_assets, args.arm, args.built)
    else:
        launch(args.path, args.case_or_assets, args.built)
