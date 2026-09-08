"""Run real companion shell operations locally on the actual cross-built bytes.

Only test-owned paths are written. The SSH runner is replaced by the portable
shell fixture; this never contacts a radio or executes the ARM payloads.
"""
from pathlib import Path
import hashlib
import json

from pluto_plus.userspace_iiod import PinnedPasswordSshIiodTransport
from pluto_plus.userspace_iiod_bundle import load_iiod_companion_bundle
from test_userspace_iiod import HOST, SERIAL, SESSION, _credentials
from test_userspace_iiod_bundle import LocalScriptRunner, ROOT

out = Path(__file__).resolve().parent
bundle = load_iiod_companion_bundle(out / "release/bundle.json")
known, password = _credentials(out / "test-credentials")

class Runner(LocalScriptRunner):
    def run(self, argv, *, stdin, timeout_s):
        # Adapt the fixed test namespace to this build's random runtime root.
        argv = (*argv[:-1], argv[-1].replace(bundle.remote_directory, ROOT))
        return super().run(argv, stdin=stdin, timeout_s=timeout_s)

runner = Runner(out / "local-script-scratch")
transport = PinnedPasswordSshIiodTransport(host=HOST, expected_serial=SERIAL,
    known_hosts_file=known, password_file=password, runner=runner)
transport.stage_companions(bundle, SESSION)
observed = {file.name: hashlib.sha256((runner.root / file.name).read_bytes()).hexdigest()
            for file in bundle.files}
assert observed == {file.name: file.sha256 for file in bundle.files}
transport.verify_companions(bundle, SESSION)
transport.cleanup_companions(bundle, SESSION)
assert not runner.root.exists()
receipt = dict(scope="Actual ARM bundle bytes through local shell fixture; no ARM execution/RF",
    manifest_sha256=bundle.manifest_sha256, observed=observed, companions=len(bundle.files),
    bytes=sum(len(file.payload) for file in bundle.files), script_operations=len(runner.calls),
    remote_calls=0, scratch_removed=True, original_release_retained=True)
with (out / "local-stage-receipt.json").open("x") as stream:
    json.dump(receipt, stream, indent=2)
    stream.write("\n")
print(json.dumps(receipt, indent=2))
