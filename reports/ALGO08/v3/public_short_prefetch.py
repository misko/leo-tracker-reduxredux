"""Isolate one-member prefetch on the saved northern full-short receiver."""

import argparse
from contextlib import contextmanager
from functools import partial
from hashlib import sha256
from importlib import import_module
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

from . import full_short_cold as original, sparse_cold_input as cold
from .signed_ingress_reuse import AcquisitionCosts, measured_ingress


HERE = Path(__file__).resolve().parent
ORDERS = (("advice", "prefetch"), ("prefetch", "advice"))
ASSIGNMENT = cold.CACHE_LIBRARY.parent / "exact-curved-lookahead-north-inside/pair.json"
ASSIGNMENT_SHA = "9bf5dc4e3ef1e2df17f8d8184bca74f2ce9559a1e154401b9f6330f8e97feaeb"
OFFER_SHA = "f4ff743e9f3d00bc18344143bffaaf7801276018dbd75b6ab2ec5207e887e891"
RECORDING = Path("/tmp/leo-regional-qZJKBw4W/public/0abe7b4514be674d9f5388e3")
MANIFEST_SHA = "0205ca2d10c1282f6c782c93a32d2bff1ae8a7b39ff959c93b4ca3613f0f07eb"
ARCHIVED = Path("/var/tmp/leo-north-short-regional-nov23/containing")
ARCHIVED_PACKET = ARCHIVED / "fast-scan-automatic-work/algo08-v2-113262a9d6ff6ba8b303ad51dfdf6acf/detections.json"
PACKET_SHA = "2b4e1282f8205a5c90cef2ab6acb7c666d445592963634e93911160205403427"
INVENTORY_SHA = "985dfe1e0423b1106f5e205b9ccf1aec7f9d1e156d9262da19852521dd703d4b"
FIRST_ADVICE_RECEIPT_SHA = "8788843fc0be5784bacba8b4e7bb27b16478e1c49f5ad746a9948d70bec03dd1"


def require_tmpfs(path):
    if subprocess.check_output(["findmnt", "-T", path, "-no", "FSTYPE"], text=True).strip() != "tmpfs":
        raise ValueError(f"Expected independent tmpfs: {path}")


def verify_residency(observation, size, page_size):
    pages = (size+page_size-1)//page_size
    if (observation["observed_members"] != 1 or observation["unavailable"]
            or observation["cached_pages"] != pages or observation["observed_file_pages"] != pages):
        raise ValueError("A signed source file is not fully resident")
    return pages


def stage(root, query, binary):
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.multirate_window_recording import ShortWindowManifestV2
    from tools.pipeline_eval.qualification.cache_residency import cache_snapshot

    require_tmpfs(RECORDING)
    assignment = json.loads(cold.verified(ASSIGNMENT, ASSIGNMENT_SHA))
    offer_path = Path(assignment["region"])
    offer = Algo08Region.parse(json.loads(cold.verified(offer_path, OFFER_SHA))).document()
    candidate = assignment["runs"]["candidate"]
    native = json.loads(cold.verified(ARCHIVED_PACKET, PACKET_SHA))
    session = native["source"]["session_id"]
    inventory = json.loads(cold.verified(ARCHIVED / "fast-scan-inputs" / (session+".json"), INVENTORY_SHA))
    entry, = inventory["segments"]
    if (Path(assignment["recording"]) != RECORDING or Path(entry["path"]) != RECORDING
            or offer != candidate["receipt"]["region"] or entry["manifest_digest"] != "sha256:"+MANIFEST_SHA
            or native["source"]["input_manifest_sha256"] != "sha256:"+INVENTORY_SHA
            or native["source"]["raw_recording_authority_digest"] != candidate["raw_authority"]
            or len(native["source"]["probes"]) != 2*inventory["window_count"]):
        raise ValueError("Public recording, receiver packet or original offer changed")
    manifest_path = RECORDING / "manifest.json"
    content = cold.verified(manifest_path, MANIFEST_SHA)
    manifest = ShortWindowManifestV2.model_validate_json(content)
    chunks = tuple(manifest.chunks[:cold.MEMBERS])
    if (manifest.sample_rate_hz != 10000000 or manifest.receiver_ids != (0, 1)
            or manifest.window_count != inventory["window_count"] or len(chunks) != cold.MEMBERS
            or any((c.first_sequence, c.window_count, c.uncompressed_bytes) != (i*64, 64, 102400000)
                   for i, c in enumerate(chunks))):
        raise ValueError("Unexpected original signed sample geometry")
    files = [(manifest_path.name, len(content), MANIFEST_SHA)]
    files.extend(entry for c in chunks for entry in (
        (c.index_relative_path, c.index_bytes, c.index_sha256),
        (c.payload_relative_path, c.compressed_bytes, c.compressed_sha256)))
    pagesize = os.sysconf("SC_PAGE_SIZE")
    residency = {}
    for name, size, _ in files:
        observation = cache_snapshot([(RECORDING, name, size)], pagesize, query)
        verify_residency(observation, size, pagesize)
        residency[name] = observation
    segment = root / RECORDING.name
    segment.mkdir(mode=0o700)
    for name, size, digest in files:
        leaf = cold.source_member_name(name)
        with (RECORDING / leaf).open("rb") as source, (segment / leaf).open("xb") as target:
            cold.copy_bounded(source, target, limit=size, expected_hash=digest, exact_size=size)
    specification = json.loads(cold.verified(cold.PAYLOAD / "spec.json", cold.SPEC_SHA))
    cold.verified(cold.PAYLOAD / "receiver.so", specification["detector_sha256"])
    cold.verified(binary, original.SHORT_SHA)
    assets = root / "assets"
    assets.mkdir()
    (assets / "cancellation-factors.so").symlink_to(cold.PAYLOAD / "receiver.so")
    edge = native["source"]["probes"][0]["edge"]
    pilot = cold.RELEASE / "assets" / (edge+".f32")
    cold.verified(pilot, original.PILOT_SHA[edge])
    (assets / pilot.name).symlink_to(pilot)
    request = root / "request.json"
    original.freeze(request, dict(entry=dict(entry, path=str(segment)), session=session,
                                  inventory_digest="sha256:"+INVENTORY_SHA))
    return request, chunks, native, offer, residency


