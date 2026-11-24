"""Use the released named and integrated entries through one sealed detector file."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]
import original_dense_intake as stock
import original_prefix_scaling as prefix


ORDER = ("named", "integrated")
INTEGRATED_PIN = "eb115ec1dd7a734693e21d8be49e2f7de87fe48936b8db8d51e1216cf37a0dff"
DETACHED_PIN = "266a6df0b7cc36a324fd7cf0fa325f3c9059d5ca0faf4811d8dde031238f6b88"
NAMED_NATIVE_PIN = "f026bb3822ad7a946979a091c55b06d11d7c675e667c564f7d984e9f38fb2651"


def read(path):
    return json.loads(path.read_bytes())


def enrolled_options(argv, offer, archive):
    result = list(argv)
    if (result.count("--sparse8-primary") != 1 or result.count("--verify-original-once") != 1
            or "--legacy-first-map-replay" in result or "--strict-packed-eight" in result):
        raise ValueError("The selected integrated receiver must be original-format sparse and verified once")
    for flag, value in (("--region", offer), ("--archive", archive["root"]),
                        ("--archive-sha256", archive["snapshots_sha256"])):
        result[result.index(flag) + 1] = value
    return result


def admit():
    from first_member_0163_resume import ADDITIONAL_BYTES, PREFIX_BYTES, SIZE, TARGET, bindings
    from leo.contracts.digests import canonical_digest

    request, first, member, original_source, _ = bindings()
    stage = TARGET / "resumed-stage.json"
    receipt = read(stage)
    if (not receipt["verified_complete"] or receipt["source"] != str(original_source)
            or receipt["member"] != member or receipt["manifest_sha256"] != first["manifest_digest"]
            or (receipt["reused_local_prefix_bytes"], receipt["original_new_bytes"]) != (PREFIX_BYTES, ADDITIONAL_BYTES)
            or receipt["prefix_or_complete_sha256"] != member["compressed_sha256"]
            or receipt["decoded"]["raw_sha256"] != member["uncompressed_sha256"]):
        raise ValueError("No complete verified first original member is available")
    source = TARGET / original_source.parent.name
    archive = request["local_archive"]
    original = dict(archive=archive, offer=request["offer_file"], inventory=request["inventory"],
                    parent_native=request["native_file"], cutoff_utc_ns=request["causal_cutoff_utc_ns"])
    prefix.pinned(Path(original["offer"]), request["offer_sha256"])
    prefix.pinned(source / "manifest.json", first["manifest_digest"])
    index = prefix.pinned(source / member["index_relative_path"], member["index_sha256"])
    points = [json.loads(r) for r in index.splitlines()]
    if len(points) != 64 or not all(row["sequence"] == i for i, row in enumerate(points)):
        raise ValueError("Require all original issued rows of the completed member")
    inventory = dict(schema_version=1, kind="research-original-recording-prefix", window_count=64,
                     original_recording=request["recording"], original_inventory_sha256=request["inventory"],
                     prefix_members=[member], segments=[dict(first, path=str(source), windows=64)])
    pin = canonical_digest(inventory)
    control = json.loads(gzip.decompress(prefix.pinned(HERE / "measurements/integrated-original.json.gz", INTEGRATED_PIN)))
    previous = control["runs"]["positive_first"]["DS30-0016"]["result"]["document"]
    options = enrolled_options(previous["admission"]["command"][6:], original["offer"], archive)
    return dict(source=str(source), original=original, candidate_options=options, stage_sha256=stock.sha(stage),
                scopes={"1": dict(inventory=inventory, digest=pin, session="fast-" + pin[7:39], stop=64, bytes=SIZE)},
                iq=[row["iq_sha256"] for row in points], last_sample_counter=points[-1]["acquisition"]["sample_end"])


def worker(root, binding, mode):
    if mode == "named":
        audit = {"stock_iq": []}
        scope = binding["scopes"]["1"]
        sys.addaudithook(prefix.guard(prefix.files(binding, scope)))
        with patch.object(stock, "INPUT", Path(binding["source"])):
            try:
                stock.named(scope | {"original": binding["original"]}, root, audit)
            except stock.Published:
                pass
        if "native" not in audit or list(root.rglob("terminal.json")) or list(root.rglob("*.png")):
            raise ValueError("The installed probe must stop at the sealed detector file")
        stock.write(root / "worker.json", audit)
    else:
        import integrated_original_entry as integrated

        prefix.worker(root, binding, 1, entrypoint=integrated.main)


def launch(root):
    from dense_geographic_trial import host
    from eight_ms_south_transfer import environment_for
    from empty_bootstrap import RELEASE
    from short_raw_diagnostic import measure
    from visit_frame_raw_0016 import resident

    binding = admit() | {"machine": host(), "driver_sha256": stock.sha(Path(__file__))}
    paths = prefix.files(binding, binding["scopes"]["1"])
    resident(paths)
    root.mkdir(mode=0o700)
    for folder in ("tmp", "fonts"):
        (root / folder).mkdir()
    stock.write(root / "binding.json", binding)
    result = {}
    for mode in ORDER:
        output = root / mode
        before = resident(paths)
        command = ["/usr/bin/timeout", "--kill-after=2s", "20s", str(RELEASE / "venv/bin/python"), "-IB",
                   str(Path(__file__).resolve()), "worker", str(output), "--mode", mode, "--binding", str(root / "binding.json")]
        clock = measure(command, environment_for(root), output)
        result[mode] = dict(clock=clock, before=before, after=resident(paths), command=command)
        stock.write(root / f"{mode}-clock.json", result[mode])
        if clock["exit_code"]:
            raise ValueError(clock["stderr_tail"])
    stock.write(root / "launch.json", dict(order=ORDER, result=result, binding_sha256=stock.sha(root / "binding.json")))


def without_candidates(rows):
    return [{k: v for k, v in row.items() if k != "candidates"} for row in rows]


def score(root):
    from leo.contracts.digests import canonical_digest, canonical_json_bytes

    launched = read(root / "launch.json")
    if launched["binding_sha256"] != stock.sha(root / "binding.json") or tuple(launched["order"]) != ORDER:
        raise ValueError("The signed prefix and original launch order changed")
    binding = read(root / "binding.json")
    scope = binding["scopes"]["1"]
    original = json.loads(prefix.pinned(Path(binding["original"]["parent_native"]), NAMED_NATIVE_PIN))
    old = json.loads(prefix.pinned(Path("/tmp/leo-ds30-partial-window-detector01/DS30-0163.json"), DETACHED_PIN))
    before_reference = [lane["mixed_20_8"] for visit in old["visits"] for lane in visit["lanes"]]
    expected_named = [p for p in original["source"]["probes"] if p["visit_index"] < 64]
    expected_excluded = [p for p in original["provenance"]["excluded_windows"] if p["visit"] < 64]
    authority = canonical_digest([scope["digest"], binding["iq"]])
    result = {}
    for mode in ORDER:
        directory = root / mode
        audit = read(directory / "worker.json")
        path = directory / (audit["native"] if mode == "named" else "detections.json")
        packet = read(path)
        timed = launched["result"][mode]["clock"]
        rows = packet["source"]["probes"]
        if (timed["exit_code"] or canonical_json_bytes(packet) != path.read_bytes()
                or packet["source"]["input_manifest_sha256"] != scope["digest"]
                or packet["source"]["raw_recording_authority_digest"] != authority
                or packet["clock_anchor"] != original["clock_anchor"] or packet["delivery_clocks"] != original["delivery_clocks"][:64]
                or packet["last_sample_counter"] != binding["last_sample_counter"]
                or packet["provenance"]["excluded_windows"] != expected_excluded
                or without_candidates(rows) != without_candidates(expected_named)):
            raise ValueError("Published detection packet lacks the full original first-member evidence")
        if mode == "named" and (canonical_json_bytes(rows) != canonical_json_bytes(expected_named)
                                 or audit["stock_iq"] != binding["iq"]):
            raise ValueError("Installed 20 ms first member changed the original detections")
        if mode == "integrated" and (canonical_json_bytes([p for p in audit["before_selection"] if p["visit_index"] < 29])
                                      != canonical_json_bytes(before_reference) or audit["iq"] != binding["iq"]
                                      or packet["provenance"]["detector_sha256"] !=
                                      "sha256:ce13caaadf150f474a024fda7da31a33f9e293e9bb9e4d91613c552c3cd7335a"):
            raise ValueError("Actual sparse receiver or its typed detached overlap changed")
        published = (audit["detector_published_unix_ns"] - timed["started_unix_ns"]) / 1e9
        if not 0 < published <= timed["elapsed_s"]:
            raise ValueError("Detector commit is outside the actual paid process boundary")
        result[mode] = dict(clock=timed, detector_published_s=published, audited_receiver=audit["receiver_acquire"],
                            packet_sha256=stock.sha(path), method=packet["provenance"]["detector_sha256"],
                            issued=64, admitted=len(rows) // 2, excluded=len(expected_excluded),
                            factors=sum(len(row["candidates"]) for row in rows),
                            empty_lanes=sum(not row["candidates"] for row in rows),
                            receiver=audit.get("receiver"), selection=audit.get("selection"), source=audit.get("source"))
    stock.write(root / "result.json", dict(result=result, launch=launched, input=binding, authority=authority,
                                           backing_waveform_reads=0, solver_workers=0, qualified=True))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "worker", "score"))
    cli.add_argument("root", type=Path)
    cli.add_argument("--mode", choices=ORDER)
    cli.add_argument("--binding", type=Path)
    args = cli.parse_args()
    if args.action == "worker":
        worker(args.root, read(args.binding), args.mode)
    elif args.action == "launch":
        launch(args.root)
    else:
        score(args.root)
