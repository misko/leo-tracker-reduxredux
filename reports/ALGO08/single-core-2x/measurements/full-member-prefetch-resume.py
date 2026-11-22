import json
import os
from functools import partial
from hashlib import sha256
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from leo.storage.fast_scan import FastScanStore
from leo.storage.short_window import ShortWindowReader

trial = import_module("reports.ALGO08.single-core-2x.full_member_lookahead_trial")
bench = Path("/tmp/leo-algo08v2-2x-bench")
froze = bench / "integration-exact-curved-lookahead"
fixture = Path("/srv/bulk/leo-dev/leo-private-full-member-zw36phkh")
recording = fixture / "private-iq"
cache = bench / "ds30-cache-residency.so"

spec_bytes = (froze / "spec.json").read_bytes()
assert sha256(spec_bytes).hexdigest() == "652f8573e2fdec746dd318849c82992eb7786f014e8dbc393c0352b54e421e46"
spec = json.loads(spec_bytes)
trial.prefetch_comparison(spec)
receiver, hasher = Path(spec["detector"]), Path(spec["paired_sha256"]["library"])
assert sha256(receiver.read_bytes()).hexdigest() == spec["detector_sha256"]
assert sha256(hasher.read_bytes()).hexdigest() == spec["paired_sha256"]["sha256"]
assert trial.PairedSha256(hasher).hardware
assert fixture.stat().st_uid == os.getuid() and fixture.stat().st_mode & 0o077 == 0
source = ShortWindowReader(recording)
assert source.manifest_sha256 == "sha256:a749a509873f7d2bf8d97930f078d39853a4d89cf13e2024a58edf2f94e20f5f"
assert source.manifest.radio["serial"] == "private-full-member-synthetic"
assert source.manifest.status == "complete" and source.manifest.window_count == trial.WINDOWS
members = trial.synthetic_members(recording)
sizes = [size for _, (_, _, size) in members]
assert len(sizes) == trial.CHUNKS and all(trial.MIN_COMPRESSED <= size <= trial.MAX_COMPRESSED for size in sizes)
assert all(chunk.window_count == trial.WINDOWS_PER_CHUNK for chunk in source.manifest.chunks)
intake = FastScanStore(fixture).inventory(recording, verify_windows=False)
timed = partial(trial.measure,
    buffer=trial.frozen_context(froze, spec, "receiver_ingress.py", "compressed_input_buffer"),
    hint=trial.frozen_context(froze, spec, "receiver_member_lookahead.py", "compressed_member_lookahead"),
    hashes=trial.frozen_context(froze, spec, "paired_sha256.py", "paired_decoded_hashes"),
)
query, page_size = trial.load_query(cache), os.sysconf("SC_PAGE_SIZE")
expected_pages = [trial.pages(size, page_size) for size in sizes]
print(json.dumps(dict(build=trial.ALGO08V3, receiver_sha256=spec["detector_sha256"],
    manifest_sha256=source.manifest_sha256, member_bytes=sizes, expected_pages=expected_pages,
    cpu=sorted(os.sched_getaffinity(0)))), flush=True)
with TemporaryDirectory(dir="/var/tmp", prefix="leo-v3-prefetch-assets-") as directory:
    assets = Path(directory)
    (assets / "cancellation-factors.so").symlink_to(receiver.resolve())
    (assets / "lower.f32").symlink_to(trial.algo08_assets() / "lower.f32")
    with patch.dict(trial.algo08_scan.PINS, {"cancellation-factors.so": spec["detector_sha256"]}):
        expected = timed(assets, hasher, intake, arm="hint")
        assert expected["selected"]
        print(json.dumps(dict(condition="preload", **expected)), flush=True)
        for condition in ("cold", "warm"):
            for pair in range(2):
                order = ("hint", "prefetch") if not pair else ("prefetch", "hint")
                for arm in order:
                    starting_pages = trial.verified_start(members, query, expected_pages, cold=condition == "cold")
                    row = timed(assets, hasher, intake, arm=arm)
                    assert row["acquisition_sha256"] == expected["acquisition_sha256"]
                    if arm == "prefetch":
                        read = row["prefetch"]
                        assert (read["submitted"], read["hits"], read["hit_bytes"], read["fallback"]) == (
                            trial.CHUNKS - 1, trial.CHUNKS - 1, sum(sizes[1:]), 0,
                        )
                    print(json.dumps(dict(condition=condition, pair=pair, arm=arm,
                        starting_pages=starting_pages, **row)), flush=True)