def worker(mode, request_path, binary, output):
    from tools.pipeline_eval.variants.experimental import receiver_member_prefetch as prefetch

    host = original.check_machine()
    specification = json.loads(cold.verified(cold.PAYLOAD / "spec.json", cold.SPEC_SHA))
    for name, expected in cold.RUNTIME.items():
        cold.verified(Path(import_module(name).__file__), expected)
    request = json.loads(request_path.read_bytes())
    cpus, costs = set(), AcquisitionCosts()
    frozen_function = cold.frozen_function
    stock_worker = prefetch.prefetch_member

    def inspect_worker(*args):
        affinity = os.sched_getaffinity(0)
        if affinity != {2}:
            raise ValueError("The reader worker must share the acquisition CPU")
        cpus.update(affinity)
        return stock_worker(*args)

    @contextmanager
    def next_member():
        with patch.object(prefetch, "prefetch_member", inspect_worker), prefetch.compressed_member_prefetch() as stats:
            yield stats

    def profiled(spec, source, attribute):
        function = frozen_function(spec, source, attribute)
        if (source, attribute) == ("receiver_ingress.py", "compressed_input_buffer"):
            return partial(measured_ingress, function, costs)
        if mode == "prefetch" and attribute == "compressed_member_lookahead":
            return next_member
        return function

    with patch.object(cold, "frozen_function", profiled):
        row = original.scope("full-short", request_path.parent / "assets", binary, specification, request, output)
    row.update(ingress=mode, machine=host, worker_cpus=sorted(cpus), checked=costs.receipt())
    original.freeze(output.with_suffix(".receipt.json"), row)


def validate(row, chunks, packet, prior):
    expected = [[name, size, digest] for c in chunks for name, size, digest in (
        (c.index_relative_path, c.index_bytes, c.index_sha256),
        (c.payload_relative_path, c.compressed_bytes, c.compressed_sha256))]
    checked = row["checked"]
    probes = prior["source"]["probes"][:2*cold.WINDOWS]
    if (packet["source"]["probes"] != probes or packet["clock_anchor"] != prior["clock_anchor"]
            or packet["delivery_clocks"] != prior["delivery_clocks"][:cold.WINDOWS]
            or checked["verified_members"] != expected
            or checked["decoded_members"] != [c.uncompressed_sha256 for c in chunks]
            or checked["calls"]["decoded_sha"] != cold.WINDOWS+cold.MEMBERS
            or row["native"]["native_calls"] != {"full": 48, "short_primary": 336}):
        raise ValueError("Signed waveform, or schedule or verified members changed")
    overlap = row["overlap"]
    if overlap["submitted"] != 2 or (
        row["ingress"] == "prefetch" and (
            row["worker_cpus"] != [2] or overlap["hits"] != 2 or overlap["fallback"] != 0
            or overlap["hit_bytes"] != sum(c.compressed_bytes for c in chunks[1:])
        )
    ):
        raise ValueError("The frozen one-member read-ahead was not exercised")


def recover_advice(path, chunks, prior, entry, expected):
    from copy import deepcopy
    from leo.contracts.digests import canonical_digest, canonical_json_bytes

    row = json.loads(cold.verified(path, FIRST_ADVICE_RECEIPT_SHA))
    section = deepcopy(prior)
    idx = Path(entry["path"]) / chunks[-1].index_relative_path
    last_row = json.loads(cold.verified(idx, chunks[-1].index_sha256).splitlines()[-1])
    source = section["source"]
    source["probes"] = source["probes"][:2*cold.WINDOWS]
    section["delivery_clocks"] = section["delivery_clocks"][:cold.WINDOWS]
    section["last_sample_counter"] = last_row["acquisition"]["sample_end"]
    raw = canonical_digest([source["input_manifest_sha256"], row["decoded_iq_hashes"]])
    detection = canonical_digest(["cancellation", raw, row["detector_pin"], source["probes"]])
    source.update(raw_recording_authority_digest=raw, analysis_manifest_sha256=detection)
    section["provenance"].update(run_id="blind-compact-"+detection[7:39], window_count=cold.WINDOWS,
                                 processed_windows=cold.WINDOWS)
    validate(row, chunks, section, prior)
    if (sha256(canonical_json_bytes(section)).hexdigest() != row["sealed_detection_sha256"]
            or raw != row["raw_authority"] or row["start_cache_pages"] != expected
            or row["end_cache_pages"] != expected or row["ingress"] != "advice"):
        raise ValueError("Archived first measurement did not validate against the genuine scoped packet")
    return row


def run(binary, output, resume_advice=None):
    from tools.pipeline_eval.qualification.cache_residency import load_query, pages

    host = original.check_machine()
    require_tmpfs(output.parent.resolve(strict=True))
    cold.verified(cold.CACHE_LIBRARY, cold.CACHE_SHA)
    query = load_query(cold.CACHE_LIBRARY)
    output.mkdir(mode=0o700, exist_ok=False)
    with TemporaryDirectory(dir=output, prefix="signed-members-") as folder:
        root = Path(folder)
        start, cpu = perf_counter_ns(), process_time_ns()
        request, chunks, prior, offer, source_residency = stage(root, query, binary)
        staged = dict(wall_ns=perf_counter_ns()-start, cpu_ns=process_time_ns()-cpu)
        members = [root / RECORDING.name / c.payload_relative_path for c in chunks]
        identities = [cold.private_identity(path, root) for path in members]
        expected = [pages(c.compressed_bytes, os.sysconf("SC_PAGE_SIZE")) for c in chunks]

        def residency():
            return [cold.cache_pages(path, root, identity, query, cold=False)
                    for path, identity in zip(members, identities, strict=True)]

        env = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, (
            HERE.parents[2], cold.RELEASE / "src", cold.RELEASE, cold.PAYLOAD))))
        interpreter = str(cold.RELEASE / "venv/bin/python")
        rows = []
        for trial, arms in enumerate(ORDERS):
            for mode in arms:
                if resume_advice is not None and (trial, mode) == (0, "advice"):
                    entry = json.loads(request.read_bytes())["entry"]
                    row = recover_advice(resume_advice, chunks, prior, entry, expected)
                    original.freeze(output / "0-advice.json", row)
                    rows.append(row)
                    continue
                before = residency()
                if before != expected:
                    raise ValueError("The private signed payloads are not resident")
                path = root / f"{trial}-{mode}.json"
                command = [interpreter, "-BPs", "-m", __spec__.name, "worker", mode,
                           str(request), str(binary), str(path)]
                started = perf_counter_ns()
                subprocess.run(command, env=env, check=True, timeout=30)
                external = perf_counter_ns()-started
                row = json.loads(path.with_suffix(".receipt.json").read_bytes())
                after = residency()
                row.update(start_cache_pages=before, end_cache_pages=after, process_wall_ns=external)
                original.freeze(output / f"{trial}-{mode}.json", row)
                validate(row, chunks, json.loads(cold.verified(path, row["sealed_detection_sha256"])), prior)
                if after != expected:
                    raise ValueError("Payload residency changed")
                rows.append(row)
        if (len({row["sealed_detection_sha256"] for row in rows}) != 1
                or any(row["decoded_iq_hashes"] != rows[0]["decoded_iq_hashes"] for row in rows)):
            raise ValueError("The two ingress paths produced different signed acquisitions")
    pins = {name: sha256((HERE / name).read_bytes()).hexdigest() for name in (
        "public-short-prefetch-protocol.md", "public_short_prefetch.py", "full_short_cold.py", "signed_ingress_reuse.py")}
    original.freeze(output / "prefetch.json", dict(machine=host, arms=rows, orders=ORDERS, original_offer=offer,
                    offer_file_sha256=OFFER_SHA, original_sim_packet_sha256=PACKET_SHA, assignment_sha256=ASSIGNMENT_SHA,
                    inventory_sha256=INVENTORY_SHA, staged=staged, source_residency=source_residency,
                    reused_first_advice_receipt_sha256=FIRST_ADVICE_RECEIPT_SHA if resume_advice is not None else None,
                    runtime_sha256=cold.RUNTIME, source_sha256=pins,
                    members=[c.model_dump(mode="json") for c in chunks]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    pair = sub.add_parser("run")
    pair.add_argument("binary", type=Path)
    pair.add_argument("output", type=Path)
    pair.add_argument("--resume-advice", type=Path)
    child = sub.add_parser("worker")
    child.add_argument("mode", choices=("advice", "prefetch"))
    for name in ("request_path", "binary", "output"):
        child.add_argument(name, type=Path)
    args = vars(parser.parse_args())
    (run if args.pop("action") == "run" else worker)(**args)
